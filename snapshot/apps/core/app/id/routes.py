"""HTTP-Endpoints von Dizzi-ID (OIDC-Provider, Präfix /id).

Flow (Authorization Code + PKCE, RFC 9700-konform):
  App → GET /id/authorize ──(keine Session)──► /id/login (Passwort | Google)
      └─(Session ok)──► 302 redirect_uri?code=…  → App: POST /id/token
        → {id_token (EdDSA), access_token, refresh_token (rotierend)}

Sicherheit: PKCE S256 Pflicht · Codes single-use/60 s · exakter redirect_uri-
Abgleich gegen die Client-Registry · Refresh-Reuse widerruft die Familie ·
alle Ereignisse im Audit-Log. Fehlertexte sind bewusst knapp (keine Orakel).
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import db
from ..config import DEFAULT_USER_ID
from . import ISSUER, google, keys, store, totp, webauthn

_LEVEL_ORD = {"lokal": 0, "verifiziert": 1, "hochsicher": 2}

router = APIRouter(prefix="/id", tags=["dizzi-id"])

_SESSION_COOKIE = "dizzi_id_session"
_GFLOW_COOKIE = "dizzi_id_gflow"

# Browser-Navigation HOST-RELATIV (gleicher Host wie der Aufruf). Entscheidend:
# (1) Session-Cookies sind host-gebunden — localhost und 127.0.0.1 sind
#     verschiedene Hosts; absolute Redirects auf einen festen Host verlören die
#     Anmeldung des anderen. (2) WebAuthn-RP-ID = Host: eine IP (127.0.0.1) ist
#     als RP-ID UNGÜLTIG, ein Name (localhost) gültig — der Nutzer muss daher
#     durchgehend auf localhost bleiben können. ISSUER bleibt absolut, aber NUR
#     für die OIDC-Aussteller-Identität (Discovery + iss-Claim).
_NAV = "/id"

# Loopback-Hosts, auf die ``next`` zeigen darf (Open-Redirect-Schutz, s. _safe_next).
_NEXT_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _safe_next(next_url: str) -> str:
    """Härtung (Tiefen-Review 12.06.): ``next`` ist Angreifer-beeinflussbar
    (Link in E-Mail/Webseite). Erlaubt sind NUR relative Pfade (``/…``) und
    absolute URLs auf die eigenen Loopback-Hosts — alles andere wird verworfen
    (leer ⇒ Login-Seite). Verhindert Open-Redirects von der Login-Seite weg."""
    n = (next_url or "").strip()
    if not n:
        return ""
    # RD-1 (28.06., Angreifer-2.-Tiefe): Backslashes + Control-Chars hart abweisen.
    # Browser normalisieren '\' -> '/' (WHATWG-URL), Pythons urlsplit (RFC 3986) NICHT
    # ⇒ ``https://evil.com\@localhost/`` parst hier host=localhost (erlaubt), der Browser
    # navigiert aber zu evil.com = Open-Redirect-Bypass. Control-Chars (\r\n) ⇒ Header-/
    # HTML-Injection. Legitime Loopback-/Relativ-URLs enthalten beides nie.
    if "\\" in n or any(ord(c) < 0x20 for c in n):
        return ""
    if n.startswith("/") and not n.startswith("//"):
        return n
    try:
        u = urlsplit(n)
    except ValueError:
        return ""
    if u.scheme in ("http", "https") and (u.hostname or "").lower() in _NEXT_HOSTS:
        return n
    return ""


def _esc(text: str) -> str:
    """HTML-Attribut-/Text-Escaping für eingebettete Werte (XSS-Schutz)."""
    import html
    return html.escape(text or "", quote=True)


def _js_str(text: str) -> str:
    """Sicheres JS-String-Literal (auch gegen ``</script>``-Ausbruch)."""
    return json.dumps(text or "").replace("<", "\\u003c")


def _ensure_ready() -> None:
    store.ensure_clients()  # intern billig geguarded (Test-DB-Wechsel sicher)
    store.totp_seed_migrieren()  # F7: Klartext-Alt-Seed einmalig schützen


def _audit(action: str, detail: dict[str, Any] | None = None,
           actor: str = "system") -> None:
    db.audit(DEFAULT_USER_ID, actor, action, detail or {})


# --- Discovery + JWKS ---------------------------------------------------------

@router.get("/.well-known/openid-configuration")
def discovery() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "jwks_uri": f"{ISSUER}/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "id_token_signing_alg_values_supported": [keys.ALG],
        "scopes_supported": ["openid", "email"],
        "subject_types_supported": ["public"],
    }


@router.get("/jwks.json")
def jwks() -> dict[str, Any]:
    return keys.jwks()


# --- Authorize (Code + PKCE) ----------------------------------------------------

@router.get("/authorize")
def authorize(request: Request,
              client_id: str = Query(...),
              redirect_uri: str = Query(...),
              response_type: str = Query(...),
              code_challenge: str = Query(...),
              code_challenge_method: str = Query(...),
              state: str = Query(""),
              nonce: str = Query(""),
              scope: str = Query("openid"),
              acr_values: str = Query("")):
    _ensure_ready()
    uris = store.client_redirects(client_id)
    if uris is None or redirect_uri not in uris:
        # KEIN Redirect auf ungeprüfte URIs (Open-Redirect-Schutz).
        _audit("id_authorize_abgelehnt", {"client_id": client_id})
        return JSONResponse({"error": "invalid_client"}, status_code=400)
    if response_type != "code" or code_challenge_method != "S256" or not code_challenge:
        return _redirect_err(redirect_uri, state, "invalid_request")

    session = store.get_session(request.cookies.get(_SESSION_COOKIE))
    if session is None:
        nxt = str(request.url)
        return RedirectResponse(f"{_NAV}/login?{urlencode({'next': nxt})}",
                                status_code=302)

    # Step-up (R1.3): verlangt der Client eine höhere Stufe (acr_values),
    # als die Session hat, geht es erst zur MFA-Verifikation.
    wanted = acr_values.strip()
    if wanted in _LEVEL_ORD and \
            _LEVEL_ORD[session["level"]] < _LEVEL_ORD[wanted]:
        nxt = str(request.url)
        return RedirectResponse(f"{_NAV}/stepup?{urlencode({'next': nxt})}",
                                status_code=302)

    code = store.issue_code(client_id, redirect_uri, code_challenge,
                            nonce or None, session["level"], session["amr"])
    _audit("id_code_ausgestellt", {"client_id": client_id}, actor="user")
    sep = "&" if urlsplit(redirect_uri).query else "?"
    return RedirectResponse(
        f"{redirect_uri}{sep}{urlencode({'code': code, 'state': state})}",
        status_code=302)


def _redirect_err(redirect_uri: str, state: str, err: str) -> RedirectResponse:
    sep = "&" if urlsplit(redirect_uri).query else "?"
    return RedirectResponse(
        f"{redirect_uri}{sep}{urlencode({'error': err, 'state': state})}",
        status_code=302)


# --- Token (Code-Einlösung + Refresh-Rotation) ----------------------------------

def _tokens_for(client_id: str, level: str, amr: list[str],
                nonce: str | None, refresh: str) -> dict[str, Any]:
    now = int(time.time())
    base = {"iss": ISSUER, "sub": DEFAULT_USER_ID, "aud": client_id,
            "iat": now, "amr": amr, "dizzi_level": level}
    id_claims = {**base, "exp": now + store.IDTOKEN_TTL_S}
    if nonce:
        id_claims["nonce"] = nonce
    access_claims = {**base, "exp": now + store.ACCESS_TTL_S,
                     "token_use": "access", "scope": "openid"}
    return {
        "token_type": "Bearer",
        "id_token": keys.sign(id_claims),
        "access_token": keys.sign(access_claims),
        "expires_in": store.ACCESS_TTL_S,
        "refresh_token": refresh,
        "dizzi_level": level,
    }


@router.post("/token")
def token(grant_type: str = Form(...),
          client_id: str = Form(...),
          code: str = Form(""),
          redirect_uri: str = Form(""),
          code_verifier: str = Form(""),
          refresh_token: str = Form("")):
    _ensure_ready()
    if grant_type == "authorization_code":
        info = store.redeem_code(code, client_id, redirect_uri, code_verifier)
        if info is None:
            _audit("id_token_abgelehnt", {"client_id": client_id, "grant": grant_type})
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        refresh = store.issue_refresh(client_id, info["level"], info["amr"])
        _audit("id_token_ausgestellt", {"client_id": client_id}, actor="user")
        return _tokens_for(client_id, info["level"], info["amr"], info["nonce"], refresh)

    if grant_type == "refresh_token":
        result = store.rotate_refresh(refresh_token, client_id)
        if result is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if result.get("reuse"):
            _audit("id_refresh_REUSE_familie_widerrufen",
                   {"client_id": client_id, "family": result["family"]})
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        _audit("id_refresh_rotiert", {"client_id": client_id}, actor="user")
        return _tokens_for(client_id, result["level"], result["amr"], None,
                           result["token"])

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


@router.get("/userinfo")
def userinfo(request: Request):
    authz = request.headers.get("authorization", "")
    if not authz.lower().startswith("bearer "):
        return JSONResponse({"error": "invalid_token"}, status_code=401)
    try:
        claims = keys.verify(authz[7:])
        assert claims.get("iss") == ISSUER
        assert claims.get("token_use") == "access"
        assert float(claims.get("exp", 0)) >= time.time()
    except Exception:
        return JSONResponse({"error": "invalid_token"}, status_code=401)
    return {"sub": claims["sub"], "dizzi_level": claims.get("dizzi_level"),
            "amr": claims.get("amr", [])}


# --- Login (lokales Passwort + Google-Broker) -----------------------------------

_LOGIN_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Dizzi-ID — Anmelden</title>
<style>
 body{{background:#0e1014;color:#e8edf5;font-family:'Segoe UI',system-ui,sans-serif;
      display:grid;place-items:center;min-height:100vh;margin:0}}
 .card{{background:#161b22;border:1px solid rgba(47,231,255,.35);padding:28px 30px;
       width:330px;box-shadow:0 0 34px -12px rgba(47,231,255,.55)}}
 h1{{font-size:19px;margin:0 0 4px;color:#2fe7ff;letter-spacing:.4px}}
 p{{color:#93a0b4;font-size:12.5px;margin:0 0 16px}}
 input{{width:100%;box-sizing:border-box;background:#0e1014;color:#e8edf5;
       border:1px solid rgba(150,165,190,.3);padding:9px 10px;margin:5px 0 11px}}
 button,a.gbtn{{display:block;width:100%;box-sizing:border-box;text-align:center;
       background:transparent;color:#2fe7ff;border:1px solid #2fe7ff;padding:9px 0;
       cursor:pointer;font-weight:700;text-decoration:none;margin-top:4px}}
 a.gbtn{{color:#ff3df0;border-color:#ff3df0;margin-top:12px}}
 .err{{color:#ff3df0;font-size:12.5px;margin:0 0 10px}}
</style></head><body><div class="card">
<h1>Dizzi-ID</h1><p>Einmal anmelden — überall angemeldet.</p>
{err}{body}
</div></body></html>"""


