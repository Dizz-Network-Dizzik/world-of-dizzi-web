"""Ereignis-Spine — netzweiter, replaybarer Ereignis-Log (Agenten-Regie W2, RG-1).

**Status: BAU RG-1 (docs/83 §1).** Der Spine ist das Fundament der reaktiven
Agenten-Regie: Apps schreiben Betriebs-Ereignisse als **Outbox-Zeile in der
EIGENEN DB, in DERSELBEN Transaktion wie der Domain-Write** (``ereignis_anlegen``
nimmt die offene ``conn`` entgegen); Konsumenten (Core-Regie, Management-Eichung)
ZIEHEN sie per Cursor (``ereignisse_seit``). Kein Broker, kein Kafka, kein
SSE-als-Wahrheit — SSE bleibt reine Live-Anzeige.

Bewusst NICHT ``events.py``: jenes Modul ist der best-effort **Meldungs-Push** an
die Mensch-Glocke (verlierbar, das ist ok). Der Spine ist die **Maschinen-Schiene**
(persistent, replaybar, at-least-once). Zwei Schienen, bewusst getrennt, bewusst
beide — ``events.py`` bleibt in W2 unangetastet ([A-7]).

Drei harte Verträge, hier als Code statt als Doku-Satz:
- **Zeiger, nie Inhalte:** ein Ereignis trägt ``typ`` + ``ref`` + registrierte
  skalare Meta-Felder — NIE Betreff, Absender, Gesundheitswert, Betrag. Der
  Payload wird gegen das **Typ-Register** validiert (``EreignisTypRegister``);
  Freitext-Feldnamen sind verboten, unbekannte Felder fliegen fail-closed
  (``ValueError``). So ist „was darf ein Event über hoch/höchst-Apps tragen?"
  strukturell beantwortet: nichts Schützenswertes — nicht per Disziplin,
  per Schema.
- **Zustell-Sichtbarkeit fail-closed:** ``ereignis_zustellbar`` — ein Ereignis
  aus einer ``hoch``/``höchst``-Quelle erreicht NUR Agenten, die mindestens so
  sensitiv (= lokal_only) laufen. Ein Boost-fähiger ``normal``-Agent sieht nicht
  einmal den Zeiger eines hoch-Ereignisses.
- **Löschbar:** ``user_id`` UND ``deleted_at`` auf jeder Zeile ⇒ die Soft-Delete-
  Kaskade (``db.soft_delete_user``) erfasst Ereignisse bei Konto-Löschung
  AUTOMATISCH und netzweit (KA-H1-Lösch-Invariante, kein Per-App-Hook nötig);
  ``ereignisse_seit`` überspringt Soft-Gelöschtes, ``aufraeumen`` purgt nach Alter.
  Bewusster Kontrast zur Bizzi-Chronik (docs/80, retention-immun): dort
  Beleg-Ledger, hier Betriebssignale — Löschbarkeit schlägt Unveränderlichkeit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .db import Database, new_id, now_iso

# --- Sichtbarkeits-Politik (docs/83 §1.2) ----------------------------------------

#: Sensitivitäts-Rang: streng monoton. Ein Ereignis ist einem Agenten nur
#: zustellbar, wenn dessen Rang >= dem Quell-Rang ist (der Agent also mindestens
#: so lokal_only läuft wie die Quelle sensibel ist). ``höchst``/``hoechst`` = ein
#: Wert (das Netz schreibt beides).
_SENS_RANG = {"normal": 0, "hoch": 1, "hoechst": 2, "höchst": 2}


def _norm_sens(s: str) -> str:
    return (s or "").strip().lower()


def ereignis_zustellbar(quelle_sens: str, agent_sens: str) -> bool:
    """Darf ein Ereignis aus ``quelle_sens`` einem Agenten mit ``agent_sens``
    gezeigt werden? Fail-closed in beide Richtungen:

    - **unbekannte Quelle ⇒ maximal streng** (Rang 2, wie ``höchst``): im Zweifel
      wird ein Ereignis wie höchst-sensibel behandelt.
    - **unbekannter Agent ⇒ minimal vertraut** (Rang 0, wie ``normal``): im
      Zweifel bekommt der Agent nur unsensible Ereignisse.

    Ergebnis: hoch-Ereignisse erreichen nie einen normal-/Boost-Agenten (der
    Kernschutz); höchst-Ereignisse nur höchst-Agenten (zusätzlich streng).
    """
    quelle_rang = _SENS_RANG.get(_norm_sens(quelle_sens), 2)   # Quelle: streng
    agent_rang = _SENS_RANG.get(_norm_sens(agent_sens), 0)     # Agent: streng
    return agent_rang >= quelle_rang


# --- Typ-Register: der „Zeiger, nie Inhalt"-Vertrag (docs/83 §1) -----------------

#: Feldnamen, die nach FREITEXT/INHALT riechen — im Payload eines Ereignisses
#: verboten. Der Spine trägt Zeiger + Meta-Skalare, nie den Inhalt selbst; ein
#: Register, das eines dieser Felder deklariert, ist ein Vertragsbruch und wirft
#: schon bei ``register()`` (nicht erst zur Laufzeit).
VERBOTENE_FELDER = frozenset({
    "inhalt", "text", "betreff", "body", "content", "subject", "nachricht",
    "message", "html", "klartext", "snippet", "vorschau", "preview",
    "absender", "empfaenger", "from", "to", "cc", "bcc", "adresse",
    "betrag", "summe", "wert", "amount", "iban", "passwort", "token", "secret",
})

#: Maximale Länge eines String-Payload-Werts. Meta-Skalare (IDs, Status, Zähler)
#: sind kurz; alles Längere ist verkappter Inhalt und wird abgelehnt.
MAX_WERT_LEN = 200

#: Zulässige Payload-Werttypen: nur Skalare. dict/list ⇒ verkappter Inhalt.
_SKALAR = (str, int, float, bool)


class EreignisRegisterFehler(ValueError):
    """Register-/Payload-Vertragsbruch — fail-closed, nie stiller Durchlass."""


class EreignisTypRegister:
    """Deklariert je App die erlaubten Ereignis-Typen und ihre Meta-Felder.

    ``register(typ, felder)`` ist der Vertrag: nur deklarierte Typen dürfen
    angelegt werden, und ein Payload darf **nur** die deklarierten Felder tragen
    (Schlüssel ⊆ ``felder``). Verbotene (Freitext-)Feldnamen werden schon beim
    Deklarieren abgelehnt — die „Zeiger, nie Inhalt"-Garantie ist damit statisch
    prüfbar (Conformance-Test der App-Suite), nicht bloß Laufzeit-Hoffnung.
    """

    def __init__(self, app_id: str) -> None:
        self.app_id = app_id
        self._typen: dict[str, frozenset[str]] = {}

    def register(self, typ: str, felder: Iterable[str] = ()) -> None:
        typ = (typ or "").strip()
        if not typ:
            raise EreignisRegisterFehler("Ereignis-Typ darf nicht leer sein")
        feld_set = frozenset(f.strip().lower() for f in felder)
        if "" in feld_set:
            raise EreignisRegisterFehler(f"{typ!r}: leerer Feldname")
        verboten = feld_set & VERBOTENE_FELDER
        if verboten:
            raise EreignisRegisterFehler(
                f"{self.app_id}/{typ}: Freitext-/Inhaltsfelder im Ereignis "
                f"verboten (Zeiger, nie Inhalt): {sorted(verboten)}")
        self._typen[typ] = feld_set

    def kennt(self, typ: str) -> bool:
        return typ in self._typen

    def typen(self) -> tuple[str, ...]:
        return tuple(sorted(self._typen))

    def pruefe(self, typ: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        """Validiert ``typ`` + ``payload`` fail-closed und gibt das saubere
        Payload-Dict zurück. Wirft ``EreignisRegisterFehler`` bei unbekanntem
        Typ, unbekanntem Feld, nicht-skalarem oder zu langem Wert."""
        if typ not in self._typen:
            raise EreignisRegisterFehler(
                f"{self.app_id}: unbekannter Ereignis-Typ {typ!r} "
                f"(erlaubt: {self.typen()})")
        p = dict(payload or {})
        erlaubt = self._typen[typ]
        unbekannt = set(p) - erlaubt
        if unbekannt:
            raise EreignisRegisterFehler(
                f"{self.app_id}/{typ}: unbekannte Payload-Felder "
                f"{sorted(unbekannt)} (erlaubt: {sorted(erlaubt)})")
        for k, v in p.items():
            if not isinstance(v, _SKALAR):
                raise EreignisRegisterFehler(
                    f"{self.app_id}/{typ}.{k}: nur Skalare erlaubt "
                    f"(kein {type(v).__name__} — verkappter Inhalt)")
            if isinstance(v, str) and len(v) > MAX_WERT_LEN:
                raise EreignisRegisterFehler(
                    f"{self.app_id}/{typ}.{k}: Wert > {MAX_WERT_LEN} Zeichen "
                    f"(verkappter Inhalt gehört nicht in den Spine)")
        return p


# --- Netzweite Standard-Typen (docs/83 §1/§4) ------------------------------------

#: Typen, die JEDE Spine-App führt. ``hitl_entschieden`` ist die Ground-Truth-
#: Quelle für die Eval-Eichung (docs/83 §4): jede Nutzer-Entscheidung über einen
#: Agenten-Vorschlag (approve/reject) wird EIN Ereignis — netzweit, weil der Hook
#: zentral in ``create_app`` sitzt. Nur Zeiger + Skalare (Aktions-Name = Bezeichner,
#: kein Inhalt); ``klasse`` reist in der eigenen Spalte, nicht im Payload.
STANDARD_TYPEN: dict[str, tuple[str, ...]] = {
    "hitl_entschieden": ("aktion", "approve", "status", "agent_id", "lauf_id"),
}


def standard_register(app_id: str) -> EreignisTypRegister:
    """Register mit den netzweiten Standard-Typen vorbelegt. Eine App erweitert es
    um ihre eigenen Typen (``reg.register("mail_eingegangen", (...))``) und übergibt
    es an ``create_app(ereignis_register=reg)`` — ab da emittiert die App
    ``hitl_entschieden`` automatisch (docs/83 §4), ohne eigenen Code."""
    reg = EreignisTypRegister(app_id)
    for typ, felder in STANDARD_TYPEN.items():
        reg.register(typ, felder)
    return reg


# --- Schema (je App-DB; additiv über extra_schema, Hausmuster db.py) --------------

#: Ereignis-Outbox. ``seq`` = Reihenfolge JE QUELLE + Cursor-Anker; ``id`` =
#: netzweite Dedup-Identität; ``ref`` = Zeiger 'app:entitaet:id' (nie Inhalt);
#: ``quelle_sens`` wird beim Anlegen gestempelt (Sichtbarkeits-Prüfung §1.2).
#: user_id auf jeder Zeile ⇒ purgebar (KA-Löschpfad).
SCHEMA_EREIGNISSE_SQL = """
CREATE TABLE IF NOT EXISTS ereignisse (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  id          TEXT NOT NULL UNIQUE,
  user_id     TEXT NOT NULL,
  typ         TEXT NOT NULL,
  ref         TEXT NOT NULL DEFAULT '',
  bereich_id  TEXT NOT NULL DEFAULT '',
  klasse      TEXT NOT NULL DEFAULT '',
  payload     TEXT NOT NULL DEFAULT '{}',
  quelle_sens TEXT NOT NULL DEFAULT 'hoechst',
  created_at  TEXT NOT NULL,
  deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ereignisse_seq ON ereignisse (user_id, seq);
"""

# JSON-Serialisierung lokal, damit das Modul nicht an db-Interna hängt.
import json as _json  # noqa: E402


def ereignis_anlegen(conn, user_id: str, typ: str, *,
                     register: EreignisTypRegister,
                     ref: str = "", bereich_id: str = "", klasse: str = "",
                     payload: Mapping[str, Any] | None = None,
                     quelle_sens: str = "hoechst") -> str:
    """Schreibt EIN Ereignis in die OFFENE Verbindung ``conn`` — gedacht für den
    Aufruf **innerhalb** ``with db.transaktion() as conn:`` (Outbox-Garantie: das
    Domain-Faktum und sein Ereignis teilen ein Schicksal; Rollback nimmt beides
    mit). ``conn`` wird NICHT committet — das erledigt der Transaktions-Block des
    Aufrufers (bzw. der Aufrufer selbst im Standalone-Fall).

    Der Payload wird gegen ``register`` validiert (fail-closed, wirft) — ein
    unregistrierter Typ oder ein Freitext-/Nicht-Skalar-Feld stirbt hier, nicht
    still in Produktion. Gibt die vergebene Ereignis-``id`` (uuid) zurück.
    """
    sauber = register.pruefe(typ, payload)
    eid = new_id()
    conn.execute(
        "INSERT INTO ereignisse "
        "(id, user_id, typ, ref, bereich_id, klasse, payload, quelle_sens, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (eid, user_id, typ, ref, bereich_id, klasse,
         _json.dumps(sauber, ensure_ascii=False), quelle_sens, now_iso()),
    )
    return eid


def _zeile_zu_dict(r) -> dict[str, Any]:
    return {
        "seq": r["seq"], "id": r["id"], "user_id": r["user_id"],
        "typ": r["typ"], "ref": r["ref"], "bereich_id": r["bereich_id"],
        "klasse": r["klasse"], "payload": _json.loads(r["payload"]),
        "quelle_sens": r["quelle_sens"], "created_at": r["created_at"],
    }


def ereignisse_seit(conn, user_id: str, seit_seq: int = 0,
                    limit: int = 200) -> list[dict[str, Any]]:
    """Pull-/Replay-Lesefläche: alle Ereignisse eines Nutzers mit ``seq`` >
    ``seit_seq``, aufsteigend (stabile Reihenfolge je Quelle), höchstens
    ``limit`` Stück. Der Konsument merkt sich die höchste gesehene ``seq`` als
    Cursor und rückt ihn erst NACH persistierter Verarbeitung vor (at-least-once
    ⇒ der Konsument dedupt über ``id``). ``limit`` wird auf [1, 1000] geklemmt."""
    limit = max(1, min(int(limit), 1000))
    rows = conn.execute(
        "SELECT seq, id, user_id, typ, ref, bereich_id, klasse, payload, "
        "quelle_sens, created_at FROM ereignisse "
        "WHERE user_id=? AND seq>? AND deleted_at IS NULL ORDER BY seq ASC LIMIT ?",
        (user_id, int(seit_seq), limit),
    ).fetchall()
    return [_zeile_zu_dict(r) for r in rows]


def aufraeumen(db: Database, behalte_tage: int = 90) -> int:
    """Retention: löscht Ereignisse älter als ``behalte_tage`` ENDGÜLTIG (der
    Spine ist Betriebssignal, kein Beleg-Ledger — Löschbarkeit vor
    Unveränderlichkeit). Der Replay-Horizont IST diese Retention (ehrlich
    dokumentiert). Idempotent, billig; committet selbst. Gibt die Anzahl
    gelöschter Zeilen zurück. ``behalte_tage < 1`` ⇒ No-op (nie „alles löschen"
    durch eine 0)."""
    if behalte_tage < 1:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=behalte_tage)
              ).isoformat(timespec="seconds")
    conn = db.get_conn()
    n = conn.execute("DELETE FROM ereignisse WHERE created_at<?", (cutoff,)).rowcount
    conn.commit()
    return int(n or 0)


# --- Read-only-Router (docs/83 §1: EIN appkit-Router, je App gemountet) ----------

def router_factory(db: Database, register: EreignisTypRegister, *, user_dep=None):
    """Baut den read-only Pull-Router ``GET /api/ereignisse?seit=&limit=`` (SSO
    über die App-Auth). ``user_dep`` ist die Auth-Dependency (Default:
    ``appkit.auth.current_user``); Tests injizieren einen Fake, der ein Objekt
    mit ``.user_id`` liefert — so ist der Router ohne Auth-Infrastruktur prüfbar.

    Read-only mit Absicht: der Spine kennt keinen HTTP-Schreibpfad. Ereignisse
    entstehen ausschließlich in der Domain-Transaktion der App (``ereignis_anlegen``),
    nie über eine offene API — es gibt keinen Weg, dem Log von außen etwas
    unterzuschieben."""
    from fastapi import APIRouter, Depends, Query

    if user_dep is None:                      # spät importiert: kein Auth-Zwang beim Import
        from .auth import current_user as user_dep  # type: ignore

    router = APIRouter()

    @router.get("/api/ereignisse")
    def _ereignisse(seit: int = Query(0, ge=0),
                    limit: int = Query(200, ge=1, le=1000),
                    user=Depends(user_dep)) -> dict[str, Any]:
        eintraege = ereignisse_seit(db.get_conn(), user.user_id, seit, limit)
        cursor = eintraege[-1]["seq"] if eintraege else seit
        return {"eintraege": eintraege, "cursor": cursor,
                "typen": list(register.typen())}

    return router
