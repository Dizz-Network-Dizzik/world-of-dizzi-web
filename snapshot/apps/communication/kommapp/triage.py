"""KI-Triage — lokale Posteingangs-Auswertung (hoechst-App: NUR Ollama).

Fasst den Posteingang zusammen und hebt hervor, was Aufmerksamkeit braucht —
die Inhalte verlassen die Maschine dabei NIE (Ollama :11434, 0 €; das ist
für eine hoechst-App nicht verhandelbar, Dossier §6). Opt-in über das
K2-Setting ``ki_triage_aktiv`` (Default aus).

Die LLM-Ausgabe wird strikt auf das erwartete JSON geprüft; bei Müll oder
Ollama-Ausfall kommt eine ehrliche Fehler-Antwort statt halluzinierter Triage.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from pydantic import BaseModel

from appkit.ollama import post

OLLAMA_URL = os.environ.get("DIZZ_OLLAMA_URL", "http://127.0.0.1:11434")


# --- Antwort-Schemas (Pydantic-Single-Source, docs/50 P2.1-Nachzug) ----------
# Für die SKALAREN KI-Funktionen (frage/zusammenfassung/entwurf) ist ein Pydantic-
# Modell EINE Quelle für format= (Grammatik) UND Validierung. Die drei LISTEN-
# Funktionen (triagiere/klassifiziere/erkenne_termine) behalten BEWUSST ihr dict-
# Schema + die explizite PER-ITEM-Nachvalidierung: sie verwerfen einzelne Müll-
# Einträge und behalten die guten (z. B. unbekannte Kategorie/Index außerhalb ⇒
# nur DIESER Eintrag fällt weg). Pydantics List-Validierung ist all-or-nothing —
# ein einziger ungültiger Eintrag würde die GANZE Antwort verwerfen; das wäre ein
# Robustheits-Rückschritt (test_klassifiziere_verwirft_muell). Darum dort kein Umbau.
class _Frage(BaseModel):
    antwort: str
    belege: list[str] = []


class _Zusammenfassung(BaseModel):
    zusammenfassung: str


class _Entwurf(BaseModel):
    entwurf: str

_SYSTEM = (
    "Du bist die lokale Triage eines E-Mail-Posteingangs. Antworte NUR mit "
    'JSON: {{"zusammenfassung":"2-3 Saetze","wichtig":[{{"betreff":"...",'
    '"grund":"..."}}]}}. "wichtig" = maximal {max_wichtig} Nachrichten, die '
    "Reaktion/Frist/Geld betreffen. Keine Erfindungen: nur aus der Liste."
)


def _chat(system: str, nutzer: str, modell: str, http_post: Callable | None,
          schema: type[BaseModel], was: str, temperature: float = 0):
    """Struktur-erzwungener Chat für die skalaren KI-Funktionen → ``(modell, None)``
    oder ``(None, error-dict)``. Erhält die drei ehrlichen Fehler-Pfade getrennt:
    HTTP≠200 · Netz-/Client-Fehler · schema-ungültige Antwort (kein gültiges JSON)."""
    try:
        r = (http_post or post)(f"{OLLAMA_URL}/api/chat", {
            "model": modell, "stream": False, "format": schema.model_json_schema(),
            "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": nutzer}]})
        if getattr(r, "status_code", 0) != 200:
            return None, {"error": f"Ollama antwortet nicht (HTTP {getattr(r, 'status_code', '?')})"}
        content = (r.json().get("message") or {}).get("content", "")
    except Exception as e:
        return None, {"error": f"{was} fehlgeschlagen: {type(e).__name__}: {e}"}
    try:
        return schema.model_validate_json(content), None
    except Exception:
        return None, {"error": f"{was} unbrauchbar (kein gültiges JSON-Schema)"}


def triagiere(nachrichten: list[dict[str, Any]], modell: str = "qwen3:4b",
              max_wichtig: int = 5, http_post: Callable | None = None) -> dict[str, Any]:
    """Triagiert eine Nachrichten-Liste (betreff/von_adresse/text).
    Liefert {zusammenfassung, wichtig} oder {error} — wirft nie."""
    if not nachrichten:
        return {"zusammenfassung": "Posteingang ist leer.", "wichtig": []}
    zeilen = []
    for n in nachrichten[:30]:
        zeilen.append(f"- Von {n.get('von_adresse', '?')}: "
                      f"{n.get('betreff', '(ohne Betreff)')} — "
                      f"{(n.get('text') or '')[:200]}")
    # JSON-Schema als format erzwingt die Struktur (Live-Lehre 12.06., News).
    schema = {"type": "object",
              "properties": {"zusammenfassung": {"type": "string"},
                             "wichtig": {"type": "array", "items": {
                                 "type": "object",
                                 "properties": {"betreff": {"type": "string"},
                                                "grund": {"type": "string"}},
                                 "required": ["betreff"]}}},
              "required": ["zusammenfassung", "wichtig"]}
    try:
        r = (http_post or post)(f"{OLLAMA_URL}/api/chat", {
            "model": modell, "stream": False, "format": schema,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system",
                 "content": _SYSTEM.format(max_wichtig=max_wichtig)},
                {"role": "user", "content": "\n".join(zeilen)}]})
        if r.status_code != 200:
            return {"error": f"Ollama antwortet nicht (HTTP {r.status_code})"}
        roh = json.loads((r.json().get("message") or {}).get("content", ""))
    except Exception as e:
        return {"error": f"Triage fehlgeschlagen: {type(e).__name__}: {e}"}
    if not isinstance(roh, dict) or not isinstance(roh.get("zusammenfassung"), str):
        return {"error": "Triage-Antwort unbrauchbar (kein gültiges JSON-Schema)"}
    wichtig = [w for w in (roh.get("wichtig") or [])[:max_wichtig]
               if isinstance(w, dict) and isinstance(w.get("betreff"), str)]
    return {"zusammenfassung": roh["zusammenfassung"].strip(),
            "wichtig": wichtig, "modell": modell,
            "nachrichten_betrachtet": len(zeilen)}


# --- Per-Nachricht-Triage (Wichtigkeit/Kategorie) ----------------------------

# Feste Vokabulare ⇒ als JSON-Schema-``enum`` erzwingbar (kein freies Halluzinat).
KATEGORIEN = ["wichtig", "persoenlich", "arbeit", "benachrichtigung",
              "werbung", "sonstiges"]
WICHTIGKEIT = ["hoch", "mittel", "niedrig"]

_SYSTEM_KLASS = (
    "Du bist die lokale Posteingangs-Triage. Ordne JEDE nummerierte Nachricht "
    "ein. Antworte NUR mit JSON {\"eintraege\":[{\"index\":0,\"kategorie\":<eine "
    "von " + str(KATEGORIEN) + ">,\"wichtigkeit\":<eine von " + str(WICHTIGKEIT) +
    ">,\"grund\":\"kurz\"}]}. index ist die Zahl in [..]. Keine Erfindungen, "
    "nur aus der Liste; gib zu jeder Nachricht genau einen Eintrag.")


def klassifiziere(nachrichten: list[dict[str, Any]], modell: str = "qwen3:4b",
                  http_post: Callable | None = None) -> dict[str, Any]:
    """Klassifiziert je Nachricht Wichtigkeit + Kategorie — strikt lokal (Ollama),
    Vokabular per JSON-Schema-``enum`` erzwungen. Liefert {eintraege:[{index,
    id?,betreff,kategorie,wichtigkeit,grund}]} oder {error}; wirft nie.

    Jeder Eintrag wird über seinen ``index`` an die Quell-Nachricht
    rückgebunden (id/betreff werden aus der Liste übernommen, nicht aus der
    LLM-Antwort — so kann das Modell die Zuordnung nicht verfälschen)."""
    if not nachrichten:
        return {"eintraege": [], "nachrichten_betrachtet": 0}
    liste = nachrichten[:30]
    zeilen = []
    for i, n in enumerate(liste):
        zeilen.append(f"[{i}] Von {n.get('von_adresse', '?')}: "
                      f"{n.get('betreff', '(ohne Betreff)')} — "
                      f"{(n.get('text') or '')[:160]}")
    schema = {
        "type": "object",
        "properties": {"eintraege": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "kategorie": {"type": "string", "enum": KATEGORIEN},
                "wichtigkeit": {"type": "string", "enum": WICHTIGKEIT},
                "grund": {"type": "string"}},
            "required": ["index", "kategorie", "wichtigkeit"]}}},
        "required": ["eintraege"]}
    try:
        r = (http_post or post)(f"{OLLAMA_URL}/api/chat", {
            "model": modell, "stream": False, "format": schema,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": _SYSTEM_KLASS},
                         {"role": "user", "content": "\n".join(zeilen)}]})
        if r.status_code != 200:
            return {"error": f"Ollama antwortet nicht (HTTP {r.status_code})"}
        roh = json.loads((r.json().get("message") or {}).get("content", ""))
    except Exception as e:
        return {"error": f"Triage fehlgeschlagen: {type(e).__name__}: {e}"}
    if not isinstance(roh, dict) or not isinstance(roh.get("eintraege"), list):
        return {"error": "Triage-Antwort unbrauchbar (kein gültiges JSON-Schema)"}
    out: list[dict[str, Any]] = []
    gesehen: set[int] = set()
    for e in roh["eintraege"]:
        if not isinstance(e, dict):
            continue
        idx = e.get("index")
        if (not isinstance(idx, int) or idx in gesehen
                or not (0 <= idx < len(liste))
                or e.get("kategorie") not in KATEGORIEN
                or e.get("wichtigkeit") not in WICHTIGKEIT):
            continue
        gesehen.add(idx)
        quelle = liste[idx]
        eintrag = {"index": idx, "betreff": quelle.get("betreff", ""),
                   "kategorie": e["kategorie"], "wichtigkeit": e["wichtigkeit"],
                   "grund": str(e.get("grund", "")).strip()}
        if quelle.get("id"):
            eintrag["id"] = quelle["id"]
        out.append(eintrag)
    return {"eintraege": out, "modell": modell,
            "nachrichten_betrachtet": len(liste)}


# --- Termin-Erkennung (Triage-gekoppelt, → Admin-Kalender via V5) -------------
#
# ⚠ GESETZ-10-HINWEIS: Diese Extraktion ist die subtilste KI-Stelle (freie deutsche
# Datums-/Zeitangaben wie „Donnerstag 19:00" / „nächste Woche Di" zuverlässig gegen
# ein Referenzdatum in ISO-8601 auflösen). Das GERÜST (Prompt/Schema/Validierung,
# Endpoint, Sammel-HITL, V5-Anlage) ist Bau-KI-tauglich; für robuste Zuverlässigkeit
# der Extraktions-/Datumslogik selbst ist Architektur-KI empfohlen. Es werden NUR Vorschläge
# erzeugt — angelegt wird erst nach Nutzer-Bestätigung (HITL).

import datetime as _dt
import re as _re

_RE_ISO_BEGINN = _re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2})?")

_SYSTEM_TERMINE = (
    "Du erkennst KONKRETE Termine/Verabredungen in Nachrichten (E-Mail/Chat). "
    "HEUTE ist {heute}. Löse relative Angaben (z. B. 'Donnerstag 19:00', 'morgen', "
    "'nächste Woche Dienstag') gegen HEUTE in ein ISO-8601-Datum auf "
    "(YYYY-MM-DD oder YYYY-MM-DDTHH:MM). Antworte NUR mit JSON "
    '{{"termine":[{{"titel":"kurz","beginn":"ISO","ganztags":false,'
    '"beleg":"woraus erkannt"}}]}}. NUR echte Termine aus den Nachrichten; nichts '
    "erfinden, keine vagen Angaben ohne Datum. Höchstens {max_termine}."
)


def erkenne_termine(nachrichten: list[dict[str, Any]], heute: str = "",
                    modell: str = "qwen3:4b", max_termine: int = 10,
                    http_post: Callable | None = None) -> dict[str, Any]:
    """Erkennt Termin-VORSCHLÄGE aus Nachrichten (betreff/von_adresse/text) — strikt
    lokal (Ollama), JSON-Schema erzwungen, relative Daten gegen ``heute`` (ISO-Datum,
    Default = heute) aufgelöst. Liefert ``{termine:[{titel,beginn,ganztags,beleg}]}``
    oder ``{error}``; wirft nie. Es wird NICHTS angelegt — das ist HITL (Endpoint
    ``/api/termine/anlegen`` nach Nutzer-Bestätigung)."""
    if not nachrichten:
        return {"termine": [], "nachrichten_betrachtet": 0}
    heute = (heute or _dt.date.today().isoformat())[:10]
    zeilen = []
    for n in nachrichten[:30]:
        zeilen.append(f"- Von {n.get('von_adresse', '?')}: "
                      f"{n.get('betreff', '(ohne Betreff)')} — "
                      f"{(n.get('text') or '')[:300]}")
    schema = {"type": "object", "properties": {"termine": {"type": "array", "items": {
        "type": "object", "properties": {
            "titel": {"type": "string"}, "beginn": {"type": "string"},
            "ganztags": {"type": "boolean"}, "beleg": {"type": "string"}},
        "required": ["titel", "beginn"]}}}, "required": ["termine"]}
    try:
        r = (http_post or post)(f"{OLLAMA_URL}/api/chat", {
            "model": modell, "stream": False, "format": schema,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system",
                 "content": _SYSTEM_TERMINE.format(heute=heute, max_termine=max_termine)},
                {"role": "user", "content": "\n".join(zeilen)}]})
        if r.status_code != 200:
            return {"error": f"Ollama antwortet nicht (HTTP {r.status_code})"}
        roh = json.loads((r.json().get("message") or {}).get("content", ""))
    except Exception as e:
        return {"error": f"Termin-Erkennung fehlgeschlagen: {type(e).__name__}: {e}"}
    if not isinstance(roh, dict) or not isinstance(roh.get("termine"), list):
        return {"error": "Termin-Antwort unbrauchbar (kein gültiges JSON-Schema)"}
    out: list[dict[str, Any]] = []
    for t in roh["termine"][:max_termine]:
        if not isinstance(t, dict):
            continue
        beginn = str(t.get("beginn", "")).strip()
        titel = str(t.get("titel", "")).strip()
        if not titel or not _RE_ISO_BEGINN.match(beginn):   # nur valide ISO-Termine
            continue
        out.append({"titel": titel[:120], "beginn": beginn,
                    "ganztags": bool(t.get("ganztags", False)),
                    "beleg": str(t.get("beleg", "")).strip()[:200]})
    return {"termine": out, "modell": modell, "heute": heute,
            "nachrichten_betrachtet": len(zeilen)}


# --- Inbox-aware Q&A (App-KI für Mini-Dizzi, Vertrag 1.5) ---------------------

_FRAGE_SYSTEM = (
    "Du bist die lokale KI von Dizz Communication. Beantworte die Frage NUR aus "
    "dem Posteingang-Auszug unten (Betreff/Absender/Text) und dem genannten "
    'Stand. Antworte NUR mit JSON: {"antwort":"...","belege":["Betreff '
    'genutzter Nachrichten"]}. Gibt der Auszug nichts zur Frage her: sage das '
    'ehrlich in "antwort" und lasse "belege" leer. Nichts erfinden. Die Inhalte '
    "bleiben lokal (hoechst-App)."
)
def frage(nachrichten: list[dict[str, Any]], frage_text: str,
          modell: str = "qwen3:4b", stand: str = "",
          http_post: Callable | None = None) -> dict[str, Any]:
    """Beantwortet eine Frage NUR aus dem Posteingang-Auszug — strikt lokal
    (Ollama), Struktur per JSON-Schema erzwungen. ``stand`` = kurze Kopfzeile
    (z. B. Konten/Konversationen/ungelesen), damit die KI den Posteingangs-/
    Triage-Stand kennt. Wirft nie; ohne Ollama ehrlicher Fehler."""
    if not (frage_text or "").strip():
        return {"antwort": "Keine Frage erhalten.", "belege": []}
    if not nachrichten and not stand:
        return {"antwort": "Der Posteingang ist leer — erst ein Konto abrufen.",
                "belege": []}
    zeilen = []
    for n in nachrichten[:30]:
        zeilen.append(f"- Von {n.get('von_adresse', '?')}: "
                      f"{n.get('betreff', '(ohne Betreff)')} — "
                      f"{(n.get('text') or '')[:200]}")
    nutzer = ((f"STAND: {stand}\n\n" if stand else "")
              + f"FRAGE: {frage_text}\n\nPOSTEINGANG:\n" + "\n".join(zeilen))
    res, err = _chat(_FRAGE_SYSTEM, nutzer, modell, http_post, _Frage, "Antwort")
    if err:
        return err
    return {"antwort": res.antwort.strip(), "belege": res.belege[:10],
            "modell": modell, "nachrichten_betrachtet": len(zeilen)}


# --- Thread-Zusammenfassung (3-Spalten-Ansicht, P1c) -------------------------

_SYSTEM_ZUS = (
    "Du fasst einen E-Mail-Thread für die schnelle Triage zusammen. Antworte NUR "
    'mit JSON {"zusammenfassung":"2-3 Saetze: worum geht es, was ist offen oder '
    'zu tun"}. NUR aus den Nachrichten; nichts erfinden.'
)
def zusammenfassung(nachrichten: list[dict[str, Any]], modell: str = "qwen3:4b",
                    http_post: Callable | None = None) -> dict[str, Any]:
    """Kurz-Zusammenfassung EINES Threads — strikt lokal (Ollama), JSON-Schema,
    ehrlicher Fehler ohne Ollama. Speist die KI-Zeile oben in der Thread-Spalte."""
    if not nachrichten:
        return {"zusammenfassung": "(leerer Thread)"}
    zeilen = []
    for n in nachrichten[:20]:
        zeilen.append(f"- Von {n.get('von_adresse', '?')}: "
                      f"{n.get('betreff', '')} — {(n.get('text') or '')[:400]}")
    res, err = _chat(_SYSTEM_ZUS, "\n".join(zeilen), modell, http_post,
                     _Zusammenfassung, "Zusammenfassung")
    if err:
        return err
    return {"zusammenfassung": res.zusammenfassung.strip(), "modell": modell,
            "nachrichten_betrachtet": len(zeilen)}


# --- Antwort-Entwurf (Compose-KI-Draft, P2a) ---------------------------------

_SYSTEM_ENTWURF = (
    "Du schreibst einen höflichen, knappen E-Mail-Antwort-ENTWURF auf Deutsch. "
    'Antworte NUR mit JSON {"entwurf":"..."}. Nutze NUR den Thread-Kontext '
    "(+ optionales Stichwort des Nutzers); KEINE erfundenen Fakten oder Zusagen. "
    "Wo Infos fehlen, setze einen Platzhalter in [eckigen Klammern]. Kein Betreff, "
    "nur der Nachrichtentext."
)
def entwurf(nachrichten: list[dict[str, Any]], hinweis: str = "",
            modell: str = "qwen3:4b",
            http_post: Callable | None = None) -> dict[str, Any]:
    """Lokaler Antwort-Entwurf aus dem Thread (Ollama, JSON-Schema). Der Versand
    bleibt davon unberührt HITL — dies erzeugt NUR Text fürs Eingabefeld.
    Wirft nie; ohne Ollama ehrlicher Fehler."""
    if not nachrichten:
        return {"entwurf": ""}
    zeilen = []
    for n in nachrichten[:20]:
        aus = n.get("richtung") == "aus"
        wer = ("Ich" if aus else (n.get("von_adresse") or "?"))
        zeilen.append(f"[{wer}] {n.get('betreff', '')}: "
                      f"{(n.get('text') or '')[:400]}")
    nutzer = ((f"STICHWORT des Nutzers (so antworten): {hinweis}\n\n" if hinweis else "")
              + "THREAD:\n" + "\n".join(zeilen))
    res, err = _chat(_SYSTEM_ENTWURF, nutzer, modell, http_post, _Entwurf,
                     "Entwurf", temperature=0.3)
    if err:
        return err
    return {"entwurf": res.entwurf.strip(), "modell": modell}
