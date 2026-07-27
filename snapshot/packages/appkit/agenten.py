"""Agenten-Regie — Vertrag der Agent-Entität, Inbox-Erweiterung und Autonomie
(FP-4, docs/63 = Bau-Spec; VO-3/D5/D13).

**Status: VERTRAG (FP-4, Architektur-KI 03.07.2026).** Diese Datei definiert Datenmodell,
Schema-Verträge und die puren Politik-Funktionen; den Bau machen die Pakete
Z4.1/Z4.2 (docs/63 §8, Bau-KI-Loop). Bis dahin importiert KEIN Produktiv-Pfad
dieses Modul — rein additiv, 0 Verhaltenswechsel (Muster FP-3 ``runtime.py``).

Rollen (docs/52 E4.2, fixiert): **Core** führt aus (``app/ai/agent.py`` bleibt
die EINE Runtime, unangetastet — Worker werden ihm als synthetische Tools
``delegiere_<slug>`` injiziert) · **Management** ist Regie/Governance (Heimat,
D13) · **Apps** führen Aktionen im eigenen K4-Registry aus. Trading wird NICHT
angeschlossen.

Drei harte Sicherheits-Verträge, hier als Code statt als Doku-Satz:
- ``KLASSEN_BODEN``: ``geld``/``gesundheit`` kommen NIE über ``pre_approval`` —
  als OBERGRENZE gedeutet (V-1, docs/83 §3): das strengere ``beobachten`` ist für
  sie erlaubt, gelockert werden sie nie (kein UI-Bug lockert das, VO-3 fail-closed).
- ``wirksame_stufe``: alles Unkonfigurierte ⇒ ``beobachten`` (V-1 — Schatten-Betrieb
  ist die neue Null, docs/83 §3; strenger als das frühere ``pre_approval``, weil
  Inbox-Fluten durch Fehlkonfiguration selbst ein Schadensmuster sind); Lockerung
  über ``pre_approval`` hinaus NUR mit ``eval_gruen`` (Q2-Klemme, VO-3 „Evals vor
  Autonomie-Lockerung").
- ``werkzeuge_filter``: deny-by-default — ein Agent sieht exakt die gewährte
  Schnittmenge, Unbekanntes fliegt kommentarlos raus (Least-Privilege, §3.F
  Tool-Misuse-Cascades).

Gate G-TREPPE-V1 (docs/83 §8): das Vertrags-Delta V-1 (``beobachten`` als neue
Null + Kappen-Deutung) ist gebaut und getestet, aber erst mit Davids Nicken live —
noch ist kein Agent aktiviert, die 0-Bruch-Lage ist ehrlich (Vertrags-Tests ändern
sich dokumentiert mit).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

# --- Konstanten (docs/63 §1/§4) --------------------------------------------------

#: Maximale Baum-Tiefe in EBENEN (Orchestrator=1). VO-3: „flach, 2–3 Ebenen";
#: die UI defaultet auf 2, der Vertrag deckelt hart bei 3 (Anti-Swarm, §3.F).
MAX_EBENEN = 3

#: Aktions-Klassen = SEMANTIK der Entscheidung (worüber wird entschieden) —
#: orthogonal zum K4-``level`` (wie stark muss die Freigabe authentifiziert sein).
AKTIONS_KLASSEN = ("entwurf", "aussenwirkung", "geld", "gesundheit")

#: Autonomie-Stufen, aufsteigend locker (Index = Lockerheit; min() = strenger).
#: beobachten = Schatten-Betrieb: read-Tools ja, Schreib-Absichten NUR ins Schatten-
#: Protokoll — weder ausgeführt noch vorgeschlagen (V-1, docs/83 §3, die neue Null) ·
#: pre_approval = heutiger K4-Pfad (Vorschlag wartet in der Inbox) ·
#: monitored = führt aus + Pflicht-Sichtbarkeit (Live-Feed, on-the-loop) ·
#: autonom_audit = führt aus, Audit-Log.
AUTONOMIE_STUFEN = ("beobachten", "pre_approval", "monitored", "autonom_audit")

#: Klassen-OBERGRENZE (V-1, docs/83 §3): geld/gesundheit kommen NIE über pre_approval —
#: das strengere ``beobachten`` ist für sie erlaubt, gelockert werden sie nie
#: (VO-3 „health/money fest höchste Stufe"). Bewusst keine Setting-Umgehung. Deutung
#: als OBERGRENZE (nicht als fester Wert) macht ``beobachten`` für geld/gesundheit möglich.
KLASSEN_BODEN = {"geld": "pre_approval", "gesundheit": "pre_approval"}

#: Default-Ableitung Aktions-Klasse aus dem K4-Level (``klasse_von_level``);
#: Apps dürfen je Aktion explizit STRENGER deklarieren (healthy ⇒ 'gesundheit').
_LEVEL_ZU_KLASSE = {"lokal": "entwurf", "verifiziert": "aussenwirkung",
                    "hochsicher": "geld"}

#: Lauf-Ereignisse für den Q3-Event-Spine (C13). Bis C13 existiert, ist die
#: Senke ``ereignis_verwerfen`` — die SIGNATUR steht heute, die Verdrahtung kommt.
EREIGNISSE = ("lauf_gestartet", "runde", "delegation", "tool_aufruf",
              "hitl_wartet", "lauf_ende", "lauf_stop")

#: Ereignis-Senke: (ereignis_name, daten) → None. Absichtlich schmal — der
#: Event-Spine (C13) definiert Persistenz/Fan-out, nicht dieser Vertrag.
EventSenke = Callable[[str, dict[str, Any]], None]


def ereignis_verwerfen(name: str, daten: dict[str, Any]) -> None:
    """No-op-Senke (Default bis C13): Ereignisse verschwinden ehrlich —
    kein heimlicher Puffer, der später als „Event-Historie" missdeutet wird."""


