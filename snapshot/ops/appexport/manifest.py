"""Manifest-Schemata + Validierung (docs/66 §4) — pure Funktionen, schon real.

Zwei Manifeste: ``apps/<id>/export_manifest.json`` (App-Deklaration, App-Besitz)
und ``BUNDLE_MANIFEST.json`` (Bündel-Identität, vom Builder erzeugt). Validierung
liefert eine FEHLER-LISTE (leer = gültig) statt zu werfen — der Aufrufer
entscheidet über Abbruch und kann alle Mängel auf einmal berichten.
"""

from __future__ import annotations

import re
from typing import Any

from .editionen import EDITIONEN, KERN_APPS, PAKET_TYPEN, SENSITIVITAETEN

EXPORT_SCHEMA_VERSION = 1
BUNDLE_SCHEMA_VERSION = 1

EXPORT_PFLICHTFELDER: tuple[str, ...] = (
    "schema", "app_id", "paket", "port", "appkit_direkt", "pip_eigen",
    "statisch", "editionen", "sensitivitaet", "nachgeladen",
)
BUNDLE_PFLICHTFELDER: tuple[str, ...] = (
    "schema", "bundle_id", "bundle_version", "erzeugt_am", "quelle_commit",
    "edition", "paket_typ", "apps", "appkit_module", "lizenz_manifest_sha256",
    "daten_anker_default",
)

# bundle_version = <JJJJ-MM-TT>+<sha8..40> (docs/66 §8: lexikographisch vergleichbar, I-1)
BUNDLE_VERSION_MUSTER = re.compile(r"^\d{4}-\d{2}-\d{2}\+[0-9a-f]{7,40}$")


def _fehlende_felder(d: dict[str, Any], pflicht: tuple[str, ...]) -> list[str]:
    return [f"Pflichtfeld fehlt: {feld}" for feld in pflicht if feld not in d]


def _pruefe_sortierte_namensliste(wert: Any, feld: str) -> list[str]:
    """Sortiert + dupfrei + nur nicht-leere Strings — Reproduzierbarkeits-Regel (§3.2)."""
    fehler: list[str] = []
    if not isinstance(wert, list) or not all(isinstance(m, str) and m for m in wert):
        return [f"{feld} muss eine Liste nicht-leerer Strings sein"]
    if wert != sorted(wert):
        fehler.append(f"{feld} muss sortiert sein (Reproduzierbarkeit)")
    if len(set(wert)) != len(wert):
        fehler.append(f"{feld} enthält Duplikate")
    return fehler


def validiere_export_manifest(d: dict[str, Any]) -> list[str]:
    """Vertrags-Validierung der App-Deklaration (docs/66 §4.1). Leere Liste = gültig."""
    fehler = _fehlende_felder(d, EXPORT_PFLICHTFELDER)
    if fehler:
        return fehler
    if d["schema"] != EXPORT_SCHEMA_VERSION:
        fehler.append(f"schema muss {EXPORT_SCHEMA_VERSION} sein, ist {d['schema']!r}")
    for feld in ("app_id", "paket"):
        if not isinstance(d[feld], str) or not d[feld]:
            fehler.append(f"{feld} muss ein nicht-leerer String sein")
    if not isinstance(d["port"], int):
        fehler.append("port muss int sein")
    fehler += _pruefe_sortierte_namensliste(d["appkit_direkt"], "appkit_direkt")
    if not isinstance(d["pip_eigen"], list):
        fehler.append("pip_eigen muss eine Liste sein")
    if not isinstance(d["statisch"], list):
        fehler.append("statisch muss eine Liste sein")
    if not isinstance(d["editionen"], list) or not set(d["editionen"]) <= set(EDITIONEN):
        fehler.append(f"editionen muss Teilmenge von {EDITIONEN} sein")
    if d["sensitivitaet"] not in SENSITIVITAETEN:
        fehler.append(f"sensitivitaet muss in {SENSITIVITAETEN} liegen")
    if not isinstance(d["nachgeladen"], list):
        fehler.append("nachgeladen muss eine Liste sein")
    else:
        for i, eintrag in enumerate(d["nachgeladen"]):
            if not isinstance(eintrag, dict) or not eintrag.get("name") or not eintrag.get("zweck"):
                fehler.append(f"nachgeladen[{i}]: name + zweck sind Pflicht (gate darf null sein)")
    return fehler


def validiere_bundle_manifest(d: dict[str, Any]) -> list[str]:
    """Vertrags-Validierung der Bündel-Identität (docs/66 §4.2). Leere Liste = gültig."""
    fehler = _fehlende_felder(d, BUNDLE_PFLICHTFELDER)
    if fehler:
        return fehler
    if d["schema"] != BUNDLE_SCHEMA_VERSION:
        fehler.append(f"schema muss {BUNDLE_SCHEMA_VERSION} sein, ist {d['schema']!r}")
    if not isinstance(d["bundle_version"], str) or not BUNDLE_VERSION_MUSTER.match(d["bundle_version"]):
        fehler.append("bundle_version muss dem Muster JJJJ-MM-TT+<sha7..40> folgen (I-1/§8)")
    if d["edition"] not in EDITIONEN:
        fehler.append(f"edition muss in {EDITIONEN} liegen")
    if d["paket_typ"] not in PAKET_TYPEN:
        fehler.append(f"paket_typ muss in {PAKET_TYPEN} liegen")
    if not isinstance(d["apps"], list) or not all(isinstance(a, str) and a for a in d["apps"]):
        fehler.append("apps muss eine Liste nicht-leerer Strings sein")
    else:
        for kern in KERN_APPS:
            if kern not in d["apps"]:
                fehler.append(f"'{kern}' fehlt in apps — Core ist IMMER dabei (docs/56 §2.1)")
    fehler += _pruefe_sortierte_namensliste(d["appkit_module"], "appkit_module")
    return fehler
