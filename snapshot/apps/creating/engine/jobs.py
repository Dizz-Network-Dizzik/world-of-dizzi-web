"""Job-Queue der Creating-Engine — GPU ist seriell, also ist es die Queue auch.

Ein Worker-Thread arbeitet Jobs strikt nacheinander ab (VRAM-Schutz auf
16 GB); Status/Ergebnis sind thread-sicher abfragbar. Bewusst stdlib-pur —
die App-Schicht (R2.x) bringt Persistenz/HITL über den App-Vertrag dazu.
"""

from __future__ import annotations

import queue
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

JobFn = Callable[["Job"], Any]

_STATUS = ("pending", "running", "done", "failed", "cancelled", "unterbrochen")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    kind: str                                   # z. B. 'bild', 'video', 'schnitt'
    params: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"
    progress: float = 0.0                       # 0..1, vom Adapter gemeldet
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None

    def report(self, progress: float) -> None:
        """Adapter melden Fortschritt (geklemmt 0..1)."""
        self.progress = min(1.0, max(0.0, progress))

    def snapshot(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "progress": round(self.progress, 3), "error": self.error,
                "created_at": self.created_at, "finished_at": self.finished_at}


class JobQueue:
    """Serieller Job-Abarbeiter. ``submit`` liefert sofort die Job-ID;
    ``status``/``listing`` sind jederzeit abfragbar; ``cancel`` wirkt nur auf
    noch nicht gestartete Jobs (laufende GPU-Arbeit ist nicht sicher abbrechbar
    — ehrliche Grenze, dokumentiert)."""

    def __init__(self, max_history: int = 500, *,
                 on_change: "Callable[[Job], None] | None" = None,
                 on_remove: "Callable[[str], None] | None" = None) -> None:
        self._q: "queue.Queue[Job | None]" = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._fns: dict[str, JobFn] = {}
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop = False
        # Persistenz-Hooks (App-Schicht, R2.x): Job-Zustand spiegeln / geprunten
        # Job loeschen. ``engine/jobs`` bleibt stdlib-pur — KEIN DB-Wissen hier;
        # die Hooks duerfen den Job-Lauf NIE scheitern lassen (s. _spiegeln).
        self._on_change = on_change
        self._on_remove = on_remove
        # Beschränkte Historie: fertige Jobs (mit ihren params/Ergebnissen —
        # z. B. großen Workflow-Graphen) sammeln sich sonst unbegrenzt im
        # Speicher eines dauerlaufenden Servers. ``max_history`` ist die Zahl
        # der behaltenen ABGESCHLOSSENEN Jobs; laufende/wartende zählen NICHT
        # mit und bleiben immer erhalten.
        self._max_history = max_history

    def register(self, kind: str, fn: JobFn) -> None:
        if kind in self._fns:
            raise ValueError(f"Job-Art doppelt registriert: {kind!r}")
        self._fns[kind] = fn

    def submit(self, kind: str, params: dict[str, Any] | None = None) -> str:
        if kind not in self._fns:
            raise KeyError(f"Unbekannte Job-Art: {kind!r}")
        job = Job(kind=kind, params=params or {})
        with self._lock:
            self._jobs[job.id] = job
        self._q.put(job)
        self._ensure_worker()
        self._spiegeln(job)                       # Persistenz: 'pending' sichern
        return job.id

    def cancel(self, job_id: str) -> bool:
        storniert = None
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.status == "pending":
                job.status = "cancelled"
                job.finished_at = _now()
                storniert = job
        if storniert is not None:
            self._spiegeln(storniert)
            return True
        return False

    def restore(self, jobs: "list[Job]") -> None:
        """Persistierte Jobs beim App-Start zurueckspielen (Historie + die als
        ``unterbrochen`` markierten Ex-Running/Pending). Re-queued NICHTS — es gibt
        KEIN automatisches Neu-Ausfuehren (kein Doppel-GPU-Risiko); der Nutzer sieht
        seine Jobs nach Neustart wieder, statt 404. Vorhandene IDs bleiben unberuehrt."""
        with self._lock:
            for job in jobs:
                self._jobs.setdefault(job.id, job)

    def status(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job else None

    def result(self, job_id: str) -> Any:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.result if job else None

    def owner(self, job_id: str) -> str | None:
        """Owner-Kennung (``params['user_id']``) eines Jobs — für App-seitiges
        Multi-User-Scoping. Bewusst NICHT in ``snapshot()``: das wird breit
        konsumiert (status/listing), die Owner-Kennung gehört nicht in jeden
        Status-Payload. ``None`` für unbekannte/owner-lose Jobs ⇒ der Aufrufer
        behandelt fremd wie nicht-existent (404, Existenz nicht leaken). Owner
        bleibt über den ganzen Lebenszyklus erhalten (``_run`` poppt nur
        'workflow', nicht 'user_id')."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not isinstance(job.params, dict):
                return None
            return job.params.get("user_id")

    def listing(self, limit: int = 50,
                nur_user: str | None = None) -> list[dict[str, Any]]:
        """Jüngste Jobs als Snapshot (ohne params). ``nur_user`` filtert auf
        Jobs dieses Owners VOR dem Limit — ein Nutzer sieht bis zu ``limit`` der
        EIGENEN Jobs, nicht ``limit`` über alle und dann gefiltert."""
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at,
                          reverse=True)
            if nur_user is not None:
                jobs = [j for j in jobs if isinstance(j.params, dict)
                        and j.params.get("user_id") == nur_user]
            return [j.snapshot() for j in jobs[:limit]]

    def beschaeftigt(self) -> bool:
        """Nicht-blockierende Schwester von ``wait_idle``: True, solange ein Job
        wartet ODER läuft (die serielle GPU-Lane ist belegt). Für Status-Abfragen
        (ComfyUI-Stop-Wache: nie mitten in einer Generierung killen)."""
        with self._lock:
            return any(j.status in ("pending", "running")
                       for j in self._jobs.values())

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Für Tests/Shutdown: blockiert, bis die Queue leer ist."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                busy = any(j.status in ("pending", "running")
                           for j in self._jobs.values())
            if not busy:
                return True
            time.sleep(0.02)
        return False

    def shutdown(self) -> None:
        self._stop = True
        self._q.put(None)

    # --- intern ---------------------------------------------------------------

    def _ensure_worker(self) -> None:
        # Unter dem Lock (Audit 29.06.): zwei gleichzeitige ``submit``-Aufrufe
        # dürfen NICHT beide den Check passieren und zwei Worker starten — das
        # bräche die EINE serielle GPU-Queue (parallele GPU-Last ⇒ OOM).
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True,
                                                name="creating-engine-worker")
                self._worker.start()

    def _spiegeln(self, job: "Job") -> None:
        # Persistenz darf den Job-Lauf NIE scheitern lassen (Gesetz 5): ein DB-Fehler
        # ist nicht fatal — der Job laeuft im Speicher korrekt weiter.
        if self._on_change is not None:
            try:
                self._on_change(job)
            except Exception:
                pass

    def _spiegel_weg(self, job_id: str) -> None:
        if self._on_remove is not None:
            try:
                self._on_remove(job_id)
            except Exception:
                pass

    def _run(self) -> None:
        while not self._stop:
            job = self._q.get()
            if job is None:
                return
            with self._lock:
                if job.status != "pending":      # z. B. cancelled
                    continue
                job.status = "running"
            self._spiegeln(job)                  # Persistenz: 'running' (Crash ⇒ verwaist)
            # Die (lange, GPU-blockierende) Arbeit läuft OHNE Lock.
            ergebnis: Any = None
            fehler: str | None = None
            spur: dict[str, Any] | None = None
            try:
                ergebnis = self._fns[job.kind](job)
            except Exception as e:
                fehler = f"{type(e).__name__}: {e}"
                spur = {"traceback": traceback.format_exc(limit=4)}
            # Finaler Status-Wechsel + Prune UNTER dem Lock (Audit 29.06.):
            # status()/listing()/result() lesen unter demselben Lock ⇒ kein
            # Teil-/Zwischenzustand wird sichtbar. Zusätzlich den großen Workflow-
            # Graphen aus der behaltenen Historie nehmen (Speicher über Nacht).
            entfernt: list[str] = []
            with self._lock:
                if fehler is None:
                    job.result = ergebnis
                    job.status = "done"
                    job.progress = 1.0
                else:
                    job.status = "failed"
                    job.error = fehler
                    job.result = spur
                job.finished_at = _now()
                if isinstance(job.params, dict):
                    job.params.pop("workflow", None)
                entfernt = self._prune()
            self._spiegeln(job)                  # Persistenz: Endzustand (done/failed)
            for rid in entfernt:
                self._spiegel_weg(rid)           # geprunte Jobs auch aus dem Store

    def _prune(self) -> list[str]:
        """Älteste ABGESCHLOSSENE Jobs entfernen, bis ihre Zahl wieder
        ``max_history`` erreicht (nur im Lock-Kontext aufrufen). Wartende/
        laufende Jobs zählen NICHT mit und werden nie verworfen. Gibt die
        entfernten Job-IDs zurück (damit die Persistenz sie ebenfalls löscht)."""
        fertige = sorted(
            (j for j in self._jobs.values()
             if j.status in ("done", "failed", "cancelled", "unterbrochen")),
            key=lambda j: j.finished_at or j.created_at)
        ueberzaehlig = len(fertige) - self._max_history
        entfernt: list[str] = []
        for j in fertige[:max(0, ueberzaehlig)]:
            self._jobs.pop(j.id, None)
            entfernt.append(j.id)
        return entfernt
