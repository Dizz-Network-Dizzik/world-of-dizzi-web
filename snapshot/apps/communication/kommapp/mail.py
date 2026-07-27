"""E-Mail-Schiene — das risikofreie Fundament von Dizz Communication.

Hier steht die schwer nachrüstbare Substanz (Architektur-KI):
- **XOAUTH2** (SASL-String, RFC-konform) — OAuth ist 2026 Pflicht bei allen
  großen Providern (Microsoft beendet Basic Auth am 30.04.2026); Gmail läuft
  damit über normales IMAP (imap.gmail.com), KEIN Google-API-Client nötig.
- **Sync-Zustandsmaschine** (``sync_plan``): inkrementeller Abruf über
  UIDVALIDITY/UIDNEXT je Ordner — pure Funktion, der eine Punkt, an dem
  über voll/inkrementell/nichts entschieden wird.
- **Parsing/Threading**: stdlib ``email`` (policy.default decodiert Header),
  Konversations-Schlüssel aus References/In-Reply-To/Message-ID.
- **ImapQuelle**: stdlib ``imaplib`` mit injizierbarer Verbindungs-Fabrik —
  der Kern ist ohne Netz testbar (Fake-IMAP), live ist es derselbe Code.
- **Versand** (``sende_mail``): stdlib ``smtplib``, ebenfalls injizierbar.
  Der Aufruf läuft in der App NUR als HITL-Aktion (K4) — nie autonom.

Geheimnisse (Passwort/OAuth-Token) leben im K2-Tresor, NIE in der DB —
die Konten-Tabelle hält nur eine ``tresor_ref``.
"""

from __future__ import annotations

import base64
import email
import email.message
import imaplib
import re
import smtplib
from dataclasses import dataclass, field
from email.policy import default as _email_policy
from html.parser import HTMLParser
from typing import Any, Callable, Sequence

KANAL_EMAIL = "email"


# --- XOAUTH2 (SASL-Initial-Response für IMAP/SMTP AUTHENTICATE) --------------


def xoauth2_string(benutzer: str, access_token: str) -> str:
    """``user=<u>\\x01auth=Bearer <t>\\x01\\x01`` — das Format, das Gmail/
    Outlook bei ``AUTHENTICATE XOAUTH2`` erwarten (unkodiert; imaplib
    base64-kodiert das Initial-Response selbst)."""
    return f"user={benutzer}\x01auth=Bearer {access_token}\x01\x01"


def xoauth2_b64(benutzer: str, access_token: str) -> str:
    """Base64-Variante für Protokolle, die selbst nicht kodieren (SMTP)."""
    return base64.b64encode(
        xoauth2_string(benutzer, access_token).encode("utf-8")).decode("ascii")


# --- Sync-Zustandsmaschine (UIDVALIDITY/UIDNEXT, RFC 3501) -------------------


@dataclass
class OrdnerZustand:
    """Persistierter Sync-Stand eines IMAP-Ordners (0/0 = nie synchronisiert)."""

    uidvalidity: int = 0
    uidnext: int = 0


# Mengen-Deckel (Live-Lehre 12.06.: ungedeckelter Erstsync gegen ein volles
# Gmail-Postfach = Voll-Download aller Mails ⇒ Timeout):
ERSTSYNC_NEUESTE = 50                    # Erst-/Resync: nur die NEUESTEN N
BATCH_MAX = 200                          # Inkrement je Lauf; Rest folgt beim nächsten


def sync_plan(alt: OrdnerZustand, uidvalidity: int,
              uidnext: int) -> tuple[str, tuple[int, int] | None]:
    """Entscheidet den Abruf: ('voll'|'inkrementell'|'nichts', UID-Bereich).

    - UIDVALIDITY gewechselt (Server hat UIDs neu vergeben) ⇒ Resync, aber
      GEDECKELT auf die neuesten ERSTSYNC_NEUESTE (ein volles Postfach wird
      bewusst NICHT rückwärts aufgesogen — der Posteingang lebt vorwärts).
    - sonst inkrementell ab dem letzten Stand, höchstens BATCH_MAX am Stück;
      der Aufrufer persistiert ``bereich_ende+1`` als neuen Stand, der Rest
      kommt verlustfrei beim nächsten Lauf.
    """
    if alt.uidvalidity != uidvalidity:
        if uidnext <= 1:
            return ("voll", None)
        return ("voll", (max(1, uidnext - ERSTSYNC_NEUESTE), uidnext - 1))
    if uidnext > alt.uidnext:
        return ("inkrementell",
                (alt.uidnext, min(uidnext - 1, alt.uidnext + BATCH_MAX - 1)))
    return ("nichts", None)


