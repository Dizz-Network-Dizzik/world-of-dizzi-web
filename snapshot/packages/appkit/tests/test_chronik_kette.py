"""B1 §7 — Kette + Merkle (Property, seeded ≥200) + Siegel-Kette + pruefe/beweis (C-4/C-7/C-8)."""
import hashlib
import json
import random

import pytest

from appkit import chronik as C
from appkit import chronik_pruef as P
import chronik_gen as G


@pytest.fixture(autouse=True)
def _reset():
    yield
    C.reset_kontext()


# ── Merkle-Property: 220 seeded Fälle, Größen 1…17, Beweis + Manipulation ─────

def test_merkle_property_beweise_und_manipulation():
    r = random.Random(0xD1221)
    faelle = 0
    for _ in range(220):
        n = r.randint(1, 17)
        hs = [hashlib.sha256(bytes([r.randint(0, 255) for _ in range(8)])).digest() for _ in range(n)]
        wurzel = C.merkle_wurzel(hs)
        for idx in range(n):
            beweis = C.merkle_beweis(hs, idx)
            assert C.merkle_pruefe_beweis(hs[idx], beweis, wurzel)
            # manipuliertes Blatt fällt gegen den echten Pfad
            manip = hs[idx][:-1] + bytes([hs[idx][-1] ^ 0x01])
            assert not C.merkle_pruefe_beweis(manip, beweis, wurzel)
        faelle += 1
    assert faelle == 220


def test_merkle_odd_promote_deterministisch():
    # 3 Blätter: das ungerade steigt unverändert auf (kein Duplizieren, CVE-2012-2459).
    hs = [hashlib.sha256(bytes([i])).digest() for i in range(3)]
    links = C._knoten(C._blatt(hs[0]), C._blatt(hs[1]))
    erwartet = C._knoten(links, C._blatt(hs[2]))
    assert C.merkle_wurzel(hs) == erwartet


# ── Ketten-Property: 220 seeded Zeilen, verify grün, 1-Bit-Flip bricht ────────

def test_kette_property_verify_und_flip(tmp_path):
    sk = C.konfiguriere(tmp_path / "chronik")
    pub = C.lade_pruefmaterial(tmp_path / "chronik").chronist_pub
    r = random.Random(0xD1221)
    prev_h = C.NULL_HASH
    n = 0
    for _ in range(220):
        n += 1
        nutz = {"buchung_id": f"b{n}", "wert": str(r.randint(-10**6, 10**6))}
        zeile = {"n": n, "app": "money", "i": n, "ts": C.now_iso(), "art": "money.buchung",
                 "subjekt": "u:" + "a" * 36, "entscheid": "",
                 "nutzlast_hash": C._sha256_hex(C.kanon(nutz)), "nutzlast": nutz,
                 "prev": "sha256:" + prev_h.hex()}
        h_n = C.kette_hash(prev_h, zeile)
        zeile["sig"] = C.signiere(h_n, sk.chronist)
        assert C.verifiziere_zeile(zeile, prev_h, pub) == h_n

        # 1-Bit-Flip in einem zufälligen Feld ⇒ verifiziere_zeile bricht
        kaputt = json.loads(json.dumps(zeile))
        feld = r.choice(["nutzlast", "sig", "ts", "subjekt"])
        if feld == "nutzlast":
            kaputt["nutzlast"]["wert"] = str(int(kaputt["nutzlast"]["wert"]) + 1)
        elif feld == "sig":
            schema, kid, b64 = kaputt["sig"].split(":", 2)   # erstes b64-Zeichen = volle 6 echte Bits
            kaputt["sig"] = f"{schema}:{kid}:{('B' if b64[0] != 'B' else 'C')}{b64[1:]}"
        else:
            kaputt[feld] = kaputt[feld] + "x"
        with pytest.raises(C.ChronikFehler):
            C.verifiziere_zeile(kaputt, prev_h, pub)

        prev_h = h_n


# ── pruefe / beweis gegen echte Segmente+Siegel (Golden-Generator) ────────────

def test_pruefe_gruen_und_beweis_fuer_jedes_n(tmp_path):
    cdir = tmp_path / "chronik"
    ev = [G.buchung(f"b{k}", str(1000 + k)) for k in range(8)]
    stat = G.baue_chronik(cdir, ev, epoche_groesse=3)     # Genesis+8 = 9 Zeilen → 3 Epochen
    assert stat["zeilen"] == 9 and stat["epochen"] == 3
    P.pruefe(cdir)                                          # grün ⇒ keine Exception
    for n in range(1, stat["zeilen"] + 1):
        b = P.beweis(cdir, n)
        assert b["n"] == n and b["wurzel"].startswith("sha256:")


def test_pruefe_flip_nennt_erste_bruchstelle(tmp_path):
    cdir = tmp_path / "chronik"
    G.baue_chronik(cdir, [G.buchung(f"b{k}", str(1000 + k)) for k in range(8)], epoche_groesse=3)
    # E2 trägt n=4,5,6 — manipuliere die erste Zeile (n=4): kippe ein sig-Zeichen.
    seg = cdir / "segmente" / "E00000002.dzc"
    zeilen = seg.read_text("utf-8").splitlines()
    z = json.loads(zeilen[0])
    assert z["n"] == 4
    schema, kid, b64 = z["sig"].split(":", 2)
    z["sig"] = f"{schema}:{kid}:{('B' if b64[0] != 'B' else 'C')}{b64[1:]}"
    zeilen[0] = C.kanon(z)
    seg.write_text("\n".join(zeilen) + "\n", "utf-8")

    with pytest.raises(P.Bruch) as ex:
        P.pruefe(cdir)
    assert ex.value.n == 4                                  # exakt die erste Bruchstelle


def test_torn_write_wird_als_bruch_erkannt(tmp_path):
    cdir = tmp_path / "chronik"
    G.baue_chronik(cdir, [G.buchung(f"b{k}", str(1000 + k)) for k in range(4)], epoche_groesse=2)
    seg = cdir / "segmente" / "E00000002.dzc"
    seg.write_text(seg.read_text("utf-8") + '{"n":99,"app":"money","i":9', "utf-8")  # halbe Zeile
    with pytest.raises(P.Bruch):
        P.pruefe(cdir)


def test_siegel_ketten_bruch_faellt(tmp_path):
    cdir = tmp_path / "chronik"
    G.baue_chronik(cdir, [G.buchung(f"b{k}", str(1000 + k)) for k in range(6)], epoche_groesse=2)
    sfile = cdir / "siegel" / "S00000002.json"
    s = json.loads(sfile.read_text("utf-8"))
    s["prev_siegel"] = C.GENESIS_PREV_SIEGEL               # falsche Vorgänger-Kette
    sfile.write_text(json.dumps(s), "utf-8")
    with pytest.raises(P.Bruch):
        P.pruefe(cdir)


def test_beweis_fehlendes_n(tmp_path):
    cdir = tmp_path / "chronik"
    G.baue_chronik(cdir, [G.buchung("b1", "1000")], epoche_groesse=4)
    with pytest.raises(P.Bruch):
        P.beweis(cdir, 999)
