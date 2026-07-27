"""RG-6 (docs/83 §5.7): die drei kleinen E-Mail-Pilot-Aktionen der Agenten-Regie.

Zwei Ebenen, beide runtime-/netz-frei:
- **IMAP-Substanz** (Fake-IMAP-Verbindung): ``ImapQuelle.entwurf_ablegen`` macht ein
  APPEND (Flag ``\\Draft``), ``markiere`` sucht die UID (Message-ID) und setzt ein Flag,
  ``verschiebe`` kopiert + löscht + expunged; „nicht gefunden" scheitert fail-closed.
- **Handler-/Registry-Verdrahtung** (Fake-Schreib-Quelle über die Aktions-API): die drei
  Aktionen sind level ``lokal`` (⇒ Klasse ``entwurf``), ``mail_senden`` bleibt ``verifiziert``
  (⇒ ``aussenwirkung``); Freigabe vollzieht die IMAP-Op und zieht die lokale Zeile mit.

Plus: der Einzel-Nachricht-Lese-Endpoint ([A-3]) und die Wiederanlauf-Idempotenz der
K4-Schicht (``propose(idem=nachricht_ref+aktion)``, docs/83 §5.7) am echten Aktions-Namen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from appkit.actions import ActionRegistry, propose
from appkit.db import Database
from kommapp.main import build_app
from kommapp.mail import (ImapQuelle, KanalFehler, KanalQuelle, OrdnerZustand,
                          baue_entwurf_bytes)


# --- Ebene 1: die echte IMAP-Substanz gegen eine Fake-Verbindung ------------

class FakeImap:
    """Minimale IMAP4-artige Verbindung: merkt sich die abgesetzten Verben, damit die
    Tests die reale Protokoll-Sequenz (SELECT/APPEND/UID SEARCH/STORE/COPY/EXPUNGE)
    prüfen können — ohne Netz."""

    def __init__(self, such_uid: bytes = b"42") -> None:
        self.selected: list[tuple[str, bool]] = []
        self.appended: list[tuple[str, str, bytes]] = []
        self.stored: list[tuple] = []
        self.copied: list[tuple] = []
        self.expunged = False
        self._such_uid = such_uid

    def login(self, u, p):            # noqa: D401 (Fake)
        return ("OK", [b""])

    def select(self, ordner, readonly=False):
        self.selected.append((ordner, readonly))
        return ("OK", [b"1"])

    def append(self, ordner, flags, dt, msg):
        self.appended.append((ordner, flags, msg))
        return ("OK", [b"[APPENDUID 1 1]"])

    def uid(self, cmd, *args):
        c = cmd.lower()
        if c == "search":
            return ("OK", [self._such_uid])
        if c == "store":
            self.stored.append(args)
            return ("OK", [b""])
        if c == "copy":
            self.copied.append(args)
            return ("OK", [b""])
        return ("OK", [b""])

    def expunge(self):
        self.expunged = True
        return ("OK", [b""])

    def logout(self):
        return ("BYE", [b""])


def _imap(fake: FakeImap) -> ImapQuelle:
    return ImapQuelle("host", "u@x", "pw", imap_factory=lambda h, p: fake)


def test_entwurf_bytes_traegt_thread_kopf():
    roh = baue_entwurf_bytes("me@x", "you@y", "Re: Hallo", "Text", in_reply_to="<a@x>")
    assert b"To: you@y" in roh and b"Subject: Re: Hallo" in roh
    assert b"In-Reply-To: <a@x>" in roh and b"References: <a@x>" in roh


def test_entwurf_ablegen_macht_append_mit_draft_flag():
    fake = FakeImap()
    res = _imap(fake).entwurf_ablegen(baue_entwurf_bytes("me@x", "you@y", "Re: X", "T"),
                                      "Drafts")
    assert res == {"abgelegt": True, "ordner": "Drafts"}
    assert len(fake.appended) == 1
    ordner, flags, _msg = fake.appended[0]
    assert ordner == "Drafts" and "Draft" in flags


def test_markiere_sucht_uid_und_setzt_flag():
    fake = FakeImap(such_uid=b"7")
    res = _imap(fake).markiere("INBOX", "<a@x>", "\\Seen", setzen=True)
    assert res == {"markiert": True, "flag": "\\Seen"}
    assert ("INBOX", False) in fake.selected            # schreibbar geöffnet
    assert fake.stored and fake.stored[0][0] == "7"      # gefundene UID
    assert fake.stored[0][1] == "+FLAGS" and "\\Seen" in fake.stored[0][2]


def test_markiere_entfernt_flag_mit_minus():
    fake = FakeImap()
    _imap(fake).markiere("INBOX", "<a@x>", "\\Seen", setzen=False)
    assert fake.stored[0][1] == "-FLAGS"


def test_verschiebe_copy_delete_expunge():
    fake = FakeImap(such_uid=b"9")
    res = _imap(fake).verschiebe("INBOX", "<a@x>", "Archiv")
    assert res == {"verschoben": True, "ziel": "Archiv"}
    assert fake.copied and fake.copied[0] == ("9", "Archiv")
    assert any(s[1] == "+FLAGS" and "\\Deleted" in s[2] for s in fake.stored)
    assert fake.expunged is True


def test_uid_nicht_gefunden_fail_closed():
    fake = FakeImap(such_uid=b"")                        # SEARCH liefert nichts
    with pytest.raises(KanalFehler):
        _imap(fake).markiere("INBOX", "<weg@x>", "\\Seen")


# --- Ebene 2: Handler + Registry über die Aktions-API -----------------------

class FakeSchreib:
    """Schreibfähige Quelle (statt ImapQuelle) — merkt die Handler-Aufrufe."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def entwurf_ablegen(self, roh, ordner="Drafts"):
        self.calls.append(("entwurf", ordner, roh))
        return {"abgelegt": True, "ordner": ordner}

    def markiere(self, ordner, message_id, flag, setzen=True):
        self.calls.append(("markiere", ordner, message_id, flag, setzen))
        return {"markiert": setzen, "flag": flag}

    def verschiebe(self, ordner, message_id, ziel_ordner):
        self.calls.append(("verschiebe", ordner, message_id, ziel_ordner))
        return {"verschoben": True, "ziel": ziel_ordner}