# Gemeinsame WebAuthn-Ceremony im Browser (base64url ⇄ ArrayBuffer + die
# beiden navigator.credentials-Aufrufe). Wird in Step-up- und Geräte-Seite
# eingebettet; {B} = _NAV (host-relativ — fetch bleibt auf dem aktuellen Host,
# Cookie + WebAuthn-RP-ID konsistent; s. _NAV-Kommentar oben).
_WEBAUTHN_JS = """
const B='{B}';
const u8=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')
  .padEnd(s.length+(4-s.length%4)%4,'=')),c=>c.charCodeAt(0));
const b64=buf=>btoa(String.fromCharCode(...new Uint8Array(buf)))
  .replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
async function passkeyRegister(label){{
  const o=await (await fetch(B+'/webauthn/register/begin',{{method:'POST'}})).json();
  if(o.error)throw new Error(o.error);
  o.challenge=u8(o.challenge); o.user.id=u8(o.user.id);
  (o.excludeCredentials||[]).forEach(c=>c.id=u8(c.id));
  const cr=await navigator.credentials.create({{publicKey:o}});
  const r=await (await fetch(B+'/webauthn/register/finish',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
    id:cr.id,label:label,response:{{
      clientDataJSON:b64(cr.response.clientDataJSON),
      attestationObject:b64(cr.response.attestationObject)}}}})}})).json();
  if(!r.ok)throw new Error(r.error||'Registrierung fehlgeschlagen');
  return r;
}}
async function passkeyStepup(){{
  const o=await (await fetch(B+'/webauthn/stepup/begin',{{method:'POST'}})).json();
  if(o.error)throw new Error(o.error);
  o.challenge=u8(o.challenge);
  (o.allowCredentials||[]).forEach(c=>c.id=u8(c.id));
  const cr=await navigator.credentials.get({{publicKey:o}});
  const r=await (await fetch(B+'/webauthn/stepup/finish',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
    id:cr.id,response:{{
      clientDataJSON:b64(cr.response.clientDataJSON),
      authenticatorData:b64(cr.response.authenticatorData),
      signature:b64(cr.response.signature)}}}})}})).json();
  if(!r.ok)throw new Error(r.error||'Passkey-Anmeldung fehlgeschlagen');
  return r;
}}
"""


