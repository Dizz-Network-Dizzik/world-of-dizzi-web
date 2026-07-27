"""Text-Extraktion für den Tresor-Volltext-Index — jetzt geteilt in ``appkit.extract``.

Die Extraktions-Naht (DOCX/TXT stdlib · PDF pypdf · Bild-OCR) wurde nach
``packages/appkit/extract.py`` promoted (KA-M7, W-1-Muster), damit sowohl der
Admin-Tresor als auch die Memory-RAG-Ingestion aus EINER Quelle schöpfen. Dieses
Modul re-exportiert die Namen 1:1, damit die Admin-Aufrufer (``tresor.py``:
``extract.extrahiere_text`` / ``extract.verfuegbarkeit``) und die Tests
(``adminapp.extract``) unverändert gültig bleiben — exakt wie
``news/extract.py`` → ``appkit.net_safe``.
"""

from __future__ import annotations

from appkit.extract import (  # noqa: F401  (Re-Export für Rückwärts-Kompatibilität)
    MAX_TEXT,
    _bild_ocr,
    _docx_text,
    _pdf_text,
    extrahiere_text,
    verfuegbarkeit,
)