# --- Entität (docs/63 §1) ---------------------------------------------------------

@dataclass(frozen=True)
class AgentBudget:
    """Runaway-Schutz als Teil der ENTITÄT, damit die Agent-Karte ihn zeigen
    kann (P7 sichtbare Guardrails). ``max_runden`` spiegelt heutiges
    ``agent.MAX_ROUNDS`` (=4) als Default — Parität, kein neues Verhalten.
    Der Z4.2-Wrapper beendet bei Überschreitung EHRLICH (status='fehler' +
    Grund), er kappt nie still."""
    max_runden: int = 4
    max_tool_aufrufe: int = 32
    max_delegationen: int = 8
    max_laufzeit_s: int = 600
    laeufe_pro_tag: int = 20


@dataclass(frozen=True)
class AgentDef:
    """Ein Agent als DATEN (D5-d „geisteskrank erweiterbar" = Erweitern ist
    CRUD, nie Deployment). Persistenz: ``SCHEMA_AGENTEN_SQL`` (Management-DB —
    Definition ist Governance, Heimat D13); JSON-Spalten tragen die
    Sequenz-/Mapping-Felder.

    - ``task_klasse``/``modell_explizit``: Modell-Bindung übers Profil (FP-3),
      Präzedenz in ``modell_fuer`` — Kanal-Upgrades heben alle Agenten.
    - ``werkzeuge``: deny-by-default, nur Namen aus tools.registry/MCP-Katalog;
      wirksam wird stets ``werkzeuge_filter(werkzeuge, katalog)``.
    - ``sensitivitaet``: wirksam ist ``max(App, Agent)`` — strenger ja,
      lockerer nie (Manifest-Schalter bleibt unantastbar).
    - ``autonomie``: Mapping Aktions-Klasse → Wunsch-Stufe des Agenten;
      wirksam entscheidet ``wirksame_stufe`` (Bereich + Boden + Q2-Klemme).
    - ``sub_agenten``: Agent-IDs, Baum flach (``validiere_agentenbaum``)."""
    id: str
    name: str
    rolle: str = ""
    system_prompt: str = ""
    task_klasse: str = "chat"
    modell_explizit: str = ""
    werkzeuge: tuple[str, ...] = ()
    sub_agenten: tuple[str, ...] = ()
    bereich_id: str = ""
    sensitivitaet: str = "hoch"
    autonomie: Mapping[str, str] = field(default_factory=dict)
    budget: AgentBudget = field(default_factory=AgentBudget)
    status: str = "entwurf"          # 'entwurf' | 'aktiv' | 'pausiert'

    def modell_fuer(self, profil: Any) -> str | None:
        """Modell-Auflösung, FP-3-Präzedenz gespiegelt: ``modell_explizit`` >
        ``profil.modell_fuer(task_klasse)`` (``modellprofil.ModellProfil``).
        ``None`` = weder Override noch Slot — der Aufrufer degradiert auf
        seinen ehrlichen Fallback (heutige Konstanten-Kette)."""
        if self.modell_explizit.strip():
            return self.modell_explizit.strip()
        return profil.modell_fuer(self.task_klasse) if profil is not None else None


