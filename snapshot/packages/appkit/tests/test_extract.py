"""appkit.extract — die geteilte „Datei → Text"-Naht (KA-M7 C1).

Deckt die stdlib-Pfade (DOCX/TXT/MD), den pypdf-PDF-Pfad (echte Textschicht),
die ehrlichen Fallbacks (unbekannte Endung / kaputtes PDF / XXE-DOCX ⇒ nie eine
Ausnahme nach außen) und die verfuegbarkeit()-Diagnose ab.
"""

from __future__ import annotations

import io
import zipfile

from appkit.extract import MAX_TEXT, extrahiere_text, verfuegbarkeit


def _docx(text: str) -> bytes:
    """Minimal-gültiges DOCX (ZIP mit word/document.xml) — reicht der stdlib-Extraktion."""
    doc = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _mini_pdf(text: str) -> bytes:
    """Minimal-gültiges 1-Seiten-PDF mit echter Textzeile + KORREKTER xref-Tabelle
    (Byte-Offsets live berechnet), damit pypdf eine echte Textschicht extrahiert."""
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


def test_docx_stdlib():
    text, methode = extrahiere_text(_docx("Kündigung Behörde Quartalsende"), ".docx")
    assert methode == "docx"
    assert "Quartalsende" in text


def test_txt_und_md():
    text, methode = extrahiere_text("Zeile eins\nZeile zwei".encode("utf-8"), ".txt")
    assert methode == "txt" and "Zeile zwei" in text
    # .md läuft denselben Pfad (der Vault IST Markdown)
    text2, methode2 = extrahiere_text(b"# Titel\nInhalt", ".md")
    assert methode2 == "txt" and "Inhalt" in text2


def test_pdf_pypdf_echte_textschicht():
    text, methode = extrahiere_text(_mini_pdf("Rechnung Quartalsende 2026"), ".pdf")
    assert methode == "pdf:pypdf"
    assert "Rechnung" in text and "Quartalsende" in text


def test_pdf_ohne_textschicht_ehrlich_keiner():
    # Kaputtes/text-loses „PDF" ⇒ kein Crash, ehrlicher Fallback.
    text, methode = extrahiere_text(b"%PDF-1.4 kein echter Inhalt", ".pdf")
    assert (text, methode) == ("", "keiner")


def test_unbekannte_endung_keiner():
    assert extrahiere_text(b"beliebig", ".xyz") == ("", "keiner")


def test_leere_bytes_kein_crash():
    # Wirft NIE — jede Endung mit leeren Bytes endet in einem Fallback.
    for ext in (".pdf", ".docx", ".txt", ".png"):
        text, methode = extrahiere_text(b"", ext)
        assert methode in ("keiner", "fehler", "txt")   # txt(leer)="" ist ok


def test_docx_xxe_bombe_graceful():
    # Präpariertes DOCX (Billion-Laughs im document.xml) ⇒ appkit.xml_safe wirft,
    # extrahiere_text fängt ab: ("", "fehler"), NIE eine Ausnahme nach außen.
    bombe = ('<?xml version="1.0"?>'
             '<!DOCTYPE lolz [<!ENTITY a "AAAAAAAAAA">'
             '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
             '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
             '<w:body><w:p><w:r><w:t>&b;</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", bombe)
    text, methode = extrahiere_text(buf.getvalue(), ".docx")
    assert (text, methode) == ("", "fehler")


def test_docx_deflate_bombe_gedeckelt(monkeypatch):
    # DL-R1-1: Präparierte Deflate-„Dekompressions-Bombe" — winzig gepackt, riesig
    # entpackt. Der gedeckelte Read greift VOR der vollen Entpackung ⇒ ("", "fehler"),
    # kein RAM-Spike (das Riesen-XML wird nie ganz materialisiert).
    from appkit import extract
    monkeypatch.setattr(extract, "MAX_DOCX_XML", 50_000)
    riesig = ('<?xml version="1.0"?>'
              '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:body><w:p><w:r><w:t>' + "A" * 2_000_000 + '</w:t></w:r></w:p></w:body></w:document>'
              ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", riesig)
    gepackt = buf.getvalue()
    assert len(gepackt) < 50_000                      # echte Bombe: klein gepackt …
    text, methode = extract.extrahiere_text(gepackt, ".docx")
    assert (text, methode) == ("", "fehler")          # … aber gedeckelt ⇒ graceful


def test_docx_knapp_unter_deckel_ok(monkeypatch):
    # Regression: der Deckel bricht ein normales DOCX knapp unter der Grenze NICHT.
    from appkit import extract
    monkeypatch.setattr(extract, "MAX_DOCX_XML", 50_000)
    text, methode = extract.extrahiere_text(_docx("Quartalsende unter Deckel"), ".docx")
    assert methode == "docx" and "Quartalsende" in text


def test_max_len_deckel():
    gross = ("x" * (MAX_TEXT + 5000)).encode("utf-8")
    text, methode = extrahiere_text(gross, ".txt", max_len=100)
    assert methode == "txt" and len(text) <= 100


def test_verfuegbarkeit_struktur():
    verf = verfuegbarkeit()
    assert set(verf.keys()) == {"docx", "txt", "pdf", "ocr"}
    assert verf["docx"] is True and verf["txt"] is True
    assert isinstance(verf["pdf"], bool)
    # ocr ist dreiwertig: "vlm" (VLM erreichbar) | "tesseract" | False
    assert verf["ocr"] in ("vlm", "tesseract", False)


def test_bild_ocr_vlm_bevorzugt(monkeypatch):
    # Bild-OCR nimmt zuerst das lokale VLM (appkit.vision) — methode "ocr:vlm".
    from appkit import vision
    monkeypatch.setattr(vision, "ocr_bild", lambda daten: "VLM erkannter Text")
    text, methode = extrahiere_text(b"\x89PNG-nicht-echt", ".png")
    assert methode == "ocr:vlm" and "VLM erkannter" in text


def test_bild_ocr_fallback_keiner_ohne_vlm(monkeypatch):
    # VLM weg (None) + ungültige Bild-Bytes ⇒ auch ein evtl. installiertes
    # pytesseract wirft (PIL kann sie nicht öffnen) ⇒ ehrlicher Fallback "keiner".
    from appkit import vision
    monkeypatch.setattr(vision, "ocr_bild", lambda daten: None)
    assert extrahiere_text(b"\x89PNG-nicht-echt", ".png") == ("", "keiner")
