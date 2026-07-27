"""Smart Contacts — Kontakt-Unifikation über Kanäle (docs/35 §5.3).

Ein kanonischer Kontakt bündelt mehrere Kanal-Identitäten (E-Mail-Adresse /
Handle / Telefon). Diese Datei hält die REINE, deterministische Matching-Logik
(kein LLM, hoechst-App ⇒ lokal): sie liefert nur **Merge-VORSCHLÄGE** — das
tatsächliche Zusammenführen/Trennen ist eine Nutzer-Aktion (main.py-Endpoints),
nie automatisch (eine Falsch-Verschmelzung wäre teuer rückgängig zu machen).

Architektur-Hinweis: Kontakt-Unifikation ist laut docs/35 §5.3 ein eigener
Baustein und **Kit-Kandidat** (Communication ist der Pionier). Darum lebt die
Kernlogik hier modular und app-unabhängig — sie lässt sich später in ein
geteiltes Identitäts-Kit heben, ohne die Domäne umzubauen.
"""

from __future__ import annotations

import re
from typing import Any

_WS = re.compile(r"\s+")


def normalisiere_name(name: str) -> str:
    """Anzeigename → Vergleichsform (klein, getrimmt, Mehrfach-Whitespace zu 1)."""
    return _WS.sub(" ", (name or "").strip().lower())


def local_part(adresse: str) -> str:
    """Identitäts-Stamm einer Kanal-Adresse: bei E-Mail der Teil vor ``@``, bei
    Handles ohne führendes ``@``/``+``. ``Max.Muster@gmx.de`` → ``max.muster``,
    ``@maxmuster`` → ``maxmuster``. Leer ⇒ leer (wird nicht gematcht)."""
    a = (adresse or "").strip().lower()
    if "@" in a and not a.startswith("@"):
        a = a.split("@", 1)[0]
    return a.lstrip("@+").strip()


def _paar_key(a: str, b: str) -> tuple[str, str]:
    """Ungeordnetes Paar als stabiler, sortierter Schlüssel (Dedupe a<b)."""
    return (a, b) if a <= b else (b, a)


def finde_merge_vorschlaege(kontakte: list[dict[str, Any]],
                            limit: int = 50) -> list[dict[str, Any]]:
    """Heuristische Merge-Vorschläge über eine Liste Kontakte.

    Erwartet je Kontakt ``{"id", "name", "aliasse": [{"kanal_typ", "adresse"}]}``.
    Zwei deterministische Regeln (lokal, ohne LLM):

    - **Gleicher Name** (normalisiert, nicht leer) ⇒ starker Vorschlag (Score 3).
    - **Gleicher Identitäts-Stamm** (``local_part``) über Kanäle hinweg ⇒
      Vorschlag (Score 2, wenn verschiedene Kanal-Typen; sonst Score 1, z. B.
      ``nutzer@example.com`` ↔ ``max@gmx``).

    Liefert ``[{a, b, a_name, b_name, grund, score}]``, dedupliziert je Paar
    (höchster Score + kombinierter Grund), höchster Score zuerst, dann nach id.
    Personal-Postfach-Größe ⇒ Gruppierung statt naivem O(n²)."""
    # Vorindizieren: Name-Gruppen + local-part → [(kontakt_id, kanal_typ)]
    nach_name: dict[str, list[str]] = {}
    nach_stamm: dict[str, list[tuple[str, str]]] = {}
    namen: dict[str, str] = {}
    for k in kontakte:
        kid = k["id"]
        namen[kid] = k.get("name", "") or ""
        nn = normalisiere_name(k.get("name", ""))
        if nn:
            nach_name.setdefault(nn, []).append(kid)
        for al in k.get("aliasse", []):
            stamm = local_part(al.get("adresse", ""))
            if stamm:
                nach_stamm.setdefault(stamm, []).append((kid, al.get("kanal_typ", "")))

    treffer: dict[tuple[str, str], dict[str, Any]] = {}

    def _merken(a: str, b: str, grund: str, score: int) -> None:
        if a == b:
            return
        key = _paar_key(a, b)
        vor = treffer.get(key)
        if vor is None or score > vor["score"]:
            treffer[key] = {"a": key[0], "b": key[1], "grund": grund, "score": score}
        elif grund not in vor["grund"]:
            vor["grund"] += " · " + grund

    # Regel 1 — gleicher Name
    for ids in nach_name.values():
        uniq = sorted(set(ids))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                _merken(uniq[i], uniq[j], "gleicher Name", 3)

    # Regel 2 — gleicher Identitäts-Stamm (bevorzugt über Kanäle hinweg)
    for eintraege in nach_stamm.values():
        # nach Kontakt eindeutig machen (ein Kontakt mit zwei Aliassen gleichen
        # Stamms ist kein Selbst-Vorschlag)
        prok: dict[str, set[str]] = {}
        for kid, kt in eintraege:
            prok.setdefault(kid, set()).add(kt)
        ids = sorted(prok)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                cross = bool(prok[ids[i]] ^ prok[ids[j]]) or \
                    prok[ids[i]] != prok[ids[j]]
                _merken(ids[i], ids[j],
                        "gleicher Handle/Stamm" + (" über Kanäle" if cross else ""),
                        2 if cross else 1)

    out = list(treffer.values())
    for t in out:
        t["a_name"] = namen.get(t["a"], "")
        t["b_name"] = namen.get(t["b"], "")
    out.sort(key=lambda t: (-t["score"], t["a"], t["b"]))
    return out[:max(0, limit)]