def _login_body(nxt: str) -> str:
    parts = []
    if store.has_local_password():
        parts.append(
            f'<form method="post" action="{_NAV}/login/local">'
            f'<input type="hidden" name="next" value="{_esc(nxt)}">'
            '<input type="password" name="password" placeholder="Passwort" autofocus>'
            "<button>Anmelden</button></form>")
    else:
        parts.append(
            f'<form method="post" action="{_NAV}/local/setup">'
            f'<input type="hidden" name="next" value="{_esc(nxt)}">'
            '<input type="password" name="password" placeholder="Neues Passwort (min. 8)" autofocus>'
            "<button>Passwort festlegen &amp; anmelden</button></form>")
    if google.configured():
        parts.append(f'<a class="gbtn" href="{_NAV}/login/google?'
                     f'{urlencode({"next": nxt})}">Mit Google anmelden</a>')
    return "".join(parts)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = Query(""), err: str = Query("")):
    # Bereits angemeldet? Direkt-Besucher sehen ihren Zustand statt erneut des
    # Formulars (UX-Fix 12.06.); mit next-Ziel geht es sofort dorthin weiter.
    next = _safe_next(next)
    session = store.get_session(request.cookies.get(_SESSION_COOKIE))
    if session is not None and not err:
        if next:
            return RedirectResponse(next, status_code=302)
        mfa = store.totp_state()
        mfa_zeile = ("MFA aktiv — Stufe 'hochsicher' verfügbar."
                     if mfa["confirmed"] else
                     f'<a class="gbtn" href="{_NAV}/stepup?next=">'
                     "MFA einrichten (Stufe hochsicher)</a>")
        body = (f"<p><b style='color:#36e0a0'>✓ Angemeldet</b> als "
                f"<b>{session['user_id']}</b> — Stufe <b>{session['level']}</b> "
                f"({', '.join(session['amr'])}).</p>"
                f"<p>Einmal anmelden ⇒ alle verbundenen Apps (SSO).</p>{mfa_zeile}"
                f'<a class="gbtn" href="{_NAV}/geraete">Sitzungen &amp; Geräte</a>'
                f'<form method="post" action="{_NAV}/logout" style="margin-top:10px">'
                "<button>Abmelden</button></form>")
        return HTMLResponse(_LOGIN_HTML.format(err="", body=body))
    msg = '<p class="err">Anmeldung fehlgeschlagen.</p>' if err else ""
    return HTMLResponse(_LOGIN_HTML.format(err=msg, body=_login_body(next)))


