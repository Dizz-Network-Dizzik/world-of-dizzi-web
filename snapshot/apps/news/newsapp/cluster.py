"""Cross-Source-Dedup / Story-Clustering — Backlog docs/33 §news.

Dieselbe Meldung kommt oft aus mehreren Feeds (tagesschau + Guardian + …). Ohne
Zusammenführung zeigt der Digest die Story 5×. Dieser Modul fasst Artikel, die
mit hoher Sicherheit DIESELBE Story sind, zu Clustern zusammen.

**Deterministisch + lokal** (keine KI, kein Netz): die Entscheidung beruht auf
- **Titel-Token-Jaccard** (lowercased, Stoppwörter/Kurzwörter raus; DE+EN), und
- **URL-Slug-Ähnlichkeit** (letztes Pfadsegment), und
- **Enthaltensein** (kurzer Titel vollständig im langen, mit genug Substanz).
Greedy in Eingabe-Reihenfolge (Aufrufer liefern neueste zuerst ⇒ der neueste
Treffer wird Repräsentant); Vergleich nur gegen die Repräsentanten ⇒ stabil/O(n·k).

Bewusst KONSERVATIV (lieber eine Dublette übersehen als zwei verschiedene Stories
falsch verschmelzen) — Schwellen unten dokumentiert.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

# Schwellen (konservativ; eher trennen als falsch mergen).
TITEL_SCHWELLE = 0.5      # Jaccard der Titel-Token
SLUG_SCHWELLE = 0.6       # Jaccard der URL-Slug-Token
SLUG_MIN_GETEILT = 2      # so viele Slug-Token müssen gemeinsam sein (s. gleiche_story)
MIN_ENTHALTEN = 3         # so viele Token muss der kurze Titel mind. haben (Subset-Regel)

_WORT = re.compile(r"[0-9a-zA-ZäöüÄÖÜß]+")

# Kleiner DE+EN-Stoppwort-Satz (Titel-Rauschen raus, damit Jaccard das Thema misst).
_STOPP = {
    # DE
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines",
    "und", "oder", "aber", "mit", "von", "für", "auf", "aus", "bei", "nach",
    "über", "vor", "zum", "zur", "ist", "sind", "war", "waren", "wird", "werden",
    "hat", "haben", "nicht", "auch", "sich", "als", "wie", "was", "wer", "wenn",
    "dass", "im", "in", "an", "am", "zu", "so", "es", "er", "sie", "wir", "ihr",
    "sein", "seine", "ihre", "mehr", "neue", "neuer", "neues", "gegen",
    # EN
    "the", "and", "or", "but", "with", "for", "from", "this", "that", "into",
    "over", "after", "are", "was", "were", "will", "has", "have", "not", "its",
    "new", "now", "you", "your", "his", "her", "they", "how", "why", "who",
    "when", "where", "what", "a", "an", "to", "of", "on", "at", "by", "as",
    "is", "it", "be", "in",
}


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _WORT.findall((text or "").lower())
                     if len(t) >= 3 and t not in _STOPP)


def titel_tokens(titel: str) -> frozenset[str]:
    """Bedeutungstragende Titel-Token (Stoppwörter/Kurzwörter entfernt)."""
    return _tokens(titel)


def url_slug_tokens(link: str) -> frozenset[str]:
    """Token aus dem letzten URL-Pfadsegment (der „Slug" trägt oft den Titel).
    Reine Zahlen (Datums-/ID-Segmente) fallen weg."""
    try:
        path = urlsplit(link or "").path
    except Exception:
        return frozenset()
    segmente = [s for s in path.split("/") if s]
    if not segmente:
        return frozenset()
    last = re.sub(r"\.(html?|php|aspx?|amp)$", "", segmente[-1], flags=re.I)
    return frozenset(t for t in _tokens(last) if not t.isdigit())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def gleiche_story(a_tok: frozenset[str], b_tok: frozenset[str],
                  a_slug: frozenset[str], b_slug: frozenset[str]) -> bool:
    """Entscheidet, ob zwei Artikel dieselbe Story sind (konservativ)."""
    if _jaccard(a_tok, b_tok) >= TITEL_SCHWELLE:
        return True
    # Enthaltensein: der kürzere (substanzielle) Titel steckt komplett im längeren.
    if a_tok and b_tok:
        kleiner, groesser = sorted((a_tok, b_tok), key=len)
        if len(kleiner) >= MIN_ENTHALTEN and kleiner <= groesser:
            return True
    # URL-Slug: NUR mit genug gemeinsamer Substanz. Ein einzelnes generisches
    # Slug-Wort (z. B. „video" aus …/video-12345.html) darf NIE mergen — sonst
    # verschmelzen alle Video-Beiträge einer Quelle (real beobachtet 20.06.).
    if (len(a_slug & b_slug) >= SLUG_MIN_GETEILT
            and _jaccard(a_slug, b_slug) >= SLUG_SCHWELLE):
        return True
    return False


def _gruppen(artikel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Greedy-Gruppierung; intern: {rep, tok, slug, dubletten:[...]}."""
    reps: list[dict[str, Any]] = []
    for row in artikel:
        tok = titel_tokens(row.get("titel"))
        slug = url_slug_tokens(row.get("link"))
        ziel = None
        for c in reps:
            if gleiche_story(tok, c["tok"], slug, c["slug"]):
                ziel = c
                break
        if ziel is None:
            reps.append({"rep": row, "tok": tok, "slug": slug, "dubletten": []})
        else:
            ziel["dubletten"].append(row)
    return reps


def clustere(artikel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fasst gleiche Stories zusammen. Liefert je Cluster den Repräsentanten plus
    ``anzahl``, ``quellen`` (eindeutig, in Erst-Reihenfolge) und ``dubletten``."""
    out: list[dict[str, Any]] = []
    for c in _gruppen(artikel):
        rep, dub = c["rep"], c["dubletten"]
        quellen: list[str] = []
        for r in (rep, *dub):
            qn = str(r.get("quelle") or "")
            if qn and qn not in quellen:
                quellen.append(qn)
        eintrag = {k: rep.get(k) for k in
                   ("id", "titel", "link", "quelle", "sektor",
                    "published_at", "created_at", "zusammenfassung")}
        eintrag["anzahl"] = 1 + len(dub)
        eintrag["quellen"] = quellen
        eintrag["dubletten"] = [{k: d.get(k) for k in
                                 ("id", "titel", "link", "quelle", "sektor")}
                                for d in dub]
        out.append(eintrag)
    return out


def dedupe(artikel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nur je EIN Repräsentant pro Story (für die KI-Eingabe) — voller Original-
    Datensatz, Reihenfolge wie Eingabe."""
    return [c["rep"] for c in _gruppen(artikel)]
