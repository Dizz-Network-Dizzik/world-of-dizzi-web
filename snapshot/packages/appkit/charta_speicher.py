"""DzCharta — Speicher (V-BIZZI-2, B2 · Runde 2): Tabellen · Signatur · CAS ·
Aktivierungs-Strecke · Vier-Augen (self-contained in ``charta_entscheide``).

Trennt die *Persistenz/Krypto* vom reinen Urteils-Kern (``charta.py`` bleibt
≤500 Zeilen, wirft-nie). Hier:

- **Tabellen** ``charta_versionen``/``charta_entscheide`` (B2.4) als additives
  ``SCHEMA`` (Muster ``chronik.AUSGANG_SCHEMA``).
- **Entscheid = signierte Einmal-Capability** (CH-6): antrag_hash-gebunden, TTL,
  CAS ``offen→verbraucht`` (wörtlich das ``actions.decide``-Muster), Signatur mit
  eigenem Charta-Schlüssel (Stamm-Brief-beglaubigt — Domänen nie mischen, B2.5).
- **Aktivierungs-Strecke** (B3.3, CH-7): Versions-Flip + ``chronik.schreibe(
  charta.version)`` in EINER ``db.transaktion()`` → Commit → ``flush_und_warte()``
  → idempotenter Siegel-Referenz-Nachtrag; Rollback = NEUES Ereignis (CH-13).
- **Vier-Augen** (CH-11) über ``charta_entscheide`` (zweit_subjekt/zweit_auth_ref):
  zweiter ≠ Ersteller, frische hochsicher-Auth, Zeitstempel NACH dem Antrag.

★ NICHT enthalten (an WA/post-RG-4 deferiert): die §B5-Anbindung an
``app_actions``/``actions.decide`` (``pruefer_id``) — ``chat/management`` (RG-4)
editiert ``actions.py`` live (packages-seriell max-1). Die Vier-Augen-Garantie
CH-11 ist hier vollständig und geprüft; nur die Inbox-Oberfläche fehlt.

Vertrag: ``docs/84_BIZZI_CONTROLLING_UND_CHARTA_FABLE.md`` §B2.4/§B3/§B5.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import chronik as C
from . import charta as CH
from .db import new_id, now_iso


class ChartaSpeicherFehler(Exception):
    """Fail-loud bei Schlüssel-/Brief-/Aktivierungs-Verletzung."""


# ─────────────────────────────────────────────────────────────────────────────
# Schema (B2.4) — additiv, wie chronik.AUSGANG_SCHEMA (die App hängt es an ihr
# ``extra_schema``; genau EINE Zeile status='aktiv' via partiellem UNIQUE-Index).
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS charta_versionen (
  version        TEXT PRIMARY KEY,
  artikel        TEXT NOT NULL,
  artikel_hash   TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'entwurf',   -- entwurf | aktiv | abgeloest
  aktiviert_at   TEXT,
  chronik_epoche INTEGER,
  chronik_siegel TEXT,
  created_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_charta_eine_aktive
  ON charta_versionen (status) WHERE status = 'aktiv';

CREATE TABLE IF NOT EXISTS charta_entscheide (
  id             TEXT PRIMARY KEY,
  user_id        TEXT NOT NULL,                     -- Ersteller (opake UUID, BZ-C-10)
  antrag         TEXT NOT NULL,                      -- kanon()-JSON (Replay-Grundlage!)
  antrag_hash    TEXT NOT NULL,                      -- Entscheid passt NUR auf diesen Antrag
  artikel        TEXT NOT NULL,                      -- Aktion
  ergebnis       TEXT NOT NULL,                      -- gewaehrt
  obliegenheiten TEXT NOT NULL DEFAULT '[]',
  policy_version TEXT NOT NULL,
  zweit_subjekt  TEXT NOT NULL DEFAULT '',
  auth_ref       TEXT NOT NULL,
  zweit_auth_ref TEXT NOT NULL DEFAULT '',
  entscheid_hash TEXT NOT NULL DEFAULT '',           -- final beim Verbrauch (CH-15)
  gueltig_bis    TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'offen',       -- offen | verbraucht | verfallen
  sig            TEXT NOT NULL,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_charta_entscheide_status
  ON charta_entscheide (user_id, status, created_at);
"""


