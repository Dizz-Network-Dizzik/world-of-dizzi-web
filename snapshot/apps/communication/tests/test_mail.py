"""E-Mail-Fundament: XOAUTH2, Sync-Zustandsmaschine, Parsing/Threading,
ImapQuelle gegen Fake-Server, SMTP-Versand gegen Fake."""

from __future__ import annotations

import base64
import smtplib
from email.message import EmailMessage

import pytest

from kommapp.mail import (ImapQuelle, JmapQuelle, KanalFehler, OrdnerZustand,
                          html_zu_text, nachricht_aus_bytes, sende_mail,
                          sync_plan, xoauth2_b64, xoauth2_string)


def roh_mail(betreff: str, mid: str = "<m1@x>", refs: str | None = None,
             von: str = "alice@example.org", text: str = "Hallo") -> bytes:
    msg = EmailMessage()
    msg["From"] = von
    msg["To"] = "dizzi@local"
    msg["Subject"] = betreff
    msg["Message-ID"] = mid
    if refs:
        msg["References"] = refs
    msg["Date"] = "Thu, 12 Jun 2026 10:00:00 +0200"
    msg.set_content(text)
    return msg.as_bytes()


def test_xoauth2_format():
    s = xoauth2_string("u@example.org", "tok-123")
    assert s == "user=u@example.org\x01auth=Bearer tok-123\x01\x01"
    assert base64.b64decode(xoauth2_b64("u@example.org", "tok-123")) == s.encode()


def test_sync_plan():
    # nie synchronisiert ⇒ Vollabruf
    assert sync_plan(OrdnerZustand(), 3, 10) == ("voll", (1, 9))
    # bekannter Stand ⇒ nur das Neue
    assert sync_plan(OrdnerZustand(3, 7), 3, 10) == ("inkrementell", (7, 9))
    # nichts Neues
    assert sync_plan(OrdnerZustand(3, 10), 3, 10) == ("nichts", None)
    # UIDVALIDITY-Wechsel ⇒ Voll-Resync (Server hat UIDs neu vergeben)
    assert sync_plan(OrdnerZustand(3, 10), 4, 6) == ("voll", (1, 5))
    # leerer Ordner nach Wechsel
    assert sync_plan(OrdnerZustand(3, 10), 4, 1) == ("voll", None)


def test_sync_plan_deckel():
    """Live-Lehre 12.06.: volles Gmail-Postfach darf den Erstsync nicht
    ersticken — nur die neuesten 50; Inkremente in 200er-Häppchen."""
    assert sync_plan(OrdnerZustand(), 3, 10_001) == ("voll", (9951, 10_000))
    assert sync_plan(OrdnerZustand(3, 1), 3, 1001) == ("inkrementell", (1, 200))


def test_inkrement_batches_verlustfrei(monkeypatch):
    """Gedeckelte Batches setzen beim nächsten Lauf nahtlos fort."""
    import kommapp.mail as m
    monkeypatch.setattr(m, "BATCH_MAX", 2)
    server = FakeImap({u: roh_mail(f"Mail {u}", mid=f"<{u}@x>")
                       for u in range(1, 6)})
    q = ImapQuelle("imap.example.org", "d@example.org", "pw",
                   imap_factory=lambda h, p: server)
    z = OrdnerZustand(3, 1)              # bekannter Stand, 5 neue warten
    betreffs = []
    for _ in range(4):
        nachrichten, z = q.hole_neue("INBOX", z)
        betreffs += [n["betreff"] for n in nachrichten]
    assert betreffs == [f"Mail {u}" for u in range(1, 6)]   # alle, nichts doppelt
    assert q.hole_neue("INBOX", z)[0] == []                  # und dann Ruhe


def test_parsing_und_threading():
    n = nachricht_aus_bytes(roh_mail("Hällo Ümlaut", mid="<a@x>"))
    assert n["betreff"] == "Hällo Ümlaut"
    assert n["extern_id"] == "<a@x>" and n["thread_schluessel"] == "<a@x>"
    assert "Hallo" in n["text"] and n["kanal_typ"] == "email"

    antwort = nachricht_aus_bytes(
        roh_mail("Re: Hällo", mid="<b@x>", refs="<a@x> <zwischen@x>"))
    assert antwort["thread_schluessel"] == "<a@x>"   # Wurzel der Kette


class FakeImap:
    """Minimaler IMAP4-Ersatz: genau die Schnittstelle, die ImapQuelle nutzt."""

    def __init__(self, mails: dict[int, bytes], uidvalidity: int = 3):
        self.mails, self.uidvalidity = mails, uidvalidity
        self.auth_aufrufe: list = []

    def login(self, u, p):
        self.auth_aufrufe.append(("login", u, p))
        return ("OK", [b""])

    def authenticate(self, mech, fn):
        self.auth_aufrufe.append((mech, fn(b"")))
        return ("OK", [b""])

    def select(self, ordner, readonly=False):
        return ("OK", [b"1"])

    def response(self, name):
        if name == "UIDVALIDITY":
            return (name, [str(self.uidvalidity).encode()])
        nxt = max(self.mails) + 1 if self.mails else 1
        return (name, [str(nxt).encode()])

    def uid(self, cmd, bereich, was):
        a, b = (int(x) for x in bereich.split(":"))
        out = []
        for u in range(a, b + 1):
            if u in self.mails:
                out.append((f"{u} (RFC822)".encode(), self.mails[u]))
        return ("OK", out)

    def logout(self):
        return ("BYE", [b""])