# --- Schema-Verträge (Bau: Z4.1-A/-B · Z4.2-B; docs/63 §1/§2) ---------------------

#: Agent-Definitionen — MANAGEMENT-DB (Regie-Heimat, D13). JSON-Spalten wie
#: kommentiert; Soft-Delete + Zeitstempel = Hausmuster.
SCHEMA_AGENTEN_SQL = """
CREATE TABLE IF NOT EXISTS agenten (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  rolle TEXT NOT NULL DEFAULT '',
  system_prompt TEXT NOT NULL DEFAULT '',
  task_klasse TEXT NOT NULL DEFAULT 'chat',
  modell_explizit TEXT NOT NULL DEFAULT '',
  werkzeuge TEXT NOT NULL DEFAULT '[]',
  sub_agenten TEXT NOT NULL DEFAULT '[]',
  bereich_id TEXT NOT NULL DEFAULT '',
  sensitivitaet TEXT NOT NULL DEFAULT 'hoch',
  autonomie TEXT NOT NULL DEFAULT '{}',
  budget TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'entwurf',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agenten_user ON agenten(user_id, status);
"""

#: Läufe — CORE-DB (Ausführungszustand wohnt beim Ausführenden, E4.2).
#: ``definition`` = JSON-Snapshot der AUFGELÖSTEN AgentDef zum Startzeitpunkt:
#: Audit + reload-fest + kein Cross-DB-Join; spätere Edits verfälschen nie die
#: Historie. ``nutzung`` = rohe Engine-Zähler (RuntimeEreignis.ende, Q1-Anker).
#: ``stop_signal`` = P1-Stop: der Z4.2-Wrapper prüft je Event und schließt den
#: Iterator (aclose) — Stop wirkt an der nächsten Token-/Tool-Grenze.
SCHEMA_LAEUFE_SQL = """
CREATE TABLE IF NOT EXISTS agent_laeufe (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  definition TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'laeuft',
  stop_signal INTEGER NOT NULL DEFAULT 0,
  runden INTEGER NOT NULL DEFAULT 0,
  tool_aufrufe INTEGER NOT NULL DEFAULT 0,
  delegationen INTEGER NOT NULL DEFAULT 0,
  nutzung TEXT NOT NULL DEFAULT '{}',
  fehler TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL,
  ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_laeufe ON agent_laeufe(user_id, status, started_at);
"""

#: Inbox-Erweiterung von ``app_actions`` (K4) — ADDITIV, idempotente ALTER im
#: Bau Z4.1-B (Muster ``migriere_bereich``). ``propose()`` bekommt gleichnamige
#: nur-Keyword-Parameter mit Default '' (0-Bruch für Bestands-Aufrufer);
#: WARUM wird bei ``source='agent'`` PFLICHT — ein Agent ohne Warum hat keins.
#: ``idem`` (RG-4, docs/83 §2) = Wirkungs-Idempotenz: gleiche ``idem`` bei bestehender
#: pending-Aktion ⇒ die bestehende zurück statt Dublette (at-least-once × Wiederanlauf
#: erzeugt sonst Inbox-Müll); leer = kein Dedup (Bestands-Aufrufer unverändert).
INBOX_ZUSATZSPALTEN = (
    ("agent_id", "TEXT NOT NULL DEFAULT ''"),
    ("warum", "TEXT NOT NULL DEFAULT ''"),
    ("lauf_id", "TEXT NOT NULL DEFAULT ''"),
    ("idem", "TEXT NOT NULL DEFAULT ''"),
)