def _session_redirect(nxt: str, amr: list[str]) -> RedirectResponse:
    sid = store.create_session("verifiziert", amr)
    resp = RedirectResponse(_safe_next(nxt) or f"{_NAV}/login", status_code=302)
    resp.set_cookie(_SESSION_COOKIE, sid, httponly=True, samesite="lax",
                    max_age=store.SESSION_TTL_S, path="/")
    return resp


@router.post("/login/local")
def login_local(password: str = Form(...), next: str = Form("")):
    if not store.check_local_password(password):
        sperre = store.lockout_rest("passwort")          # H4: sichtbar im Audit
        _audit("id_login_fehlgeschlagen",
               {"via": "pwd", "lockout_s": round(sperre)} if sperre
               else {"via": "pwd"})
        return RedirectResponse(
            f"{_NAV}/login?{urlencode({'next': next, 'err': '1'})}", status_code=302)
    _audit("id_login_ok", {"via": "pwd"}, actor="user")
    return _session_redirect(next, ["pwd"])


@router.post("/local/setup")
def local_setup(password: str = Form(...), next: str = Form("")):
    if store.has_local_password():                       # Setup nur EINMAL
        return JSONResponse({"error": "bereits_eingerichtet"}, status_code=409)
    try:
        store.set_local_password(password)
    except ValueError:
        return RedirectResponse(
            f"{_NAV}/login?{urlencode({'next': next, 'err': '1'})}", status_code=302)
    _audit("id_lokales_passwort_gesetzt", {}, actor="user")
    return _session_redirect(next, ["pwd"])


@router.get("/login/google")
def login_google(request: Request, next: str = Query("")):
    if not google.configured():
        return JSONResponse({"error": "google_nicht_konfiguriert",
                             "hinweis": "DIZZI_GOOGLE_CLIENT_ID/SECRET in "
                                        r"C:\Dizzik\data\.env hinterlegen"},
                            status_code=503)
    verifier, challenge = google.make_pkce()
    state = secrets.token_urlsafe(16)
    # Callback host-konsistent zum aktuellen Zugriff (Dauerlösung): kein Cookie-Welt-Split.
    ru = google.redirect_uri_for(request.url.hostname)
    resp = RedirectResponse(google.auth_url(state, challenge, ru), status_code=302)
    resp.set_cookie(_GFLOW_COOKIE,
                    json.dumps({"state": state, "verifier": verifier,
                                "next": _safe_next(next), "redirect_uri": ru}),
                    httponly=True, samesite="lax", max_age=600, path="/id")
    return resp