# --- Parsing & Threading (stdlib email) --------------------------------------


class _HtmlZuText(HTMLParser):
    """Minimaler HTML->Klartext-Extraktor (stdlib, 0 Abhaengigkeiten): wirft
    script/style/head weg, macht aus Block-Elementen Zeilenumbrueche und liefert
    lesbaren Text. Reicht fuer die Posteingangs-Anzeige/Suche; KEIN Rich-Render
    (rohes HTML wuerde die UI ohnehin escapen => XSS-sicher)."""

    _SKIP = {"script", "style", "head", "title"}
    _BLOCK = {"p", "div", "br", "li", "tr", "table", "ul", "ol", "blockquote",
              "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header",
              "footer", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)   # Entities -> Klartext in handle_data
        self._teile: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self._teile.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self._teile.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._teile.append(data)

    def text(self) -> str:
        zeilen: list[str] = []
        for z in "".join(self._teile).splitlines():
            z = re.sub(r"\s+", " ", z).strip()    # \s ist Unicode-aware (auch nbsp)
            if z:
                zeilen.append(z)
            elif zeilen and zeilen[-1] != "":
                zeilen.append("")                 # eine Leerzeile als Absatz-Trenner
        return "\n".join(zeilen).strip()


def html_zu_text(html: str) -> str:
    """HTML -> lesbarer Klartext; bei kaputtem Markup grober Tag-Strip-Fallback."""
    parser = _HtmlZuText()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
    return parser.text()


def _text_aus(msg: email.message.EmailMessage) -> str:
    """Bester Klartext: text/plain bevorzugt; ist nur HTML da, wird es in
    lesbaren Text gewandelt (statt rohes Markup zu speichern -- das verschmutzte
    Anzeige, Suche und KI-Triage)."""
    teil = msg.get_body(preferencelist=("plain", "html"))
    if teil is None:
        return ""
    try:
        inhalt = teil.get_content() or ""
    except Exception:
        return ""
    if teil.get_content_type() == "text/html":
        return html_zu_text(inhalt)
    return inhalt.strip()


def nachricht_aus_bytes(roh: bytes) -> dict[str, Any]:
    """Parst eine RFC-822-Nachricht in unser kanal-agnostisches Format.
    Header werden decodiert (policy.default: =?utf-8?…?= ⇒ Klartext)."""
    msg = email.message_from_bytes(roh, policy=_email_policy)
    return {
        "kanal_typ": KANAL_EMAIL,
        "extern_id": (msg.get("Message-ID") or "").strip(),
        "von_adresse": str(msg.get("From") or ""),
        "an_adressen": str(msg.get("To") or ""),
        "betreff": str(msg.get("Subject") or "").strip(),
        "text": _text_aus(msg)[:20_000],
        "gesendet_at": str(msg.get("Date") or ""),
        "thread_schluessel": thread_schluessel(msg),
    }


def thread_schluessel(msg: email.message.EmailMessage) -> str:
    """Konversations-Schlüssel: Wurzel der References-Kette > In-Reply-To >
    eigene Message-ID — so landen Antworten in derselben Konversation."""
    refs = (msg.get("References") or "").split()
    if refs:
        return refs[0].strip()
    in_reply = (msg.get("In-Reply-To") or "").strip()
    if in_reply:
        return in_reply
    return (msg.get("Message-ID") or "").strip()


# --- KanalSource-Schnitt ------------------------------------------------------

ImapFactory = Callable[[str, int], Any]          # (host, port) -> IMAP4-artig
SmtpFactory = Callable[[str, int], Any]          # (host, port) -> SMTP-artig


class KanalFehler(RuntimeError):
    """Quelle nicht erreichbar/Fähigkeit fehlt — mit ehrlicher Begründung."""


class KanalQuelle:
    """Basis aller Kanäle (E-Mail, später Matrix/Webview): EIN Interface,
    viele Stecker (Dossier §5). Unterklassen implementieren nur, was sie
    wirklich können — alles andere scheitert ehrlich (fail-closed)."""

    art: str = ""

    def hole_neue(self, ordner: str,
                  zustand: OrdnerZustand) -> tuple[list[dict[str, Any]], OrdnerZustand]:
        raise KanalFehler(f"{self.art}: Abruf nicht implementiert")

    def senden(self, an: str, betreff: str, text: str) -> None:
        raise KanalFehler(f"{self.art}: Versand nicht implementiert")


