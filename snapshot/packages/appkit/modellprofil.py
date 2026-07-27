"""Modell-Profil-System — Task-Klasse → Modell + Fähigkeiten (E1.2) und der
release-gegatete Kanal-Verweis „bestes lokales Profil Stufe N" (E1.3).

**Status: VERTRAG (FP-3, Bau-Spec docs/62 §3).** ``vram_probe`` ist ein ehrlicher
Stub (→ ``None``); der Aufbau kommt mit C3/C4 (docs/53). Bis dahin liest NIEMAND
im Produktiv-Pfad dieses Modul — rein additiv.

Zwei getrennte Fähigkeits-Ebenen (bewusst — die docs blurren das):
- ``runtime.RuntimeFaehigkeiten`` = ADAPTER-Klasse (cd-Dialekt, Tool-Streaming,
  Kontext STEUERBARKEIT) — statisch je Runtime.
- ``ModellFaehigkeiten`` (hier) = MODELL (kontext_max, tools, cd-tauglich,
  mehrsprachig, dim) — je Profil-Slot. Effektiver Kontext = min(beider Welten);
  die Komposition macht der Aufrufer.

Präzedenz der Modellwahl (0-Verhaltenswechsel-Anker für C3):
**Nutzer-Setting (``ai_model``) > Profil-Slot > alte Konstante.** Ein heute
gesetztes ``ai_model`` gewinnt weiter; das Profil ersetzt nur die KONSTANTEN
(``DEFAULT_LOCAL_MODEL``/``FAST_LOCAL_MODEL``/``EMBED_MODELL``) als Default-Quelle.

Kanal-Mechanik (E1.3): ``STUFEN`` ist die kuratierte Release-Liste („durch
Nachrichten freigegeben" = neuer Eintrag mit ``freigegeben=True`` kommt per
appkit-Release, nie zur Laufzeit). ``aufloese_stufe`` wählt deterministisch die
höchste freigegebene Stufe, deren ``vram_min_bytes`` auf die Maschine passt —
Stufe 0 (vram_min 0) ist der unbedingte Boden. Ein Stufen-Wechsel, der den
embed-Slot ändert, wird NIE still angewendet: ``profil_wechsel_folgen`` meldet
``reindex_noetig`` und der Re-Index-LAUF bleibt gegated (Nutzer-Go) — das
Verwerfen selbst erledigt ``rag._migriere_modellwechsel`` (VEC_SCHEMA-Disziplin).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# Die 6 Task-Klassen (E1.2; „schnell" deckt auch strukturiert/Triage — heutige
# FAST_LOCAL_MODEL-Rolle). Apps dürfen weiter EXPLIZITE Modelle je Aufruf setzen
# (z. B. News-Triage); das Profil liefert nur den Netz-DEFAULT je Klasse.
TASK_KLASSEN = ("chat", "schnell", "embed", "rerank", "vision", "voice")


@dataclass(frozen=True)
class ModellFaehigkeiten:
    """Fähigkeits-Flags EINES Modells. ``kontext_max`` = natives Maximum laut
    Modellkarte (informativ, nicht enforced — die Runtime kann enger deckeln,
    z. B. Ollama num_ctx). ``mehrsprachig`` als Bool statt Sprachliste: das
    de-first-System braucht nur die Ja/Nein-Frage. ``dim`` nur für embed-Slots
    (muss zur ``rag.EMBED_MODELLE``-Registry passen — Vektorraum-Vertrag)."""
    kontext_max: int | None = None
    tools: bool = False
    cd: bool = False                 # constrained-decoding-tauglich
    mehrsprachig: bool = False
    vision: bool = False
    dim: int | None = None


@dataclass(frozen=True)
class ModellSlot:
    """Ein besetzter Task-Slot im Profil: Modellname + dessen Fähigkeiten."""
    modell: str
    faehigkeiten: ModellFaehigkeiten = ModellFaehigkeiten()


@dataclass(frozen=True)
class ModellProfil:
    """Ein kuratiertes Gesamt-Profil (= eine Kanal-Stufe, E1.3).

    ``zuordnung`` mappt Task-Klasse → Slot; FEHLENDE Klasse = dormant (ehrlich:
    Stufe 0 hat KEIN rerank/vision/voice, weil heute keins im Kern verdrahtet
    ist — memory injiziert ``rerank_fn`` optional, Default None).
    ``vram_min_bytes`` gatet die hardware-bewusste Auswahl; ``freigegeben``
    ist das Release-Gate — NICHT per Setting umgehbar (Kurations-Sicherung;
    Entwickler testen über ein explizites ``stufen=``-Argument)."""
    stufe: int
    name: str
    freigegeben: bool
    vram_min_bytes: int
    zuordnung: dict[str, ModellSlot] = field(default_factory=dict)

    def slot(self, task: str) -> ModellSlot | None:
        return self.zuordnung.get(task)

    def modell_fuer(self, task: str) -> str | None:
        s = self.slot(task)
        return s.modell if s else None


# --- Stufe 0 = heutiges Live-Verhalten, wertgleich gepinnt ----------------------
# qwen3:14b/4b: kontext_max = 32768 (nativ laut Qwen3-Karte; via YaRN mehr —
# informativ, effektiv entscheidet num_ctx). bge-m3: 8192 Ctx / 1024 dim — dim
# MUSS ``rag.EMBED_MODELLE['bge-m3']`` spiegeln (Test pinnt das Literal).
STUFE_0 = ModellProfil(
    stufe=0, name="stufe-0", freigegeben=True, vram_min_bytes=0,
    zuordnung={
        "chat": ModellSlot("qwen3:14b", ModellFaehigkeiten(
            kontext_max=32768, tools=True, cd=True, mehrsprachig=True)),
        "schnell": ModellSlot("qwen3:4b", ModellFaehigkeiten(
            kontext_max=32768, tools=True, cd=True, mehrsprachig=True)),
        "embed": ModellSlot("bge-m3", ModellFaehigkeiten(
            kontext_max=8192, mehrsprachig=True, dim=1024)),
        # rerank/vision/voice: dormant bis C10 bzw. Reranker-Entscheid (docs/30-W5).
    })

# Kuratierte Release-Liste — WÄCHST nur per appkit-Release (E1.3 „durch
# Nachrichten freigegeben"). Stufe 0 bleibt Default bis zum 1. Release.
STUFEN: tuple[ModellProfil, ...] = (STUFE_0,)


@dataclass(frozen=True)
class WechselFolgen:
    """Folgen eines Profil-/Stufen-Wechsels — v. a. die Re-Index-Frage.
    ``reindex_noetig`` ⇒ der Wechsel darf NICHT still angewendet werden
    (gegateter Lauf; betrifft core-L3 UND memory-RAG, gleiche bge-m3-Räume)."""
    embed_wechsel: bool
    reindex_noetig: bool
    hinweis: str = ""


def profil_wechsel_folgen(alt: ModellProfil, neu: ModellProfil) -> WechselFolgen:
    """Vergleicht die embed-Slots zweier Profile. Modell- ODER Dim-Änderung
    (auch Slot erscheint/verschwindet) ⇒ Vektorräume inkompatibel ⇒ Re-Index
    (das Verwerfen macht ``rag._migriere_modellwechsel`` selbst — hier entsteht
    nur das GATE, damit der teure Lauf nutzer-gegated bleibt)."""
    a, n = alt.slot("embed"), neu.slot("embed")
    if a is None and n is None:
        return WechselFolgen(False, False)
    gewechselt = (a is None) != (n is None) or (
        a is not None and n is not None and (
            a.modell != n.modell or a.faehigkeiten.dim != n.faehigkeiten.dim))
    if not gewechselt:
        return WechselFolgen(False, False)
    return WechselFolgen(True, True, (
        f"embed-Wechsel {a.modell if a else '—'} → {n.modell if n else '—'}: "
        f"Re-Index aller RAG-Indizes nötig (VEC_SCHEMA-Disziplin, gegated)."))


def aufloese_stufe(vram_bytes: int | None, *,
                   stufen: Sequence[ModellProfil] = STUFEN,
                   pin: int | None = None) -> ModellProfil:
    """Deterministische Kanal-Auflösung (E1.3, pure — testbar ohne Hardware):
    1. ``pin`` (Nutzer-Setting ``modell_profil_stufe``) gewinnt, sofern die
       Stufe existiert UND freigegeben ist (Release-Gate schlägt Pin).
    2. Sonst: höchste freigegebene Stufe mit ``vram_min_bytes <= vram_bytes``;
       ``vram_bytes=None`` (Probe fehlgeschlagen) wie 0 ⇒ nur der Boden passt.
    Wirft nur bei leerer/bodenloser ``stufen``-Liste (Programmierfehler —
    ``STUFEN`` enthält per Vertrag immer eine freigegebene vram_min-0-Stufe)."""
    freigegeben = [s for s in stufen if s.freigegeben]
    if pin is not None:
        for s in freigegeben:
            if s.stufe == pin:
                return s
    vram = vram_bytes or 0
    passend = [s for s in freigegeben if s.vram_min_bytes <= vram]
    if not passend:
        raise ValueError("Keine freigegebene Boden-Stufe (vram_min 0) vorhanden "
                         "— STUFEN verletzt den Kanal-Vertrag (docs/62 §3).")
    return max(passend, key=lambda s: s.stufe)


def vram_probe() -> int | None:
    """GESAMT-GPU-VRAM in Bytes (C4/M9) — fail-safe: wirft NIE. Jeder Fehler
    (kein ``nvidia-smi`` im PATH, Timeout, Nicht-Null-Exit, leere/kaputte Ausgabe,
    Nicht-NVIDIA-GPU) ⇒ ``None`` = unbekannt ⇒ ``aufloese_stufe`` wählt den Boden
    (Stufe 0).

    Gemessen wird die KAPAZITÄT (``memory.total``), NICHT der momentan freie
    Speicher: die Kanal-Stufe ist eine Hardware-Eigenschaft (was passt auf diese
    Karte), kein Laufzeit-Zustand — sonst würde ein geladenes Modell die Stufe
    fälschlich herabstufen. Nur NVIDIA (``nvidia-smi``); andere GPUs ⇒ ``None``
    (ehrlich unbekannt ⇒ Boden). Lazy-Imports (kein Import-Zeit-Effekt); bei
    mehreren GPUs zählt die erste Zeile."""
    import shutil
    import subprocess
    try:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return None
        aus = subprocess.run(
            [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3.0)
        if aus.returncode != 0:
            return None
        zeilen = [z.strip() for z in aus.stdout.splitlines() if z.strip()]
        if not zeilen:
            return None
        return int(zeilen[0]) * 1024 * 1024      # nvidia-smi liefert MiB → Bytes
    except Exception:
        return None