# ─────────────────────────────────────────────────────────────────────────────
# Charta-Schlüssel (eigener Ed25519, Stamm-Brief-beglaubigt — B2.5 / docs/80 §2.6)
# ─────────────────────────────────────────────────────────────────────────────


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _neues_okp_jwk() -> dict:
    from joserfc.jwk import OKPKey
    key = OKPKey.generate_key("Ed25519", {"alg": "Ed25519", "use": "sig"})
    data = key.as_dict(private=True)
    data["kid"] = key.thumbprint()
    return data


def _oeffentlich(jwk: dict) -> dict:
    return {k: jwk[k] for k in ("kty", "crv", "x", "kid") if k in jwk}


def _verify(sig_str: str, digest: bytes, pub: dict) -> bool:
    try:
        schema, kid, b64 = sig_str.split(":", 2)
    except (ValueError, AttributeError):
        return False
    if schema != "ed25519" or pub.get("kid") != kid:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(_b64u_dec(pub["x"])).verify(_b64u_dec(b64), digest)
        return True
    except (InvalidSignature, ValueError, KeyError):
        return False


def lade_oder_erzeuge_charta_schluessel(cdir: Path | None = None) -> dict:
    """Lädt den privaten Charta-Schlüssel (secrets_os/DPAPI); erzeugt ihn beim
    ersten Aufruf + schreibt ``charta_brief.json`` (vom **Stamm** beglaubigt —
    eigener Key, Domänen nie mischen). Der Stamm stammt aus der Chronik (B1)."""
    from . import secrets_os
    from .io_safe import atomic_write_text

    cdir = cdir or C.chronik_dir()
    cdir.mkdir(parents=True, exist_ok=True)
    stamm = C.lade_oder_erzeuge_schluessel(cdir).stamm
    key_p, brief_p = cdir / "charta_key.json", cdir / "charta_brief.json"

    roh = secrets_os.lese_geheim(key_p)
    if roh:
        return json.loads(roh.decode("utf-8"))

    priv = _neues_okp_jwk()
    secrets_os.schreibe_geheim(key_p, json.dumps(priv).encode("utf-8"))
    kern = {"modul": "charta", "kid": priv["kid"],
            "pubkey": _oeffentlich(priv), "gueltig_ab": now_iso()}
    basis = hashlib.sha256(C.kanon(kern).encode("utf-8")).digest()
    brief = {**kern, "brief_sig": C.signiere(basis, stamm)}
    atomic_write_text(brief_p, C.kanon(brief))
    return priv


def lade_charta_pubkey(cdir: Path | None = None) -> dict:
    """Öffentlicher Charta-Schlüssel für die Verifikation (Prüfer/policy-replay).
    Verifiziert den Stamm-beglaubigten Brief beim Laden (wirft bei Bruch)."""
    cdir = cdir or C.chronik_dir()
    stamm_pub = C.lade_pruefmaterial(cdir).stamm_pub
    brief = json.loads((cdir / "charta_brief.json").read_text("utf-8"))
    kern = {k: brief[k] for k in ("modul", "kid", "pubkey", "gueltig_ab")}
    basis = hashlib.sha256(C.kanon(kern).encode("utf-8")).digest()
    if not _verify(brief["brief_sig"], basis, stamm_pub):
        raise ChartaSpeicherFehler("charta_brief-Signatur ungültig (Stamm beglaubigt Charta nicht)")
    return brief["pubkey"]