@router.get("/callback/google")
def callback_google(request: Request, code: str = Query(""), state: str = Query("")):
    raw = request.cookies.get(_GFLOW_COOKIE)
    if not raw or not code:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    try:
        flow = json.loads(raw)
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    if not secrets.compare_digest(state, flow.get("state", "")):
        _audit("id_google_state_mismatch", {})
        return JSONResponse({"error": "invalid_state"}, status_code=400)
    try:
        tokens = google.exchange_code(code, flow["verifier"],
                                      flow.get("redirect_uri", google.REDIRECT_URI))
        claims = google.verify_id_token(tokens["id_token"])
    except Exception:
        _audit("id_login_fehlgeschlagen", {"via": "google"})
        return JSONResponse({"error": "google_login_fehlgeschlagen"}, status_code=502)
    if not store.pin_google(str(claims["sub"]), str(claims.get("email", ""))):
        _audit("id_google_fremdes_konto_abgelehnt", {})
        return JSONResponse({"error": "fremdes_google_konto"}, status_code=403)
    _audit("id_login_ok", {"via": "google"}, actor="user")
    resp = _session_redirect(flow.get("next", ""), ["google"])
    resp.delete_cookie(_GFLOW_COOKIE, path="/id")
    return resp


# --- Step-up auf 'hochsicher' (R1.3: TOTP jetzt, WebAuthn/Passkey = R1.3b) ----

@router.get("/stepup", response_class=HTMLResponse)
def stepup_page(request: Request, next: str = Query(""), err: str = Query("")):
    next = _safe_next(next)
    session = store.get_session(request.cookies.get(_SESSION_COOKIE))
    if session is None:
        return RedirectResponse(
            f"{_NAV}/login?{urlencode({'next': str(request.url)})}", status_code=302)
    msg = '<p class="err">Code ungültig.</p>' if err else ""
    state = store.totp_state()
    if not state["confirmed"]:
        # Enrollment: Geheimnis erzeugen/zeigen (QR-URI), erster gültiger Code aktiviert.
        if not state["enrolled"]:
            secret = totp.new_secret()
            store.totp_begin_enroll(secret)
            _audit("id_mfa_enrollment_gestartet", {}, actor="user")
        else:
            secret = store.totp_secret_klartext()  # pending fortsetzen (entschlüsselt)
        uri = totp.otpauth_uri(secret)
        body = (
            "<p><b>MFA einrichten:</b> Geheimnis in die Authenticator-App "
            f"übertragen, dann Code eingeben.</p><p style='word-break:break-all;"
            f"font-size:11.5px;color:#93a0b4'>{secret}</p>"
            f"<p style='word-break:break-all;font-size:10.5px;color:#5d6a7d'>{uri}</p>"
            f'<form method="post" action="{_NAV}/stepup">'
            f'<input type="hidden" name="next" value="{_esc(next)}">'
            '<input name="code" placeholder="6-stelliger Code" autofocus '
            'inputmode="numeric" autocomplete="one-time-code">'
            "<button>Aktivieren &amp; freischalten</button></form>")
    else:
        body = (
            "<p><b>Hochsicher-Freigabe:</b> Code aus der Authenticator-App.</p>"
            f'<form method="post" action="{_NAV}/stepup">'
            f'<input type="hidden" name="next" value="{_esc(next)}">'
            '<input name="code" placeholder="6-stelliger Code" autofocus '
            'inputmode="numeric" autocomplete="one-time-code">'
            "<button>Freischalten</button></form>")
    # Passkey-Weg (R1.3b): registriert ⇒ als bevorzugte, schnellste Freigabe oben.
    if store.webauthn_state()["enrolled"]:
        body = (
            '<button onclick="pk()" style="border-color:#ff3df0;color:#ff3df0">'
            "🔐 Mit Passkey freischalten</button>"
            '<p id="pkmsg" class="err"></p>'
            "<p style='text-align:center;color:#5d6a7d;margin:10px 0'>— oder —</p>"
            + body +
            "<script>" + _WEBAUTHN_JS.format(B=_NAV) +
            "async function pk(){try{await passkeyStepup();"
            f"location.href={_js_str(next)}||B+'/login';}}"
            "catch(e){document.getElementById('pkmsg').textContent=e.message;}}"
            "</script>")
    return HTMLResponse(_LOGIN_HTML.format(err=msg, body=body))


