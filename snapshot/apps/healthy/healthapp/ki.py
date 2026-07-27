"""KI-Ebene von Dizz Healthy (App-KI-Slot für Mini-Dizzi + /api/analyse, Vertrag 1.5).

Gleiche Schule wie Dizz Plans/Admin/News: lokales Ollama (0 €), striktes JSON-Schema
als Grammatik (gegen Format-Abdriften bei großem Input), ehrlicher Fehler statt
Halluzination. Die KI arbeitet AUSSCHLIESSLICH auf dem App-Kontext (Trends der
Messwerte, aktive Supplements, offene Verletzungen, Training, nächste Termine) —
sie erfindet keine Werte dazu.

═══ SICHERHEITS-GRUNDREGEL (docs/RECHERCHE §4–§5, APP_GRUNDLAGEN §A1) ════════════
- HOCHSENSIBEL ⇒ **strikt lokal**. Diese KI läuft nur gegen lokales Ollama; das
  Manifest-Routing (sensitivity='hoechst' ⇒ lokal_only) verbietet jeden Boost-/
  Cloud-Pfad. Gesundheitsdaten verlassen den Rechner NIE über ein Modell.
- **Beobachten + Hinweise, KEINE Diagnose.** Jede Ausgabe trägt den Disclaimer.
  Die KI deutet sanft an („Ruhepuls zog die letzten Tage an — vielleicht beobachten"),
  diagnostiziert/behandelt aber nicht und ersetzt keine ärztliche Beratung.
═════════════════════════════════════════════════════════════════════════════════

``main.py`` registriert ``frage`` über ``mini_dizzi.set_app_ki``; der Domänen-Router
ruft ``analysiere`` für die strukturierte Auswertung. Liefert die KI nichts
Brauchbares, gibt sie ``{"antwort": ""}`` bzw. eine leere Hinweisliste zurück ⇒ der
Aufrufer fällt sauber zurück (kein erfundener Inhalt).
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from appkit.ollama import strukturiert

DISCLAIMER = ("Dizz Healthy beobachtet und gibt Anregungen — es stellt KEINE "
              "Diagnose und ersetzt keine ärztliche Beratung.")

_SYSTEM = (
    "Du bist die Gesundheits-KI von Dizz Healthy. Du beobachtest die selbst "
    "eingetragenen Werte des Nutzers (Vitalwerte, Gewicht, Supplements, "
    "Verletzungen, Training, Termine) und gibst SANFTE, allgemeine Hinweise und "
    "Anregungen. Beantworte NUR aus dem gegebenen Kontext. WICHTIG: Du stellst "
    "KEINE Diagnose, empfiehlst keine Medikamente/Dosierungen und ersetzt keine "
    "ärztliche Beratung — bei auffälligen oder anhaltenden Werten rätst du, "
    "ärztlichen Rat einzuholen. Antworte knapp, ruhig und auf Deutsch, NUR als "
    "JSON: {\"antwort\":\"...\"}. Gibt der Kontext nichts zur Frage her, sage das "
    "ehrlich. Nichts erfinden, nichts dramatisieren."
)

_SYSTEM_ANALYSE = (
    "Du bist die Gesundheits-KI von Dizz Healthy. Werte den gegebenen Kontext "
    "(Trends der Messwerte, aktive Supplements, offene Verletzungen, jüngstes "
    "Training, nächste Termine) aus und gib 2–5 SANFTE, konkrete Beobachtungs-"
    "Hinweise (z. B. auffällige Trends, Erholung vs. Belastung, anstehende "
    "Vorsorge). KEINE Diagnose, keine Medikamenten-/Dosierungs-Empfehlung, kein "
    "Alarmismus — bei Auffälligkeiten zu ärztlichem Rat ermutigen. Nur aus dem "
    "Kontext, nichts erfinden. Antworte auf Deutsch, NUR als JSON: "
    "{\"hinweise\":[\"...\"]}. Keine Hinweise möglich ⇒ leere Liste."
)

# Antwort-Schemas: Pydantic = EINE Quelle für format= UND Validierung (docs/50 P2.1).
# model_json_schema() erzwingt die Struktur per Grammatik (Live-Lehre 12.06.: bloßes
# format="json" wich bei großem Input auf fremde Formen aus).
class _Antwort(BaseModel):
    antwort: str


class _Hinweise(BaseModel):
    hinweise: list[str] = []


class _Vorschlaege(BaseModel):
    vorschlaege: list[str] = []


_SYSTEM_VORSCHLAG = (
    "Du bist die Gesundheits-KI von Dizz Healthy. Gib auf Basis der heutigen "
    "Datenlage (Trainings, Aktivität, Supplements, Termine) 1–3 KONKRETE, sanfte, "
    "umsetzbare Alltags-Vorschläge — z. B. eine einfache, ausgewogene Mahlzeiten-Idee, "
    "eine kurze Bewegungs- oder Erholungs-Anregung. KEINE Diagnose, KEINE Medikamenten-/ "
    "Dosierungs-Empfehlung, keine speziellen Diäten bei Erkrankungen, kein Alarmismus. "
    "Allgemein und freundlich, nur aus dem Kontext, nichts erfinden. Antworte auf "
    "Deutsch, NUR als JSON: {\"vorschlaege\":[\"...\"]}. Nichts Sinnvolles möglich ⇒ leere Liste."
)
# (Schema _Vorschlaege oben definiert — Single-Source, P2.1)


def _trend_pfeil(richtung: str) -> str:
    return {"steigend": "↑", "fallend": "↓", "stabil": "→"}.get(richtung, "·")


def _kontext_text(kontext: dict[str, Any]) -> str:
    trends = kontext.get("trends") or []
    supp = kontext.get("supplements") or []
    verl = kontext.get("verletzungen") or []
    train = kontext.get("training") or []
    term = kontext.get("termine") or []

    zeilen = ["MESSWERT-TRENDS (jüngster Wert · Richtung · Schnitt im Zeitfenster):"]
    if trends:
        for t in trends[:14]:
            ref = ""
            if t.get("im_referenzbereich") is False:
                ref = " [außerhalb des üblichen Bereichs — orientierend, keine Diagnose]"
            zeilen.append(
                f"- {t.get('label', t.get('art'))}: {t.get('letzter_wert')} "
                f"{t.get('einheit', '')} {_trend_pfeil(t.get('richtung', ''))} "
                f"({t.get('richtung', '?')}, Ø {t.get('mittel', '?')}, "
                f"n={t.get('anzahl', 0)}){ref}")
    else:
        zeilen.append("- (noch keine Messwerte erfasst)")

    zeilen.append("AKTIVE SUPPLEMENTS:")
    zeilen.append("\n".join(
        f"- {s.get('name', '?')} ({s.get('dosis', '')} {s.get('einheit', '')}, "
        f"{s.get('frequenz', '')})" for s in supp[:15]) or "- (keine)")

    zeilen.append("OFFENE VERLETZUNGEN:")
    zeilen.append("\n".join(
        f"- {x.get('koerperregion', '?')}: {x.get('beschreibung', '')} "
        f"(Status {x.get('status', '?')}, Schwere {x.get('schweregrad', '?')})"
        for x in verl[:10]) or "- (keine)")

    zeilen.append("JÜNGSTES TRAINING:")
    zeilen.append("\n".join(
        f"- {t.get('trainiert_am', '')}: {t.get('art', '?')} "
        f"({t.get('dauer_min', '?')} min, {t.get('intensitaet', '?')})"
        for t in train[:10]) or "- (keins)")

    zeilen.append("NÄCHSTE TERMINE:")
    zeilen.append("\n".join(
        f"- {t.get('beginn', '?')}: {t.get('titel', '?')} "
        f"({t.get('kategorie', '')})" for t in term[:10]) or "- (keine)")

    return "\n".join(zeilen)


def frage(kontext: dict[str, Any], frage_text: str, modell: str = "qwen3:4b",
          http_post: Callable | None = None) -> dict[str, Any]:
    """Beantwortet eine Frage NUR aus dem Health-Kontext. Wirft nie.
    ``{"antwort": ""}`` ⇒ Mini-Dizzi nutzt seinen generischen Fallback."""
    frage_text = (frage_text or "").strip()
    if not frage_text:
        return {"antwort": ""}
    res = strukturiert(_SYSTEM, f"FRAGE: {frage_text}\n\nKONTEXT:\n{_kontext_text(kontext)}",
                       modell=modell, schema=_Antwort, http_post=http_post, temperature=0.1)
    return {"antwort": res.antwort.strip() if res else ""}


def analysiere(kontext: dict[str, Any], modell: str = "qwen3:4b",
               http_post: Callable | None = None) -> dict[str, Any]:
    """Strukturierte Auswertung: sanfte Hinweise (Liste) aus dem Kontext + immer der
    Disclaimer. Wirft nie; ohne erreichbares Ollama ⇒ leere Hinweisliste + ehrlicher
    Quellen-Hinweis (die deterministischen Trends liefert die Domäne separat)."""
    res = strukturiert(_SYSTEM_ANALYSE, f"KONTEXT:\n{_kontext_text(kontext)}",
                       modell=modell, schema=_Hinweise, http_post=http_post, temperature=0.2)
    if res is None:
        return {"hinweise": [], "disclaimer": DISCLAIMER, "quelle": "kein_ollama"}
    hinweise = [h.strip() for h in res.hinweise if h.strip()]
    return {"hinweise": hinweise[:6], "disclaimer": DISCLAIMER, "quelle": "lokale_ki"}


def vorschlaege(kontext: dict[str, Any], modell: str = "qwen3:4b",
                http_post: Callable | None = None) -> dict[str, Any]:
    """Weiche, konkrete Alltags-Vorschläge (Mahlzeit/Bewegung/Erholung) aus dem
    Kontext — die OPTIONALE KI-Schicht über den deterministischen Nudges. Wirft nie;
    ohne erreichbares Ollama ⇒ leere Liste (die Regel-Nudges der Domäne bleiben gültig).
    HOCHSENSIBEL ⇒ strikt lokal; NIE Diagnose."""
    res = strukturiert(_SYSTEM_VORSCHLAG, f"KONTEXT:\n{_kontext_text(kontext)}",
                       modell=modell, schema=_Vorschlaege, http_post=http_post, temperature=0.3)
    if res is None:
        return {"vorschlaege": [], "disclaimer": DISCLAIMER, "quelle": "kein_ollama"}
    vors = [v.strip() for v in res.vorschlaege if v.strip()]
    return {"vorschlaege": vors[:3], "disclaimer": DISCLAIMER, "quelle": "lokale_ki"}
