"""DzCharta — Erreichbarkeits-Enumerator (V-BIZZI-2, B2 · Runde 3, CH-14).

Statische Analyse der aktiven Charta über **endliche Domänen** (Rollen/Bereiche
der Belegschaft) + **Betrags-Intervalle aus den Artikel-Schwellen selbst** —
vier Berichte:

- **CFO** „wer kann Aktion A?" (``wer_kann``)
- **Betriebsrat** „niemand außer …"-Beweis (``niemand_ausser``)
- **SoD-Matrix** Paar-Erreichbarkeit durch dieselbe Identität (``sod_matrix``)
- **Tote Artikel** — unter der aktuellen Belegschaft unerfüllbar (Konfigurations-
  Ehrlichkeit, D2/§B9) — inkl. vier_augen ohne zweite berechtigte Identität.

Reine Analyse über ``charta.pruefe`` (best-case-Erreichbarkeit: existiert EIN
Antrag über die endlichen Wahlpunkte, der gewährt?). Keine DB, kein Cedar.
"""

from __future__ import annotations

from . import charta as CH

# §B9 · Ehrlichkeits-Kasten (Gesetz 2 — wörtlich, gehört in Doku + Abnahme).
EHRLICHKEIT = """\
- Ausdrucks-Grenzen sind gewollt: keine Beziehungs-Graphen, keine Arithmetik,
  keine Wildcards, keine Kaskaden-Rollen — die Kleinheit IST die Prüfbarkeit;
  Erweiterung nur per neuem Gate.
- Rubber-Stamping bleibt menschlich: 4 Augen ≠ 4 wache Augen — Rotation/
  Diff-Anzeige/Stichproben sind Milderung, keine Lösung.
- Replay-Beweiskraft-Grenze: Replay beweist „Entscheid folgt aus (Antrag,
  Version)"; die Wahrheit der Subjekt-Attribute stützt sich auf Verzeichnis-
  Tabellen + hash_only-Offenlegung — Klartext-Historie der Rollen steht NICHT
  in der Kette (Krypto-Schredder-Grenze, bewusst).
- Notweg: der Stammschlüssel-Besitzer kann per Wiederherstellungs-Artikel jede
  Charta-Version zurückrollen — sichtbar als Ereignis, nie unsichtbar; in
  quorum=1-Editionen ist das der Konto-Inhaber (Schutzhöhen-Ehrlichkeit).
- Cedar ist Test-Orakel, keine Zweitmeinung zur Laufzeit.
- Solo-/KEIM-Realität: mit <2 berechtigten Identitäten sind vier_augen-Artikel
  tote Artikel — sichtbar im Enumerator, ehrlich gemeldet, nie still übersprungen.
"""

_ZEIT_KANDIDATEN = ("2026-07-13T09:00:00+00:00", "2026-07-13T23:30:00+00:00")


def _artikel_fuer(charta: dict, aktion: str) -> dict:
    for art in (charta.get("artikel") or []):
        if isinstance(art, dict) and art.get("aktion") == aktion:
            return art
    return {}


def _praedikate(article: dict):
    for zeile in article.get("gewaehre", []) or []:
        if isinstance(zeile, list):
            yield from (p for p in zeile if isinstance(p, dict))
    for s in article.get("schranken", []) or []:
        if isinstance(s, dict):
            yield from (p for p in s.get("wenn", []) or [] if isinstance(p, dict))


def _betrag_kandidaten(article: dict) -> list[str]:
    schwellen = sorted({int(p["w"]) for p in _praedikate(article)
                        if p.get("p") in ("betrag_ab", "betrag_bis", "einzel_max_ab")
                        and str(p.get("w", "")).isdigit()})
    werte = {"0"}
    for s in schwellen:                                # Intervall-Ränder (Splitting-Erreichbarkeit)
        werte.update({str(max(0, s - 1)), str(s), str(s + 1)})
    return sorted(werte, key=int)


