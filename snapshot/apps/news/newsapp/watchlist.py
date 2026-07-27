"""Watchlist-Themen-Matching (Phase 3) — deterministisch + lokal.

Eine **Watchlist** ist ein lebender Themen-Ordner mit freier Beschreibung
(``thema``). Nach jedem Abruf werden neue Artikel, die thematisch zur Beschreibung
passen, automatisch ergänzt. Das Matching ist **DETERMINISTISCH** (Token-Overlap,
wiederverwendet die Tokenisierung/Stoppwörter aus ``cluster.py``) — 0 Netz,
test-sicher, fail-safe (wirft nie, kein Modell nötig).

Kern-Maß ist die **Containment** = Anteil der bedeutungstragenden THEMEN-Token,
die im Artikel (Titel + Summary + Volltext-Auszug) vorkommen. Das passt besser als
Jaccard, weil der Artikel meist viel länger als die Themenbeschreibung ist.

Optionale KI-Schärfung (Nutzer-Wunsch „Embeddings"): ein injizierbarer
``embed_fn(text) -> list[float]`` (z. B. Ollama-Embedding) + ``cosine`` sind hier
vorbereitet (Gesetz 5), aber standardmäßig AUS — der deterministische Pfad ist der
ausgelieferte Default; Embeddings sind ein späterer, opt-in Aufsatz.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from . import cluster

# Anteil der Themen-Token, der im Artikel vorkommen muss (per Setting überschreibbar).
SCHWELLE = 0.34
# Volltext-Auszug, der ins Matching einfließt (begrenzt Rauschen + Aufwand).
_VOLLTEXT_MAX = 600


def thema_tokens(thema: str) -> frozenset[str]:
    """Bedeutungstragende Token der Themenbeschreibung (Stoppwörter raus)."""
    return cluster._tokens(thema or "")


def artikel_tokens(a: dict[str, Any]) -> frozenset[str]:
    """Token aus Titel + Summary + (gedeckeltem) Volltext eines Artikels."""
    teile = [str(a.get("titel") or ""), str(a.get("zusammenfassung") or ""),
             str(a.get("volltext") or "")[:_VOLLTEXT_MAX]]
    return cluster._tokens(" ".join(teile))


def score(thema_tok: frozenset[str], art_tok: frozenset[str]) -> float:
    """Containment: Anteil der Themen-Token, die im Artikel vorkommen (0..1)."""
    if not thema_tok:
        return 0.0
    return len(thema_tok & art_tok) / len(thema_tok)


def passt(thema_tok: frozenset[str], art_tok: frozenset[str],
          schwelle: float = SCHWELLE) -> bool:
    """True, wenn der Artikel thematisch zur Watchlist passt (deterministisch)."""
    return bool(thema_tok) and score(thema_tok, art_tok) >= schwelle


def bewerte_artikel(thema: str, artikel: dict[str, Any],
                    schwelle: float = SCHWELLE) -> tuple[bool, float]:
    """Komfort-Wrapper für EINEN Artikel: ``(passt?, score)`` (gerundet)."""
    tt = thema_tokens(thema)
    s = score(tt, artikel_tokens(artikel))
    return (bool(tt) and s >= schwelle, round(s, 3))


# --------- optionaler Embedding-Pfad (vorbereitet, Default AUS, Gesetz 5) --------

def cosine(a: list[float], b: list[float]) -> float:
    """Cosinus-Ähnlichkeit zweier Vektoren; 0.0 bei leeren/Null-Vektoren."""
    if not a or not b or len(a) != len(b):
        return 0.0
    pa = math.sqrt(sum(x * x for x in a))
    pb = math.sqrt(sum(x * x for x in b))
    if pa == 0 or pb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (pa * pb)


def passt_embedding(thema_vec: list[float], art_vec: list[float],
                    schwelle: float = 0.6) -> bool:
    """Embedding-Variante (opt-in): Cosinus(Thema, Artikel) ≥ Schwelle.
    Aufrufer reicht vorberechnete Vektoren (``embed_fn``) — hier kein Netz."""
    return cosine(thema_vec, art_vec) >= schwelle


def embed_seam_aktiv(embed_fn: Callable | None) -> bool:
    """Doku-Helfer: ob der optionale Embedding-Pfad verdrahtet ist."""
    return embed_fn is not None
