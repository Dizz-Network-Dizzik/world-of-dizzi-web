"""DzCharta — Prüfkern-Anschluss (V-BIZZI-2, B2 · Runde 3, §B6).

Zwei Einstiege für ``bizzi-pruef`` (delegiert von ``chronik_pruef``), derselbe
Evaluator wie in-process (C-13-analog):

- **policy-replay**: je verbrauchtem Entscheid — Signatur (Charta-Schlüsselbrief) ·
  ``antrag_hash == sha256(kanon(antrag))`` · Neu-Evaluation gegen
  ``charta_versionen[policy_version]`` ⇒ identisches Ergebnis + Obliegenheiten ·
  Ketten-Gegenprobe ``entscheid_hash``.
- **erreichbarkeit**: CH-14-Berichte (CFO / tote Artikel) über die aktive Version
  + die Belegschaft aus dem Verzeichnis-KEIM.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import charta as CH
from . import charta_erreichbar as E
from . import charta_speicher as S
from . import chronik as C

EXIT_GRUEN, EXIT_BRUCH, EXIT_DIVERGENZ, EXIT_TOTE = 0, 2, 3, 4


def aktive_charta(conn) -> dict | None:
    row = conn.execute(
        "SELECT version, artikel FROM charta_versionen WHERE status='aktiv'").fetchone()
    return None if row is None else {"charta_version": row["version"],
                                     "artikel": json.loads(row["artikel"])}


def policy_replay(conn, *, cdir: Path | None = None):
    """§B6 policy-replay. Exit 0 grün · 2 Bruch (Signatur/Material) · 3 Divergenz
    (Entscheid-ID + Grund)."""
    try:
        pub = S.lade_charta_pubkey(cdir)
    except Exception as e:                              # kein/kaputtes Schlüsselmaterial
        return EXIT_BRUCH, [f"BRUCH: Charta-Schlüsselmaterial: {e}"]

    versionen = {r["version"]: json.loads(r["artikel"])
                 for r in conn.execute("SELECT version, artikel FROM charta_versionen")}
    rows = conn.execute("SELECT * FROM charta_entscheide WHERE status='verbraucht'").fetchall()

    bruch: list[str] = []          # Integrität (Signatur/Hash/Material) — Exit 2
    divergenz: list[str] = []      # Neu-Evaluation weicht ab — Exit 3
    geprueft = 0
    for row in rows:
        eid = row["id"]
        if S._sha256_hex(row["antrag"]) != row["antrag_hash"]:
            bruch.append(f"BRUCH {eid}: antrag_hash deckt den archivierten Antrag nicht")
            continue
        basis = hashlib.sha256(C.kanon(S._kern_ausstellung(row)).encode("utf-8")).digest()
        if not S._verify(row["sig"], basis, pub):
            bruch.append(f"BRUCH {eid}: Signatur ungültig")
            continue
        if row["entscheid_hash"] and row["entscheid_hash"] != S._entscheid_hash_final(row):
            bruch.append(f"BRUCH {eid}: entscheid_hash deckt den Entscheid nicht")
            continue
        artikel = versionen.get(row["policy_version"])
        if artikel is None:
            bruch.append(f"BRUCH {eid}: policy_version {row['policy_version']} fehlt")
            continue
        urteil = CH.pruefe(json.loads(row["antrag"]),
                           {"charta_version": row["policy_version"], "artikel": artikel})
        soll = "gewaehrt" if urteil.gewaehrt else "verweigert"
        if soll != row["ergebnis"]:
            divergenz.append(f"DIVERGENZ {eid}: Ergebnis {soll} != archiviert {row['ergebnis']}")
            continue
        if sorted(urteil.obliegenheiten) != json.loads(row["obliegenheiten"]):
            divergenz.append(f"DIVERGENZ {eid}: Obliegenheiten weichen ab")
            continue
        geprueft += 1

    if bruch:
        return EXIT_BRUCH, bruch + divergenz
    if divergenz:
        return EXIT_DIVERGENZ, divergenz
    return EXIT_GRUEN, [f"grün — {geprueft} Entscheid(e) replayed "
                        "(Signatur · antrag_hash · Neu-Evaluation · entscheid_hash)"]


def erreichbarkeit(conn):
    """CH-14 über die aktive Version + Verzeichnis-KEIM-Belegschaft. Exit 0 ·
    4 (tote Artikel vorhanden — Hinweis, kein Fehler)."""
    charta = aktive_charta(conn)
    if charta is None:
        return EXIT_GRUEN, ["keine aktive Charta-Version"]
    try:
        from . import charta_verzeichnis as V
        belegschaft = V.belegschaft(conn)
    except Exception:
        belegschaft = []
    bericht = E.bericht(charta, belegschaft)
    zeilen = [f"{aktion}: {len(ids)} berechtigt" + (f" ({', '.join(ids)})" if ids else "")
              for aktion, ids in bericht["cfo"].items()]
    if bericht["tote_artikel"]:
        zeilen.append("TOTE ARTIKEL (unter aktueller Belegschaft unerfüllbar): "
                      + ", ".join(bericht["tote_artikel"]))
        return EXIT_TOTE, zeilen
    return EXIT_GRUEN, zeilen
