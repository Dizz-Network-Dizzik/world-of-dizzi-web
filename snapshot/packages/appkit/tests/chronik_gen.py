"""Test-Helfer / Golden-Generator (Vertrag §11 Runde 1): baut ein vollständiges
chronik-Verzeichnis (Segmente + Siegel) aus einer Ereignis-Liste.

Nimmt den Chronist-Tick (Runde 2) vorweg, nutzt aber die ``chronik.py``-Produktionsbausteine
(``schreibe`` → Outbox → Segment-Zeilen + ``baue_siegel``), damit ``chronik_pruef`` gegen echte,
signierte Fixtures läuft. Kein Tick/Lock/Recovery — das ist Runde-2-Verantwortung.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from appkit import chronik as C


def baue_chronik(cdir: Path, ereignisse: list[dict], *, app: str = "money",
                 epoche_groesse: int = 4, quorum: int = 1) -> dict:
    """Erzeugt ``cdir`` mit Schlüsseln, ``segmente/`` und ``siegel/``.

    ``ereignisse`` = ``[{"art","nutzlast"(dict),"subjekt"?,"entscheid_id"?}]`` — werden über
    ``chronik.schreibe`` in eine In-Memory-Outbox geschrieben, dann (nach der Genesis-Zeile)
    zu signierten Segment-Zeilen + Epochen-Siegeln verkettet.
    """
    sk = C.konfiguriere(cdir)
    conn = sqlite3.connect(":memory:")
    conn.executescript(C.AUSGANG_SCHEMA)
    for ev in ereignisse:
        C.schreibe(conn, art=ev["art"], nutzlast=ev["nutzlast"],
                   subjekt=ev.get("subjekt", "system"), entscheid_id=ev.get("entscheid_id", ""))
    outbox = conn.execute(
        "SELECT i, art, nutzlast, nutzlast_hash, entscheid_id, subjekt, created_at "
        "FROM chronik_ausgang ORDER BY i").fetchall()

    # Zeilen-Rohlinge (noch ohne n/prev/sig): Genesis zuerst, dann die Outbox-Ereignisse.
    gts = C.now_iso()
    gnutz = {"version": C.FORMAT_VERSION, "angelegt": gts, "stamm_kid": sk.stamm["kid"]}
    roh: list[dict] = [{
        "app": "chronik", "i": 0, "ts": gts, "art": "chronik.genesis", "subjekt": "system",
        "entscheid": "", "nutzlast_hash": C._sha256_hex(C.kanon(gnutz)), "nutzlast": gnutz}]
    for i, art, last, lasthash, entscheid, subjekt, created in outbox:
        roh.append({
            "app": app, "i": i, "ts": created, "art": art, "subjekt": subjekt,
            "entscheid": entscheid, "nutzlast_hash": lasthash,
            "nutzlast": (json.loads(last) if last else "")})

    (cdir / "segmente").mkdir(parents=True, exist_ok=True)
    (cdir / "siegel").mkdir(parents=True, exist_ok=True)
    prev_h, prev_siegel, n, epoche, idx = C.NULL_HASH, C.GENESIS_PREV_SIEGEL, 0, 0, 0

    while idx < len(roh):
        epoche += 1
        gruppe = roh[idx: idx + epoche_groesse]
        idx += epoche_groesse
        seg_lines, h_liste, von_n = [], [], n + 1
        for z in gruppe:
            n += 1
            zeile = dict(z)
            zeile["n"], zeile["prev"] = n, "sha256:" + prev_h.hex()
            h_n = C.kette_hash(prev_h, zeile)
            zeile["sig"] = C.signiere(h_n, sk.chronist)
            prev_h = h_n
            h_liste.append(h_n)
            seg_lines.append(C.kanon(zeile))
        (cdir / "segmente" / f"E{epoche:08d}.dzc").write_text("\n".join(seg_lines) + "\n", "utf-8")
        siegel = C.baue_siegel(
            epoche=epoche, wurzel=C.merkle_wurzel(h_liste), prev_siegel=prev_siegel,
            ereignisse=len(h_liste), von_n=von_n, bis_n=n, quorum=quorum, chronist_jwk=sk.chronist)
        (cdir / "siegel" / f"S{epoche:08d}.json").write_text(C.kanon(siegel), "utf-8")
        prev_siegel = C.siegel_hash(siegel)

    return {"zeilen": n, "epochen": epoche}


def buchung(bid: str, betrag_minor: str, *, subjekt: str = "u:" + "a" * 36,
            datum: str = "2026-07-01") -> dict:
    """Bequemer money.buchung-Ereignisbauer für Tests (2 Postings, Σ=0)."""
    return {"art": "money.buchung", "subjekt": subjekt, "nutzlast": {
        "buchung_id": bid, "datum": datum, "quelle": "manuell",
        "postings": [{"konto_id": "1200", "betrag_minor": betrag_minor},
                     {"konto_id": "8400", "betrag_minor": "-" + betrag_minor.lstrip("-")}]}}
