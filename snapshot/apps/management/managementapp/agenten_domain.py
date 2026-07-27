"""Agenten-Regie — Datenmodell + CRUD (Z4.1-A, docs/63 §1/§8; FP-4/VO-3/D13).

Dizz Management ist die **KI-Agenten-Verwaltung des Netzes** (D13, G-AGENT-HEIMAT ✅);
hier wohnt die **Definition** der Agenten (Governance-Seite). Die Ausführung wohnt beim
Core (``agent.py``, Z4.2), die Aktions-Freigabe bei der besitzenden App (K4). Diese Datei
baust die **Definitions-Schicht** unter den fertigen Vertrag ``appkit.agenten``:

- **Schema** = ``appkit.agenten.SCHEMA_AGENTEN_SQL`` (Management-DB — Definition ist
  Governance, Heimat D13). Wird über ``extra_schema`` an die Database gehängt (main.py).
- **CRUD** ``/api/agenten`` — anlegen/lesen/ändern/löschen. „Agent = Datensatz, nicht Code"
  (D5-d): Erweitern ist CRUD, nie Deployment.
- **Baum-Wächter beim Schreiben** — jede Schreib-Operation prüft den GESAMTEN Agenten-Wald
  gegen ``validiere_agentenbaum`` (Tiefe ≤ ``MAX_EBENEN`` = 3, zyklenfrei); Verstoß ⇒ 422.
  *Begründung: der Vertrag deckelt hart bei 3 Ebenen (Anti-Swarm, §3.F); die Laufzeit prüft
  in Z4.2-A ZUSÄTZLICH fail-closed — die Definition traut niemandem.*

Reine Projektionen (``agent_karte``) und Politik (``wirksame_stufe``, ``werkzeuge_filter``)
liegen im Vertrag ``appkit.agenten`` und werden hier NUR benutzt, nie dupliziert.

Noch KEINE Ausführung (das ist Z4.2, Core). Diese Schicht ist rein additiv: eine neue Tabelle
+ ein neuer Router; kein Bestands-Verhalten von Dizz Management ändert sich.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, AsyncIterator, Callable
from urllib.error import URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from appkit import agenten as ag
from appkit import events
from appkit import modellprofil as mp
from appkit.actions import ActionRegistry, listing
from appkit.auth import UserContext, current_user
from appkit.db import Database, new_id, now_iso
from appkit.netz import CORE_URL, NETZ_APPS, NetzApp, netz_app

from . import agenten_eval as ev
from . import agenten_eichung as eich
from . import agenten_vorlagen as vorlagen

# Schema der Agent-Definitionen (Management-DB) — EINE Quelle = der Vertrag.
SCHEMA_AGENTEN = ag.SCHEMA_AGENTEN_SQL

# Bereichs-Autonomie-Matrix (P4): Stufe je (Bereich × Aktions-Klasse). ``bereich_id=''``
# = Allgemein (globaler Default). Speist ``wirksame_stufe(bereich_stufe=…)`` in Z4.2-C;
# geld/gesundheit werden hier fail-closed auf pre_approval gehalten (nie speicherbar höher).
SCHEMA_AUTONOMIE = """
CREATE TABLE IF NOT EXISTS agent_bereich_autonomie (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  bereich_id  TEXT NOT NULL DEFAULT '',
  klasse      TEXT NOT NULL,
  stufe       TEXT NOT NULL DEFAULT 'pre_approval',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  deleted_at  TEXT,
  UNIQUE (user_id, bereich_id, klasse)
);
CREATE INDEX IF NOT EXISTS idx_agent_autonomie ON agent_bereich_autonomie (user_id, bereich_id);
"""

# Abo-Tabelle der reaktiven Regie (RG-3b, docs/83 §2): bindet EINEN Fach-Orchestrator
# an EINEN Ereignis-Strom. Determinismus in DATEN, nicht im LLM: die ``UNIQUE`` erzwingt
# **genau EIN Zuständiger** je (Nutzer × Quelle × Ereignis-Typ × Bereich); ``aktiv``
# entsteht AUS (fail-closed — David schaltet). Reist als Teil der Regie-Karte zum Core.
SCHEMA_AGENT_ABOS = """
CREATE TABLE IF NOT EXISTS agent_abos (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  agent_id     TEXT NOT NULL,
  quelle_app   TEXT NOT NULL,
  ereignis_typ TEXT NOT NULL,
  bereich_id   TEXT NOT NULL DEFAULT '',
  auftrag      TEXT NOT NULL DEFAULT '',
  max_pro_tag  INTEGER NOT NULL DEFAULT 20,
  aktiv        INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  deleted_at   TEXT,
  UNIQUE (user_id, quelle_app, ereignis_typ, bereich_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_abos ON agent_abos (user_id, aktiv);
"""

#: Manifest-Sensitivität DIESER App (Dizz Management = hoch ⇒ lokal_only). Die
#: WIRKSAME Sensitivität eines Regie-Agenten ist ``max(App, Agent)`` (Manifest-Schalter
#: unantastbar) — genau dieser Wert reist als ``agent_sens`` zum Core und gatet dort
#: ``ereignis_zustellbar`` fail-closed (docs/83 §1.2 / [A-9]).
MANAGEMENT_SENS = "hoch"

# Lebenszyklus einer Agent-Definition (Library-Tab P1 braucht ihn; Soft-Delete-Hausmuster).
AGENT_STATUS = ("entwurf", "aktiv", "pausiert")

# Wirksame Sensitivität = max(App, Agent): ein Agent darf STRENGER sein, nie lockerer
# (Manifest-Schalter bleibt unantastbar). Aufsteigend streng — Index = Strenge.
SENSITIVITAETEN = ("normal", "hoch", "höchst")

# --- Autonomie-Treppe (RG-4, docs/83 §3) -----------------------------------------
# Kuratierte Preset-Folge ÜBER der Klassen-Matrix — KEINE neue Achse: die Matrix bleibt
# die Wahrheit, die Treppe ist ihre begehbare UI. Jedes Preset ist per Konstruktion
# ≤ Klassen-Obergrenze (geld/gesundheit nie über pre_approval); Anheben verlangt zusätzlich
# eval_gruen (Q2) + hochsicher-Auth (HTTP), Senken/T0 ist immer erlaubt.
TREPPE_STUFEN = ("T0", "T1", "T2", "T3")
TREPPE_PRESETS: dict[str, dict[str, str]] = {
    "T0": {"entwurf": "beobachten", "aussenwirkung": "beobachten",
           "geld": "beobachten", "gesundheit": "beobachten"},
    "T1": {"entwurf": "pre_approval", "aussenwirkung": "beobachten",
           "geld": "beobachten", "gesundheit": "beobachten"},
    "T2": {"entwurf": "pre_approval", "aussenwirkung": "pre_approval",
           "geld": "pre_approval", "gesundheit": "pre_approval"},
    "T3": {"entwurf": "autonom_audit", "aussenwirkung": "monitored",
           "geld": "pre_approval", "gesundheit": "pre_approval"},
}
TREPPE_LABEL = {"T0": "beobachten", "T1": "vorschlagen",
                "T2": "mit Freigabe handeln", "T3": "autonom in engen Grenzen"}

# --- Auto-Rückstufung (RG-4, docs/83 §3) — messbare Trigger, Einzel-Nutzer [A-8] --
RUECKSTUFUNG_ABLEHN_FENSTER = 10     # „letzte 10 Inbox-Entscheidungen"
RUECKSTUFUNG_ABLEHN_SCHWELLE = 3     # ≥3 Ablehnungen im Fenster ⇒ Trigger
RUECKSTUFUNG_FEHLER_QUOTE = 0.5      # Lauf-Fehlerquote >50% im Tagesfenster
RUECKSTUFUNG_MIN_LAEUFE = 2          # …ab mind. 2 Läufen (ein Fluke stuft nicht zurück)


def rueckstufung_noetig(*, ablehnungen: int = 0, entscheidungen: int = 0,
                        lauf_fehler: int = 0, laeufe: int = 0,
                        invarianten_verstoss: bool = False) -> tuple[bool, str]:
    """Auto-Rückstufungs-Trigger (docs/83 §3, pure + messbar): (True, Klartext-Grund),
    sobald EINER zutrifft — in Prioritäts-Reihenfolge:

    1. **JEDER Invarianten-Verstoß** (Versuch auf nicht gewährtes Tool / Anhebe-Versuch
       geld|gesundheit) ⇒ sofort.
    2. **Ablehnungsquote** ``ablehnungen`` ≥ 3 der letzten 10 Inbox-Entscheidungen zu
       diesem Agenten (der Aufrufer zählt im Fenster).
    3. **Lauf-Fehlerquote** > 50 % im Tagesfenster (ab ``RUECKSTUFUNG_MIN_LAEUFE`` Läufen,
       damit ein einzelner Fehlschlag nicht gleich zurückstuft).

    Sonst (False, ''). Die Metriken sind INPUT (der Aufrufer beschafft sie aus Inbox-
    Entscheidungen/Läufen) — so bleibt der Trigger prüfbar und deterministisch."""
    if invarianten_verstoss:
        return (True, "Invarianten-Verstoß (nicht gewährtes Tool / Anhebe-Versuch "
                      "geld|gesundheit)")
    if ablehnungen >= RUECKSTUFUNG_ABLEHN_SCHWELLE:
        fenster = min(max(entscheidungen, ablehnungen), RUECKSTUFUNG_ABLEHN_FENSTER)
        return (True, f"Ablehnungsquote {ablehnungen}/{fenster} "
                      f"(≥{RUECKSTUFUNG_ABLEHN_SCHWELLE} der letzten "
                      f"{RUECKSTUFUNG_ABLEHN_FENSTER} Entscheidungen)")
    if laeufe >= RUECKSTUFUNG_MIN_LAEUFE and lauf_fehler / laeufe > RUECKSTUFUNG_FEHLER_QUOTE:
        return (True, f"Lauf-Fehlerquote {lauf_fehler}/{laeufe} > "
                      f"{int(RUECKSTUFUNG_FEHLER_QUOTE * 100)} % (Tagesfenster)")
    return (False, "")

#: Apps, deren pending-Aktionen die Netz-Inbox aggregiert (docs/63 §2). Quelle =
#: kanonisches Verzeichnis (appkit.netz); OHNE ``tradingbot`` (read-only-Gesetz, NIE
#: angeschlossen, §0/§9) und OHNE ``management`` selbst (das liest seine eigene DB direkt,
#: kein Self-HTTP → kein Event-Loop-Deadlock).
INBOX_POLL_APPS: tuple[NetzApp, ...] = tuple(
    a for a in NETZ_APPS if a.id not in ("tradingbot", "management"))

#: Fetcher-Signatur: (NetzApp) → Liste roher pending-Aktionszeilen (wie ``listing()``).
#: Wirft bei Offline/Timeout ⇒ die App landet EHRLICH in ``apps_offline`` (nie still leer).
InboxFetch = Callable[[NetzApp], list[dict[str, Any]]]


def _default_inbox_fetch(app: NetzApp) -> list[dict[str, Any]]:
    """Read-only-Poll der pending-Aktionen einer App über localhost (docs/63 §2 —
    Management pollt, führt NICHTS aus). Kurzer Timeout; Connection-refused/Timeout
    wirft ⇒ App gilt als offline. Server-seitig (kein Browser ⇒ kein CORS); Approve/
    Reject laufen später Browser-direkt an die besitzende App (Enforcement bleibt dort)."""
    req = UrlRequest(f"{app.url}/api/actions?status=pending",
                     headers={"Accept": "application/json"})
    with urlopen(req, timeout=1.5) as resp:                # noqa: S310 (localhost, fixe URL)
        data = json.loads(resp.read().decode("utf-8"))
    return list(data.get("liste", []))


# --- Eichungs-Poll (RG-5, docs/83 §4): Management misst, eigener Cursor -----------
#: Golden-/Injection-Gate als Management-Setting (fail-closed False): erst wenn die
#: Golden-Suite (apps/core/tests/eval/) bestätigt grün ist, DARF eine Eichung überhaupt
#: grün werden (deploy-/CI-gesetzt, bewusster Akt — nichts geht eigenmächtig live). Bis
#: dahin bleibt jede Ampel ungrün, egal wie gut die Betriebs-Metriken sind (Leitplanke).
EICHUNG_GOLDEN_SETTING = "eval_golden_gruen"

#: Spine-Quellen des Eichungs-Polls = dieselben Apps wie die Netz-Inbox (ohne
#: tradingbot/management). Jede emittiert netzweit ``hitl_entschieden`` (Ground-Truth);
#: Apps ohne Spine antworten 404 ⇒ ehrlich „offline" (nie still leer).
EICHUNG_QUELLEN: tuple[str, ...] = tuple(a.id for a in INBOX_POLL_APPS)


def _default_eichung_fetch(quelle_app: str, seit: int) -> list[dict[str, Any]]:
    """Read-only-Pull der Spine-Ereignisse einer App ab ``seit`` (docs/83 §4 — Management
    MISST, führt NICHTS aus). Kurzer Timeout; refused/Timeout/404 wirft ⇒ die Quelle gilt
    als offline (der Poll überspringt sie ehrlich). Server-seitig (localhost, kein CORS)."""
    eintrag = netz_app(quelle_app)
    if eintrag is None:
        raise ValueError(f"Unbekannte Spine-Quelle: {quelle_app}")
    req = UrlRequest(f"{eintrag.url}/api/ereignisse?seit={int(seit)}&limit=1000",
                     headers={"Accept": "application/json"})
    with urlopen(req, timeout=1.5) as resp:                # noqa: S310 (localhost, fixe URL)
        data = json.loads(resp.read().decode("utf-8"))
    return list(data.get("eintraege", []))


class CoreClient:
    """Schmaler Client zur Core-Ausführungs-API (Z4.2-D, docs/63 §3). Management BESITZT die
    Definition und ruft Core **server-seitig** (localhost, kein Browser-CORS) — das IST die
    Definition-Brücke (Mgmt pusht den Snapshot, Core führt aus), NICHT der verbotene Proxy:
    der §2-Proxy galt dem *Approve* (Enforcement bleibt bei der besitzenden App); Läufe
    starten/ansehen/stoppen hat keine solche Enforcement-Grenze — Core bleibt der einzige
    Ausführende + Halter der Lauf-DB. Injizierbar ⇒ der Test ersetzt ihn ohne HTTP/Ollama."""

    def __init__(self, base_url: str = CORE_URL) -> None:
        self.base = base_url.rstrip("/")

    async def laeufe(self, status: str = "") -> list[dict[str, Any]]:
        import httpx
        params = {"status": status} if status else {}
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{self.base}/api/agenten/laeufe", params=params)
            r.raise_for_status()
            return r.json()

    async def stop(self, lauf_id: str) -> dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.post(f"{self.base}/api/agenten/lauf/{lauf_id}/stop")
            r.raise_for_status()
            return r.json()

    async def regie_karte_push(self, karte: dict[str, Any]) -> dict[str, Any]:
        """Pusht die Regie-Karte (Abos + Agent-Wald + agent_sens) an den Core (RG-3b,
        docs/83 §2) — die Definition-Brücke der reaktiven Regie: Management BESITZT die
        Regie-Konfig, Core hält die Arbeitskopie (KEIN Core→Mgmt-Fetch). Kurzer Timeout;
        wirft bei Core-offline (der Aufrufer meldet es ehrlich, nie still)."""
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.post(f"{self.base}/api/agenten/regie-karte", json=karte)
            r.raise_for_status()
            return r.json()

    async def regie_status(self) -> dict[str, Any]:
        """Liest den Regie-Status vom Core (Master-Schalter, Tick, Zünd-Zähler, RG-3b)."""
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{self.base}/api/agenten/regie/status")
            r.raise_for_status()
            return r.json()

    async def regie_schalter(self, aktiv: bool) -> dict[str, Any]:
        """Setzt den Not-Aus-Master-Schalter am Core (docs/83 §3). Ausschalten immer,
        Einschalten = gegatete Live-Vorbedingung (G-REGIE-LIVE)."""
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.post(f"{self.base}/api/agenten/regie/schalter",
                             json={"aktiv": bool(aktiv)})
            r.raise_for_status()
            return r.json()

    async def lauf_stream(self, snapshot: dict[str, Any],
                          auftrag: str) -> AsyncIterator[bytes]:
        """Streamt den Core-SSE-Lauf durch (Live-Log). ``timeout=None``: ein Lauf darf
        länger dauern als ein normaler Request (Token-für-Token)."""
        import httpx
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("POST", f"{self.base}/api/agenten/lauf",
                                json={"snapshot": snapshot, "auftrag": auftrag}) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk


# --- Normalisierung (deny-by-default / fail-closed beim Schreiben) ----------------

def _clean_werkzeuge(werte: Any) -> list[str]:
    """Tool-Grants: Liste nicht-leerer Namen, Duplikate raus, Reihenfolge erhalten.
    Der WIRKSAME Filter gegen den verfügbaren Katalog ist ``werkzeuge_filter``
    (Laufzeit/Karte) — hier wird nur der Roh-Grant sauber abgelegt."""
    out: list[str] = []
    for w in werte or []:
        s = str(w).strip()
        if s and s not in out:
            out.append(s)
    return out


def _clean_sub_agenten(werte: Any) -> list[str]:
    out: list[str] = []
    for s in werte or []:
        v = str(s).strip()
        if v and v not in out:
            out.append(v)
    return out


def _clean_autonomie(werte: Any) -> dict[str, str]:
    """Nur bekannte (Klasse→Stufe)-Paare überleben (deny-by-default). geld/gesundheit
    dürfen hier stehen, werden aber von ``wirksame_stufe`` IMMER auf pre_approval
    gebodet — die Speicherung ist harmlos, die Auflösung ist fail-closed (§4)."""
    out: dict[str, str] = {}
    for k, v in (werte or {}).items():
        if k in ag.AKTIONS_KLASSEN and v in ag.AUTONOMIE_STUFEN:
            out[k] = v
    return out


def _clean_budget(werte: Any) -> dict[str, int]:
    """Budget = AgentBudget-Defaults, überschrieben von gültigen Ganzzahlen (>0).
    Runaway-Schutz gehört in die Entität, damit die Karte ihn zeigt (P7)."""
    base = asdict(ag.AgentBudget())
    for k in base:
        if werte and k in werte:
            try:
                n = int(werte[k])
            except (TypeError, ValueError):
                continue
            if n > 0:
                base[k] = n
    return base


def _norm(wert: str, erlaubt: tuple[str, ...], default: str) -> str:
    return wert if wert in erlaubt else default


# --- Request-Modelle: MODUL-Ebene zwingend (PEP-563-Falle, s. domain.py) ----------

class AgentIn(BaseModel):
    name: str
    rolle: str = ""
    system_prompt: str = ""
    task_klasse: str = "chat"
    modell_explizit: str = ""
    werkzeuge: list[str] = []
    sub_agenten: list[str] = []
    bereich_id: str = ""
    sensitivitaet: str = "hoch"
    autonomie: dict[str, str] = {}
    budget: dict[str, int] = {}
    status: str = "entwurf"


class AgentPatch(BaseModel):
    name: str | None = None
    rolle: str | None = None
    system_prompt: str | None = None
    task_klasse: str | None = None
    modell_explizit: str | None = None
    werkzeuge: list[str] | None = None
    sub_agenten: list[str] | None = None
    bereich_id: str | None = None
    sensitivitaet: str | None = None
    autonomie: dict[str, str] | None = None
    budget: dict[str, int] | None = None
    status: str | None = None


class AutonomieIn(BaseModel):
    bereich_id: str = ""
    klasse: str
    stufe: str


class LaufStartIn(BaseModel):
    auftrag: str = ""


class AboIn(BaseModel):
    """Neues Abo (RG-3b): bindet ``agent_id`` an den Ereignis-Strom
    ``quelle_app × ereignis_typ`` (optional bereichs-scharf). ``aktiv`` entsteht AUS."""
    agent_id: str
    quelle_app: str
    ereignis_typ: str
    bereich_id: str = ""
    auftrag: str = ""
    max_pro_tag: int = 20
    aktiv: bool = False


class AboPatch(BaseModel):
    """Änderbar sind Zuordnungs-Agent, 1-Satz-Auftrag, Tages-Deckel, Aktiv-Schalter.
    Die Strom-Identität (quelle_app/ereignis_typ/bereich_id) ist NICHT patchbar —
    ein anderer Strom ist ein anderes Abo (löschen + neu, UNIQUE bleibt sauber)."""
    agent_id: str | None = None
    auftrag: str | None = None
    max_pro_tag: int | None = None
    aktiv: bool | None = None


class TreppeIn(BaseModel):
    """Treppen-Preset auf einen Bereich anwenden (T0–T3, docs/83 §3)."""
    bereich_id: str = ""
    treppe: str


class RueckstufenIn(BaseModel):
    """Auto-Rückstufungs-Prüfung: die messbaren Trigger-Metriken (der Aufrufer beschafft
    sie aus Inbox-Entscheidungen/Läufen). Ohne Werte ⇒ kein Trigger (nichts passiert)."""
    ablehnungen: int = 0
    entscheidungen: int = 0
    lauf_fehler: int = 0
    laeufe: int = 0
    invarianten_verstoss: bool = False


class RegieSchalterIn(BaseModel):
    """Not-Aus-Master-Schalter (docs/83 §3): Einschalten = gegatete Live-Vorbedingung."""
    aktiv: bool


class AgentenDomaene:
    """Definitions-Schicht der Agenten-Regie (Management-DB). Baut einen Router
    ``/api/agenten`` + den Baum-Wächter + die Netz-Inbox-Aggregation; keine
    Ausführung (Z4.2, Core), kein Approve/Reject (das läuft Browser-direkt an die
    besitzende App, §2). ``registry`` = die eigene K4-Registry (own pending direkt aus
    der DB); ``inbox_fetch`` = injizierbarer Poll der anderen Apps (Test/Prod)."""

    def __init__(self, db: Database, registry: ActionRegistry | None = None,
                 inbox_fetch: InboxFetch | None = None,
                 core_client: CoreClient | None = None,
                 event_push: Any = None,
                 eichung_fetch: "eich.EichungFetch | None" = None) -> None:
        self.db = db
        self.registry = registry
        self.inbox_fetch = inbox_fetch or _default_inbox_fetch
        # Eichungs-Poll (RG-5): read-only Spine-Pull je Quelle (eigener Cursor). Injizierbar
        # (Test = Fake-Spine; Produktion = HTTP an /api/ereignisse der Quell-Apps).
        self.eichung_fetch = eichung_fetch or _default_eichung_fetch
        # Ausführungs-Brücke zum Core (Z4.2-D): Läufe starten/listen/stoppen. Injizierbar.
        self.core = core_client or CoreClient()
        # Glocke der Auto-Rückstufung (RG-4) — injizierbar (Test = Spy; Produktion =
        # appkit.events.push_event an die Core-Meldungs-Glocke, best-effort).
        self._event_push = event_push or events.push_event

    # --- Projektion ---------------------------------------------------------
    @staticmethod
    def _agentdef(row) -> ag.AgentDef:
        """Baut die Vertrags-Entität aus einer DB-Zeile (für Projektionen)."""
        b = json.loads(row["budget"] or "{}")
        budget = ag.AgentBudget(**{k: b[k] for k in asdict(ag.AgentBudget()) if k in b})
        return ag.AgentDef(
            id=row["id"], name=row["name"], rolle=row["rolle"],
            system_prompt=row["system_prompt"], task_klasse=row["task_klasse"],
            modell_explizit=row["modell_explizit"],
            werkzeuge=tuple(json.loads(row["werkzeuge"] or "[]")),
            sub_agenten=tuple(json.loads(row["sub_agenten"] or "[]")),
            bereich_id=row["bereich_id"], sensitivitaet=row["sensitivitaet"],
            autonomie=json.loads(row["autonomie"] or "{}"), budget=budget,
            status=row["status"])

    def _public(self, row) -> dict[str, Any]:
        """Voll-Serialisierung (Roh-Felder zum Editieren + ``karte``-Projektion P2).
        Die Karte zeigt die WIRKSAMEN Tools; v1-Katalog = die Roh-Grants des Agenten
        (bis der MCP-Katalog §4/Z4.2 den echten verfügbaren Katalog liefert, filtert
        ``werkzeuge_filter`` dann Unverfügbares heraus — ohne die Karte anzufassen)."""
        a = self._agentdef(row)
        return {
            "id": a.id, "name": a.name, "rolle": a.rolle,
            "system_prompt": a.system_prompt, "task_klasse": a.task_klasse,
            "modell_explizit": a.modell_explizit, "werkzeuge": list(a.werkzeuge),
            "sub_agenten": list(a.sub_agenten), "bereich_id": a.bereich_id,
            "sensitivitaet": a.sensitivitaet, "autonomie": dict(a.autonomie),
            "budget": asdict(a.budget), "status": a.status,
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "karte": ag.agent_karte(a, werkzeug_katalog=a.werkzeuge),
        }

    # --- Definition-Brücke (docs/63 §1/§8): Snapshot aus dem Wald ------------
    def schnappschuss(self, user_id: str, agent_id: str) -> dict[str, Any] | None:
        """Löst den Agenten + seinen erreichbaren Sub-Baum aus dem Wald (Management-DB) zu
        einem JSON-Snapshot auf, den Core beim Lauf-Start AUSFÜHRT — Management BESITZT die
        Definition und PUSHT sie (KEIN Core→Mgmt-Fetch). Form identisch zu
        ``agenten_laeufe.schnappschuss`` (``{"wurzel": id, "agenten": {id: AgentDef-dict}}``);
        Reuse/Zyklen sind egal (``gesehen``), fehlende Sub-IDs gelten als Blatt. ``None`` =
        Wurzel-Agent unbekannt/gelöscht."""
        conn = self.db.get_conn()

        def _laden(aid: str) -> ag.AgentDef | None:
            row = conn.execute("SELECT * FROM agenten WHERE id=? AND user_id=? "
                               "AND deleted_at IS NULL", (aid, user_id)).fetchone()
            return self._agentdef(row) if row is not None else None

        wurzel = _laden(agent_id)
        if wurzel is None:
            return None
        gesehen: dict[str, Any] = {}

        def _geh(a: ag.AgentDef) -> None:
            if a.id in gesehen:
                return
            gesehen[a.id] = asdict(a)
            for sid in a.sub_agenten:
                w = _laden(sid)
                if w is not None:
                    _geh(w)

        _geh(wurzel)
        return {"wurzel": wurzel.id, "agenten": gesehen}

    # --- Baum-Wächter beim Schreiben (docs/63 §1/§3) ------------------------
    def _pruefe_baum(self, user_id: str, agent_id: str,
                     sub_agenten: list[str]) -> None:
        """Prüft den GESAMTEN Agenten-Wald des Nutzers nach der geplanten Änderung:
        Tiefe ≤ ``MAX_EBENEN`` und zyklenfrei. Validiert von JEDEM Agenten als Wurzel —
        das deckt auch Verstöße ab, die relativ zu einem ANDEREN Orchestrator entstehen
        (z. B. Worker so vertiefen, dass ein Vorfahre auf Ebene 4 gerät). Fehlende
        Sub-Agenten-IDs gelten als Blatt (Entwurf-Reihenfolge egal). Verstoß ⇒ 422."""
        conn = self.db.get_conn()
        kinder: dict[str, list[str]] = {}
        for r in conn.execute(
                "SELECT id, sub_agenten FROM agenten WHERE user_id=? AND deleted_at IS NULL",
                (user_id,)).fetchall():
            if r["id"] != agent_id:
                kinder[r["id"]] = json.loads(r["sub_agenten"] or "[]")
        kinder[agent_id] = sub_agenten
        try:
            for wurzel in kinder:
                ag.validiere_agentenbaum(wurzel, kinder)
        except ValueError as e:
            raise HTTPException(422, str(e))

    # --- Bereichs-Autonomie-Matrix (docs/63 §4/P4 + V-1 docs/83 §3) ---------
    def bereich_stufe(self, user_id: str, bereich_id: str, klasse: str) -> str:
        """Gespeicherte Bereichs-Stufe für (Bereich × Klasse) oder ``beobachten``
        (V-1 fail-closed Default — die neue Null: unkonfiguriert heißt Zuschauen). Das
        ist der ``bereich_stufe``-Eingang für ``wirksame_stufe`` (Z4.2-C liest ihn VOR
        jeder Ausführung)."""
        row = self.db.get_conn().execute(
            "SELECT stufe FROM agent_bereich_autonomie WHERE user_id=? AND bereich_id=? "
            "AND klasse=? AND deleted_at IS NULL", (user_id, bereich_id, klasse)).fetchone()
        return row["stufe"] if row and row["stufe"] in ag.AUTONOMIE_STUFEN else "beobachten"

    def autonomie_matrix(self, user_id: str, bereich_id: str) -> list[dict[str, Any]]:
        """Volle Matrix-Zeile je Aktions-Klasse (feste Reihenfolge): aktuelle Stufe +
        ``gesperrt`` (geld/gesundheit = auf pre_approval GEDECKELT, sichtbar mit Schloss
        statt versteckt, P4) + ``kappe`` (die Obergrenze). V-1: Default aller Klassen ist
        ``beobachten``; geld/gesundheit dürfen ``beobachten``/``pre_approval``, nie höher."""
        out = []
        for klasse in ag.AKTIONS_KLASSEN:
            gesperrt = klasse in ag.KLASSEN_BODEN
            kappe = ag.KLASSEN_BODEN.get(klasse, ag.AUTONOMIE_STUFEN[-1])
            out.append({"klasse": klasse,
                        "stufe": self.bereich_stufe(user_id, bereich_id, klasse),
                        "gesperrt": gesperrt, "kappe": kappe,
                        "grund": ("geld/gesundheit: gedeckelt auf pre_approval — "
                                  "beobachten (strenger) erlaubt, höher nie (VO-3 fail-closed)"
                                  if gesperrt else "")})
        return out

    def autonomie_setzen(self, user_id: str, bereich_id: str, klasse: str,
                         stufe: str) -> dict[str, Any]:
        """Speichert eine Bereichs-Stufe. Fail-closed: unbekannte Klasse/Stufe ⇒ 400;
        über die Klassen-Obergrenze ⇒ 422 (geld/gesundheit nie über pre_approval — kein
        UI-Bug lockert das, VO-3; ``beobachten`` STRENGER ist für sie erlaubt, V-1)."""
        if klasse not in ag.AKTIONS_KLASSEN:
            raise HTTPException(400, f"Unbekannte Aktions-Klasse: {klasse!r}.")
        if stufe not in ag.AUTONOMIE_STUFEN:
            raise HTTPException(400, f"Unbekannte Autonomie-Stufe: {stufe!r}.")
        if ag.stufe_ueber_kappe(klasse, stufe):
            raise HTTPException(422, f"'{klasse}' ist auf 'pre_approval' gedeckelt "
                                     "(beobachten strenger erlaubt, höher nie — VO-3).")
        conn = self.db.get_conn()
        ts = now_iso()
        conn.execute(
            "INSERT INTO agent_bereich_autonomie (id, user_id, bereich_id, klasse, stufe, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT (user_id, bereich_id, klasse) DO UPDATE SET "
            "stufe=excluded.stufe, updated_at=excluded.updated_at, deleted_at=NULL",
            (new_id(), user_id, bereich_id, klasse, stufe, ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "agent_autonomie_gesetzt",
                      {"bereich_id": bereich_id, "klasse": klasse, "stufe": stufe})
        return {"ok": True, "bereich_id": bereich_id, "klasse": klasse, "stufe": stufe}

    # --- Autonomie-Treppe: begehbare Preset-Folge über der Matrix (docs/83 §3) --
    def treppe_erkennen(self, user_id: str, bereich_id: str) -> str:
        """Erkennt die aktuelle Treppen-Stufe eines Bereichs, indem die Ist-Matrix gegen
        die Presets gematcht wird. ``''`` = eigene Kombination (nicht auf einer Stufe).
        Ein frischer Bereich (alles beobachten) steht auf T0."""
        ist = {k: self.bereich_stufe(user_id, bereich_id, k) for k in ag.AKTIONS_KLASSEN}
        for t in TREPPE_STUFEN:
            if all(ist[k] == TREPPE_PRESETS[t][k] for k in ag.AKTIONS_KLASSEN):
                return t
        return ""

    def treppe_anwenden(self, user_id: str, bereich_id: str, treppe: str) -> dict[str, Any]:
        """Wendet ein Treppen-Preset (T0–T3) auf die Bereichs-Matrix an — schreibt alle
        vier Klassen-Zeilen (jede ≤ Obergrenze, ``autonomie_setzen`` erzwingt es). Die
        Treppe ist NUR die begehbare UI der Matrix, kein zweiter Speicher (docs/83 §3).
        Anheben ist damit ein bewusster Nutzer-Akt (Auth-Gate an der HTTP-Schicht); die
        wirksame Lockerung über pre_approval greift ohnehin erst mit eval_gruen (Q2)."""
        if treppe not in TREPPE_PRESETS:
            raise HTTPException(400, f"Unbekannte Treppen-Stufe: {treppe!r} "
                                     f"(erlaubt: {', '.join(TREPPE_STUFEN)}).")
        for klasse, stufe in TREPPE_PRESETS[treppe].items():
            self.autonomie_setzen(user_id, bereich_id, klasse, stufe)
        self.db.audit(user_id, "user", "agent_treppe_gesetzt",
                      {"bereich_id": bereich_id, "treppe": treppe})
        return {"ok": True, "bereich_id": bereich_id, "treppe": treppe,
                "matrix": self.autonomie_matrix(user_id, bereich_id)}

    # --- Auto-Rückstufung: Rückholbarkeit in Sekunden (docs/83 §3) ----------
    def rueckstufen(self, user_id: str, agent_id: str, grund: str, *,
                    event_push: Any = None) -> dict[str, Any]:
        """Stuft einen Agenten SOFORT auf T0 (alle Klassen ``beobachten``) zurück —
        Automatik darf senken, nie heben (Selbst-Check 2). Setzt die Agenten-``autonomie``
        auf T0, schreibt ein Audit-Ereignis MIT WARUM (Trigger-Metrik im Klartext) und
        meldet die Glocke (warn). Der eval_gruen-Entzug ist in RG-4 ein No-op (eval_gruen
        ist netzweit noch hart False; RG-5 verdrahtet ``agent_evals`` — dann erlischt die
        Grün-Marke hier mit)."""
        conn = self.db.get_conn()
        row = conn.execute("SELECT id FROM agenten WHERE id=? AND user_id=? "
                           "AND deleted_at IS NULL", (agent_id, user_id)).fetchone()
        if row is None:
            raise HTTPException(404, f"Agent nicht gefunden: {agent_id}")
        t0 = dict(TREPPE_PRESETS["T0"])                  # alle Klassen beobachten
        conn.execute("UPDATE agenten SET autonomie=?, updated_at=? WHERE id=? AND user_id=?",
                     (json.dumps(t0, ensure_ascii=False), now_iso(), agent_id, user_id))
        conn.commit()
        self.db.audit(user_id, "system", "agent_rueckgestuft",
                      {"agent_id": agent_id, "treppe": "T0", "grund": grund})
        push = event_push or self._event_push
        try:                                              # Glocke best-effort (nie den Pfad kippen)
            push("management", "warn", f"Agent auf T0 zurückgestuft: {grund}",
                 {"agent_id": agent_id, "grund": grund})
        except Exception:
            pass
        return {"ok": True, "agent_id": agent_id, "treppe": "T0", "grund": grund}

    def pruefe_und_rueckstufe(self, user_id: str, agent_id: str, *, ablehnungen: int = 0,
                              entscheidungen: int = 0, lauf_fehler: int = 0, laeufe: int = 0,
                              invarianten_verstoss: bool = False,
                              event_push: Any = None) -> dict[str, Any]:
        """Prüft die Auto-Rückstufungs-Trigger (messbar) und stuft nur bei Bedarf zurück.
        Die Metriken sind INPUT (der Aufrufer beschafft sie aus Inbox-Entscheidungen und
        Läufen) — so ist die Governance-Regel prüfbar. ``rueckgestuft=False`` ⇒ nichts."""
        noetig, grund = rueckstufung_noetig(
            ablehnungen=ablehnungen, entscheidungen=entscheidungen, lauf_fehler=lauf_fehler,
            laeufe=laeufe, invarianten_verstoss=invarianten_verstoss)
        if not noetig:
            return {"rueckgestuft": False, "agent_id": agent_id}
        return {"rueckgestuft": True, **self.rueckstufen(user_id, agent_id, grund,
                                                          event_push=event_push)}

    # --- Netz-Inbox-Aggregation (docs/63 §2, Z4.1-D) ------------------------
    @staticmethod
    def _projekt(app_id: str, url: str, brand: str,
                 aktion: dict[str, Any]) -> dict[str, Any]:
        """inbox_eintrag-Projektion + Herkunfts-URL (Browser braucht sie, um Approve/
        Reject DIREKT an die besitzende App zu schicken — Management proxyt nie, §2)."""
        e = ag.inbox_eintrag(app_id, aktion, aktion.get("level", "verifiziert"))
        e["app_url"] = url
        e["app_brand"] = brand
        return e

    def agent_inbox(self, user_id: str) -> dict[str, Any]:
        """Netzweite Aggregation der pending-Aktionen (READ-ONLY). Eigene Aktionen aus
        der DB, fremde per read-only-Poll; Offline-Apps EHRLICH benannt (nie still leer,
        Health-Watch-Regel). Agent-originierte Einträge zuerst (die Agenten-Regie-Sicht).
        Führt NICHTS aus — Approve/Reject laufen Browser-direkt an die besitzende App."""
        eintraege: list[dict[str, Any]] = []
        apps_offline: list[str] = []
        if self.registry is not None:      # eigene pending-Aktionen ohne Self-HTTP
            for a in listing(self.db, user_id, self.registry, status="pending"):
                eintraege.append(self._projekt("management", "", "Dizz Management", a))
        for app in INBOX_POLL_APPS:        # andere Apps read-only pollen
            try:
                zeilen = self.inbox_fetch(app)
            except (URLError, OSError, ValueError, TimeoutError):
                apps_offline.append(app.id)
                continue
            for a in zeilen:
                eintraege.append(self._projekt(app.id, app.url, app.brand, a))
        # agent-originierte zuerst (agent_id gesetzt), dann nach Zeit (älteste zuerst).
        eintraege.sort(key=lambda e: (e.get("agent_id", "") == "", e.get("created_at", "")))
        return {"eintraege": eintraege, "apps_offline": apps_offline}

    # --- Abos + Regie-Karte (RG-3b, docs/83 §2): reaktive Regie --------------
    @staticmethod
    def _abo_public(row) -> dict[str, Any]:
        return {"id": row["id"], "agent_id": row["agent_id"],
                "quelle_app": row["quelle_app"], "ereignis_typ": row["ereignis_typ"],
                "bereich_id": row["bereich_id"], "auftrag": row["auftrag"],
                "max_pro_tag": row["max_pro_tag"], "aktiv": bool(row["aktiv"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def abo_liste(self, user_id: str) -> list[dict[str, Any]]:
        """Alle Abos des Nutzers (Ereignis-Strom → Zuständiger), stabil sortiert."""
        rows = self.db.get_conn().execute(
            "SELECT * FROM agent_abos WHERE user_id=? AND deleted_at IS NULL "
            "ORDER BY quelle_app, ereignis_typ, bereich_id", (user_id,)).fetchall()
        return [self._abo_public(r) for r in rows]

    @staticmethod
    def _wirksame_sens(deklariert: str) -> str:
        """Wirksame Sensitivität eines Regie-Agenten = strenger(App, Agent): die App
        (Management) ist ``hoch``, ein Agent darf strenger (``höchst``) sein, nie
        lockerer (max-Regel, Manifest unantastbar, [A-9]). Genau dieser Wert gatet im
        Core ``ereignis_zustellbar`` fail-closed (docs/83 §1.2)."""
        def rang(s: str) -> int:
            return SENSITIVITAETEN.index(s) if s in SENSITIVITAETEN else len(SENSITIVITAETEN) - 1
        return SENSITIVITAETEN[max(rang(MANAGEMENT_SENS), rang(deklariert))]

    def regie_karte(self, user_id: str) -> dict[str, Any]:
        """Baut die Regie-Karte für den Core-Push (docs/83 §2 + §4): alle Abos + der
        aufgelöste Agent-Wald (jeder abonnierte Orchestrator + sein erreichbarer
        Sub-Baum, dedupliziert) + ``agent_sens`` (wirksame Sensitivität je Agent) +
        **RG-5**: ``eval_status`` (je Agent × Klasse ``{gruen, def_hash}`` — das echte
        ``eval_gruen``, das der Core in ``wirksame_stufe`` einsetzt, bereits def_hash-/
        Ablauf-gegated) + ``bereich_stufen`` (je Agent × Klasse die Bereichs-Kappe seines
        Bereichs — die Core-seitige ``bereich_stufe``, die W1 offen ließ). Reine Projektion
        (kein Seiteneffekt); ``_push_karte`` reicht sie an den Core."""
        jetzt = now_iso()
        abos = self.abo_liste(user_id)
        agenten: dict[str, Any] = {}
        for aid in {a["agent_id"] for a in abos}:
            snap = self.schnappschuss(user_id, aid)
            if snap is not None:
                agenten.update(snap["agenten"])         # Wälder mergen (Reuse egal)
        agent_sens = {aid: self._wirksame_sens(d.get("sensitivitaet", "hoch"))
                      for aid, d in agenten.items()}
        def_hashes = self._alle_def_hashes(user_id)
        wald_hashes = {aid: def_hashes[aid] for aid in agenten if aid in def_hashes}
        eval_status = ev.eval_status_fuer_karte(self.db, user_id, wald_hashes, jetzt_iso=jetzt)
        bereich_stufen = {
            aid: {k: self.bereich_stufe(user_id, d.get("bereich_id", ""), k)
                  for k in ag.AKTIONS_KLASSEN}
            for aid, d in agenten.items()}
        return {"abos": abos, "agenten": agenten, "agent_sens": agent_sens,
                "eval_status": eval_status, "bereich_stufen": bereich_stufen,
                "pushed_at": jetzt}

    async def _push_karte(self, user_id: str) -> bool:
        """Pusht die aktuelle Regie-Karte best-effort an den Core (nach jedem Abo-Edit,
        docs/83 §2). Core offline ⇒ False (der Edit gilt trotzdem; die Karte reist beim
        nächsten Edit oder per explizitem Push). Wirft NIE in den CRUD-Pfad."""
        try:
            await self.core.regie_karte_push(self.regie_karte(user_id))
            return True
        except Exception:
            return False

    # --- Eichungs-Poll (RG-5, docs/83 §4): Management misst -----------------
    def _alle_def_hashes(self, user_id: str) -> dict[str, str]:
        """Agent-ID → Hash der AKTUELLEN Definition (``definitions_hash``) für alle
        lebenden Agenten. Das Frische-Gate der Eichung: jeder Prompt-/Tool-/Modell-/
        Budget-Edit ändert den Hash ⇒ die Eichung erlischt sofort (docs/83 §4)."""
        out: dict[str, str] = {}
        for row in self.db.get_conn().execute(
                "SELECT * FROM agenten WHERE user_id=? AND deleted_at IS NULL",
                (user_id,)).fetchall():
            out[row["id"]] = ag.definitions_hash(self._agentdef(row))
        return out

    async def eichung_ausfuehren(self, user_id: str) -> dict[str, Any]:
        """Führt EINEN Eichungs-Lauf aus (docs/83 §4): pollt die Spines (eigener Cursor,
        read-only), rechnet die Eichung je (Agent × Klasse) und legt sie in ``agent_evals``
        ab. Budget-Disziplin aus den Core-Läufen (best-effort; Core offline ⇒ nicht
        gemessen), das Golden-Gate aus dem Setting (fail-closed False — bis David/CI die
        Golden-Suite bestätigt, bleibt jede Ampel ungrün). Misst nur, zündet nichts; danach
        best-effort Regie-Karte-Push, damit der Core das aufgefrischte eval_gruen sieht."""
        def_hashes = self._alle_def_hashes(user_id)
        golden = bool(self.db.setting_get(user_id, EICHUNG_GOLDEN_SETTING, False))
        try:
            budget = eich.budget_aus_laeufen(await self.core.laeufe(""))
        except Exception:
            budget = {}
        res = eich.eichung_lauf(self.db, user_id, EICHUNG_QUELLEN, self.eichung_fetch,
                                def_hashes, golden_gruen=golden, jetzt_iso=now_iso(),
                                budget_fuer=budget)
        res["gepusht"] = await self._push_karte(user_id)
        self.db.audit(user_id, "system", "agent_eichung_gepollt",
                      {"verbucht": res["verbucht"], "evals": len(res["evals"]),
                       "quellen_offline": res["quellen_offline"]})
        return res

    def eichung_uebersicht(self, user_id: str) -> list[dict[str, Any]]:
        """Alle Eichungen je Agent gruppiert, MIT Frische (``aktuell_gruen`` gegen die
        AKTUELLE Definition + ``frische``-Grund) + Agent-Name — die Eine-Fetch-Projektion
        der Eichungs-Karten (+U). Ein editierter Prompt zeigt hier sofort ``aktuell_gruen``
        False, auch wenn die gespeicherte Eichung noch grün war (ehrlich, docs/83 §4)."""
        def_hashes = self._alle_def_hashes(user_id)
        jetzt = now_iso()
        namen = {r["id"]: r["name"] for r in self.db.get_conn().execute(
            "SELECT id, name FROM agenten WHERE user_id=? AND deleted_at IS NULL",
            (user_id,)).fetchall()}
        aus: dict[str, dict[str, Any]] = {}
        for z in ev.evals_liste(self.db, user_id):
            aid = z["agent_id"]
            gueltig, grund = ev.eval_gueltig(z["def_hash"], def_hashes.get(aid, ""),
                                             z["gueltig_bis"], jetzt_iso=jetzt)
            z["aktuell_gruen"] = bool(z["gruen"]) and gueltig
            z["frische"] = grund or "aktuell"
            aus.setdefault(aid, {"agent_id": aid, "name": namen.get(aid, aid),
                                 "evals": []})["evals"].append(z)
        return list(aus.values())

    # --- Werks-Vorlagen (RG-5/RG-7, agenten_vorlagen): Domäne-Nähte per Klick --
    def _agent_aus_spec(self, conn, user_id: str, spec: dict[str, Any], ts: str,
                        sub_ids: list[str] | tuple[str, ...] = ()) -> str:
        """Legt EINEN Vorlagen-Agenten idempotent an (reuse nach Name) und liefert seine id.
        ``sub_ids`` (die zuvor angelegten Worker) landen als ``sub_agenten`` — so baut der
        E-Mail-Manager-Pilot (RG-7) seinen Orchestrator+Worker-Baum, und die Einzel-Agent-
        Vorlage (Produktionsleiter) ruft es einfach mit leerem ``sub_ids`` (Verhalten
        byte-gleich). Alle Felder laufen durch dieselben fail-closed Cleaner wie die
        Agent-CRUD (deny-by-default Grants/Autonomie, normierte Slots)."""
        row = conn.execute("SELECT id FROM agenten WHERE user_id=? AND name=? "
                           "AND deleted_at IS NULL", (user_id, spec["name"])).fetchone()
        if row is not None:
            return row["id"]
        aid = new_id()
        conn.execute(
            "INSERT INTO agenten (id, user_id, name, rolle, system_prompt, task_klasse, "
            "modell_explizit, werkzeuge, sub_agenten, bereich_id, sensitivitaet, autonomie, "
            "budget, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, user_id, spec["name"], spec.get("rolle", ""), spec.get("system_prompt", ""),
             _norm(spec.get("task_klasse", "chat"), mp.TASK_KLASSEN, "chat"), "",
             json.dumps(_clean_werkzeuge(spec.get("werkzeuge", [])), ensure_ascii=False),
             json.dumps(_clean_sub_agenten(sub_ids), ensure_ascii=False), "",
             _norm(spec.get("sensitivitaet", "hoch"), SENSITIVITAETEN, "hoch"),
             json.dumps(_clean_autonomie(spec.get("autonomie", {})), ensure_ascii=False),
             json.dumps(_clean_budget({}), ensure_ascii=False), "aktiv", ts, ts))
        conn.commit()
        self.db.audit(user_id, "user", "agent_vorlage_installiert",
                      {"id": aid, "agent": spec["name"]})
        return aid

    async def vorlage_installieren(self, user_id: str, name: str) -> dict[str, Any]:
        """Installiert eine Werks-Vorlage (Agenten-Baum + Abo, ``agenten_vorlagen``) und pusht
        die Regie-Karte. **Fail-closed:** das Abo entsteht AUS, die Autonomie ist die
        Pilot-Kappe (bzw. leer ⇒ beobachten/T0) — eine ruhende, SICHERE Naht; nichts zündet
        ohne Davids Wort (Abo aktiv + Not-Aus AN + eval_gruen + Bereichs-Treppe). Idempotent:
        erneuter Aufruf reused Agenten (nach Name) + Abo (nach Strom), nie ein Duplikat.

        Baum-Vorlagen (RG-7, ``worker``-Liste, z. B. E-Mail-Manager): die Sub-Agenten werden
        ZUERST angelegt, dann als ``sub_agenten`` an den Orchestrator gehängt (Tiefe 2 ≤ 3).
        Einzel-Agent-Vorlagen haben keinen ``worker``-Schlüssel ⇒ leere Worker-Liste."""
        v = vorlagen.vorlage(name)
        if v is None:
            raise HTTPException(404, f"Unbekannte Vorlage: {name}")
        conn = self.db.get_conn()
        ts = now_iso()
        worker_ids = [self._agent_aus_spec(conn, user_id, w, ts)
                      for w in v.get("worker", [])]
        aid = self._agent_aus_spec(conn, user_id, v["agent"], ts, sub_ids=worker_ids)
        abo = v["abo"]
        quelle, typ, bereich = abo["quelle_app"], abo["ereignis_typ"], ""
        vorhanden = conn.execute(
            "SELECT id, deleted_at FROM agent_abos WHERE user_id=? AND quelle_app=? AND "
            "ereignis_typ=? AND bereich_id=?", (user_id, quelle, typ, bereich)).fetchone()
        aktiv = 1 if abo.get("aktiv") else 0
        if vorhanden is not None and vorhanden["deleted_at"] is None:
            abo_id = vorhanden["id"]
        elif vorhanden is not None:                      # soft-gelöscht ⇒ wiederbeleben
            abo_id = vorhanden["id"]
            conn.execute("UPDATE agent_abos SET agent_id=?, auftrag=?, max_pro_tag=?, aktiv=?, "
                         "updated_at=?, deleted_at=NULL WHERE id=?",
                         (aid, abo.get("auftrag", ""), int(abo.get("max_pro_tag", 20)),
                          aktiv, ts, abo_id))
            conn.commit()
        else:
            abo_id = new_id()
            conn.execute(
                "INSERT INTO agent_abos (id, user_id, agent_id, quelle_app, ereignis_typ, "
                "bereich_id, auftrag, max_pro_tag, aktiv, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (abo_id, user_id, aid, quelle, typ, bereich, abo.get("auftrag", ""),
                 int(abo.get("max_pro_tag", 20)), aktiv, ts, ts))
            conn.commit()
            self.db.audit(user_id, "user", "agent_abo_angelegt",
                          {"id": abo_id, "agent_id": aid, "quelle_app": quelle,
                           "ereignis_typ": typ})
        return {"ok": True, "vorlage": name, "agent_id": aid, "abo_id": abo_id,
                "aktiv": bool(aktiv), "gepusht": await self._push_karte(user_id)}

    # --- Router -------------------------------------------------------------
    def build_router(self) -> APIRouter:
        r = APIRouter()
        db = self.db

        @r.get("/api/agenten/katalog")
        def katalog(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Vokabular für die Regie-UI: Aktions-Klassen · Autonomie-Stufen (+ die
            fail-closed gebodeten Klassen geld/gesundheit) · Task-Klassen (Modell-Slots) ·
            Sensitivitäten · Status · Baum-Grenze · Budget-Defaults."""
            return {
                "aktions_klassen": list(ag.AKTIONS_KLASSEN),
                "autonomie_stufen": list(ag.AUTONOMIE_STUFEN),
                "klassen_boden": dict(ag.KLASSEN_BODEN),   # geld/gesundheit gedeckelt
                "treppe_stufen": list(TREPPE_STUFEN),       # RG-4: begehbare Treppe T0–T3
                "treppe_presets": TREPPE_PRESETS,
                "treppe_labels": TREPPE_LABEL,
                "task_klassen": list(mp.TASK_KLASSEN),
                "sensitivitaeten": list(SENSITIVITAETEN),
                "status": list(AGENT_STATUS),
                "max_ebenen": ag.MAX_EBENEN,
                "budget_default": asdict(ag.AgentBudget()),
            }

        # Literal-Routen VOR /api/agenten/{aid} (sonst fängt der Platzhalter sie ab).
        @r.get("/api/agenten/autonomie")
        def autonomie_holen(bereich_id: str = "",
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Bereichs-Autonomie-Matrix (P4) für einen Bereich ('' = Allgemein)."""
            return {"bereich_id": bereich_id.strip(),
                    "matrix": self.autonomie_matrix(user.user_id, bereich_id.strip())}

        @r.put("/api/agenten/autonomie")
        def autonomie_setzen_ep(body: AutonomieIn,
                                user: UserContext = Depends(current_user)) -> dict[str, Any]:
            return self.autonomie_setzen(user.user_id, body.bereich_id.strip(),
                                         body.klasse, body.stufe)

        # --- Autonomie-Treppe (RG-4, docs/83 §3): begehbare Preset-Folge -----
        @r.get("/api/agenten/treppe")
        def treppe_holen(bereich_id: str = "",
                         user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Aktuelle Treppen-Stufe des Bereichs ('' = eigene Kombination) + Presets +
            Labels + die Ist-Matrix — die Regie-Zentrale rendert die begehbare Treppe."""
            bid = bereich_id.strip()
            return {"bereich_id": bid, "treppe": self.treppe_erkennen(user.user_id, bid),
                    "stufen": list(TREPPE_STUFEN), "presets": TREPPE_PRESETS,
                    "labels": TREPPE_LABEL,
                    "matrix": self.autonomie_matrix(user.user_id, bid)}

        @r.put("/api/agenten/treppe")
        def treppe_setzen_ep(body: TreppeIn,
                             user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Wendet ein Treppen-Preset (T0–T3) auf einen Bereich an. Anheben ist ein
            bewusster Nutzer-Akt; die wirksame Lockerung >pre_approval greift erst mit
            eval_gruen (Q2)."""
            return self.treppe_anwenden(user.user_id, body.bereich_id.strip(),
                                        body.treppe.strip())

        @r.get("/api/agent-inbox")
        def agent_inbox_ep(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Netz-Inbox (docs/63 §2): aggregierte pending-Aktionen + offline-Apps ehrlich."""
            return self.agent_inbox(user.user_id)

        # --- Running-Tab-Brücke zum Core (Z4.2-D, docs/63 §3/§5 P1) ----------
        # Literal VOR /api/agenten/{aid} (sonst fängt der Platzhalter „laeufe"/„lauf").
        @r.get("/api/agenten/laeufe")
        async def laeufe_ep(status: str = "",
                            user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Task-Ledger (P8, Running-Tab): Läufe + Guardrail-Zähler vom Core
            (Ausführungs-Rolle E4.2). Core offline ⇒ EHRLICH leer (Health-Watch-Regel)."""
            try:
                return {"laeufe": await self.core.laeufe(status.strip()), "core_offline": False}
            except Exception:
                return {"laeufe": [], "core_offline": True}

        @r.post("/api/agenten/lauf/{lauf_id}/stop")
        async def lauf_stop_ep(lauf_id: str,
                               user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """P1-Stop an Core weiterreichen (wirkt ≤1 Event später). Core offline ⇒ 502."""
            try:
                return await self.core.stop(lauf_id)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(502, "Core nicht erreichbar — Stop nicht zugestellt.")

        # --- Abos + Regie-Karte-Push (RG-3b, docs/83 §2) --------------------
        # Literal VOR /api/agenten/{aid} (sonst fängt der Platzhalter „abos"/„regie-karte").
        @r.get("/api/agenten/abos")
        def abo_liste_ep(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """Alle Abos (Ereignis-Strom → Zuständiger, read-only)."""
            return self.abo_liste(user.user_id)

        @r.post("/api/agenten/abos")
        async def abo_anlegen_ep(body: AboIn,
                                 user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Neues Abo. Fail-closed: Pflichtfelder nicht leer, Agent muss existieren,
            genau EIN Zuständiger je Strom (bestehendes aktives Abo ⇒ 409; ein
            soft-gelöschtes wird wiederbelebt). Danach best-effort Regie-Karte-Push."""
            agent_id, quelle, typ = (body.agent_id.strip(), body.quelle_app.strip(),
                                     body.ereignis_typ.strip())
            bereich = body.bereich_id.strip()
            if not (agent_id and quelle and typ):
                raise HTTPException(400, "agent_id, quelle_app und ereignis_typ sind Pflicht.")
            conn = db.get_conn()
            if conn.execute("SELECT id FROM agenten WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (agent_id, user.user_id)).fetchone() is None:
                raise HTTPException(404, f"Agent nicht gefunden: {agent_id}")
            vorhanden = conn.execute(
                "SELECT id, deleted_at FROM agent_abos WHERE user_id=? AND quelle_app=? "
                "AND ereignis_typ=? AND bereich_id=?",
                (user.user_id, quelle, typ, bereich)).fetchone()
            if vorhanden is not None and vorhanden["deleted_at"] is None:
                raise HTTPException(409, "Für diesen Ereignis-Strom gibt es bereits ein Abo "
                                         "(genau EIN Zuständiger je Quelle×Typ×Bereich).")
            ts = now_iso()
            werte = (agent_id, body.auftrag.strip(), max(1, int(body.max_pro_tag)),
                     1 if body.aktiv else 0)
            if vorhanden is not None:                    # soft-gelöscht ⇒ wiederbeleben
                aid = vorhanden["id"]
                conn.execute("UPDATE agent_abos SET agent_id=?, auftrag=?, max_pro_tag=?, "
                             "aktiv=?, updated_at=?, deleted_at=NULL WHERE id=?",
                             (*werte, ts, aid))
            else:
                aid = new_id()
                conn.execute(
                    "INSERT INTO agent_abos (id, user_id, agent_id, quelle_app, ereignis_typ, "
                    "bereich_id, auftrag, max_pro_tag, aktiv, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (aid, user.user_id, agent_id, quelle, typ, bereich,
                     body.auftrag.strip(), max(1, int(body.max_pro_tag)),
                     1 if body.aktiv else 0, ts, ts))
            conn.commit()
            db.audit(user.user_id, "user", "agent_abo_angelegt",
                     {"id": aid, "agent_id": agent_id, "quelle_app": quelle, "ereignis_typ": typ})
            return {"ok": True, "id": aid, "gepusht": await self._push_karte(user.user_id)}

        @r.patch("/api/agenten/abos/{abo_id}")
        async def abo_patch_ep(abo_id: str, body: AboPatch,
                               user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Abo ändern (Zuständiger/Auftrag/Deckel/Aktiv-Schalter). Strom-Identität
            ist nicht patchbar (löschen+neu). Danach best-effort Regie-Karte-Push."""
            conn = db.get_conn()
            row = conn.execute("SELECT * FROM agent_abos WHERE id=? AND user_id=? "
                               "AND deleted_at IS NULL", (abo_id, user.user_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Abo nicht gefunden.")
            felder, werte = [], []

            def _set(spalte: str, wert: Any) -> None:
                felder.append(f"{spalte}=?"); werte.append(wert)

            if body.agent_id is not None and body.agent_id.strip():
                aid = body.agent_id.strip()
                if conn.execute("SELECT id FROM agenten WHERE id=? AND user_id=? "
                                "AND deleted_at IS NULL", (aid, user.user_id)).fetchone() is None:
                    raise HTTPException(404, f"Agent nicht gefunden: {aid}")
                _set("agent_id", aid)
            if body.auftrag is not None:
                _set("auftrag", body.auftrag.strip())
            if body.max_pro_tag is not None:
                _set("max_pro_tag", max(1, int(body.max_pro_tag)))
            if body.aktiv is not None:
                _set("aktiv", 1 if body.aktiv else 0)
            if felder:
                _set("updated_at", now_iso())
                werte += [abo_id, user.user_id]
                conn.execute(f"UPDATE agent_abos SET {', '.join(felder)} "
                             "WHERE id=? AND user_id=?", werte)
                conn.commit()
                db.audit(user.user_id, "user", "agent_abo_geaendert", {"id": abo_id})
            return {"ok": True, "id": abo_id, "gepusht": await self._push_karte(user.user_id)}

        @r.delete("/api/agenten/abos/{abo_id}")
        async def abo_delete_ep(abo_id: str,
                                user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Abo entfernen (Soft-Delete). Danach best-effort Regie-Karte-Push (Core
            hört auf, den Strom zu zünden)."""
            conn = db.get_conn()
            if conn.execute("SELECT id FROM agent_abos WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (abo_id, user.user_id)).fetchone() is None:
                raise HTTPException(404, "Abo nicht gefunden.")
            conn.execute("UPDATE agent_abos SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), abo_id, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "agent_abo_geloescht", {"id": abo_id})
            return {"ok": True, "id": abo_id, "gepusht": await self._push_karte(user.user_id)}

        @r.get("/api/agenten/regie-karte")
        def regie_karte_ep(user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Inspektion: die Regie-Karte, die an den Core gepusht würde (Abos + Wald +
            agent_sens). Reine Projektion."""
            return self.regie_karte(user.user_id)

        @r.post("/api/agenten/regie-karte/push")
        async def regie_karte_push_ep(
                user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Explizit die Regie-Karte an den Core pushen (Definition-Brücke, docs/83
            §2). Core offline ⇒ ehrlich ``core_offline=True`` (der Master-Schalter bleibt
            ohnehin AUS bis zum Go)."""
            try:
                res = await self.core.regie_karte_push(self.regie_karte(user.user_id))
                return {"ok": True, "core_offline": False, **res}
            except Exception:
                return {"ok": False, "core_offline": True}

        # --- Not-Aus (RG-4, docs/83 §3): Master-Schalter am Core -------------
        @r.get("/api/agenten/regie/status")
        async def regie_status_ep(
                user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Regie-Status vom Core (Master-Schalter, Tick, Zünd-Zähler). Core offline ⇒
            ehrlich (Health-Watch-Regel), nie hängend."""
            try:
                return {"core_offline": False, **await self.core.regie_status()}
            except Exception:
                return {"core_offline": True, "aktiv": False}

        @r.post("/api/agenten/regie/schalter")
        async def regie_schalter_ep(body: RegieSchalterIn,
                                    user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Not-Aus umlegen (an den Core weitergereicht). Ausschalten immer; Einschalten
            = gegatete Live-Vorbedingung (G-REGIE-LIVE). Core offline ⇒ 502."""
            try:
                return await self.core.regie_schalter(bool(body.aktiv))
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(502, "Core nicht erreichbar — Schalter nicht gesetzt.")

        # --- Eichung (RG-5, docs/83 §4): Management misst, eigener Cursor ----
        # Literal VOR /api/agenten/{aid} (sonst fängt der Platzhalter „evals"/„eichung").
        @r.get("/api/agenten/evals")
        def evals_liste_ep(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """Alle Eichungen (Agent × Klasse) mit Ampel + Gründen (read-only, flach)."""
            return ev.evals_liste(self.db, user.user_id)

        @r.get("/api/agenten/eichung")
        def eichung_uebersicht_ep(
                user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """Eichungs-Übersicht je Agent (Name + Karten mit aktuell_gruen/Frische) — die
            Eine-Fetch-Projektion, aus der die Regie-Zentrale die Eichungs-Karten rendert."""
            return self.eichung_uebersicht(user.user_id)

        @r.post("/api/agenten/eichung/poll")
        async def eichung_poll_ep(
                user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Löst einen Eichungs-Lauf aus (Spines pollen → Metriken rechnen →
            agent_evals). Read-only gegenüber den Quellen (misst, zündet nichts); danach
            Regie-Karte-Push, damit der Core das aufgefrischte eval_gruen bekommt."""
            return await self.eichung_ausfuehren(user.user_id)

        # --- Werks-Vorlagen (RG-5): Domäne-Nähte per Klick (K-9 Produktionsleiter) --
        @r.get("/api/agenten/vorlagen")
        def vorlagen_liste_ep(
                user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """Verfügbare Werks-Vorlagen (Name + Titel + Ziel-Ereignis-Strom, read-only)."""
            return vorlagen.liste()

        @r.get("/api/agenten/geschaefts-slots")
        def geschaefts_slots_ep(
                user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            """RG-8 (docs/83 §6): das kuratierte Geschäfts-Vorlagen-Set für einen
            ``geschaeft``-Bereich (E-Mail-Manager + Fristen-Wächter) samt fail-closed
            ``aktiv=False``-Stand — „der geschaeft-Bereich zeigt Slots" (read-only)."""
            return vorlagen.geschaefts_slots()

        @r.post("/api/agenten/vorlagen/{name}")
        async def vorlage_install_ep(name: str,
                                     user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Installiert eine Vorlage (Agent + Abo, fail-closed AUS + T0) und pusht die
            Regie-Karte. Idempotent (genau EINE Naht je Strom)."""
            return await self.vorlage_installieren(user.user_id, name.strip())

        @r.post("/api/agenten")
        def agent_anlegen(body: AgentIn,
                          user: UserContext = Depends(current_user)) -> dict[str, Any]:
            if not body.name.strip():
                raise HTTPException(400, "Name ist Pflicht.")
            aid = new_id()
            subs = _clean_sub_agenten(body.sub_agenten)
            self._pruefe_baum(user.user_id, aid, subs)      # 422 bei Tiefe>3/Zyklus
            ts = now_iso()
            db.get_conn().execute(
                "INSERT INTO agenten (id, user_id, name, rolle, system_prompt, task_klasse, "
                "modell_explizit, werkzeuge, sub_agenten, bereich_id, sensitivitaet, autonomie, "
                "budget, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, user.user_id, body.name.strip(), body.rolle.strip(),
                 body.system_prompt, _norm(body.task_klasse, mp.TASK_KLASSEN, "chat"),
                 body.modell_explizit.strip(),
                 json.dumps(_clean_werkzeuge(body.werkzeuge), ensure_ascii=False),
                 json.dumps(subs, ensure_ascii=False), body.bereich_id.strip(),
                 _norm(body.sensitivitaet, SENSITIVITAETEN, "hoch"),
                 json.dumps(_clean_autonomie(body.autonomie), ensure_ascii=False),
                 json.dumps(_clean_budget(body.budget), ensure_ascii=False),
                 _norm(body.status, AGENT_STATUS, "entwurf"), ts, ts))
            db.get_conn().commit()
            db.audit(user.user_id, "user", "agent_angelegt", {"id": aid, "name": body.name.strip()})
            return {"ok": True, "id": aid}

        @r.get("/api/agenten")
        def agent_liste(status: str = "", bereich_id: str = "",
                        user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
            q = "SELECT * FROM agenten WHERE user_id=? AND deleted_at IS NULL"
            params: list[Any] = [user.user_id]
            if status:
                q += " AND status=?"; params.append(status)
            if bereich_id:                       # '' = kein Filter (alle Bereiche)
                q += " AND bereich_id=?"; params.append(bereich_id.strip())
            q += " ORDER BY name ASC"
            return [self._public(row)
                    for row in db.get_conn().execute(q, params).fetchall()]

        @r.get("/api/agenten/{aid}")
        def agent_holen(aid: str, user: UserContext = Depends(current_user)) -> dict[str, Any]:
            row = db.get_conn().execute(
                "SELECT * FROM agenten WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (aid, user.user_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Agent nicht gefunden.")
            return self._public(row)

        @r.get("/api/agenten/{aid}/snapshot")
        def snapshot_ep(aid: str,
                        user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Definition-Brücke (Inspektion): der aufgelöste Snapshot, den Core beim Start
            bekäme. Der Live-Start (POST …/lauf) nutzt ihn intern (Push, kein Mgmt-Fetch)."""
            snap = self.schnappschuss(user.user_id, aid)
            if snap is None:
                raise HTTPException(404, "Agent nicht gefunden.")
            return snap

        @r.get("/api/agenten/{aid}/eval")
        def agent_eval_ep(aid: str,
                          user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Die Eichungs-Karte EINES Agenten (docs/83 §4): je Klasse Ampel + Metriken +
            Gründe + Frische (def_hash-Gate gegen die AKTUELLE Definition, Gültigkeit). Ein
            geänderter Prompt macht ``aktuell_gruen`` sofort False (auch wenn die gespeicherte
            Eichung noch grün war) — genau das zeigt die Karte ehrlich."""
            if self.db.get_conn().execute(
                    "SELECT id FROM agenten WHERE id=? AND user_id=? AND deleted_at IS NULL",
                    (aid, user.user_id)).fetchone() is None:
                raise HTTPException(404, "Agent nicht gefunden.")
            aktuell = self._alle_def_hashes(user.user_id).get(aid, "")
            jetzt = now_iso()
            zeilen = ev.eval_holen(self.db, user.user_id, aid)
            for z in zeilen:
                gueltig, grund = ev.eval_gueltig(z["def_hash"], aktuell, z["gueltig_bis"],
                                                 jetzt_iso=jetzt)
                z["aktuell_gruen"] = bool(z["gruen"]) and gueltig
                z["frische"] = grund or "aktuell"
            return {"agent_id": aid, "def_hash": aktuell, "evals": zeilen}

        @r.post("/api/agenten/{aid}/lauf")
        async def lauf_start_ep(aid: str, body: LaufStartIn,
                                user: UserContext = Depends(current_user)) -> StreamingResponse:
            """Startet einen Lauf: löst den Snapshot aus dem Wald (Definition-Brücke) und
            streamt Cores SSE durch (Live-Log, same-origin für den Browser). Core offline ⇒
            ehrliches Fehler-Event, nie hängend. Nur der Nutzer-Klick startet — nichts läuft
            eigenmächtig (AI-Act Art. 50)."""
            snap = self.schnappschuss(user.user_id, aid)
            if snap is None:
                raise HTTPException(404, "Agent nicht gefunden.")

            async def gen() -> AsyncIterator[bytes]:
                try:
                    async for chunk in self.core.lauf_stream(snap, body.auftrag):
                        yield chunk
                except Exception as e:   # noqa: BLE001 — Core offline ⇒ ehrlich beenden
                    for obj in ({"error": f"Core nicht erreichbar: {e}"},
                                {"done": True, "status": "fehler"}):
                        yield f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()

            return StreamingResponse(gen(), media_type="text/event-stream")

        @r.post("/api/agenten/{aid}/rueckstufen")
        async def rueckstufen_ep(aid: str, body: RueckstufenIn,
                                 user: UserContext = Depends(current_user)) -> dict[str, Any]:
            """Auto-Rückstufung prüfen + bei Trigger ausführen (docs/83 §3): der Agent geht
            sofort auf T0 (beobachten), mit Audit + Glocke. Danach best-effort Regie-Karte-
            Push (Core sieht die gesenkte Stufe). Metriken kommen als Body (messbar/prüfbar)."""
            res = self.pruefe_und_rueckstufe(
                user.user_id, aid, ablehnungen=body.ablehnungen,
                entscheidungen=body.entscheidungen, lauf_fehler=body.lauf_fehler,
                laeufe=body.laeufe, invarianten_verstoss=body.invarianten_verstoss)
            if res.get("rueckgestuft"):
                res["gepusht"] = await self._push_karte(user.user_id)
            return res

        @r.patch("/api/agenten/{aid}")
        def agent_patch(aid: str, body: AgentPatch,
                        user: UserContext = Depends(current_user)) -> dict[str, Any]:
            conn = db.get_conn()
            row = conn.execute("SELECT * FROM agenten WHERE id=? AND user_id=? "
                               "AND deleted_at IS NULL", (aid, user.user_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Agent nicht gefunden.")
            # sub_agenten-Änderung ⇒ Wald neu prüfen (mit der KÜNFTIGEN Kinder-Menge).
            if body.sub_agenten is not None:
                self._pruefe_baum(user.user_id, aid, _clean_sub_agenten(body.sub_agenten))
            felder, werte = [], []

            def _set(spalte: str, wert: Any) -> None:
                felder.append(f"{spalte}=?"); werte.append(wert)

            if body.name is not None and body.name.strip():
                _set("name", body.name.strip())
            if body.rolle is not None:
                _set("rolle", body.rolle.strip())
            if body.system_prompt is not None:
                _set("system_prompt", body.system_prompt)
            if body.task_klasse is not None:
                _set("task_klasse", _norm(body.task_klasse, mp.TASK_KLASSEN, "chat"))
            if body.modell_explizit is not None:
                _set("modell_explizit", body.modell_explizit.strip())
            if body.werkzeuge is not None:
                _set("werkzeuge", json.dumps(_clean_werkzeuge(body.werkzeuge), ensure_ascii=False))
            if body.sub_agenten is not None:
                _set("sub_agenten", json.dumps(_clean_sub_agenten(body.sub_agenten), ensure_ascii=False))
            if body.bereich_id is not None:
                _set("bereich_id", body.bereich_id.strip())
            if body.sensitivitaet is not None:
                _set("sensitivitaet", _norm(body.sensitivitaet, SENSITIVITAETEN, "hoch"))
            if body.autonomie is not None:
                _set("autonomie", json.dumps(_clean_autonomie(body.autonomie), ensure_ascii=False))
            if body.budget is not None:
                _set("budget", json.dumps(_clean_budget(body.budget), ensure_ascii=False))
            if body.status is not None:
                _set("status", _norm(body.status, AGENT_STATUS, "entwurf"))
            if not felder:
                return {"ok": True, "id": aid}
            _set("updated_at", now_iso())
            werte += [aid, user.user_id]
            conn.execute(f"UPDATE agenten SET {', '.join(felder)} WHERE id=? AND user_id=?", werte)
            conn.commit()
            db.audit(user.user_id, "user", "agent_geaendert", {"id": aid})
            return {"ok": True, "id": aid}

        @r.delete("/api/agenten/{aid}")
        def agent_delete(aid: str, user: UserContext = Depends(current_user)) -> dict[str, Any]:
            conn = db.get_conn()
            if conn.execute("SELECT id FROM agenten WHERE id=? AND user_id=? "
                            "AND deleted_at IS NULL", (aid, user.user_id)).fetchone() is None:
                raise HTTPException(404, "Agent nicht gefunden.")
            conn.execute("UPDATE agenten SET deleted_at=? WHERE id=? AND user_id=?",
                         (now_iso(), aid, user.user_id))
            conn.commit()
            db.audit(user.user_id, "user", "agent_geloescht", {"id": aid})
            return {"ok": True, "id": aid}

        return r
