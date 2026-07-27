"""Dizz-Creating-Engine — Kern-Architektur (R1.7, Architektur-KI; Basis: Recherche R-A).

Zwei Instanzen, zwei stabile Schnittstellen (schwer nachrüstbar ⇒ jetzt fixiert):

- **Bau-Instanz** (``generator.py``): erzeugt Bilder/Videos. Primär lokal über
  **ComfyUI headless** (HTTP :8188; Flux/SDXL Bild, Wan 2.2 Video — Apache-2.0,
  verkaufs-sicher auf RTX 5070 Ti/16 GB); Cloud (fal.ai) als opt-in-Adapter.
- **Schneid-Instanz** (``editor.py``): analysiert + schneidet. ffmpeg als
  Fundament (probe/cut/silence-detect), darauf später MoviePy/PySceneDetect/
  faster-whisper/Vision-LLM (R-A §B).

Verbindendes Element: die **Job-Queue** (``jobs.py``) — die GPU ist seriell,
also läuft JEDE Erzeugung/Analyse als Job mit Status/Fortschritt/Ergebnis.
Die spätere App (R2.x) hängt die Queue an den App-Vertrag: Jobs als
HITL-Aktionen (K4), Status über /api/summary-KPIs, Assets in die DAM.

Alle Adapter sind austauschbar (Protokolle) — kein Anbieter-Lock-in (G4/R-A §C).
"""

from __future__ import annotations

__version__ = "0.1.0"
