"""Tests Dizz Admin v2: Volltext (FTS5) + Extraktion + Dedupe + DocumentSource
(FolderWatch/IMAP-Fake) + Frist-Wächter (HITL) + Integrations-Slots.

Lauf: C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe -m pytest tests/ -q
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from email.message import EmailMessage

from fastapi.testclient import TestClient

from adminapp import extract
from adminapp import main as am

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_wachter=False))

def _docx(text: str) -> bytes:
    """Minimal-gültiges DOCX (ZIP mit word/document.xml) — reicht der stdlib-Extraktion."""
    doc = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()

def _upload_docx(c, name, text, **felder):
    return c.post("/api/dokumente/upload",
                  files={"datei": (name, _docx(text), _DOCX_MIME)},
                  data=felder).json()

# ===================== Extraktion (stdlib) =====================
def test_extract_docx_stdlib():
    text, methode = extract.extrahiere_text(_docx("Kündigung Behörde Quartalsende"), ".docx")
    assert methode == "docx" and "Quartalsende" in text

def test_pdf_ohne_extraktor_graceful(tmp_path):
    # Ohne pypdf/tesseract degradiert die Extraktion ehrlich (kein Crash, kein Block).
    with _client(tmp_path) as c:
        r = c.post("/api/dokumente/upload",
                   files={"datei": ("x.pdf", b"%PDF-1.4  keintext", "application/pdf")},
                   data={}).json()
        assert r["ok"]
        d = c.get("/api/dokumente").json()[0]
        assert d["volltext_methode"] in ("keiner", "pdf:pypdf")

# ===================== Volltext (FTS5) =====================
def test_fts_volltextsuche(tmp_path):
    with _client(tmp_path) as c:
        _upload_docx(c, "kuend.docx", "Kuendigung Mietvertrag zum Quartalsende",
                     titel="Schreiben", typ="Vertrag")
        # Wort steht NUR im Volltext, nicht im Titel ⇒ FTS5 muss es finden.
        res = c.get("/api/dokumente?suche=Quartalsende").json()
        assert len(res) == 1 and res[0]["titel"] == "Schreiben"
        assert res[0]["volltext_methode"] == "docx"
        assert c.get("/api/dokumente?suche=Zebra").json() == []
        # Prefix-Suche (Teilwort) greift ebenfalls.
        assert len(c.get("/api/dokumente?suche=Miet").json()) == 1

def test_soft_delete_entfernt_aus_fts(tmp_path):
    with _client(tmp_path) as c:
        r = _upload_docx(c, "b.docx", "Sonderzahlung Bescheid Finanzamt", titel="S")
        assert len(c.get("/api/dokumente?suche=Sonderzahlung").json()) == 1
        c.delete(f"/api/dokumente/{r['id']}")
        assert c.get("/api/dokumente?suche=Sonderzahlung").json() == []

# ===================== Dedupe (SHA-256) =====================
def test_dedupe_identische_datei(tmp_path):
    with _client(tmp_path) as c:
        r1 = c.post("/api/dokumente/upload",
                    files={"datei": ("a.pdf", b"%PDF-1.4 gleich", "application/pdf")},
                    data={}).json()
        r2 = c.post("/api/dokumente/upload",
                    files={"datei": ("anders.pdf", b"%PDF-1.4 gleich", "application/pdf")},
                    data={}).json()
        assert r2.get("dedupe") is True and r2["id"] == r1["id"]
        assert len(c.get("/api/dokumente").json()) == 1

# ===================== DocumentSource: FolderWatch =====================
def test_folderwatch_ingest(tmp_path):
    with _client(tmp_path) as c:
        assert c.post("/api/dokument-quellen/ordner/scan").status_code == 400   # noch nicht konfiguriert
        ordner = tmp_path / "posteingang"
        ordner.mkdir()
        (ordner / "brief.docx").write_bytes(_docx("Finanzamt Steuerbescheid 2025"))
        (ordner / "ignore.exe").write_bytes(b"nein")           # falscher Typ -> übergangen
        assert c.put("/api/settings", json={"key": "watch_ordner",
                                            "value": str(ordner)}).status_code == 200
        res = c.post("/api/dokument-quellen/ordner/scan").json()
        assert res["neu"] == 1 and res["quelle"] == "folder"
        docs = c.get("/api/dokumente").json()
        assert len(docs) == 1 and docs[0]["quelle"] == "folder"
        assert len(c.get("/api/dokumente?suche=Steuerbescheid").json()) == 1
        assert c.post("/api/dokument-quellen/ordner/scan").json()["neu"] == 0   # Dedupe

# ===================== DocumentSource: IMAP (Fake-Client) =====================
def _mail(subj, fname, daten):
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subj, "a@b.c", "me@x.y"
    m.set_content("siehe Anhang")
    m.add_attachment(daten, maintype="application", subtype="pdf", filename=fname)
    return m.as_bytes()

class _FakeImap:
    def __init__(self, mails):
        self.mails = mails
        self.gesehen = []

    def select(self, ordner):
        return ("OK", [b""])

    def search(self, charset, kriterium):
        return ("OK", [b" ".join(str(i + 1).encode() for i in range(len(self.mails)))])

    def fetch(self, num, spec):
        return ("OK", [(num + b" (RFC822", self.mails[int(num) - 1])])

    def store(self, num, flag, wert):
        self.gesehen.append(num)
        return ("OK", [b""])

    def logout(self):
        return ("BYE", [b""])

def test_imap_fake_ingest(tmp_path):
    from adminapp.tresor_sources import ImapSource, ingest_quelle
    app = am.build_app(data_dir=tmp_path, start_wachter=False)
    dom = app.state.tresor
    mails = [_mail("Rechnung Mai", "rechnung.pdf", b"%PDF-1.4 imapdoc")]
    src = ImapSource("h", "u", "p", client_factory=lambda: _FakeImap(mails))
    with TestClient(app) as c:
        res = ingest_quelle(dom, "dizzi", src)
        assert res["neu"] == 1 and res["quelle"] == "imap"
        docs = c.get("/api/dokumente").json()
        assert len(docs) == 1 and docs[0]["quelle"] == "imap"
        # zweiter Abruf derselben Mail ⇒ Dedupe
        assert ingest_quelle(dom, "dizzi", ImapSource(
            "h", "u", "p", client_factory=lambda: _FakeImap(mails)))["uebersprungen"] == 1

# ===================== Frist-Wächter (HITL über appkit actions) =====================

# ===================== Integrations-Slots (read-only Entwürfe) =====================
def test_buchungsvorschlag_und_elster_slot(tmp_path):
    with _client(tmp_path) as c:
        r = _upload_docx(c, "r.docx",
                         "Rechnung Nr 5 Betrag 119,00 EUR Datum 14.05.2026 Stadtwerke",
                         titel="Stromrechnung", typ="Rechnung")
        bv = c.get(f"/api/dokumente/{r['id']}/buchungsvorschlag").json()
        assert bv["status"] == "entwurf" and bv["ziel_app"] == "finanzen"
        assert bv["betrag"] == 119.0 and bv["datum"] == "2026-05-14"
        el = c.get(f"/api/dokumente/{r['id']}/elster").json()
        assert el["status"] == "vorbereitet"

# ===================== Quellen-Status =====================
def test_quellen_status(tmp_path):
    with _client(tmp_path) as c:
        q = c.get("/api/dokument-quellen").json()
        assert q["extraktoren"]["docx"] is True and q["extraktoren"]["txt"] is True
        assert "imap" in q and "ordner" in q and "scan" in q
        assert q["imap"]["passwort_gesetzt"] is False

# ===================== Frontend v2 (Glocke + Quellen + Volltext + Buchung) =====================
