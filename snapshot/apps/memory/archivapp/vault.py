"""Markdown-Vault — das kanonische, portable Speicherformat von Dizz Memory.

Entscheid REV-5 / Recherche (docs/RECHERCHE.md §6): Notizen liegen als
**Markdown-Dateien mit YAML-Frontmatter** auf der Platte (Obsidian-kompatibel,
kein DB-Lock-in, direkt RAG-indexierbar). Die Ordnerstruktur wird 1:1 als
Verzeichnisbaum gespiegelt, ``[[wikilinks]]`` im Körper bleiben erhalten
(gleiches Muster wie Dizzis Gedächtnis ⇒ Konsistenz).

Arbeitsteilung (bewusst, gegen „Doppelhaltung"):
- **Vault (diese Datei) = Quelle der Wahrheit** für den Inhalt. Portabel,
  vom Nutzer mit jedem Editor lesbar, das was Dizzis L3-RAG später indexiert.
- **SQLite (main.py) = abgeleiteter Index** für schnelle Listen/Suche (FTS) und
  die Vertrags-Konventionen (user_id/Zeitstempel/Soft-Delete). Jederzeit aus dem
  Vault **rebuildbar** (``main.reindex``) — der Index hält keine eigene Wahrheit.

Diese Klasse macht ausschließlich Datei-I/O (kein DB-Wissen): main.py reicht den
fertig berechneten Ordner-Pfad herein. So bleibt der Vault testbar und schlank.

Vorbereiteter Slot (Gesetz 5): ``.trash/`` sammelt gelöschte Dateien (Soft-
Delete-Spiegel); eine spätere Vektor-/RAG-Brücke (sqlite-vec/bge-m3 → Dizzi L3)
liest denselben Vault, ohne dass das Format sich ändern muss.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from appkit.io_safe import atomic_write_text

try:  # PyYAML ist im Netzwerk-venv vorhanden; Fallback hält die App lauffähig.
    import yaml  # type: ignore
except Exception:  # pragma: no cover - Defensive, falls yaml fehlt
    yaml = None  # type: ignore

# Reihenfolge der Frontmatter-Schlüssel (deterministisch ⇒ saubere Diffs/Git).
_FM_ORDER = ("id", "titel", "ordner", "labels", "sensibel",
             "created_at", "updated_at")
_FM_GRENZE = re.compile(r"^---\s*$")
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(text: str, fallback: str = "notiz") -> str:
    """Dateinamens-tauglicher Slug (klein, ASCII-nah, kurz). Reiner Datei-
    Komfort — die fachliche Identität ist die UUID im Dateinamen-Suffix."""
    text = (text or "").strip().lower()
    text = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                .replace("ß", "ss"))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:50].rstrip("-")) or fallback


def sanitize_segment(name: str) -> str:
    """Macht einen Ordnernamen verzeichnis-tauglich (ein Pfad-Segment)."""
    name = _ILLEGAL.sub("-", (name or "").strip()).strip(". ")
    return name or "Ordner"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MarkdownVault:
    """Liest/schreibt Notiz-Dateien unter ``<root>/<user_id>/…``.

    ``pfad`` in der API ist immer **relativ** zur User-Wurzel (z. B.
    ``Projekte/2026/idee__1a2b3c4d.md``) — so bleibt der Index geräte-/
    pfad-unabhängig.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- Pfade --------------------------------------------------------------
    def user_root(self, user_id: str) -> Path:
        return self.root / sanitize_segment(user_id)

    def rel_path_for(self, ordner_pfad: str, titel: str, note_id: str) -> str:
        """Berechnet den relativen Datei-Pfad einer Notiz aus Ordner-Pfad
        (``"A/B"`` oder ``""``), Titel-Slug und UUID-Kurzform."""
        datei = f"{slugify(titel)}__{note_id[:8]}.md"
        segmente = [sanitize_segment(s) for s in ordner_pfad.split("/") if s.strip()]
        return "/".join([*segmente, datei])

    def _innerhalb(self, user_id: str, rel_path: str) -> Path:
        """Defense-in-Depth: löst ``rel_path`` unter der Nutzer-Wurzel auf und
        stellt sicher, dass er sie NICHT verlässt (``..``-Traversal) — wirft sonst
        ``ValueError``. Greift unabhängig vom Aufrufer (zusätzlich zur Sanitisierung
        in ``rel_path_for``/``_pfad_ok``): kein Datei-I/O verlässt je das User-Verzeichnis,
        egal welcher Pfad hereingereicht wird (Spiegel der Tresor-``is_relative_to``-Wache)."""
        wurzel = self.user_root(user_id).resolve()
        ziel = (self.user_root(user_id) / rel_path).resolve()
        if not ziel.is_relative_to(wurzel):
            raise ValueError(f"Pfad verlässt die Nutzer-Wurzel: {rel_path!r}")
        return ziel

    # --- Frontmatter --------------------------------------------------------
    @staticmethod
    def dump(frontmatter: dict[str, Any], body: str) -> str:
        """Serialisiert eine Notiz als Markdown mit YAML-Frontmatter."""
        geordnet = {k: frontmatter[k] for k in _FM_ORDER if k in frontmatter}
        geordnet.update({k: v for k, v in frontmatter.items() if k not in geordnet})
        if yaml is not None:
            fm = yaml.safe_dump(geordnet, allow_unicode=True, sort_keys=False).strip()
        else:  # minimaler Fallback (genügt für die kontrollierten Felder)
            zeilen = []
            for k, v in geordnet.items():
                if isinstance(v, list):
                    v = "[" + ", ".join(str(x) for x in v) + "]"
                elif isinstance(v, bool):
                    v = "true" if v else "false"
                zeilen.append(f"{k}: {v}")
            fm = "\n".join(zeilen)
        return f"---\n{fm}\n---\n\n{body.rstrip()}\n"

    @staticmethod
    def parse(text: str) -> tuple[dict[str, Any], str]:
        """Zerlegt Markdown(+Frontmatter) in (frontmatter, body). Ohne
        Frontmatter: leeres dict + ganzer Text als Körper (robust für Import)."""
        if text and text[0] == "﻿":     # UTF-8-BOM (Windows/Mem.ai-Exporte) abstreifen,
            text = text[1:]                   # sonst matcht die ---Frontmatter-Grenze nicht
        zeilen = text.splitlines()
        if zeilen and _FM_GRENZE.match(zeilen[0]):
            for i in range(1, len(zeilen)):
                if _FM_GRENZE.match(zeilen[i]):
                    roh = "\n".join(zeilen[1:i])
                    body = "\n".join(zeilen[i + 1:]).lstrip("\n")
                    fm: dict[str, Any] = {}
                    if yaml is not None:
                        try:
                            geladen = yaml.safe_load(roh)
                            if isinstance(geladen, dict):
                                fm = geladen
                        except Exception:
                            fm = {}
                    else:  # pragma: no cover
                        for z in roh.splitlines():
                            if ":" in z:
                                k, _, v = z.partition(":")
                                fm[k.strip()] = v.strip()
                    return fm, body
        return {}, text

    # --- Datei-Operationen --------------------------------------------------
    def write(self, user_id: str, rel_path: str,
              frontmatter: dict[str, Any], body: str,
              alt_pfad: str | None = None) -> None:
        """Schreibt die Notiz-Datei; räumt eine alte Position auf (Rename/Move)."""
        self._innerhalb(user_id, rel_path)
        ziel = self.user_root(user_id) / rel_path
        ziel.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(ziel, self.dump(frontmatter, body))   # temp+fsync+replace (P1.2)
        if alt_pfad and alt_pfad != rel_path:
            self._entfernen(user_id, alt_pfad)

    def read(self, user_id: str, rel_path: str) -> tuple[dict[str, Any], str] | None:
        self._innerhalb(user_id, rel_path)
        datei = self.user_root(user_id) / rel_path
        if not datei.is_file():
            return None
        return self.parse(datei.read_text(encoding="utf-8"))

    def trash(self, user_id: str, rel_path: str) -> None:
        """Soft-Delete-Spiegel: verschiebt die Datei nach ``.trash/`` (mit
        Zeitstempel-Präfix gegen Namenskollisionen). Der Inhalt bleibt damit
        wiederherstellbar — die fachliche Löschung steht im Index (deleted_at)."""
        self._innerhalb(user_id, rel_path)
        quelle = self.user_root(user_id) / rel_path
        if not quelle.is_file():
            return
        stempel = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        ziel = self.user_root(user_id) / ".trash" / f"{stempel}__{quelle.name}"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        quelle.replace(ziel)
        self._leere_eltern(quelle.parent, user_id)

    def purge_user(self, user_id: str) -> bool:
        """DSGVO-Konto-Löschung (appkit on_delete-Hook, H-7): entfernt das GESAMTE
        Vault-Verzeichnis des Nutzers (inkl. ``.trash``) hart von der Platte —
        „weg = weg". Anders als ``trash`` (Soft-Delete einzelner Notizen) ist das
        die endgültige Räumung beim Account-Löschen. Gibt True zurück, wenn etwas
        entfernt wurde; fehlertolerant (rmtree ignore_errors)."""
        import shutil
        wurzel = self.user_root(user_id)
        if not wurzel.is_dir():
            return False
        shutil.rmtree(wurzel, ignore_errors=True)
        return True

    def iter_dateien(self, user_id: str):
        """Liefert (rel_path, frontmatter, body) aller Notiz-Dateien (für
        Reindex/Import). ``.trash`` wird ausgelassen."""
        wurzel = self.user_root(user_id)
        if not wurzel.is_dir():
            return
        for datei in sorted(wurzel.rglob("*.md")):
            rel = datei.relative_to(wurzel)
            if rel.parts and rel.parts[0] == ".trash":
                continue
            try:
                fm, body = self.parse(datei.read_text(encoding="utf-8"))
            except Exception:
                continue
            yield rel.as_posix(), fm, body

    # --- intern -------------------------------------------------------------
    def _entfernen(self, user_id: str, rel_path: str) -> None:
        self._innerhalb(user_id, rel_path)
        datei = self.user_root(user_id) / rel_path
        if datei.is_file():
            datei.unlink()
            self._leere_eltern(datei.parent, user_id)

    def _leere_eltern(self, ordner: Path, user_id: str) -> None:
        """Räumt leer gewordene Ordner bis zur User-Wurzel auf (kosmetisch)."""
        wurzel = self.user_root(user_id)
        cur = ordner
        while cur != wurzel and wurzel in cur.parents:
            try:
                next(cur.iterdir())
                break  # nicht leer
            except StopIteration:
                cur.rmdir()
                cur = cur.parent
            except OSError:
                break