@router.post("/stepup")
def stepup_verify(request: Request, code: str = Form(...), next: str = Form("")):
    sid = request.cookies.get(_SESSION_COOKIE)
    if store.get_session(sid) is None:
        return RedirectResponse(f"{_NAV}/login", status_code=302)
    if not store.totp_verify(code):
        sperre = store.lockout_rest("totp")              # H4: sichtbar im Audit
        _audit("id_stepup_fehlgeschlagen",
               {"via": "totp", "lockout_s": round(sperre)} if sperre
               else {"via": "totp"})
        return RedirectResponse(
            f"{_NAV}/stepup?{urlencode({'next': next, 'err': '1'})}", status_code=302)
    store.upgrade_session(sid, "hochsicher", "totp")
    _audit("id_stepup_ok", {"via": "totp"}, actor="user")
    return RedirectResponse(_safe_next(next) or f"{_NAV}/login", status_code=302)


# --- R1.3b: WebAuthn/Passkey — Registrierung + Hochsicher-Step-up -------------
# Eigener Verifier (id/webauthn.py) auf cryptography; Origin/RP-ID werden aus
# dem Host-Header abgeleitet (funktioniert über 127.0.0.1 UND localhost,
# beides sichere Browser-Kontexte) und NIE dem Client geglaubt.

def _origin_rpid(request: Request) -> tuple[set[str], str]:
    host = request.headers.get("host", "127.0.0.1:8200")
    rp_id = host.split(":")[0]
    return {f"http://{host}"}, rp_id


def _webauthn_session(request: Request):
    """Passkeys verwalten/nutzen verlangt eine aktive Anmeldung."""
    sid = request.cookies.get(_SESSION_COOKIE)
    return sid if store.get_session(sid) is not None else None


@router.post("/webauthn/register/begin")
def webauthn_register_begin(request: Request):
    if _webauthn_session(request) is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    _, rp_id = _origin_rpid(request)
    challenge = webauthn.b64url_encode(secrets.token_bytes(32))
    store.webauthn_set_challenge("register", challenge)
    ausschluss = [{"type": "public-key", "id": c["cred_id"]}
                  for c in store.webauthn_credentials()]
    return {
        "rp": {"id": rp_id, "name": "Dizzi-ID"},
        "user": {"id": webauthn.b64url_encode(DEFAULT_USER_ID.encode()),
                 "name": DEFAULT_USER_ID, "displayName": DEFAULT_USER_ID},
        "challenge": challenge,
        "pubKeyCredParams": [{"type": "public-key", "alg": -7},
                             {"type": "public-key", "alg": -8}],
        "timeout": 120000,
        "authenticatorSelection": {"residentKey": "preferred",
                                   "userVerification": "preferred"},
        "excludeCredentials": ausschluss,
        "attestation": "none",
    }


@router.post("/webauthn/register/finish")
async def webauthn_register_finish(request: Request):
    if _webauthn_session(request) is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    origins, rp_id = _origin_rpid(request)
    body = await request.json()
    challenge = store.webauthn_take_challenge("register")
    if challenge is None:
        return JSONResponse({"error": "keine/abgelaufene Challenge"}, status_code=400)
    try:
        resp = body["response"]
        cred = webauthn.register_verify(
            webauthn.b64url_decode(resp["clientDataJSON"]),
            webauthn.b64url_decode(resp["attestationObject"]),
            challenge_b64=challenge, origins=origins, rp_id=rp_id)
    except (webauthn.WebAuthnError, KeyError, ValueError) as e:
        _audit("id_webauthn_register_fehlgeschlagen", {"grund": type(e).__name__})
        return JSONResponse({"error": "Registrierung ungültig"}, status_code=400)
    if store.webauthn_get(cred["cred_id"]):
        return JSONResponse({"error": "Passkey bereits registriert"}, status_code=409)
    label = (body.get("label") or "Passkey")[:60]
    store.webauthn_add_credential(cred["cred_id"], cred["public_key"], cred["alg"],
                                  cred["sign_count"], cred["aaguid"], label)
    _audit("id_webauthn_registriert", {"alg": cred["alg"], "label": label},
           actor="user")
    return {"ok": True, "label": label}


@router.post("/webauthn/stepup/begin")
def webauthn_stepup_begin(request: Request):
    if _webauthn_session(request) is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    if store.lockout_rest("webauthn") > 0:
        return JSONResponse({"error": "vorübergehend gesperrt"}, status_code=429)
    _, rp_id = _origin_rpid(request)
    creds = store.webauthn_credentials()
    if not creds:
        return JSONResponse({"error": "kein Passkey registriert"}, status_code=400)
    challenge = webauthn.b64url_encode(secrets.token_bytes(32))
    store.webauthn_set_challenge("assert", challenge)
    return {
        "challenge": challenge, "rpId": rp_id, "timeout": 120000,
        # M-1: Step-up hebt auf 'hochsicher' (Echtgeld-/Trading-Tor) ⇒ echte
        # User Verification (Biometrie/PIN) verlangen, nicht nur User Presence.
        "userVerification": "required",
        "allowCredentials": [{"type": "public-key", "id": c["cred_id"]}
                             for c in creds],
    }