class FakeRead(KanalQuelle):
    """Liefert beim ersten Sync EINE Nachricht mit stabiler Message-ID (extern_id)."""

    art = "fake"

    def hole_neue(self, ordner, zustand):
        if zustand.uidnext == 0:
            return ([{"kanal_typ": "email", "extern_id": "<msg-1@x>",
                      "von_adresse": "alice@example.org", "an_adressen": "dizzi@local",
                      "betreff": "Frage", "text": "Bitte antworten.",
                      "gesendet_at": "2026-07-19", "thread_schluessel": "<msg-1@x>"}],
                    OrdnerZustand(2, 2))
        return ([], zustand)


def _client(tmp_path):
    fake = FakeSchreib()
    app = build_app(data_dir=tmp_path,
                    quelle_factory=lambda konto, geheimnis: FakeRead(),
                    schreib_quelle_factory=lambda konto, geheimnis: fake)
    return TestClient(app), fake


def _konto(c) -> str:
    return c.post("/api/konten", json={"name": "K", "host": "h", "benutzer": "u@x",
                                       "geheimnis": "g", "smtp_host": "smtp.x"}).json()["id"]


def _eine_nachricht(c) -> tuple[str, str]:
    kid = _konto(c)
    c.post("/api/sync", json={"konto_id": kid})
    nid = c.get("/api/posteingang").json()[0]["id"]
    return nid, f"kommunikation:nachricht:{nid}"


def _freigeben(c, name: str, params: dict) -> dict:
    """propose (lokal) + approve — level 'lokal' gibt standalone frei (harmlos)."""
    vid = c.post("/api/actions/propose",
                 json={"name": name, "source": "user", "params": params}).json()["id"]
    return c.post(f"/api/actions/{vid}/approve").json()