# ─────────────────────────────────────────────────────────────────────────────
# Entscheid — Ausstellung (Signatur) · CAS-Verbrauch · Vier-Augen (CH-6/11/15)
# ─────────────────────────────────────────────────────────────────────────────


def _sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso_plus(iso: str, sekunden: int) -> str:
    return (datetime.fromisoformat(iso) + timedelta(seconds=sekunden)).isoformat(timespec="seconds")


def _abgelaufen(jetzt_iso: str, gueltig_bis: str) -> bool:
    try:
        return datetime.fromisoformat(jetzt_iso) > datetime.fromisoformat(gueltig_bis)
    except ValueError:
        return True                                    # fail-closed


def _kern_ausstellung(row) -> dict:
    """Der signierte Ausstellungs-Kern (ohne zweit_*/sig/status) — bit-identisch
    zwischen ``entscheid_bauen`` und Verbrauch/Replay (Signatur-Basis)."""
    return {
        "id": row["id"], "user_id": row["user_id"], "antrag_hash": row["antrag_hash"],
        "artikel": row["artikel"], "ergebnis": row["ergebnis"],
        "obliegenheiten": json.loads(row["obliegenheiten"]),
        "policy_version": row["policy_version"], "gueltig_bis": row["gueltig_bis"],
        "auth_ref": row["auth_ref"],
    }


def _entscheid_hash_final(row) -> str:
    kern = _kern_ausstellung(row)
    kern["zweit_subjekt"] = row["zweit_subjekt"]
    kern["zweit_auth_ref"] = row["zweit_auth_ref"]
    return _sha256_hex(C.kanon(kern))


def entscheid_bauen(antrag: dict, charta, *, jetzt_iso: str, auth_ref: str,
                    ttl_s: int = 120, cdir: Path | None = None,
                    vier_augen_moeglich: bool = True):
    """Wertet ``antrag`` gegen ``charta`` (dict oder ``charta.Charta``) und stellt
    bei Gewährung eine **signierte Einmal-Capability** aus (noch nicht persistiert).
    Rückgabe ``(entscheid | None, urteil)``; ``None`` ⇒ verweigert (kein Capability)."""
    if isinstance(charta, CH.Charta):
        urteil = charta.pruefe(antrag, vier_augen_moeglich=vier_augen_moeglich)
        version = charta.version
    else:
        urteil = CH.pruefe(antrag, charta, vier_augen_moeglich=vier_augen_moeglich)
        version = charta.get("charta_version", "") if isinstance(charta, dict) else ""
    if not urteil.gewaehrt:
        return None, urteil

    antrag_kanon = C.kanon(antrag)
    kern = {
        "id": new_id(),
        "user_id": (antrag.get("subjekt") or {}).get("id", ""),
        "antrag_hash": _sha256_hex(antrag_kanon),
        "artikel": antrag.get("aktion", ""),
        "ergebnis": "gewaehrt",
        "obliegenheiten": sorted(urteil.obliegenheiten),
        "policy_version": version,
        "gueltig_bis": _iso_plus(jetzt_iso, ttl_s),
        "auth_ref": auth_ref,
    }
    priv = lade_oder_erzeuge_charta_schluessel(cdir)
    basis = hashlib.sha256(C.kanon(kern).encode("utf-8")).digest()
    entscheid = {**kern, "antrag": antrag_kanon, "zweit_subjekt": "", "zweit_auth_ref": "",
                 "entscheid_hash": "", "status": "offen", "sig": C.signiere(basis, priv),
                 "created_at": jetzt_iso}
    return entscheid, urteil


