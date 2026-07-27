"""Mem-Live-Import aus lokalem Ordner (Mem.ai-Markdown-Export / beliebiger Vault):
gültiger Import inkl. Ordner-Hierarchie, Path-Traversal-Schutz, Duplikat-Dedupe,
Mem.ai-Frontmatter-Mapping, Ergebnis-Format."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from archivapp import main as am
from archivapp.vault import MarkdownVault


def _docx(text: str) -> bytes:
    """Minimal-gültiges DOCX (ZIP mit word/document.xml)."""
    doc = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _mini_pdf(text: str) -> bytes:
    """Minimal-gültiges 1-Seiten-PDF mit echter Textzeile (korrekte xref-Offsets)."""
    stream = b"BT /F1 24 Tf 72 720 Td (" + text.encode("latin-1", "replace") + b") Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += (b"trailer\n<< /Size " + str(len(objs) + 1).encode() +
            b" /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF")
    return bytes(out)


def _client(tmp_path):
    return TestClient(am.build_app(data_dir=tmp_path, start_import_timer=False))


def _schreib(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _export(tmp_path) -> Path:
    """Ein Quell-Ordner UNTERHALB des Daten-Roots (= erlaubte Wurzel)."""
    d = Path(tmp_path) / "export"
    _schreib(d / "alpha.md", "---\ntitel: Alpha\n---\n\nInhalt alpha zebra.")
    _schreib(d / "Projekte" / "beta.md", "---\ntitel: Beta\n---\n\nInhalt beta im Unterordner.")
    return d


def test_import_ordner_gueltig_mit_hierarchie(tmp_path):
    with _client(tmp_path) as c:
        d = _export(tmp_path)
        r = c.post("/api/import/ordner", json={"pfad": str(d), "rekursiv": True}).json()
        assert r["ok"] and r["importiert"] == 2 and r["uebersprungen"] == 0
        assert r["fehler"] == []
        # Unterverzeichnis wurde zur Ordner-Hierarchie
        namen = {o["name"] for o in c.get("/api/ordner").json()}
        assert "Projekte" in namen
        # Inhalt durchsuchbar (FTS)
        assert c.get("/api/suche?q=zebra").json()[0]["titel"] == "Alpha"


def test_pfad_traversal_abgelehnt(tmp_path):
    with _client(tmp_path) as c:
        # Eltern des Daten-Roots liegt AUSSERHALB der Freigabe ⇒ 403
        draussen = str(Path(tmp_path).parent)
        assert c.post("/api/import/ordner", json={"pfad": draussen}).status_code == 403
        assert c.post("/api/import/ordner",
                      json={"pfad": "C:\\Windows\\System32"}).status_code == 403


def test_duplikat_uebersprungen(tmp_path):
    with _client(tmp_path) as c:
        d = _export(tmp_path)
        erst = c.post("/api/import/ordner", json={"pfad": str(d)}).json()
        assert erst["importiert"] == 2
        # Zweiter Lauf: identischer Inhalt (SHA-256) ⇒ alles übersprungen
        zwei = c.post("/api/import/ordner", json={"pfad": str(d)}).json()
        assert zwei["importiert"] == 0 and zwei["uebersprungen"] == 2


def test_mem_ai_frontmatter_gemappt(tmp_path):
    with _client(tmp_path) as c:
        d = Path(tmp_path) / "mem"
        d.mkdir(parents=True, exist_ok=True)
        # MIT UTF-8-BOM schreiben (wie echte Mem.ai-/Windows-Exporte) — muss trotzdem parsen.
        (d / "note.md").write_text(
            "---\ntitel: Mem-Notiz\ncreated: 2025-09-01T10:00:00\n"
            "tags: [recherche, idee]\nsource: https://mem.ai/x\n---\n\nMem-Inhalt.",
            encoding="utf-8-sig")
        r = c.post("/api/import/ordner", json={"pfad": str(d)}).json()
        assert r["importiert"] == 1
        nid = c.get("/api/notizen").json()[0]["id"]
        det = c.get("/api/notizen/" + nid).json()
        assert det["created_at"] == "2025-09-01T10:00:00"          # created → created_at
        assert {l["name"] for l in det["labels"]} >= {"recherche", "idee"}  # tags → labels
        assert det["quelle"] == "https://mem.ai/x"                 # source → quelle
        assert det["import_quelle"] == "mem.ai"
        # Frontmatter der Vault-Datei trägt quelle + import_quelle
        v = MarkdownVault(Path(tmp_path) / "apps" / "memory" / "vault")
        fms = [fm for _, fm, _ in v.iter_dateien("dizzi")]
        assert any(fm.get("import_quelle") == "mem.ai" and fm.get("quelle") for fm in fms)


def test_ergebnis_format_und_leer(tmp_path):
    with _client(tmp_path) as c:
        ordner = Path(tmp_path) / "misch"
        ordner.mkdir(parents=True)
        # .txt wird jetzt IMPORTIERT (KA-M7 C2, war früher ignoriert): appkit.extract ⇒ methode "txt".
        (ordner / "notiz.txt").write_text("kein markdown aber echter Text", encoding="utf-8")
        r = c.post("/api/import/ordner", json={"pfad": str(ordner)}).json()
        assert set(r) >= {"ok", "importiert", "uebersprungen",
                          "uebersprungen_ohne_text", "fehler"}
        assert r["importiert"] == 1 and isinstance(r["fehler"], list)
        # Datei statt Ordner ⇒ 400
        f = Path(tmp_path) / "datei.md"
        f.write_text("x", encoding="utf-8")
        assert c.post("/api/import/ordner", json={"pfad": str(f)}).status_code == 400


def test_extrahierte_dateien_importiert(tmp_path):
    """KA-M7 C2: .txt/.pdf/.docx werden via appkit.extract zu Notizen + sind
    volltext-durchsuchbar (nicht nur .md). Ollama-frei (FTS)."""
    with _client(tmp_path) as c:
        d = Path(tmp_path) / "quellen"
        d.mkdir(parents=True)
        (d / "a.txt").write_text("Notiztext Wolkenkratzer", encoding="utf-8")
        (d / "b.pdf").write_bytes(_mini_pdf("Rechnung Nilpferd 2026"))
        (d / "c.docx").write_bytes(_docx("Protokoll Zebrastreifen"))
        r = c.post("/api/import/ordner", json={"pfad": str(d), "rekursiv": True}).json()
        assert r["ok"] and r["importiert"] == 3 and r["uebersprungen_ohne_text"] == 0
        for wort, quelle in (("Wolkenkratzer", "a.txt"), ("Nilpferd", "b.pdf"),
                             ("Zebrastreifen", "c.docx")):
            treffer = c.get("/api/suche", params={"q": wort}).json()
            assert treffer and treffer[0]["titel"] == quelle, f"{wort} nicht gefunden"


def test_leere_extraktion_uebersprungen(tmp_path):
    """Dateien ohne extrahierbaren Text ⇒ übersprungen + gezählt, NIE 0-Chunk-Notiz."""
    with _client(tmp_path) as c:
        d = Path(tmp_path) / "leer"
        d.mkdir(parents=True)
        (d / "leer.txt").write_text("   ", encoding="utf-8")            # nur Whitespace
        (d / "kaputt.pdf").write_bytes(b"%PDF-1.4 keine Textschicht")   # pypdf ⇒ keiner
        r = c.post("/api/import/ordner", json={"pfad": str(d)}).json()
        assert r["importiert"] == 0 and r["uebersprungen_ohne_text"] == 2
        assert c.get("/api/notizen").json() == []


def test_exe_bleibt_ignoriert(tmp_path):
    """Nicht gelistete Endungen (.exe) werden gar nicht erst aufgenommen."""
    with _client(tmp_path) as c:
        d = Path(tmp_path) / "mit_exe"
        d.mkdir(parents=True)
        (d / "tool.exe").write_bytes(b"MZ\x90\x00 binaermuell")
        (d / "echt.md").write_text("---\ntitel: Echt\n---\n\nInhalt hier.", encoding="utf-8")
        r = c.post("/api/import/ordner", json={"pfad": str(d)}).json()
        assert r["importiert"] == 1   # nur die .md; .exe ignoriert
