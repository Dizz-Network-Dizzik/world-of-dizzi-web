"""KI-Ebene von Dizz Management (App-KI-Slot für Mini-Dizzi + /api/plan, Vertrag 1.5).

Das ist die **übergreifende KI-Verwaltungs-Ebene** der App (APP_GRUNDLAGEN §B
„Multi-Agent"): der übergeordnete Manager, der ÜBER allen Kanal-Bots beobachtet und
beim Kanal-Verwalten/Content-Planen hilft. Gleiche Schule wie Dizz Healthy/Plans/
News: lokales Ollama (0 €), striktes JSON-Schema als Grammatik, ehrlicher Fehler
statt Halluzination. Sie arbeitet AUSSCHLIESSLICH auf dem App-Kontext (Kanäle,
Social-Bots, Posts, Zeitplan) — sie erfindet keine Konten/Zahlen dazu.

═══ SICHERHEITS-GRUNDREGEL (docs/RECHERCHE §4–§5, APP_GRUNDLAGEN §A1) ════════════
- **Beobachten + vorschlagen, NIE eigenmächtig posten.** Veröffentlichen ist eine
  Außenwirkungs-Aktion und läuft nur über die HITL-Aktion ``post_veroeffentlichen``
  (domain.py). Diese KI schlägt Plan/Texte/Zeiten vor — die Freigabe macht der Nutzer.
- **Lokal-first.** sensitivity='hoch' ⇒ KI-Routing-Default 'lokal_only' (Manifest):
  Inhalte/Tokens gehen NIE an Boost-/Cloud-Modelle.
═════════════════════════════════════════════════════════════════════════════════

``main.py`` registriert ``frage`` über ``mini_dizzi.set_app_ki``; der Domänen-Router
ruft ``plane`` für die strukturierte Planung. Liefert die KI nichts Brauchbares, gibt
sie ``{"antwort": ""}`` bzw. eine leere Vorschlagsliste zurück ⇒ der Aufrufer fällt
sauber zurück (kein erfundener Inhalt).

Schema-Quelle = Pydantic-Modelle (docs/50 P2.1): ``Model.model_json_schema()`` erzeugt
das Ollama-``format`` (constrained decoding), ``Model.model_validate_json`` prüft die
Antwort — EINE Quelle für Struktur UND Validierung (kein Doppel-Schema, kein Hand-Cast).
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from appkit.ollama import strukturiert

HINWEIS = ("Dizz Management beobachtet und schlägt vor — Veröffentlichen passiert "
           "NIE eigenmächtig, sondern erst nach deiner Freigabe (HITL).")

_SYSTEM = (
    "Du bist die KI von Dizz Management, der KI-Agenten-Verwaltung des Netzes; "
    "deine aktuelle Domäne ist Social Media. Du beobachtest "
    "die Kanäle, Social-Media-Bots (Themen-/Marken-Profile), Entwürfe/Posts und den "
    "Zeitplan des Nutzers und hilfst beim Verwalten und Planen. Beantworte NUR aus "
    "dem gegebenen Kontext. WICHTIG: Du POSTEST NICHTS eigenmächtig — du schlägst nur "
    "vor; Veröffentlichen gibt der Nutzer frei (HITL). Antworte knapp und auf Deutsch, "
    "NUR als JSON: {\"antwort\":\"...\"}. Gibt der Kontext nichts zur Frage her, sage "
    "das ehrlich. Nichts erfinden."
)

_SYSTEM_PLAN = (
    "Du bist die KI von Dizz Management, der KI-Agenten-Verwaltung des Netzes; "
    "deine aktuelle Domäne ist Social Media. Werte den Kontext "
    "(Kanäle, aktive Social-Bots, Entwürfe/Posts, Zeitplan) aus und gib 2–6 KONKRETE, "
    "umsetzbare Vorschläge zur Content-Planung: z. B. welche Entwürfe als nächstes "
    "geplant/veröffentlicht werden sollten, Content-Recycling über Plattformen (ein "
    "Stück → mehrere Formate), sinnvolle Posting-Zeiten, Lücken im Redaktionsplan. "
    "KEINE erfundenen Konten/Zahlen, kein eigenmächtiges Posten — nur Vorschläge. Nur "
    "aus dem Kontext. Antworte auf Deutsch, NUR als JSON: {\"vorschlaege\":[\"...\"]}. "
    "Keine Vorschläge möglich ⇒ leere Liste."
)

# Antwort-Schemas: Pydantic = EINE Quelle für format= UND Validierung (docs/50 P2.1).
# model_json_schema() erzwingt die Struktur per Grammatik (Live-Lehre 12.06.: bloßes
# format="json" wich bei großem Input auf fremde Formen aus).
class _Antwort(BaseModel):
    antwort: str


class _Vorschlaege(BaseModel):
    vorschlaege: list[str] = []




def _kontext_text(kontext: dict[str, Any]) -> str:
    kanaele = kontext.get("kanaele") or []
    bots = kontext.get("bots") or []
    posts = kontext.get("posts") or []
    zeitplan = kontext.get("zeitplan") or []

    zeilen = ["KANÄLE (Plattform · Handle · Status):"]
    zeilen.append("\n".join(
        f"- {k.get('plattform', '?')}: {k.get('handle', '') or '—'} "
        f"({k.get('status', '?')})" for k in kanaele[:30]) or "- (noch keine Kanäle)")

    zeilen.append("AKTIVE SOCIAL-BOTS (Name · Thema · Ton · Zielgruppe):")
    zeilen.append("\n".join(
        f"- {b.get('name', '?')}: {b.get('thema', '') or '—'} "
        f"(Ton {b.get('ton', '?')}, Zielgruppe {b.get('zielgruppe', '') or '—'})"
        for b in bots[:20]) or "- (keine aktiven Bots)")

    zeilen.append("JÜNGSTE POSTS/ENTWÜRFE (Titel · Plattform · Status · geplant):")
    zeilen.append("\n".join(
        f"- {p.get('titel', '') or '(ohne Titel)'} · {p.get('plattform', '') or '—'} · "
        f"{p.get('status', '?')}{(' · ' + p.get('geplant_fuer', '')) if p.get('geplant_fuer') else ''}"
        for p in posts[:20]) or "- (noch keine Posts)")

    zeilen.append("ZEITPLAN (kommende geplante Posts):")
    zeilen.append("\n".join(
        f"- {z.get('geplant_fuer', '?')}: {z.get('titel', '') or '(ohne Titel)'} "
        f"({z.get('plattform', '') or '—'})" for z in zeitplan[:15]) or "- (nichts geplant)")

    return "\n".join(zeilen)


def frage(kontext: dict[str, Any], frage_text: str, modell: str = "qwen3:4b",
          http_post: Callable | None = None) -> dict[str, Any]:
    """Beantwortet eine Frage NUR aus dem Management-Kontext. Wirft nie.
    ``{"antwort": ""}`` ⇒ Mini-Dizzi nutzt seinen generischen Fallback."""
    frage_text = (frage_text or "").strip()
    if not frage_text:
        return {"antwort": ""}
    res = strukturiert(_SYSTEM, f"FRAGE: {frage_text}\n\nKONTEXT:\n{_kontext_text(kontext)}",
                       modell=modell, schema=_Antwort, http_post=http_post, temperature=0.1)
    return {"antwort": res.antwort.strip() if res else ""}


def plane(kontext: dict[str, Any], modell: str = "qwen3:4b",
          http_post: Callable | None = None) -> dict[str, Any]:
    """Strukturierte Planung: konkrete Vorschläge (Liste) aus dem Kontext + immer der
    HITL-Hinweis. Wirft nie; ohne erreichbares Ollama ⇒ leere Liste + ehrlicher
    Quellen-Hinweis."""
    res = strukturiert(_SYSTEM_PLAN, f"KONTEXT:\n{_kontext_text(kontext)}",
                       modell=modell, schema=_Vorschlaege, http_post=http_post, temperature=0.3)
    if res is None:
        return {"vorschlaege": [], "hinweis": HINWEIS, "quelle": "kein_ollama"}
    vorschlaege = [v.strip() for v in res.vorschlaege if v.strip()]
    return {"vorschlaege": vorschlaege[:8], "hinweis": HINWEIS, "quelle": "lokale_ki"}