def entscheid_schreiben(conn, entscheid: dict) -> None:
    """INSERT der Capability (Status 'offen') — auf der offenen Verbindung, ohne
    Commit (dieselbe ``db.transaktion()`` wie die auslösende Kern-Mutation)."""
    conn.execute(
        "INSERT INTO charta_entscheide (id, user_id, antrag, antrag_hash, artikel, ergebnis, "
        "obliegenheiten, policy_version, zweit_subjekt, auth_ref, zweit_auth_ref, entscheid_hash, "
        "gueltig_bis, status, sig, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (entscheid["id"], entscheid["user_id"], entscheid["antrag"], entscheid["antrag_hash"],
         entscheid["artikel"], entscheid["ergebnis"], json.dumps(entscheid["obliegenheiten"]),
         entscheid["policy_version"], entscheid["zweit_subjekt"], entscheid["auth_ref"],
         entscheid["zweit_auth_ref"], entscheid["entscheid_hash"], entscheid["gueltig_bis"],
         "offen", entscheid["sig"], entscheid["created_at"]))


def entscheid_gegenzeichnen(conn, entscheid_id: str, *, zweit_subjekt: str,
                            zweit_auth_ref: str, zweit_auth_zeit_iso: str,
                            zweit_frisch_hochsicher: bool) -> None:
    """Vier-Augen (CH-11): trägt das zweite Subjekt in eine 'offen'e vier_augen-
    Capability. Verlangt: zweiter ≠ Ersteller, frische hochsicher-Auth, Zeitstempel
    NACH dem Antrag. Fail-loud bei jedem Verstoß (nie stilles Downgrade)."""
    row = conn.execute("SELECT * FROM charta_entscheide WHERE id=?", (entscheid_id,)).fetchone()
    if row is None or row["status"] != "offen":
        raise ChartaSpeicherFehler("Gegenzeichnung: Entscheid nicht offen")
    if "vier_augen" not in json.loads(row["obliegenheiten"]):
        raise ChartaSpeicherFehler("Gegenzeichnung: kein vier_augen-Entscheid")
    if not zweit_frisch_hochsicher:
        raise ChartaSpeicherFehler("Gegenzeichnung: zweite Auth nicht frisch/hochsicher")
    if not zweit_subjekt or zweit_subjekt == row["user_id"]:
        raise ChartaSpeicherFehler("Gegenzeichnung: Selbst-Gegenzeichnung verboten (Maker≠Checker)")
    antrag = json.loads(row["antrag"])
    if not (zweit_auth_zeit_iso > str(antrag.get("zeit", ""))):        # NACH dem Antrag
        raise ChartaSpeicherFehler("Gegenzeichnung: zweite Auth nicht NACH dem Antrag")
    cur = conn.execute(
        "UPDATE charta_entscheide SET zweit_subjekt=?, zweit_auth_ref=? "
        "WHERE id=? AND status='offen' AND zweit_subjekt=''",
        (zweit_subjekt, zweit_auth_ref, entscheid_id))
    if cur.rowcount != 1:
        raise ChartaSpeicherFehler("Gegenzeichnung: bereits gegengezeichnet oder Rennen verloren")


def entscheid_verbrauchen(conn, entscheid_id: str, *, antrag_hash: str, jetzt_iso: str,
                          cdir: Path | None = None):
    """Einmal-Verbrauch (CH-6): prüft antrag_hash-Bindung, TTL, Signatur und —
    bei vier_augen — die Gegenzeichnung; dann CAS ``offen→verbraucht`` (at-most-once,
    ``actions.decide``-Muster). Rückgabe: verbrauchte Zeile (dict) oder ``None``
    (unbekannt / abgelaufen / Bruch / Rennen verloren). Berechnet ``entscheid_hash``
    (CH-15) beim Verbrauch — er wandert in R3 in die Kern-Nutzlast (chain-verankert)."""
    row = conn.execute("SELECT * FROM charta_entscheide WHERE id=?", (entscheid_id,)).fetchone()
    if row is None or row["status"] != "offen":
        return None
    if _abgelaufen(jetzt_iso, row["gueltig_bis"]):
        conn.execute("UPDATE charta_entscheide SET status='verfallen' WHERE id=? AND status='offen'",
                     (entscheid_id,))
        return None
    if antrag_hash != row["antrag_hash"]:                              # falscher Antrag
        return None
    if not _verify(row["sig"], hashlib.sha256(C.kanon(_kern_ausstellung(row)).encode("utf-8")).digest(),
                   lade_charta_pubkey(cdir)):                          # Signatur-Bruch
        return None
    if "vier_augen" in json.loads(row["obliegenheiten"]) and not row["zweit_subjekt"]:
        return None                                                   # Gegenzeichnung fehlt

    entscheid_hash = _entscheid_hash_final(row)
    cur = conn.execute(
        "UPDATE charta_entscheide SET status='verbraucht', entscheid_hash=? "
        "WHERE id=? AND status='offen'", (entscheid_hash, entscheid_id))
    if cur.rowcount != 1:                                             # Rennen verloren
        return None
    ergebnis = dict(row)
    ergebnis["status"], ergebnis["entscheid_hash"] = "verbraucht", entscheid_hash
    return ergebnis


