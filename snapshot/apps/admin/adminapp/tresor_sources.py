"""DocumentSource-Adapter (Gesetz 5) — EIN austauschbares Einzug-Interface.

Jede Quelle liefert ``IncomingDoc``-Objekte; ``ingest_quelle`` reicht sie an den
gemeinsamen Vault-Kern ``Domain.speichere_dokument`` — dadurch gelten SHA-256-
Dedupe, Volltext-Index und die Upload-Härtung (Typ-Whitelist, Größe, Pfad-
Traversal) EINHEITLICH, egal woher das Dokument kommt.

Quellen v2:
- ``FolderWatchSource`` — lokaler Ordner (Poll, kein ``watchdog`` nötig).
- ``ImapSource``       — E-Mail-Postfach (stdlib ``imaplib``; Admin = Gmail,
                         App-Passwort im Tresor). Manueller Abruf; Auto AUS.
- ``MobileScanSource`` — Slot/Stub (Mobile-Scan kommt über den Upload-Endpoint
                         als Share-Ziel; hier dokumentiert, nicht aktiv).

Test-Haken: ``ImapSource(..., client_factory=…)`` injiziert einen Fake-IMAP-
Client (kein echtes Postfach im Test nötig).
"""

from __future__ import annotations

import email
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

# dieselbe Whitelist wie der Upload (Single Source of Truth in domain.py).
from .tresor import ALLOWED_EXT


@dataclass
class IncomingDoc:
    name: str
    daten: bytes
    typ: str = "Sonstiges"
    notiz: str = ""
    tags: list[str] = field(default_factory=list)


def _erlaubt(name: str) -> bool:
    return Path(name).suffix.lower() in ALLOWED_EXT


class FolderWatchSource:
    """Lokaler Ordner als Posteingang. Liest erlaubte Dateien (Dedupe macht der
    Vault-Kern über SHA-256 — erneutes Scannen erzeugt keine Duplikate)."""

    quelle = "folder"

    def __init__(self, ordner: str, max_dateien: int = 200) -> None:
        self.ordner = Path(ordner)
        self.max_dateien = max_dateien

    def fetch(self) -> list[IncomingDoc]:
        if not self.ordner.is_dir():
            return []
        out: list[IncomingDoc] = []
        for p in sorted(self.ordner.iterdir()):
            if not p.is_file() or not _erlaubt(p.name):
                continue
            try:
                out.append(IncomingDoc(name=p.name, daten=p.read_bytes(),
                                       notiz=f"Aus Ordner: {self.ordner.name}"))
            except Exception:
                continue
            if len(out) >= self.max_dateien:
                break
        return out


class ImapSource:
    """E-Mail-Postfach (IMAP) als Posteingang — stdlib ``imaplib``.

    Holt UNGELESENE Nachrichten und zieht deren Anhänge mit erlaubter Endung.
    Markiert geholte Mails als gelesen (idempotent zusammen mit dem SHA-Dedupe).
    Gmail: IMAP aktivieren + **App-Passwort** (2FA) verwenden — das normale
    Passwort wird von Google für IMAP-Login abgelehnt.
    """

    quelle = "imap"

    def __init__(self, host: str, user: str, passwort: str, ordner: str = "INBOX",
                 port: int = 993, ssl: bool = True, max_mails: int = 50,
                 mark_seen: bool = True,
                 client_factory: Callable[[], Any] | None = None) -> None:
        self.host, self.user, self.passwort = host, user, passwort
        self.ordner, self.port, self.ssl = ordner, port, ssl
        self.max_mails, self.mark_seen = max_mails, mark_seen
        self._client_factory = client_factory

    def _connect(self) -> Any:
        import imaplib
        M = (imaplib.IMAP4_SSL(self.host, self.port) if self.ssl
             else imaplib.IMAP4(self.host, self.port))
        M.login(self.user, self.passwort)
        return M

    def fetch(self) -> list[IncomingDoc]:
        client = (self._client_factory or self._connect)()
        out: list[IncomingDoc] = []
        try:
            client.select(self.ordner)
            _typ, data = client.search(None, "UNSEEN")
            roh = data[0] if data else b""
            ids = (roh.split() if roh else [])[: self.max_mails]
            for num in ids:
                _t, msgdata = client.fetch(num, "(RFC822)")
                raw = msgdata[0][1] if msgdata and msgdata[0] else None
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                betreff = str(msg.get("Subject", "")).strip()
                for part in msg.walk():
                    fn = part.get_filename()
                    if not fn or not _erlaubt(fn):
                        continue
                    nutzlast = part.get_payload(decode=True)
                    if not nutzlast:
                        continue
                    out.append(IncomingDoc(name=fn, daten=nutzlast,
                                           notiz=f"E-Mail: {betreff}" if betreff else "E-Mail"))
                if self.mark_seen:
                    try:
                        client.store(num, "+FLAGS", "\\Seen")
                    except Exception:
                        pass
        finally:
            try:
                client.logout()
            except Exception:
                pass
        return out


class MobileScanSource:
    """Slot/Stub: Mobile-Scan läuft über den vorhandenen Upload-Endpoint
    (PWA-/Share-Ziel ‚An Dizz Admin senden'). Als eigene Quelle vorbereitet,
    liefert hier (noch) nichts — Aktivierung = Frontend-/Share-Anbindung."""

    quelle = "scan"

    def fetch(self) -> list[IncomingDoc]:
        return []


def ingest_quelle(domain: Any, user_id: str, source: Any) -> dict[str, int | str]:
    """Zieht alle Dokumente einer Quelle in den Vault. Fehler je Dokument werden
    gezählt, stoppen aber nie den Gesamtlauf. ``dedupe`` ⇒ übersprungen."""
    neu = uebersprungen = fehler = 0
    for doc in source.fetch():
        try:
            res = domain.speichere_dokument(
                user_id, doc.daten, doc.name, titel="", typ=doc.typ,
                tags=doc.tags, notiz=doc.notiz, quelle=getattr(source, "quelle", "extern"))
            if res.get("dedupe"):
                uebersprungen += 1
            else:
                neu += 1
        except Exception:
            fehler += 1
    return {"neu": neu, "uebersprungen": uebersprungen, "fehler": fehler,
            "quelle": getattr(source, "quelle", "extern")}