def schema_pruefen(sql: str) -> None:
    """Führt ein Schema-Fragment gegen eine in-memory-SQLite aus (Vertrags-
    Test-Helfer): das Schema IST der Vertrag, also muss es heute parsen."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(sql)
    finally:
        conn.close()


# --- Baum-Validierung (docs/63 §1/§3) ---------------------------------------------

def validiere_agentenbaum(wurzel: str, kinder: Mapping[str, Sequence[str]],
                          max_ebenen: int = MAX_EBENEN) -> None:
    """Definitionszeit-Wächter: Tiefe ≤ ``max_ebenen`` (Wurzel = Ebene 1) und
    ZYKLENFREI, sonst ``ValueError`` mit ehrlicher Ursache. Wiederverwendung
    desselben Workers in mehreren Ästen ist ERLAUBT (Reuse ist kein Zyklus);
    IDs ohne ``kinder``-Eintrag gelten als Blatt.

    Die Laufzeit prüft ZUSÄTZLICH (Z4.2-A Laufkontext-Ebene, fail-closed) —
    eine nach der Validierung editierte Definition wird nicht blind vollstreckt."""
    def _ab(agent_id: str, ebene: int, pfad: tuple[str, ...]) -> None:
        if agent_id in pfad:
            raise ValueError(f"Agenten-Zyklus: {' → '.join(pfad + (agent_id,))}")
        if ebene > max_ebenen:
            raise ValueError(
                f"Agenten-Baum zu tief: Ebene {ebene} > max {max_ebenen} "
                f"(VO-3: flach bleiben) bei {agent_id!r}")
        for kind in kinder.get(agent_id, ()):  # fehlender Eintrag = Blatt
            _ab(kind, ebene + 1, pfad + (agent_id,))

    _ab(wurzel, 1, ())


_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def delegations_toolname(agent_id: str) -> str:
    """Kanonischer Name des synthetischen Delegations-Tools: ``delegiere_<slug>``.
    Worker = Tool (docs/63 §3): so erbt die Delegation Parallelität, Timeout
    und Fehler-Isolation von ``agent.py``, statt sie nachzubauen."""
    slug = _SLUG_RE.sub("_", agent_id.strip().lower()).strip("_") or "agent"
    return f"delegiere_{slug}"


# --- Autonomie-Politik (docs/63 §4) -----------------------------------------------

def klasse_von_level(level: str) -> str:
    """Default-Klasse aus dem K4-Level (lokal→entwurf · verifiziert→
    aussenwirkung · hochsicher→geld); Unbekanntes ⇒ 'geld' (strengste
    Deutung, fail-closed). Apps dürfen je Aktion explizit strenger deklarieren."""
    return _LEVEL_ZU_KLASSE.get(level, "geld")


def _stufen_index(stufe: str | None) -> int:
    """Unbekannt/leer/None ⇒ 0 (= ``beobachten``, die strengste Stufe) — fail-closed,
    nie raten. Seit V-1 ist Index 0 die neue Null (Schatten), nicht mehr pre_approval."""
    try:
        return AUTONOMIE_STUFEN.index(stufe)  # type: ignore[arg-type]
    except ValueError:
        return 0


#: Obergrenze der Stufen-Skala (autonom_audit) — „keine Kappe" für entwurf/aussenwirkung.
_STUFE_OBEN = len(AUTONOMIE_STUFEN) - 1


def _klassen_kappe_index(klasse: str) -> int:
    """Index der Klassen-OBERGRENZE (V-1, docs/83 §3):
    - unbekannte Klasse ⇒ 0 (``beobachten``): strengste Kappe, fail-closed;
    - ``geld``/``gesundheit`` ⇒ Index von ``pre_approval`` (nie höher, ``KLASSEN_BODEN``);
    - ``entwurf``/``aussenwirkung`` ⇒ ``_STUFE_OBEN`` (keine Klassen-Kappe)."""
    if klasse not in AKTIONS_KLASSEN:
        return 0
    boden = KLASSEN_BODEN.get(klasse)
    return _stufen_index(boden) if boden is not None else _STUFE_OBEN


def wirksame_stufe(klasse: str, *, bereich_stufe: str | None = None,
                   agent_stufe: str | None = None,
                   eval_gruen: bool = False) -> str:
    """DIE Autonomie-Entscheidung (pure, docs/63 §4 + V-1 docs/83 §3 — Reihenfolge
    verbindlich):

    1. **Klassen-Kappe (Obergrenze):** unbekannte Klasse ⇒ ``beobachten`` (strengst);
       ``geld``/``gesundheit`` ⇒ nie über ``pre_approval`` (``KLASSEN_BODEN`` als
       Obergrenze, nicht als Fixwert — ``beobachten`` bleibt für sie möglich).
    2. **Unkonfigurierter Agent ⇒ ``beobachten``** (V-1: die neue Null ist Zuschauen,
       nicht Vorschlagen). ``agent_stufe is None`` ⇒ Index 0.
    3. **min(Bereich, Agent, Kappe)** — die restriktivere Politik gewinnt immer.
       ``bereich_stufe is None`` heißt „der Bereich setzt KEINE Kappe" (Obergrenze) —
       nur ein GESETZTER Bereichswert schränkt ein; ein ungültiger (Nicht-None-)Wert
       ⇒ Index 0 (fail-closed). *(Der Katalog im Core kennt die Bereichs-Matrix nicht
       und reicht ``None`` = keine Bereichs-Kappe; Management reicht den echten Wert.)*
    4. Ergebnis > ``pre_approval`` NUR mit ``eval_gruen`` (Q2-Nachweis je Agent), sonst
       Klemme zurück auf ``pre_approval`` — NICHT tiefer: wer mehr wollte, darf
       wenigstens vorschlagen (docs/83 §3 V-1.3).

    Senken ist immer erlaubt (einfach Stufe niedriger setzen); das ANHEBEN verlangt
    zusätzlich Nutzer-Bestätigung auf hochsicher-Auth (HTTP-Schicht, wie die
    K4-Stufen-Prüfung — nicht Aufgabe dieser puren Funktion)."""
    if klasse not in AKTIONS_KLASSEN:
        return "beobachten"                       # unbekannte Klasse ⇒ strengste Kappe
    kappe = _klassen_kappe_index(klasse)
    a_idx = _stufen_index(agent_stufe) if agent_stufe is not None else 0
    b_idx = _stufen_index(bereich_stufe) if bereich_stufe is not None else _STUFE_OBEN
    idx = min(a_idx, b_idx, kappe)
    pre = _stufen_index("pre_approval")
    if idx > pre and not eval_gruen:              # Q2-Klemme: >pre_approval nur mit Eval
        idx = pre
    return AUTONOMIE_STUFEN[idx]


def stufe_erlaubt_ausfuehrung(stufe: str) -> bool:
    """True ⇔ die Aktion darf OHNE wartendes Approval vollzogen werden
    (monitored/autonom_audit); ``pre_approval``/``beobachten`` und alles Unbekannte
    ⇒ False — der Vorschlag geht den heutigen K4-Weg in die Inbox (oder ins Schatten-
    Protokoll, falls ``beobachten``)."""
    return stufe in ("monitored", "autonom_audit")


def stufe_erlaubt_vorschlag(stufe: str) -> bool:
    """True ⇔ die Stufe erlaubt überhaupt einen Inbox-Vorschlag — alles ab
    ``pre_approval`` aufwärts (V-1, docs/83 §3.4). ``beobachten`` (Schatten-Betrieb)
    und alles Unbekannte ⇒ False (Index 0, fail-closed): der Agent schaut zu, seine
    Schreib-Absicht landet als Schatten-Eintrag, nie in der Inbox."""
    return _stufen_index(stufe) > 0


def stufe_ueber_kappe(klasse: str, stufe: str) -> bool:
    """True ⇔ ``stufe`` läge ÜBER der Klassen-Obergrenze (V-1) — z. B. ``geld``/
    ``gesundheit`` über ``pre_approval`` oder eine unbekannte Klasse über
    ``beobachten``. Speicher-Validierung (Management ``autonomie_setzen``) nutzt es,
    damit ein Boden-Verstoß gar nicht erst persistiert. ``beobachten``/``pre_approval``
    für geld/gesundheit sind KEINE Verstöße (strenger ist erlaubt)."""
    return _stufen_index(stufe) > _klassen_kappe_index(klasse)


# --- Definitions-Hash (RG-4/RG-5, docs/83 §4) -------------------------------------

def definitions_hash(a: AgentDef) -> str:
    """Kanonischer Hash der VERHALTENS-bestimmenden Felder einer AgentDef — die
    Identität, an der ``eval_gruen`` hängt (docs/83 §4): jeder Prompt-/Tool-/Modell-/
    Budget-/Sub-Agenten-Edit macht die Eichung SOFORT ungrün (fail-closed), weil sich
    der Hash ändert.

    Erfasst (was das Verhalten ändert): ``system_prompt``, ``werkzeuge``,
    ``task_klasse``, ``modell_explizit``, ``sub_agenten``, ``budget``.
    NICHT erfasst (docs/83 §4 „Name/Beschreibung egal"): id, name, rolle,
    beschreibung, status, bereich_id, sensitivitaet, autonomie — Umbenennen,
    Verschieben oder eine Stufen-Änderung ändern das gemessene Verhalten nicht.
    Listen bleiben in Reihenfolge (Umsortieren von Tools/Sub-Agenten IST ein
    Verhaltens-Edit ⇒ ungrün); ``sort_keys`` macht die Serialisierung prozess-/
    reload-stabil."""
    kanon = {
        "system_prompt": a.system_prompt,
        "werkzeuge": list(a.werkzeuge),
        "task_klasse": a.task_klasse,
        "modell_explizit": a.modell_explizit,
        "sub_agenten": list(a.sub_agenten),
        "budget": {
            "max_runden": a.budget.max_runden,
            "max_tool_aufrufe": a.budget.max_tool_aufrufe,
            "max_delegationen": a.budget.max_delegationen,
            "max_laufzeit_s": a.budget.max_laufzeit_s,
            "laeufe_pro_tag": a.budget.laeufe_pro_tag,
        },
    }
    roh = json.dumps(kanon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


# --- Außenzugriff-Politik (docs/63 §4, G-FP4-BOOST ✅ 03.07.) ---------------------

#: Werte der Grundeinstellung ``agenten_aussenzugriff`` (settings_core, Bau Z4.1 —
#: Muster VO-1 ``effekt_intensitaet``). Der EDITION-Default setzt den Startwert
#: (docs/56): Lokal-pur ⇒ 'aus' (fail-closed, der lokale Nutzer gibt Außenzugriff
#: EXPLIZIT frei) · Hybrid/Vollserver ⇒ 'erlaubt' (läuft ohnehin über Server).
AUSSENZUGRIFF_WERTE = ("aus", "erlaubt")


def boost_erlaubt(*, setting_erlaubt: bool, sensitivitaet: str) -> bool:
    """Darf ein Agent Außenzugriff (Internet + Boost-/Cloud-Modelle) nutzen?
    Fail-closed-UND zweier Bedingungen (docs/63 §4, G-FP4-BOOST):

    1. App-Sensitivität == ``normal`` — ``hoch``/``höchst`` bleiben IMMER
       lokal_only; die Sensitivitäts-Sperre (Manifest) ist unantastbar und
       durch KEIN Setting hebbar. Unbekannte Sensitivität ⇒ False (streng).
    2. ``setting_erlaubt`` — der Aufrufer hat die Grundeinstellung
       ``agenten_aussenzugriff`` bereits zum Edition-Default aufgelöst
       (Lokal-pur='aus', Hybrid/Server='erlaubt', docs/56) inklusive etwaigem
       Bereich/App-Override; ungesetzt/unbekannt reicht er als False herein.

    Reine Funktion — kennt weder Edition-Namen noch Settings (die wohnen in
    settings_core/docs/56); sie erzwingt nur die Kombinations-Regel, genau wie
    ``wirksame_stufe`` nur die Stufen-Regel erzwingt."""
    return setting_erlaubt and sensitivitaet == "normal"


# --- Tool-Grants (docs/63 §1/§4) --------------------------------------------------

def werkzeuge_filter(gewaehrt: Sequence[str], katalog: Sequence[str]) -> tuple[str, ...]:
    """Wirksame Tool-Menge eines Agenten: Schnittmenge aus Grants und
    verfügbarem Katalog, Reihenfolge = Grant-Reihenfolge, Duplikate raus.
    Deny-by-default: leere Grants ⇒ leeres Ergebnis; Unbekanntes (Tippfehler,
    entfernter MCP-Server) fliegt KOMMENTARLOS — ein Agent bekommt nie ein
    Tool „aus Versehen", ein toter Grant wird nie zum Fehler im Lauf."""
    vorhanden = set(katalog)
    gesehen: set[str] = set()
    out: list[str] = []
    for name in gewaehrt:
        if name in vorhanden and name not in gesehen:
            gesehen.add(name)
            out.append(name)
    return tuple(out)


# --- Projektionen (docs/63 §2/§5 — UI liest Projektionen, nie Roh-Zeilen) ---------

def agent_karte(a: AgentDef, *, werkzeug_katalog: Sequence[str] = ()) -> dict[str, Any]:
    """Agent-Karte (P2): Rolle · Tools · Wissen · Grenzen — EINE Projektion
    für Management-UI, Shell und spätere Editionen. ``tools`` ist bereits die
    WIRKSAME Menge (gefiltert gegen den Katalog), nicht der Roh-Grant — die
    Karte zeigt, was der Agent wirklich kann, nicht was jemand mal tippte."""
    return {
        "id": a.id,
        "name": a.name,
        "rolle": a.rolle,
        "status": a.status,
        "tools": list(werkzeuge_filter(a.werkzeuge, werkzeug_katalog)),
        "wissen": {"bereich_id": a.bereich_id,
                   "system_prompt_auszug": a.system_prompt[:200]},
        "grenzen": {
            "sensitivitaet": a.sensitivitaet,
            "autonomie": dict(a.autonomie),
            "max_runden": a.budget.max_runden,
            "max_tool_aufrufe": a.budget.max_tool_aufrufe,
            "max_delegationen": a.budget.max_delegationen,
            "max_laufzeit_s": a.budget.max_laufzeit_s,
            "laeufe_pro_tag": a.budget.laeufe_pro_tag,
        },
        "sub_agenten": list(a.sub_agenten),
        "task_klasse": a.task_klasse,
        "modell_explizit": a.modell_explizit,
    }


def inbox_eintrag(app_id: str, aktion: Mapping[str, Any], level: str) -> dict[str, Any]:
    """Netz-Inbox-Eintrag (P3) aus einer ``app_actions``-Zeile der besitzenden
    App: WAS (Aktions-Name) + WARUM (Agenten-Begründung) + Argumente (params)
    + Herkunft (app/agent/lauf). Approve/Reject laufen IMMER gegen den
    Endpoint der besitzenden App (docs/63 §2) — dieser Eintrag ist reine
    Projektion fürs Anzeigen, nie ein zweiter Ausführungs-Weg."""
    return {
        "app_id": app_id,
        "id": aktion.get("id", ""),
        "was": aktion.get("name", ""),
        "warum": aktion.get("warum", ""),
        "argumente": aktion.get("params", {}),
        "agent_id": aktion.get("agent_id", ""),
        "lauf_id": aktion.get("lauf_id", ""),
        "level": level,
        "klasse": klasse_von_level(level),
        "status": aktion.get("status", "pending"),
        "created_at": aktion.get("created_at", ""),
    }