# ─────────────────────────────────────────────────────────────────────────────
# Aktivierungs-Strecke (B3.3 / CH-7) — Versions-Flip + charta.version in DIESELBE
# db.transaktion(), dann flush_und_warte + idempotenter Siegel-Nachtrag.
# ─────────────────────────────────────────────────────────────────────────────


def aktiviere_version(db, *, charta: dict, subjekt: str, jetzt_iso: str,
                      chronist=None) -> dict:
    """Aktiviert eine Charta-Version. Schreibt in EINER ``db.transaktion()`` den
    Versions-Flip (entwurf→aktiv, alte aktiv→abgeloest) + das siegelpflichtige
    ``charta.version``-Ereignis (voll: policy_version, artikel_hash). NACH dem
    Commit ``chronist.flush_und_warte()`` (falls übergeben) + idempotenter
    Nachtrag der Siegel-Referenz. Rollback = erneute Aktivierung = NEUES Ereignis
    (CH-13), nie Löschung. Rückgabe: {version, artikel_hash, epoche?, siegel?}."""
    artikel_hash = CH.validiere(charta)                # wirft ChartaFehler bei Verstoß
    version = charta["charta_version"]
    artikel_json = C.kanon(charta["artikel"])

    with db.transaktion() as conn:
        vorhanden = conn.execute("SELECT version FROM charta_versionen WHERE version=?",
                                 (version,)).fetchone()
        if vorhanden is None:
            conn.execute(
                "INSERT INTO charta_versionen (version, artikel, artikel_hash, status, created_at) "
                "VALUES (?,?,?,'entwurf',?)", (version, artikel_json, artikel_hash, jetzt_iso))
        conn.execute("UPDATE charta_versionen SET status='abgeloest' WHERE status='aktiv'")
        conn.execute("UPDATE charta_versionen SET status='aktiv', aktiviert_at=? WHERE version=?",
                     (jetzt_iso, version))
        C.schreibe(conn, art="charta.version", subjekt=subjekt,
                   nutzlast={"policy_version": version, "artikel_hash": artikel_hash})

    if chronist is None:
        return {"version": version, "artikel_hash": artikel_hash}

    siegel = chronist.flush_und_warte()                # NACH dem Commit (BZ-C-5)
    conn = db.get_conn()
    conn.execute(                                       # Siegel-Referenz DIESER Aktivierung
        "UPDATE charta_versionen SET chronik_epoche=?, chronik_siegel=? WHERE version=?",
        (siegel["epoche"], C.siegel_hash(siegel), version))
    conn.commit()
    # Hinweis: Der Absturz-Fall „Commit ok, Nachtrag fehlt" wird durch einen
    # Restart-Backfill geheilt (kein erneutes aktiviere_version — sonst zweites
    # Ereignis); dieser Ops-Pfad kommt mit R3 (bizzi-pruef/Task).
    return {"version": version, "artikel_hash": artikel_hash,
            "epoche": siegel["epoche"], "siegel": C.siegel_hash(siegel)}