# --- Schreib-Operationen des E-Mail-Piloten (RG-6, docs/83 §5.7) -------------
#
# Der Pilot hebt drei KLEINE, harmlose Server-Aktionen in die Agenten-Regie —
# alle level ``lokal`` ⇒ Klasse ``entwurf`` (``_LEVEL_ZU_KLASSE``): einen
# Antwort-ENTWURF in den Drafts-Ordner legen, eine Nachricht markieren (Flag),
# eine Nachricht in einen anderen Ordner verschieben. **SENDEN/LÖSCHEN/
# WEITERLEITEN sind bewusst NICHT hier** (docs/83 §5 „Was NIE automatisch
# passiert"): Senden bleibt das vorhandene, ``verifiziert``-stufige
# ``sende_mail``/``mail_senden`` (Klasse ``aussenwirkung``, immer pre_approval).
#
# Die Schreib-Methoden leben auf ``ImapQuelle`` (unten): dieselbe injizierbare
# IMAP-Fabrik wie der Abruf ⇒ der Kern ist ohne Netz testbar (Fake-IMAP), live
# derselbe Code. Jede Op ist EINE Verbindung (Provider-Limit, Dossier §3),
# scheitert ehrlich (``KanalFehler``) statt still, und findet die volatile
# IMAP-UID zur Laufzeit aus unserer stabilen ``extern_id`` (RFC-Message-ID) per
# ``UID SEARCH HEADER``.

FLAG_GELESEN = "\\Seen"
FLAG_WICHTIG = "\\Flagged"

#: Erlaubte ``email_markieren``-Flags (fachlicher Name → IMAP-System-Flag). Ein
#: unbekannter Name scheitert fail-closed im Handler — nie ein rohes Flag durchreichen.
MARKIER_FLAGS = {"gelesen": FLAG_GELESEN, "wichtig": FLAG_WICHTIG}

STANDARD_ENTWURF_ORDNER = "Drafts"


def _re_betreff(betreff: str) -> str:
    """Antwort-Betreff: genau EIN führendes ``Re:`` (kein ``Re: Re: …``-Wildwuchs)."""
    b = (betreff or "").strip()
    return b if b[:3].lower() == "re:" else f"Re: {b}" if b else "Re:"


def baue_entwurf_bytes(von: str, an: str | Sequence[str], betreff: str, text: str,
                       in_reply_to: str = "", references: str = "") -> bytes:
    """RFC-822-Bytes eines Antwort-ENTWURFs (stdlib ``email``). ``In-Reply-To``/
    ``References`` auf die Ursprungs-Message-ID gesetzt, damit der Provider den
    Entwurf im richtigen Thread führt. Rein Bau — kein Netz, kein Versand; der
    ``ImapQuelle.entwurf_ablegen``-APPEND legt das Ergebnis in den Drafts-Ordner."""
    msg = email.message.EmailMessage()
    if von:
        msg["From"] = von
    msg["To"] = an if isinstance(an, str) else ", ".join(an)
    msg["Subject"] = betreff
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(text or "")
    return bytes(msg)