def _kandidaten_objekte(article: dict, subjekt: dict) -> list[dict]:
    """Grant-günstige Objekte über die endlichen Wahlpunkte des Artikels: eigener
    Bereich (kein bereich_fremd), Nicht-Selbst-Erfasser (keine SoD-Sperre), eigener
    Eigentümer, hoechste Sensitivität, Betrags-Intervallränder."""
    bereich = next((b for b in (subjekt.get("bereiche") or []) if b), "b:__eigen__")
    return [{"betrag_minor": b, "stapel_summe_minor": b, "einzel_max_minor": b,
             "bereich_id": bereich, "eigentuemer_id": subjekt.get("id", ""),
             "erfasser_id": "u:__nicht_ersteller__", "sensitivitaet": "hoechst"}
            for b in _betrag_kandidaten(article)]


def kann(charta: dict, subjekt: dict, aktion: str, *, vier_augen_moeglich: bool = True) -> bool:
    """Best-case-Erreichbarkeit: existiert EIN Antrag (über die endlichen Objekt-/
    Zeit-Wahlpunkte), der ``aktion`` für ``subjekt`` gewährt?"""
    article = _artikel_fuer(charta, aktion)
    for zeit in _ZEIT_KANDIDATEN:
        for objekt in _kandidaten_objekte(article, subjekt):
            antrag = {"aktion": aktion, "zeit": zeit, "subjekt": dict(subjekt),
                      "agent": None, "objekt": objekt}
            if CH.pruefe(antrag, charta, vier_augen_moeglich=vier_augen_moeglich).gewaehrt:
                return True
    return False


def _aktionen(charta: dict) -> list[str]:
    return [a["aktion"] for a in (charta.get("artikel") or [])
            if isinstance(a, dict) and isinstance(a.get("aktion"), str)]


def wer_kann(charta: dict, belegschaft: list[dict], aktion: str) -> list[str]:
    """CFO-Bericht: IDs aller Identitäten, die ``aktion`` erreichen können."""
    return sorted(s.get("id", "") for s in belegschaft if kann(charta, s, aktion))


def niemand_ausser(charta: dict, belegschaft: list[dict], aktion: str) -> dict:
    """Betriebsrats-Beweis: {kann:[…], kann_nicht:[…]} für ``aktion``."""
    ja = set(wer_kann(charta, belegschaft, aktion))
    return {"kann": sorted(ja),
            "kann_nicht": sorted(s.get("id", "") for s in belegschaft if s.get("id") not in ja)}


def sod_matrix(charta: dict, belegschaft: list[dict], paare) -> list[dict]:
    """SoD-Matrix: für jedes Aktions-Paar die Identitäten, die BEIDES erreichen
    (Trennungs-Verletzungs-Kandidaten)."""
    out = []
    for a1, a2 in paare:
        beide = sorted(s.get("id", "") for s in belegschaft
                       if kann(charta, s, a1) and kann(charta, s, a2))
        if beide:
            out.append({"paar": [a1, a2], "beide": beide})
    return out


def tote_artikel(charta: dict, belegschaft: list[dict]) -> list[str]:
    """Aktionen, die unter der aktuellen Belegschaft NIEMAND erfüllen kann —
    inkl. vier_augen-Artikel mit <2 berechtigten Identitäten (D2-Ehrlichkeit)."""
    tot = []
    for aktion in _aktionen(charta):
        basis = wer_kann(charta, belegschaft, aktion)
        vier_augen_moeglich = len(basis) >= 2
        real = [s for s in belegschaft
                if kann(charta, s, aktion, vier_augen_moeglich=vier_augen_moeglich)]
        if not real:
            tot.append(aktion)
    return tot


def bericht(charta: dict, belegschaft: list[dict], *, sod_paare=()) -> dict:
    """Alle vier CH-14-Berichte in einem Objekt (menschenlesbar + JSON-fähig)."""
    return {
        "cfo": {a: wer_kann(charta, belegschaft, a) for a in _aktionen(charta)},
        "tote_artikel": tote_artikel(charta, belegschaft),
        "sod": sod_matrix(charta, belegschaft, sod_paare),
    }
