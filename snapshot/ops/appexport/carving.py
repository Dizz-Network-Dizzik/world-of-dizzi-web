"""Dependency-Carving — Hülle + Abschluss-Prüfung (docs/66 §3, Invariante I-6).

Pur und schon real: ``huelle_aus_kanten`` (transitiver Abschluss, deterministisch
sortiert), ``pruefe_abschluss`` (beobachtet⊆deklariert ⇒ sonst Fehler; Über-
Deklaration ⇒ Warnung) und ``schwer_nur_transitiv`` (Schwer-Module-Regel §3.2).
Bau-Stubs: die AST-Beobachter (C1-1) werfen ``NichtGebaut``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from . import NichtGebaut

# Schwer-Module (docs/66 §3.2): eigene Dienste/Deps — stille transitive Mitnahme
# ist erlaubt, wird aber als Warnung gemeldet (bewusste Entscheidung statt Zufall).
SCHWER_MODULE: frozenset[str] = frozenset({"ollama", "mcp", "runtime", "agenten", "app_gateway"})

# appkit-Modul → pip-Distributionen. BEWUSST LEER im Vertrag: wird in C1-2 maschinell
# erhoben (AST-Imports ∩ importlib.metadata.packages_distributions), nicht handgeraten
# (docs/66 §3.5 — Ehrlichkeit vor Aktivität).
MODUL_PIP_DEPS: dict[str, tuple[str, ...]] = {}


def huelle_aus_kanten(direkt: Iterable[str], kanten: Mapping[str, Iterable[str]]) -> tuple[str, ...]:
    """Transitiver Abschluss der direkt genutzten appkit-Module über die
    Binnen-Import-Kanten. Zyklen-fest; Knoten ohne Kanteneintrag sind Blätter;
    Ergebnis deterministisch sortiert (Reproduzierbarkeit, §3.2)."""
    huelle: set[str] = set()
    stapel = sorted(set(direkt))
    while stapel:
        modul = stapel.pop()
        if modul in huelle:
            continue
        huelle.add(modul)
        stapel.extend(nachbar for nachbar in kanten.get(modul, ()) if nachbar not in huelle)
    return tuple(sorted(huelle))


@dataclass(frozen=True)
class AbschlussBefund:
    """Ergebnis der Abschluss-Prüfung (I-6). ``fehlend`` = beobachtet, aber nicht
    deklariert (FEHLER — Export verweigert); ``ueberzaehlig`` = deklariert, aber
    nicht beobachtet (WARNUNG — erlaubt, gemeldet)."""
    fehlend: tuple[str, ...]
    ueberzaehlig: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.fehlend


def pruefe_abschluss(deklariert: Iterable[str], beobachtet: Iterable[str]) -> AbschlussBefund:
    """Vergleicht DEKLARIERT (export_manifest) mit BEOBACHTET (AST-Scan) — §3.2."""
    dek, beo = set(deklariert), set(beobachtet)
    return AbschlussBefund(
        fehlend=tuple(sorted(beo - dek)),
        ueberzaehlig=tuple(sorted(dek - beo)),
    )


def schwer_nur_transitiv(deklariert: Iterable[str], huelle: Iterable[str]) -> tuple[str, ...]:
    """Schwer-Module, die NUR über die Hülle (nicht direkt deklariert) ins Bündel
    kämen — je Treffer gibt der Prüfer eine Warnung mit Kanten-Pfad aus (C1-1)."""
    return tuple(sorted(SCHWER_MODULE & (set(huelle) - set(deklariert))))


def ermittle_direkte_nutzung(app_pfad: Path) -> frozenset[str]:
    """AST-Scan der App (ohne tests/): direkte appkit-Modul-Nutzung — Bau C1-1.
    Vertrag: reine Quelltext-Analyse, importiert NIE die App oder appkit (I-11)."""
    raise NichtGebaut("C1-1 (docs/66 §10): AST-Beobachter")


def ermittle_appkit_kanten(appkit_pfad: Path) -> dict[str, frozenset[str]]:
    """AST-Scan von packages/appkit: Binnen-Import-Kanten je Modul — Bau C1-1."""
    raise NichtGebaut("C1-1 (docs/66 §10): appkit-Kanten-Scan")
