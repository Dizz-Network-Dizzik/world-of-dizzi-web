"""Lizenz-Manifest + Ampel-Regelwerk (docs/66 §5; Invarianten I-4/I-5/I-9).

Die Ampel ist pur und schon real (fail-closed: unbekannt ⇒ rot). Der Manifest-
Generator (maschinelle Erhebung via importlib.metadata) ist Bau C1-2.
``BEKANNTE_KOMPONENTEN`` = kuratierter STARTBESTAND mit Beleg — nur Einträge,
deren Lizenz verifiziert ist; alles Übrige bleibt rot, bis C1-2 es erhebt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import NichtGebaut
from .editionen import EDITIONEN

AMPEL_GRUEN = "gruen"
AMPEL_AUFLAGE = "gruen_mit_auflage"
AMPEL_GATE = "gate"
AMPEL_ROT = "rot"
AMPELN: tuple[str, ...] = (AMPEL_GRUEN, AMPEL_AUFLAGE, AMPEL_GATE, AMPEL_ROT)

KLASSEN: tuple[str, ...] = ("eigen", "stdlib", "pip", "nachgeladen", "daten")
ISOLATION_LGPL = "lgpl_isoliert"   # I-5: unmodifiziert + austauschbar + Lizenztext in LICENSES/

PERMISSIV: frozenset[str] = frozenset({
    "MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC",
    "PSF-2.0", "Unlicense", "0BSD", "Public-Domain",
})
MPL: frozenset[str] = frozenset({"MPL-2.0"})
LGPL: frozenset[str] = frozenset({
    "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
})
COPYLEFT_HART: frozenset[str] = frozenset({
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
})


@dataclass(frozen=True)
class Komponente:
    """EINE Zeile der Bündel-Stückliste (LIZENZ_MANIFEST.json, §5.1)."""
    name: str
    lizenz: str                 # SPDX-Id bzw. "Public-Domain"/"proprietaer"
    klasse: str                 # ∈ KLASSEN
    version: str = ""
    isolation: str | None = None   # ISOLATION_LGPL bei nachgewiesener I-5-Kapselung
    gate: str | None = None        # offenes David-Gate (z. B. "G-M1-LIZENZ") ⇒ Ampel gate
    quelle: str = ""               # Beleg (Doc-Ref/Verifikationsdatum) — Warranty-of-Title-Spur


def ampel_fuer(k: Komponente, edition: str) -> str:
    """Ampel je Komponente und Edition (docs/66 §5.2). Fail-closed (I-4): alles
    nicht ausdrücklich Erlaubte ist rot. v1 bewertet alle Editionen identisch-
    konservativ; die E-SERVER-Lockerung für kommerziell lizenzierte Modelle
    (Betrieb ≠ Distribution, docs/56 §3) kommt erst mit C1-7 — bis dahin gilt
    auch dort das Gate."""
    if edition not in EDITIONEN:
        raise ValueError(f"unbekannte Edition: {edition!r}")
    if k.gate:
        return AMPEL_GATE
    if k.lizenz in PERMISSIV:
        return AMPEL_GRUEN
    if k.lizenz in MPL:
        return AMPEL_AUFLAGE
    if k.lizenz in LGPL:
        return AMPEL_AUFLAGE if k.isolation == ISOLATION_LGPL else AMPEL_ROT
    if k.lizenz in COPYLEFT_HART:
        return AMPEL_ROT
    return AMPEL_ROT


# Kuratierter Startbestand (nur VERIFIZIERTE Einträge; C1-2 vervollständigt maschinell).
BEKANNTE_KOMPONENTEN: dict[str, Komponente] = {
    "fints": Komponente(
        name="fints", lizenz="LGPL-3.0-or-later", klasse="pip",
        isolation=ISOLATION_LGPL,
        quelle="docs/64 §10 (M-6, verifiziert 03.07.2026): unmodifiziert + hinter FinTSQuelle austauschbar + Lizenztext mitführen",
    ),
    "ERiC": Komponente(
        name="ERiC", lizenz="proprietaer", klasse="nachgeladen", gate="G-M1-LIZENZ",
        quelle="docs/65 (M-1): ELSTER-Nutzungsbedingungen; Download-on-first-use, NIE im Bündel (I-9)",
    ),
    "FLUX.1": Komponente(
        name="FLUX.1", lizenz="proprietaer", klasse="nachgeladen", gate="G-FLUX-LIZENZ",
        quelle="docs/58 §3.G (VO-7): Endkunden-Gerät vermutlich Enterprise-Lizenz — VOR Ankauf klären",
    ),
    "sqlite3": Komponente(
        name="sqlite3", lizenz="Public-Domain", klasse="stdlib",
        quelle="stdlib; SEE-Verschlüsselung = eigener Ankauf-Entscheid (docs/66 §12.4)",
    ),
    "fastapi": Komponente(name="fastapi", lizenz="MIT", klasse="pip", quelle="PyPI-Metadaten (ops/requirements-lock.txt)"),
    "uvicorn": Komponente(name="uvicorn", lizenz="BSD-3-Clause", klasse="pip", quelle="PyPI-Metadaten"),
    "httpx": Komponente(name="httpx", lizenz="BSD-3-Clause", klasse="pip", quelle="PyPI-Metadaten"),
}


def erzeuge_lizenz_manifest(bundle_id: str, edition: str, komponenten: list[Komponente]) -> dict[str, Any]:
    """LIZENZ_MANIFEST.json-Erzeugung inkl. maschineller Erhebung — Bau C1-2."""
    raise NichtGebaut("C1-2 (docs/66 §10): Lizenz-Manifest-Generator")