@router.post("/webauthn/stepup/finish")
async def webauthn_stepup_finish(request: Request):
    sid = _webauthn_session(request)
    if sid is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    if store.lockout_rest("webauthn") > 0:
        return JSONResponse({"error": "vorübergehend gesperrt"}, status_code=429)
    origins, rp_id = _origin_rpid(request)
    body = await request.json()
    challenge = store.webauthn_take_challenge("assert")
    if challenge is None:
        return JSONResponse({"error": "keine/abgelaufene Challenge"}, status_code=400)
    cred_id = body.get("id", "")
    stored = store.webauthn_get(cred_id)
    if stored is None:
        return JSONResponse({"error": "unbekannter Passkey"}, status_code=400)
    try:
        resp = body["response"]
        neuer_count = webauthn.assertion_verify(
            webauthn.b64url_decode(resp["clientDataJSON"]),
            webauthn.b64url_decode(resp["authenticatorData"]),
            webauthn.b64url_decode(resp["signature"]),
            public_key_blob=stored["public_key"], challenge_b64=challenge,
            origins=origins, rp_id=rp_id, stored_sign_count=stored["sign_count"],
            verlange_uv=True)   # M-1: Hochsicher-Step-up erzwingt User Verification
    except (webauthn.WebAuthnError, KeyError, ValueError) as e:
        store._lockout_fehlversuch("webauthn")   # H4: Brute-Force-Bremse
        sperre = store.lockout_rest("webauthn")
        _audit("id_stepup_fehlgeschlagen",
               {"via": "webauthn", "grund": type(e).__name__,
                **({"lockout_s": round(sperre)} if sperre else {})})
        return JSONResponse({"error": "Passkey-Prüfung fehlgeschlagen"},
                            status_code=400)
    store._lockout_reset("webauthn")
    store.webauthn_update_sign_count(cred_id, neuer_count)
    store.upgrade_session(sid, "hochsicher", "webauthn")
    _audit("id_stepup_ok", {"via": "webauthn", "label": stored["label"]},
           actor="user")
    return {"ok": True, "level": "hochsicher"}


@router.get("/webauthn/credentials")
def webauthn_credentials_list(request: Request):
    if _webauthn_session(request) is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    return store.webauthn_credentials()


@router.post("/webauthn/{db_id}/loeschen")
def webauthn_loeschen(db_id: str, request: Request):
    if _webauthn_session(request) is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    ok = store.webauthn_delete(db_id)
    if ok:
        _audit("id_webauthn_geloescht", {"id": db_id}, actor="user")
    return {"ok": ok}


# --- K2.1b/H7: Sitzungen & Geräte (Liste, Einzel-Widerruf, überall abmelden) --