class ImapQuelle(KanalQuelle):
    """IMAP4rev1 + XOAUTH2/Passwort — deckt Gmail, Outlook und jeden
    klassischen Provider ab. Verbindungs-Disziplin: EINE Verbindung je
    Sync-Lauf (Provider-Limits, Dossier §3)."""

    art = "imap"

    def __init__(self, host: str, benutzer: str, geheimnis: str,
                 auth: str = "passwort", port: int = 993,
                 imap_factory: ImapFactory | None = None) -> None:
        self.host, self.port = host, port
        self.benutzer, self._geheimnis, self.auth = benutzer, geheimnis, auth
        self._factory = imap_factory or (
            lambda h, p: imaplib.IMAP4_SSL(h, p, timeout=15))

    def _verbinden(self):
        conn = self._factory(self.host, self.port)
        if self.auth == "xoauth2":
            conn.authenticate(
                "XOAUTH2",
                lambda _challenge: xoauth2_string(
                    self.benutzer, self._geheimnis).encode("utf-8"))
        else:
            conn.login(self.benutzer, self._geheimnis)
        return conn

    @staticmethod
    def _antwort_zahl(conn: Any, name: str, default: int) -> int:
        """Bracketed-Code aus der SELECT-Antwort (imaplib liefert ggf. [None])."""
        daten = conn.response(name)[1]
        wert = daten[0] if daten else None
        return int(wert) if wert else default

    def hole_neue(self, ordner: str,
                  zustand: OrdnerZustand) -> tuple[list[dict[str, Any]], OrdnerZustand]:
        """Inkrementeller Abruf nach ``sync_plan``; liefert geparste
        Nachrichten + den NEUEN Ordner-Zustand (Aufrufer persistiert)."""
        conn = self._verbinden()
        try:
            status, _ = conn.select(ordner, readonly=True)
            if status != "OK":
                raise KanalFehler(f"imap: Ordner {ordner!r} nicht wählbar")
            uidvalidity = self._antwort_zahl(conn, "UIDVALIDITY", 0)
            uidnext = self._antwort_zahl(conn, "UIDNEXT", 1)
            modus, bereich = sync_plan(zustand, uidvalidity, uidnext)
            if modus == "nichts" or bereich is None:
                return [], OrdnerZustand(uidvalidity=uidvalidity, uidnext=uidnext)
            # Persistierter Stand = GEHOLTES Ende + 1 (nicht Server-uidnext):
            # ein gedeckelter Inkrement-Batch verliert so nichts — der Rest
            # kommt beim nächsten Lauf dran.
            neu = OrdnerZustand(uidvalidity=uidvalidity,
                                uidnext=(uidnext if modus == "voll"
                                         else bereich[1] + 1))
            status, daten = conn.uid(
                "fetch", f"{bereich[0]}:{bereich[1]}", "(RFC822)")
            if status != "OK":
                raise KanalFehler("imap: UID FETCH fehlgeschlagen")
            out = []
            for teil in daten or []:
                if isinstance(teil, tuple) and len(teil) >= 2 and teil[1]:
                    out.append(nachricht_aus_bytes(teil[1]))
            return out, neu
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # --- Schreib-Ops des E-Mail-Piloten (RG-6, docs/83 §5.7) -----------------

    @staticmethod
    def _logout(conn: Any) -> None:
        try:
            conn.logout()
        except Exception:
            pass

    def _uid_finden(self, conn: Any, ordner: str, message_id: str) -> str:
        """Volatile IMAP-UID zur stabilen ``message_id`` (unsere ``extern_id``) im
        Ordner: SELECT (schreibbar) + ``UID SEARCH HEADER Message-ID``. Fail-closed —
        nicht wählbar / nicht gefunden ⇒ ``KanalFehler`` (nie stilles Nichts, sonst
        markiert/verschiebt der Vollzug lautlos ins Leere)."""
        status, _ = conn.select(ordner)
        if status != "OK":
            raise KanalFehler(f"imap: Ordner {ordner!r} nicht wählbar")
        status, daten = conn.uid("search", None, "HEADER", "Message-ID", message_id)
        if status != "OK":
            raise KanalFehler("imap: UID SEARCH fehlgeschlagen")
        roh = (daten[0] if daten else b"") or b""
        teile = roh.split() if isinstance(roh, (bytes, bytearray)) else str(roh).split()
        if not teile:
            raise KanalFehler(
                f"imap: Nachricht {message_id!r} in {ordner!r} nicht gefunden")
        letzte = teile[-1]
        return letzte.decode() if isinstance(letzte, (bytes, bytearray)) else str(letzte)

    def entwurf_ablegen(self, roh: bytes,
                        ordner: str = STANDARD_ENTWURF_ORDNER) -> dict[str, Any]:
        """IMAP APPEND eines Entwurfs (Flag ``\\Draft``) in den Drafts-Ordner — der
        Provider zeigt ihn als normalen Entwurf. Die Idempotenz liegt in der
        K4-Schicht (``propose(idem=…)``, docs/83 §2): ein doppelter APPEND wäre ein
        zweiter Entwurf, darum dedupt die Inbox VOR dem Vollzug, nicht IMAP hier."""
        conn = self._verbinden()
        try:
            status, _ = conn.append(ordner, "(\\Draft)", None, roh)
            if status != "OK":
                raise KanalFehler(f"imap: APPEND in {ordner!r} fehlgeschlagen")
        finally:
            self._logout(conn)
        return {"abgelegt": True, "ordner": ordner}

    def markiere(self, ordner: str, message_id: str, flag: str,
                 setzen: bool = True) -> dict[str, Any]:
        """Setzt/entfernt ein IMAP-Flag (``\\Seen``/``\\Flagged``) an der Nachricht
        mit dieser Message-ID (UID SEARCH → UID STORE), EINE Verbindung."""
        conn = self._verbinden()
        try:
            uid = self._uid_finden(conn, ordner, message_id)
            op = "+FLAGS" if setzen else "-FLAGS"
            status, _ = conn.uid("store", uid, op, f"({flag})")
            if status != "OK":
                raise KanalFehler("imap: UID STORE fehlgeschlagen")
        finally:
            self._logout(conn)
        return {"markiert": setzen, "flag": flag}

    def verschiebe(self, ordner: str, message_id: str,
                   ziel_ordner: str) -> dict[str, Any]:
        """Verschiebt die Nachricht (UID COPY → ``\\Deleted`` → EXPUNGE) in EINER
        Verbindung. COPY+DELETE+EXPUNGE statt ``UID MOVE`` = maximale Server-Kompat
        (nicht jeder Server kann MOVE); der Ziel-Ordner muss existieren."""
        conn = self._verbinden()
        try:
            uid = self._uid_finden(conn, ordner, message_id)
            status, _ = conn.uid("copy", uid, ziel_ordner)
            if status != "OK":
                raise KanalFehler(f"imap: UID COPY nach {ziel_ordner!r} fehlgeschlagen")
            conn.uid("store", uid, "+FLAGS", "(\\Deleted)")
            conn.expunge()
        finally:
            self._logout(conn)
        return {"verschoben": True, "ziel": ziel_ordner}