def test_katalog_levels_neu_und_bestand(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        kat = {a["name"]: a["level"] for a in c.get("/api/actions").json()["katalog"]}
        assert kat["email_entwurf_ablegen"] == "lokal"
        assert kat["email_markieren"] == "lokal"
        assert kat["email_verschieben"] == "lokal"
        assert kat["mail_senden"] == "verifiziert"          # Senden unverändert
        assert kat["nachricht_senden"] == "verifiziert"


def test_nachricht_lese_endpoint_a3(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        nid, _ref = _eine_nachricht(c)
        r = c.get(f"/api/nachricht/{nid}")
        assert r.status_code == 200
        n = r.json()
        assert n["betreff"] == "Frage" and n["von_adresse"] == "alice@example.org"
        assert n["text"] == "Bitte antworten." and n["extern_id"] == "<msg-1@x>"
        assert c.get("/api/nachricht/gibtsnicht").status_code == 404


def test_entwurf_ablegen_freigabe_vollzieht_append(tmp_path):
    c, fake = _client(tmp_path)
    with c:
        _nid, ref = _eine_nachricht(c)
        res = _freigeben(c, "email_entwurf_ablegen",
                         {"nachricht_ref": ref, "text": "Gern, hier die Antwort."})
        assert res["status"] == "executed"
        assert res["result"] == {"abgelegt": True, "ordner": "Drafts"}
        assert fake.calls and fake.calls[0][0] == "entwurf"
        # Antwort-Entwurf threaded über die Ursprungs-Message-ID an den Absender:
        roh = fake.calls[0][2]
        assert b"To: alice@example.org" in roh and b"In-Reply-To: <msg-1@x>" in roh


def test_markieren_freigabe_setzt_flag_und_lokale_anzeige(tmp_path):
    c, fake = _client(tmp_path)
    with c:
        nid, ref = _eine_nachricht(c)
        res = _freigeben(c, "email_markieren", {"nachricht_ref": ref, "flag": "gelesen"})
        assert res["status"] == "executed"
        assert fake.calls[0] == ("markiere", "INBOX", "<msg-1@x>", "\\Seen", True)
        # lokale Anzeige zieht bei 'gelesen' sofort mit (Server bleibt Wahrheit):
        assert c.get(f"/api/nachricht/{nid}").json()["gelesen"] == 1


def test_markieren_unbekanntes_flag_fail_closed(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        _nid, ref = _eine_nachricht(c)
        res = _freigeben(c, "email_markieren", {"nachricht_ref": ref, "flag": "quatsch"})
        assert res["status"] == "failed" and "Unbekanntes Flag" in res["error"]


def test_verschieben_freigabe_setzt_ordner(tmp_path):
    c, fake = _client(tmp_path)
    with c:
        nid, ref = _eine_nachricht(c)
        res = _freigeben(c, "email_verschieben",
                         {"nachricht_ref": ref, "ziel_ordner": "Archiv"})
        assert res["status"] == "executed"
        assert fake.calls[0] == ("verschiebe", "INBOX", "<msg-1@x>", "Archiv")
        assert c.get(f"/api/nachricht/{nid}").json()["ordner"] == "Archiv"


def test_verschieben_ohne_ziel_fail_closed(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        _nid, ref = _eine_nachricht(c)
        res = _freigeben(c, "email_verschieben", {"nachricht_ref": ref})
        assert res["status"] == "failed" and "ziel_ordner" in res["error"]


def test_aktion_unbekannte_nachricht_fail_closed(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        _konto(c)
        res = _freigeben(c, "email_entwurf_ablegen",
                         {"nachricht_ref": "kommunikation:nachricht:weg", "text": "x"})
        assert res["status"] == "failed" and "Nachricht unbekannt" in res["error"]


def test_propose_idem_dedup_je_nachricht_ref(tmp_path):
    """Wiederanlauf-Idempotenz (docs/83 §5.7): zwei Vorschläge mit demselben
    ``idem = nachricht_ref + aktion`` ⇒ EIN Inbox-Eintrag (der zweite trifft den ersten).
    Am echten Aktions-Namen, über die appkit-K4-Mechanik (RG-4)."""
    db = Database(str(tmp_path / "actions.db"))
    reg = ActionRegistry()
    reg.register("email_entwurf_ablegen", lambda p: {"ok": True}, level="lokal")
    ref = "kommunikation:nachricht:abc"
    idem = ref + "email_entwurf_ablegen"
    a = propose(db, reg, "dizzi", "email_entwurf_ablegen", {"nachricht_ref": ref},
                source="agent", warum="Antwort nötig", idem=idem)
    b = propose(db, reg, "dizzi", "email_entwurf_ablegen", {"nachricht_ref": ref},
                source="agent", warum="Antwort nötig", idem=idem)
    assert a["id"] == b["id"] and b.get("idem_treffer") is True