@router.get("/geraete", response_class=HTMLResponse)
def geraete_page(request: Request):
    """H7-UI: zentrale Sitzungsverwaltung im IdP (same-origin — jede App
    verlinkt hierher, statt cross-origin am Local-Guard zu scheitern)."""
    sid = request.cookies.get(_SESSION_COOKIE)
    if store.get_session(sid) is None:
        return RedirectResponse(
            f"{_NAV}/login?{urlencode({'next': _NAV + '/geraete'})}",
            status_code=302)
    zeilen = []
    for s in store.list_sessions(sid):
        marker = (" — <b style='color:#36e0a0'>diese Sitzung</b>" if s["aktuell"]
                  else f'<button style="width:auto;padding:3px 10px;margin-left:8px;'
                       f'font-size:11.5px" onclick="widerrufen(\'{s["id"]}\')">'
                       "abmelden</button>")
        zeilen.append(
            "<div style='border:1px solid rgba(150,165,190,.25);padding:8px 10px;"
            "margin:6px 0;font-size:12.5px'>"
            f"Stufe <b>{s['level']}</b> ({', '.join(s['amr'])})<br>"
            f"<span style='color:#93a0b4'>seit {s['created_at']}</span>{marker}</div>")
    # Passkey-Abschnitt (R1.3b): registrierte Passkeys + Neu-Registrierung.
    pk_zeilen = []
    for c in store.webauthn_credentials():
        benutzt = (f" · zuletzt {c['last_used_at']}" if c["last_used_at"]
                   else " · noch nicht benutzt")
        pk_zeilen.append(
            "<div style='border:1px solid rgba(255,61,240,.25);padding:8px 10px;"
            "margin:6px 0;font-size:12.5px'>"
            f"🔐 <b>{c['label']}</b>{benutzt}"
            f'<button style="width:auto;padding:3px 10px;margin-left:8px;'
            f'font-size:11.5px" onclick="pkdel(\'{c["id"]}\')">entfernen</button>'
            "</div>")
    pk_block = (
        "<hr style='border-color:rgba(150,165,190,.2);margin:18px 0'>"
        "<p><b>Passkeys</b> — passwortlose Hochsicher-Freigabe per Gerät "
        "(Windows Hello, Fingerabdruck, Sicherheits-Key).</p>"
        + "".join(pk_zeilen) +
        '<button onclick="pkreg()" style="border-color:#ff3df0;color:#ff3df0">'
        "Passkey hinzufügen</button><p id=\"pkmsg\" class=\"err\"></p>")
    body = (
        "<p><b>Sitzungen &amp; Geräte</b> — jede Zeile ist eine aktive "
        "Dizzi-ID-Anmeldung.</p>" + "".join(zeilen) +
        '<button style="margin-top:12px" onclick="alle()">Überall abmelden</button>'
        + pk_block +
        f'<a class="gbtn" href="{_NAV}/login">Zurück</a>'
        "<script>" + _WEBAUTHN_JS.format(B=_NAV) +
        "async function widerrufen(id){await fetch(B+'/sessions/'+id+'/widerruf',"
        "{method:'POST'});location.reload();}"
        "async function alle(){await fetch(B+'/sessions/alle_widerrufen',"
        "{method:'POST'});location.href=B+'/login';}"
        "async function pkreg(){try{const l=prompt('Name für diesen Passkey:',"
        "'Mein Gerät');if(l===null)return;await passkeyRegister(l);location.reload();}"
        "catch(e){document.getElementById('pkmsg').textContent=e.message;}}"
        "async function pkdel(id){if(!confirm('Passkey entfernen?'))return;"
        "await fetch(B+'/webauthn/'+id+'/loeschen',{method:'POST'});location.reload();}"
        "</script>")
    return HTMLResponse(_LOGIN_HTML.format(err="", body=body))


def _session_pflicht(request: Request):
    """Gemeinsames Gate der Session-Verwaltung: nur mit aktiver Session."""
    sid = request.cookies.get(_SESSION_COOKIE)
    return sid if store.get_session(sid) is not None else None


@router.get("/sessions")
def sessions(request: Request):
    sid = _session_pflicht(request)
    if sid is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    return store.list_sessions(sid)


@router.post("/sessions/{session_id}/widerruf")
def session_widerruf(session_id: str, request: Request):
    sid = _session_pflicht(request)
    if sid is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    ok = store.revoke_session_id(session_id)
    if ok:
        _audit("id_session_widerrufen", {"session": session_id}, actor="user")
    return {"ok": ok, "session": session_id}


@router.post("/sessions/alle_widerrufen")
def sessions_alle_widerrufen(request: Request):
    """„Überall abmelden" — widerruft ALLE Sessions inkl. der aktuellen;
    das Cookie wird mit gelöscht, der Nutzer meldet sich neu an."""
    sid = _session_pflicht(request)
    if sid is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=401)
    n = store.revoke_all_sessions()
    _audit("id_sessions_alle_widerrufen", {"anzahl": n}, actor="user")
    resp = JSONResponse({"ok": True, "widerrufen": n})
    resp.delete_cookie(_SESSION_COOKIE, path="/")
    return resp


@router.post("/logout")
def logout(request: Request):
    store.revoke_session(request.cookies.get(_SESSION_COOKIE))
    _audit("id_logout", {}, actor="user")
    # Browser-Formulare bekommen die Login-Seite zurück, API-Clients JSON.
    if "text/html" in request.headers.get("accept", ""):
        resp = RedirectResponse(f"{_NAV}/login", status_code=303)
    else:
        resp = JSONResponse({"ok": True})
    resp.delete_cookie(_SESSION_COOKIE, path="/")
    return resp


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    """Für Shell/Diagnose + das Konto-Fenster (docs/19 §2b): Zustand des
    Identitäts-Dienstes inkl. Anmelde-Detail der aktuellen Browser-Session
    (user_id/amr/via für die Sektion „Identität & Sicherheit")."""
    session = store.get_session(request.cookies.get(_SESSION_COOKIE))
    amr = session["amr"] if session else []
    return {"angemeldet": session is not None,
            "user_id": session["user_id"] if session else None,
            "level": session["level"] if session else None,
            "amr": amr,
            "via": ("google" if "google" in amr else "passwort") if session else "standalone",
            "lokales_passwort": store.has_local_password(),
            "google_konfiguriert": google.configured(),
            "mfa": store.totp_state(),
            "passkey": store.webauthn_state()}
