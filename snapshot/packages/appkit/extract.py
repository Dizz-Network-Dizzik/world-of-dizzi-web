"""appkit.extract — die geteilte „Datei → Text"-Naht des Netzes (KA-M7).

Liefert ``(text, methode)``. DOCX/TXT laufen mit der **stdlib** (kein Zusatzpaket).
PDF-Text (``pypdf``) und Bild-OCR sind **optional**: sie aktivieren sich automatisch,
sobald das Werkzeug da ist (Gesetz 5, Nutzer-Entscheid „graceful-optional" 15.06.).
Ist das Werkzeug nicht da, gibt es einen ehrlichen Fallback (``methode='keiner'``)
statt einer Ausnahme — der Aufruf wird NIE blockiert.

**Warum geteilt (De-Fork, W-1-Muster):** vormals nur ``adminapp/extract.py`` (Tresor-
Volltext). Jetzt EINE Quelle in appkit, aus der sowohl der Admin-Tresor als auch die
Memory-RAG-Ingestion schöpfen (``adminapp/extract.py`` re-exportiert diese Namen 1:1,
wie ``news/extract.py`` → ``appkit.net_safe``). Keine neue schwere Dependency:
``pypdf`` ist klein + pure-Python; OCR bevorzugt künftig das lokale VLM
(``appkit.vision`` / ``qwen2.5vl:7b``), Fallback ``pytesseract``.

Reihenfolge der Aktivierung ohne Code-Änderung:
  pip install pypdf            → PDF-Textschicht wird durchsuchbar
  Ollama + qwen2.5vl:7b (VLM)  → Bilder/Scans werden via appkit.vision OCR-t (siehe vision.py)
  pip install pytesseract + Tesseract-Binary (PATH) → OCR-Fallback für Fremd-Setups
"""

from __future__ import annotations

import io
import shutil
import zipfile

# WordprocessingML-Namensraum (DOCX) — Absätze <w:p>, Textläufe <w:t>.
_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_TEXT = 200_000          # gespeicherter Volltext gedeckelt (FTS/RAG bleibt schlank)
# DL-R1-1: Deckel fürs ROH-``word/document.xml`` VOR dem Entpacken. Ein winziges DOCX
# kann per Deflate-„Dekompressions-Bombe" (~1000× Blowup) beim Einzug GB an RAM
# materialisieren (speist Tresor + Memory-RAG). 64 MB deckt jedes reale Personen-
# dokument großzügig ab und begrenzt einen Angriff hart.
MAX_DOCX_XML = 64_000_000


def _docx_text(daten: bytes) -> str:
    """DOCX = ZIP mit word/document.xml — stdlib, kein python-docx nötig.

    A-1: Das Dokument-XML läuft durch den GETEILTEN ``appkit.xml_safe``-Schutz
    (wie camt/OPML) — DTD/Entity-Deklarationen werden abgewiesen, sonst könnte ein
    präpariertes DOCX per interner Entity-Expansion (Billion-Laughs) beim Einzug
    RAM/CPU sprengen.

    DL-R1-1: Zusätzlich wird das ROH-XML **gedeckelt entpackt** (``z.open`` +
    ``read(MAX_DOCX_XML+1)`` statt ``z.read``) — eine Deflate-Dekompressions-Bombe
    (winzig gepackt, riesig entpackt) läuft so NIE voll ins RAM. Die deklarierte
    Entpackgröße ist eine schnelle Vorprüfung, der gedeckelte Read der maßgebliche
    Schutz (die Deklaration kann lügen). Ein unsicheres/kaputtes/überdimensioniertes
    XML ⇒ Ausnahme ⇒ ``extrahiere_text`` fängt sie ab und indexiert eben nichts
    (best-effort, Aufruf bleibt heil — gleiches Verhalten wie der Billion-Laughs-Pfad)."""
    from appkit.xml_safe import sichere_wurzel
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        if z.getinfo("word/document.xml").file_size > MAX_DOCX_XML:
            raise ValueError("DOCX document.xml zu groß (Dekompressions-Bombe?)")
        with z.open("word/document.xml") as f:
            xml = f.read(MAX_DOCX_XML + 1)
    if len(xml) > MAX_DOCX_XML:
        raise ValueError("DOCX document.xml überschreitet den Deckel (Dekompressions-Bombe?)")
    root = sichere_wurzel(xml)
    absaetze = []
    for p in root.iter(f"{_DOCX_NS}p"):
        teile = [t.text or "" for t in p.iter(f"{_DOCX_NS}t")]
        if teile:
            absaetze.append("".join(teile))
    return "\n".join(absaetze)