def test_imap_quelle_inkrementell():
    server = FakeImap({1: roh_mail("Erste", mid="<1@x>"),
                       2: roh_mail("Zweite", mid="<2@x>")})
    q = ImapQuelle("imap.example.org", "dizzi@example.org", "pw",
                   imap_factory=lambda h, p: server)
    nachrichten, z1 = q.hole_neue("INBOX", OrdnerZustand())
    assert [n["betreff"] for n in nachrichten] == ["Erste", "Zweite"]
    assert (z1.uidvalidity, z1.uidnext) == (3, 3)
    # zweiter Lauf: nichts Neues
    assert q.hole_neue("INBOX", z1)[0] == []
    # neue Mail trifft ein ⇒ nur sie wird geholt
    server.mails[3] = roh_mail("Dritte", mid="<3@x>")
    nachrichten, z2 = q.hole_neue("INBOX", z1)
    assert [n["betreff"] for n in nachrichten] == ["Dritte"]
    assert z2.uidnext == 4
    assert server.auth_aufrufe[0][0] == "login"


def test_imap_quelle_xoauth2():
    server = FakeImap({})
    q = ImapQuelle("imap.gmail.com", "nutzer@example.com", "ya29.token",
                   auth="xoauth2", imap_factory=lambda h, p: server)
    q.hole_neue("INBOX", OrdnerZustand())
    mech, initial = server.auth_aufrufe[0]
    assert mech == "XOAUTH2"
    assert initial == xoauth2_string("nutzer@example.com", "ya29.token").encode()


class FakeSmtp:
    def __init__(self):
        self.gesendet, self.auth = [], None

    def starttls(self):
        raise smtplib.SMTPNotSupportedError()

    def login(self, u, p):
        self.auth = ("login", u, p)

    def docmd(self, cmd, arg):
        self.auth = (cmd, arg)

    def send_message(self, msg):
        self.gesendet.append(msg)

    def quit(self):
        pass


def test_html_zu_text_extraktor():
    """HTML wird lesbar: script/style/head raus, Entities/&nbsp; aufgelöst,
    Block-Elemente trennen Zeilen."""
    h = ("<html><head><style>.x{color:red}</style><title>T</title></head><body>"
         "<p>Hallo <b>Welt</b></p><script>alert(1)</script>"
         "<div>Zeile&nbsp;zwei &amp; mehr</div></body></html>")
    t = html_zu_text(h)
    assert "Hallo Welt" in t and "Zeile zwei & mehr" in t
    assert "alert" not in t and "color:red" not in t      # script/style verworfen
    assert "<" not in t and ">" not in t                  # kein rohes Markup


def test_parsing_html_only_mail_wird_klartext():
    """Eine HTML-only-Mail landet als LESBARER Text im Schema (nicht als rohes
    Markup) — sauber für Anzeige, Suche und KI-Triage."""
    msg = EmailMessage()
    msg["From"] = "alice@example.org"
    msg["To"] = "dizzi@local"
    msg["Subject"] = "HTML-Mail"
    msg["Message-ID"] = "<h@x>"
    msg["Date"] = "Thu, 12 Jun 2026 10:00:00 +0200"
    msg.set_content("<p>Bitte <b>bis Freitag</b> zahlen.</p>", subtype="html")
    n = nachricht_aus_bytes(msg.as_bytes())
    assert n["text"] == "Bitte bis Freitag zahlen."
    assert "<" not in n["text"]


def test_jmap_quelle_ist_vorbereiteter_slot():
    """Gesetz 5: der JMAP-Adapter ist vorhanden, aber funktionslos — Abruf und
    Versand scheitern EHRLICH (fail-closed), statt etwas vorzutäuschen."""
    q = JmapQuelle("api.jmap.example", "u@example.org", "tok")
    assert q.art == "jmap"
    with pytest.raises(KanalFehler):
        q.hole_neue("INBOX", OrdnerZustand())
    with pytest.raises(KanalFehler):       # senden aus dem Interface (nicht implementiert)
        q.senden("ziel@example.org", "Betreff", "Text")


def test_sende_mail():
    s = FakeSmtp()
    sende_mail("smtp.example.org", 587, "dizzi@example.org", "pw", "passwort",
               von="dizzi@example.org", an="ziel@example.org",
               betreff="Test", text="Inhalt", smtp_factory=lambda h, p: s)
    assert s.auth == ("login", "dizzi@example.org", "pw")
    assert s.gesendet[0]["Subject"] == "Test"

    s2 = FakeSmtp()
    sende_mail("smtp.gmail.com", 587, "nutzer@example.com", "tok", "xoauth2",
               von="nutzer@example.com", an="ziel@example.org",
               betreff="T", text="I", smtp_factory=lambda h, p: s2)
    assert s2.auth[0] == "AUTH" and s2.auth[1].startswith("XOAUTH2 ")
