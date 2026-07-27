"""Bau-Instanz — Generator-Schnittstelle + ComfyUI-Adapter (R-A §A).

ComfyUI läuft headless als lokaler Generations-Dienst (:8188) und führt
Workflow-Graphen aus (Flux/SDXL Bild, Wan 2.2 Video). Dieser Adapter spricht
die HTTP-API: ``POST /prompt`` (Workflow-JSON) → prompt_id, dann Polling über
``GET /history/{id}`` bis Ergebnis-Dateien vorliegen. Modell-Wechsel/VRAM
verwaltet ComfyUI selbst (16-GB-tauglich, R-A).

Der Cloud-Weg (fal.ai: Veo/Kling/Runway) ist als Protokoll-Implementierung
vorgesehen (opt-in, lokal-first-Prämisse) — gleiche Schnittstelle, eigener
Adapter, KEIN Umbau (Fragerunde 3).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

from .jobs import Job


class Generator(Protocol):
    """Vertrags-Schnittstelle der Bau-Instanz (stabil — Adapter austauschbar)."""

    def health(self) -> bool: ...
    def generate(self, job: Job) -> dict[str, Any]: ...


def _ablehnungs_text(antwort: Any) -> str:
    """ComfyUI ``POST /prompt`` lehnt einen ungültigen Graphen mit HTTP 400 ab und
    legt die Node-Validierungsfehler (``error`` + ``node_errors``) in den BODY —
    ohne den ist der Fehler nicht diagnostizierbar (Gesetz 2). Macht daraus eine
    lesbare Zeile."""
    try:
        d = antwort.json()
    except Exception:
        return (f"ComfyUI /prompt {getattr(antwort, 'status_code', '?')}: "
                f"{getattr(antwort, 'text', '')[:400]}")
    teile: list[str] = []
    fehler = d.get("error")
    if isinstance(fehler, dict) and fehler.get("message"):
        teile.append(str(fehler["message"])
                     + (f" — {fehler['details']}" if fehler.get("details") else ""))
    elif fehler:
        teile.append(str(fehler))
    for nid, ne in (d.get("node_errors") or {}).items():
        typ = ne.get("class_type", "?")
        for err in ne.get("errors", []):
            teile.append(f"Node {nid} ({typ}): {err.get('message', '')}"
                         + (f" [{err['details']}]" if err.get("details") else ""))
    return "ComfyUI lehnte den Graphen ab — " + (
        " · ".join(teile) or getattr(antwort, "text", "")[:400])


def _oom_zusatz(text: str) -> str:
    """Übersetzt einen CUDA-OOM in einen handlungsleitenden 16-GB-Hinweis (Audit
    28.06.) — der rohe „CUDA out of memory" ist für Nicht-Techniker nicht
    actionable. Leerstring, wenn es kein OOM ist."""
    t = (text or "").lower()
    if any(m in t for m in ("out of memory", "outofmemory", "tried to allocate",
                            "cuda error: out of memory")):
        return (" — VRAM erschöpft (16 GB): Auflösung/Faktor senken · Tiling/Tiled-VAE · "
                "GGUF-Q4 via params · kleineres Modell · ggf. ENV "
                "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True.")
    return ""


def _ausfuehrungs_fehler(entry: dict[str, Any]) -> str | None:
    """Ein Node-Ausführungsfehler steckt in ``history[id].status`` (``status_str``
    == ``error`` + ``messages`` mit ``execution_error``) — ohne diese Prüfung
    erschiene er nur als „keine Ergebnis-Dateien" (so verbarg sich der SAM2-Bug,
    28.06.). Liefert die echte Fehlerzeile oder None."""
    status = entry.get("status") or {}
    if status.get("status_str") != "error":
        return None
    for eintrag in status.get("messages", []):
        if isinstance(eintrag, (list, tuple)) and len(eintrag) == 2 \
                and eintrag[0] == "execution_error":
            d = eintrag[1] or {}
            msg = (f"ComfyUI-Node-Fehler in {d.get('node_type', '?')} "
                   f"(#{d.get('node_id', '?')}): {d.get('exception_type', '')}: "
                   f"{d.get('exception_message', '')}").strip()
            return msg + _oom_zusatz(f"{d.get('exception_type', '')} "
                                     f"{d.get('exception_message', '')}")
    return "ComfyUI meldete einen Ausführungsfehler (ohne Detail im History-Status)"


def _upload_name(info: dict[str, Any]) -> str:
    """Der dortige Datei-Name aus einer ComfyUI-``/upload/image``-Antwort —
    defensiv (Audit 29.06.): fehlt das ``name``-Feld (Payload-Anomalie), ehrlicher
    Fehler statt KeyError."""
    name = (info or {}).get("name")
    if not name:
        raise RuntimeError(f"ComfyUI-Upload-Antwort ohne 'name'-Feld: {info!r}")
    sub = info.get("subfolder") or ""
    return f"{sub}/{name}" if sub else name


class ComfyUIGenerator:
    """Lokaler Generator über ComfyUI headless.

    ``job.params``: {"workflow": <API-Format-Graph>, "timeout_s": 600}.
    Workflows sind app-seitig gepflegte Vorlagen (Flux/SDXL/Wan 2.2) mit
    eingesetzten Prompts — die Engine bleibt graph-agnostisch.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8188",
                 http=None) -> None:
        self.base = base_url.rstrip("/")
        self._http = http  # Test-Injektion; default httpx (lazy)

    def _client(self):
        if self._http is not None:
            return self._http
        import httpx
        self._http = httpx
        return self._http

    def health(self) -> bool:
        try:
            r = self._client().get(f"{self.base}/system_stats", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def geladene_nodes(self) -> set[str]:
        """Alle in ComfyUI geladenen Node-``class_type``s (EIN ``/object_info``-Call)
        — Basis des Fähigkeits-Health (`/api/faehigkeiten`): welche gegateten Custom-
        Nodes sind installiert. honest-fail/Down ⇒ leere Menge."""
        try:
            r = self._client().get(f"{self.base}/object_info", timeout=10.0)
            if getattr(r, "status_code", 200) != 200:
                return set()
            return set(r.json().keys())
        except Exception:
            return set()

    def hat_node(self, class_type: str) -> bool:
        """Ist ein (Custom-)Node geladen? Für honest-fail vor gegateten
        Fähigkeiten (z. B. SAM2-Tracking) — ``/object_info/<Node>`` liefert den
        Node-Eintrag nur, wenn das Node-Pack installiert ist. Bei Fehler/Down
        konservativ ``True`` (der eigentliche Job-Fehler bleibt dann ehrlich)."""
        try:
            r = self._client().get(f"{self.base}/object_info/{class_type}",
                                   timeout=5.0)
            return r.status_code == 200 and bool(r.json().get(class_type))
        except Exception:
            return True

    def generate(self, job: Job) -> dict[str, Any]:
        http = self._client()
        workflow = job.params.get("workflow")
        if not isinstance(workflow, dict) or not workflow:
            raise ValueError("params.workflow (ComfyUI-API-Graph) fehlt")
        timeout_s = float(job.params.get("timeout_s", 600))

        r = http.post(f"{self.base}/prompt", json={"prompt": workflow},
                      timeout=10.0)
        if getattr(r, "status_code", 200) >= 400:    # Node-Validierung (400-Body lesen)
            raise RuntimeError(_ablehnungs_text(r))
        prompt_id = r.json()["prompt_id"]

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            h = http.get(f"{self.base}/history/{prompt_id}", timeout=10.0)
            h.raise_for_status()
            data = h.json()
            entry = data.get(prompt_id)
            if entry:
                fehler = _ausfuehrungs_fehler(entry)   # echten Node-Fehler hochreichen
                if fehler:
                    raise RuntimeError(fehler)
                outputs = entry.get("outputs", {})
                if not outputs:                  # Audit 29.06.: ehrlich statt still []
                    raise RuntimeError(
                        f"ComfyUI-Job {prompt_id} endete OHNE outputs — Workflow-/"
                        "Modell-Fehler oder Cache-Kollision identischer Graphen "
                        "(anderer Seed/Parameter).")
                files: list[dict[str, Any]] = []
                for node in outputs.values():
                    for key in ("images", "gifs", "videos", "audio"):
                        files.extend(node.get(key, []))
                job.report(1.0)
                return {"prompt_id": prompt_id, "files": files}
            job.report(min(0.95, job.progress + 0.02))
            time.sleep(1.0)
        raise TimeoutError(f"ComfyUI-Job {prompt_id} nicht fertig in {timeout_s:.0f}s")

    def upload_bild(self, pfad: Path | str, name: str | None = None) -> str:
        """Lädt ein Eingabe-Bild in ComfyUIs Input-Ablage (für LoadImage-
        Knoten, z. B. Inpaint/Upscale) und liefert den dortigen Namen."""
        p = Path(pfad)
        r = self._client().post(
            f"{self.base}/upload/image",
            files={"image": (name or p.name, p.read_bytes(),
                             "application/octet-stream")},
            data={"overwrite": "true"}, timeout=60.0)
        r.raise_for_status()
        return _upload_name(r.json())

    def upload_audio(self, pfad: Path | str, name: str | None = None) -> str:
        """Lädt eine Eingabe-Audiodatei in ComfyUIs Input-Ablage (für LoadAudio-
        Knoten, z. B. RVC-Voice-Convert auf ein Vocal-Stem) und liefert den
        dortigen Namen. ComfyUIs ``/upload/image`` legt die Datei typ-unabhängig
        in ``input/`` ab (LoadAudio findet sie über den Namen). e2e-Finalisierung:
        sollte eine ComfyUI-Version den Endpoint typ-prüfen, hier den Audio-
        Upload-Pfad anpassen (Gesetz 2 — gegen das echte ComfyUI verifiziert)."""
        p = Path(pfad)
        r = self._client().post(
            f"{self.base}/upload/image",
            files={"image": (name or p.name, p.read_bytes(),
                             "application/octet-stream")},
            data={"overwrite": "true"}, timeout=120.0)
        r.raise_for_status()
        return _upload_name(r.json())

    def upload_video(self, pfad: Path | str, name: str | None = None) -> str:
        """Lädt eine Eingabe-Videodatei in ComfyUIs Input-Ablage (für VHS-
        ``LoadVideo``, z. B. das Control-Video von VACE-V2V/Inpaint, P14 v2) und
        liefert den dortigen Namen. Wie ``upload_audio`` über ``/upload/image``
        (legt typ-unabhängig in ``input/`` ab; VHS_LoadVideo findet die Datei
        über den Namen). e2e gegen das echte ComfyUI verifiziert (Gesetz 2):
        sollte eine Version den Endpoint typ-prüfen, hier den Video-Upload-Pfad
        anpassen."""
        p = Path(pfad)
        r = self._client().post(
            f"{self.base}/upload/image",
            files={"image": (name or p.name, p.read_bytes(),
                             "application/octet-stream")},
            data={"overwrite": "true"}, timeout=300.0)
        r.raise_for_status()
        return _upload_name(r.json())

    def lade_datei(self, datei: dict[str, Any]) -> bytes:
        """Holt eine Ergebnis-Datei (Eintrag aus ``generate()['files']``)
        über ``GET /view`` — ComfyUI kann auf anderem Rechner laufen, also
        nie auf lokale Pfade raten."""
        r = self._client().get(
            f"{self.base}/view",
            params={"filename": datei["filename"],
                    "subfolder": datei.get("subfolder", ""),
                    "type": datei.get("type", "output")},
            timeout=120.0)
        r.raise_for_status()
        return r.content
