"""Charta Cedar-Schatten-Orakel (V-BIZZI-2, §B7) — DEV-ONLY, NIE unter packages/.

Übersetzt die Eigenbau-Charta (Gewährungen → ``permit``, ``verweigere``-Schranken
→ ``forbid``) und vergleicht das **Erlaubnis-Urteil** (gewährt/verweigert) gegen
den eigenen Evaluator über ≥1000 seeded Anträge. Obliegenheiten sind in Cedar
nicht abbildbar ⇒ Vergleichs-Scope = NUR das Erlaubnis-Urteil (ehrliche
Arbeitsteilung; die Obliegenheiten-Gesetze sichern die Property-Tests P5/P6).

Cedar bleibt Test-Orakel, NIE Laufzeit (CH-18): appkit importiert dieses Modul
nie; es läuft nur im Dev-Differential (``cedar-policy`` als dev-extra, sonst CLI).
Fehlt Cedar, überspringt der zugehörige pytest-Marker ``@cedar``.
"""

from __future__ import annotations

import random

# Der Import von appkit.charta erfolgt beim Aufruf (dev-Tool, PYTHONPATH=packages).


def nach_cedar(charta: dict) -> str:
    """Übersetzt eine Charta-Version in Cedar-Policy-Text (nur Erlaubnis-Urteil)."""
    zeilen: list[str] = []
    for art in charta.get("artikel", []):
        aktion = art["aktion"]
        for i, konjunktion in enumerate(art.get("gewaehre", [])):
            bed = _bedingungen(konjunktion)
            wenn = f" when {{ {' && '.join(bed)} }}" if bed else ""
            zeilen.append(f'permit(principal, action == Action::"{aktion}", resource){wenn};')
        for s in art.get("schranken", []):
            if "verweigere" in (s.get("dann") or []):
                bed = _bedingungen(s.get("wenn", []))
                wenn = f" when {{ {' && '.join(bed)} }}" if bed else ""
                zeilen.append(f'forbid(principal, action == Action::"{aktion}", resource){wenn};')
    return "\n".join(zeilen)


def _bedingungen(praedikate: list) -> list[str]:
    """Prädikat → Cedar-when-Ausdruck (nur die urteils-relevanten; Obliegenheiten
    haben kein Cedar-Pendant und werden bewusst weggelassen, §B7)."""
    out = []
    for p in praedikate:
        name, wert = p.get("p"), p.get("w")
        if name == "rolle":
            out.append(f'context.rollen.contains("{wert}")')
        elif name == "assurance_min":
            out.append(f'context.assurance_rang >= {("lokal", "verifiziert", "hochsicher").index(wert)}')
        elif name == "art":
            out.append(f'context.art == "{wert}"')
        elif name == "edition":
            out.append(f'context.edition == "{wert}"')
        elif name == "betrag_ab":
            out.append(f'context.betrag >= {int(wert)}')
        elif name == "betrag_bis":
            out.append(f'context.betrag <= {int(wert)}')
        elif name == "bereich_fremd":
            out.append("context.bereich_fremd == true")
        elif name == "erfasser_ist_subjekt":
            out.append("context.erfasser_ist_subjekt == true")
        elif name == "eigentuemer":
            out.append("context.eigentuemer == true")
        elif name == "immer":
            out.append("true")
        # frisch/zeit/sensitivitaet: Kontext-abhängig — im Differential über context gespiegelt
    return out or ["true"]


def antrag_kandidaten(seed: int = 0xC3DA2, n: int = 1000):
    """≥n seeded Anträge über endliche Domänen (deterministisch)."""
    rng = random.Random(seed)
    rollen = ["buchhaltung", "fibu_leitung", "leser"]
    for _ in range(n):
        yield {
            "aktion": rng.choice(["fibu.buchen", "fibu.festschreiben"]),
            "zeit": "2026-07-13T09:00:00+00:00",
            "subjekt": {"art": "mensch", "id": "u:" + rng.choice("abc") * 10,
                        "assurance": rng.choice(["lokal", "verifiziert", "hochsicher"]),
                        "rollen": rng.sample(rollen, rng.randint(0, len(rollen))),
                        "bereiche": ["b:eigen"], "edition": "bizzi", "frisch_s": 0},
            "agent": None,
            "objekt": {"betrag_minor": rng.choice(["0", "500000", "1500000"]),
                       "bereich_id": "b:eigen", "erfasser_id": "u:andere"},
        }


def differential(charta: dict, n: int = 1000, seed: int = 0xC3DA2) -> list[dict]:
    """Vergleicht Eigenbau-Urteil vs. Cedar über die seeded Anträge. Braucht Cedar
    (``import cedarpy``); ohne Paket ⇒ ImportError (der pytest-Marker skippt dann).
    Rückgabe: Liste der Abweichungen (leer = 0 Differenzen)."""
    import cedarpy  # noqa: F401  — dev-only, absichtlich lazy (CH-18: nie zur Laufzeit)

    from appkit import charta as CH

    policy = nach_cedar(charta)
    abweichungen: list[dict] = []
    for antrag in antrag_kandidaten(seed, n):
        eigen = CH.pruefe(antrag, charta).gewaehrt
        cedar = _cedar_erlaubt(cedarpy, policy, antrag)
        if eigen != cedar:
            abweichungen.append({"antrag": antrag, "eigen": eigen, "cedar": cedar})
    return abweichungen


def _cedar_erlaubt(cedarpy, policy: str, antrag: dict) -> bool:
    """Cedar-Auswertung eines Antrags (Kontext gespiegelt). Implementierung folgt
    der installierten cedarpy-API; hier bewusst schmal gehalten (dev-Orakel)."""
    s = antrag["subjekt"]
    o = antrag["objekt"]
    context = {
        "rollen": s["rollen"],
        "assurance_rang": ("lokal", "verifiziert", "hochsicher").index(s["assurance"]),
        "art": s["art"], "edition": s["edition"],
        "betrag": int(o.get("betrag_minor", "0")),
        "bereich_fremd": o.get("bereich_id") not in s.get("bereiche", []),
        "erfasser_ist_subjekt": o.get("erfasser_id") == s["id"],
        "eigentuemer": o.get("eigentuemer_id") == s["id"],
    }
    antwort = cedarpy.is_authorized(
        {"principal": 'User::"u"', "action": f'Action::"{antrag["aktion"]}"',
         "resource": 'Resource::"r"', "context": context},
        policy, "")
    return getattr(antwort, "decision", None) == "Allow"


if __name__ == "__main__":
    import json
    import sys

    beispiel = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {"charta_version": "t", "artikel": []}
    print(nach_cedar(beispiel))