def _pdf_text(daten: bytes) -> str:
    from pypdf import PdfReader                     # optional (klein, pure-Python)
    reader = PdfReader(io.BytesIO(daten))
    return "\n".join((seite.extract_text() or "") for seite in reader.pages)


def _bild_ocr(daten: bytes) -> tuple[str, str]:
    """Bild → ``(text, methode)``. OCR-Kette: erst lokales VLM (``appkit.vision``,
    wenn Ollama + Modell erreichbar), dann ``pytesseract`` (falls installiert),
    sonst ``("", "keiner")``. Wirft NIE (jeder Zweig fängt ab)."""
    try:                                             # 1) lokales VLM (bevorzugt, C3)
        from appkit import vision
        t = vision.ocr_bild(daten)
        if t and t.strip():
            return t.strip(), "ocr:vlm"
    except Exception:
        pass
    try:                                             # 2) pytesseract-Fallback (Fremd-Setups)
        import pytesseract                          # optional (+ tesseract-Binary)
        from PIL import Image
        t = pytesseract.image_to_string(
            Image.open(io.BytesIO(daten)), lang="deu+eng").strip()
        if t:
            return t, "ocr:tesseract"
    except Exception:
        pass
    return "", "keiner"                              # weder VLM noch tesseract lieferten Text


def extrahiere_text(daten: bytes, ext: str, max_len: int = MAX_TEXT) -> tuple[str, str]:
    """``(text, methode)``. methode ∈ docx|txt|pdf:pypdf|ocr:vlm|ocr:tesseract|keiner|fehler.
    Wirft NIE — jede Ausnahme endet in einem ehrlichen Fallback."""
    ext = (ext or "").lower()
    try:
        if ext == ".docx":
            return _docx_text(daten)[:max_len].strip(), "docx"
        if ext in (".txt", ".md"):
            return daten.decode("utf-8", "ignore")[:max_len].strip(), "txt"
        if ext == ".pdf":
            try:
                t = _pdf_text(daten).strip()
                return (t[:max_len], "pdf:pypdf") if t else ("", "keiner")
            except Exception:
                return "", "keiner"        # pypdf fehlt o. PDF ohne Textschicht
        if ext in (".jpg", ".jpeg", ".png"):
            text, methode = _bild_ocr(daten)
            return (text[:max_len].strip(), methode) if text else ("", methode)
    except Exception:
        return "", "fehler"
    return "", "keiner"


def verfuegbarkeit() -> dict[str, object]:
    """Welche Extraktoren sind scharf? (Diagnose fürs Frontend.)

    ``ocr`` ist dreiwertig: ``"vlm"`` (lokales VLM erreichbar, bevorzugt) ·
    ``"tesseract"`` (pytesseract + Binary da) · ``False`` (nur Titel/Metadaten).
    Die VLM-Prüfung ist ein kurzer, gekapselter Ollama-Ping (``vision.verfuegbar``,
    wirft nie); ohne Ollama fällt sie auf tesseract bzw. False zurück."""
    def hat(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False
    try:
        from appkit import vision
        vlm = vision.verfuegbar()
    except Exception:
        vlm = False
    ocr: object
    if vlm:
        ocr = "vlm"
    elif hat("pytesseract") and bool(shutil.which("tesseract")):
        ocr = "tesseract"
    else:
        ocr = False
    return {"docx": True, "txt": True, "pdf": hat("pypdf"), "ocr": ocr}