class JmapQuelle(KanalQuelle):
    """JMAP-Adapter (RFC 8620/8621) — **VORBEREITETER SLOT (Gesetz 5), noch
    ohne Funktion**.

    JMAP ist der moderne, JSON-basierte Nachfolger von IMAP (Fastmail/Stalwart/
    Cyrus; Thunderbird rollt es aus — Dossier §3) und dockt als zukunftssicherer
    Stecker an DASSELBE ``KanalQuelle``-Interface wie ``ImapQuelle`` an — ein
    Adapter mehr, KEIN Schema-Umbau. Die echte Implementierung (Session-
    Discovery über das ``.well-known/jmap``, ``Email/query`` + ``Email/get``,
    Tokens im K2-Tresor) folgt in einer eigenen Session.

    Bis dahin scheitert jeder Abruf/Versand EHRLICH (fail-closed) statt etwas
    vorzutäuschen — so ist der Slot sichtbar vorhanden, ohne zu lügen. (Die
    Messenger-Stecker ``MatrixSource``/``WebviewKanal`` sind Schiene B/A und
    bewusst NICHT hier — Architektur-Entscheid, Architektur-KI-Parkplatz.)"""

    art = "jmap"

    def __init__(self, host: str, benutzer: str, geheimnis: str,
                 port: int = 443, **_ignored: Any) -> None:
        self.host, self.port = host, port
        self.benutzer, self._geheimnis = benutzer, geheimnis

    def hole_neue(self, ordner: str,
                  zustand: OrdnerZustand) -> tuple[list[dict[str, Any]], OrdnerZustand]:
        raise KanalFehler(
            "jmap: Adapter ist vorbereitet, aber noch nicht implementiert "
            "(Gesetz-5-Slot) — Abruf bewusst fail-closed.")


def sende_mail(host: str, port: int, benutzer: str, geheimnis: str,
               auth: str, von: str, an: Sequence[str] | str, betreff: str,
               text: str, smtp_factory: SmtpFactory | None = None) -> None:
    """SMTP-Versand (STARTTLS; XOAUTH2 oder Passwort). Wird in der App
    AUSSCHLIESSLICH vom freigegebenen HITL-Handler aufgerufen."""
    factory = smtp_factory or (lambda h, p: smtplib.SMTP(h, p, timeout=15))
    msg = email.message.EmailMessage()
    msg["From"] = von
    msg["To"] = an if isinstance(an, str) else ", ".join(an)
    msg["Subject"] = betreff
    msg.set_content(text)
    conn = factory(host, port)
    try:
        try:
            conn.starttls()
        except smtplib.SMTPNotSupportedError:
            pass                          # Test-Fakes/interne Relays ohne TLS
        if auth == "xoauth2":
            conn.docmd("AUTH", "XOAUTH2 " + xoauth2_b64(benutzer, geheimnis))
        else:
            conn.login(benutzer, geheimnis)
        conn.send_message(msg)
    finally:
        try:
            conn.quit()
        except Exception:
            pass
