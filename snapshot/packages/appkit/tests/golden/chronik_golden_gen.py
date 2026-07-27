"""Golden-Generator (Vertrag §7 / §11 Runde 2): erzeugt die **eingecheckten** Fixtures unter
``tests/golden/chronik/`` DETERMINISTISCH — feste Test-Schlüssel + fester Pfeffer + feste Uhr.

Die Fixtures sind der CI-Golden-Harness (C-13): ändert sich ``chronik.py`` am Format/Hash, fällt die
eingecheckte ``ok``-Fixture in ``pruefe`` auf (Drift-Wächter). Je Fehlerklasse liegt eine manipulierte
Variante mit erwartetem Exit-Code (``test_chronik_golden.py``).

Aufruf (regeneriert die Fixtures aus dem Repo-Wurzel-venv):
    PYTHONPATH=packages python packages/appkit/tests/golden/chronik_golden_gen.py

**Private Test-Schlüssel/Pfeffer werden NIE eingecheckt** — nur die öffentlichen Artefakte
(``segmente/``, ``siegel/``, ``stamm_pub.json``, ``schluesselbrief.json``), die der Prüfer braucht.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from appkit import chronik as C
from appkit import chronist as CH
from appkit import secrets_os
from appkit.chronist import Chronist, Quelle
from appkit.io_safe import atomic_write_text

GOLDEN = Path(__file__).resolve().parent / "chronik"
BASIS_ZEIT = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _det_jwk(seed: bytes) -> dict:
    """Deterministisches Ed25519-JWK aus 32 festen Seed-Bytes (kid = RFC-7638-Thumbprint)."""
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    x = _b64u(pub)
    kid = _b64u(hashlib.sha256(
        json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"), sort_keys=True)
        .encode("utf-8")).digest())
    return {"kty": "OKP", "crv": "Ed25519", "alg": "Ed25519", "use": "sig", "x": x, "d": _b64u(seed), "kid": kid}


class _Uhr:
    """Deterministischer, monoton steigender Sekunden-Takt für ``now_iso`` (Reproduzierbarkeit)."""
    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return (BASIS_ZEIT + timedelta(seconds=self.n)).isoformat(timespec="seconds")


def _schreibe_feste_schluessel(cdir: Path, ts: str) -> None:
    cdir.mkdir(parents=True, exist_ok=True)
    stamm, chronist = _det_jwk(b"\x11" * 32), _det_jwk(b"\x22" * 32)
    secrets_os.schreibe_geheim(cdir / "stamm_key.json", json.dumps(stamm).encode("utf-8"))
    secrets_os.schreibe_geheim(cdir / "chronist_key.json", json.dumps(chronist).encode("utf-8"))
    secrets_os.schreibe_geheim(cdir / "pfeffer.bin", b"\x33" * 32)
    atomic_write_text(cdir / "stamm_pub.json", C.kanon(C._oeffentlich(stamm)))
    kern = {"modul": "chronist", "kid": chronist["kid"], "pubkey": C._oeffentlich(chronist), "gueltig_ab": ts}
    sig = C._priv_von_jwk(stamm).sign(hashlib.sha256(C.kanon(kern).encode("utf-8")).digest())
    atomic_write_text(cdir / "schluesselbrief.json",
                      C.kanon({**kern, "brief_sig": f"ed25519:{stamm['kid']}:{_b64u(sig)}"}))


def _ereignisse() -> list[tuple[str, dict]]:
    def buch(bid, betrag):
        return ("money.buchung", {"buchung_id": bid, "datum": "2026-07-01", "quelle": "manuell",
                "postings": [{"konto_id": "1200", "betrag_minor": betrag},
                             {"konto_id": "8400", "betrag_minor": "-" + betrag}]})
    return [
        ("money.uebernahme", {"stichtag": "2026-06-30", "letzte_buchung_rowid": 0,
         "konten": [{"konto_id": "1200", "saldo_minor": "0"}, {"konto_id": "8400", "saldo_minor": "0"}]}),
        buch("b1", "1250"), buch("b2", "900"), buch("b3", "4200"),
        ("money.storno", {"buchung_id": "b2", "datum_storno": "2026-07-02",
         "postings": [{"konto_id": "1200", "betrag_minor": "-900"}, {"konto_id": "8400", "betrag_minor": "900"}]}),
        buch("b4", "500"),
    ]


def _erzeuge_ok(ziel: Path) -> None:
    C.reset_kontext()
    arbeit = Path(tempfile.mkdtemp())
    cdir, mdb = arbeit / "chronik", arbeit / "money.sqlite"
    orig = C.now_iso
    uhr = _Uhr()
    C.now_iso, CH.now_iso = uhr, uhr             # deterministische Zeitstempel
    try:
        _schreibe_feste_schluessel(cdir, "2026-07-01T00:00:00+00:00")
        conn = sqlite3.connect(mdb)
        conn.executescript(C.AUSGANG_SCHEMA)
        conn.commit()
        C.konfiguriere(cdir)                     # lädt die festen Schlüssel + Pfeffer
        for art, nutz in _ereignisse():
            C.schreibe(conn, art=art, nutzlast=nutz, subjekt="u:" + "a" * 36)
        conn.commit()
        conn.close()
        Chronist(cdir, [Quelle("money", str(mdb))], epoche_max=3,
                 uhr=lambda: datetime(2027, 1, 1, tzinfo=timezone.utc)).tick(flush=True)
        # nur die öffentlichen Artefakte einchecken (keine privaten Schlüssel/Pfeffer)
        if ziel.exists():
            shutil.rmtree(ziel)
        (ziel / "segmente").mkdir(parents=True)
        (ziel / "siegel").mkdir(parents=True)
        for p in (cdir / "segmente").iterdir():
            shutil.copy2(p, ziel / "segmente" / p.name)
        for p in (cdir / "siegel").iterdir():
            shutil.copy2(p, ziel / "siegel" / p.name)
        shutil.copy2(cdir / "stamm_pub.json", ziel / "stamm_pub.json")
        shutil.copy2(cdir / "schluesselbrief.json", ziel / "schluesselbrief.json")
    finally:
        C.now_iso, CH.now_iso = orig, orig
        C.reset_kontext()
        shutil.rmtree(arbeit, ignore_errors=True)


def _kopiere(quelle: Path, ziel: Path) -> None:
    if ziel.exists():
        shutil.rmtree(ziel)
    shutil.copytree(quelle, ziel)


def _erzeuge_varianten(ok: Path) -> None:
    """Je eine manipulierte Variante pro Fehlerklasse — jede trifft einen ANDEREN Prüf-Pfad in ``pruefe``."""
    # (1) Zeilen-Signatur-Bruch: ein Zeichen im ersten Segment kippen (Content-Manipulation)
    kb = ok.parent / "kette_bruch"
    _kopiere(ok, kb)
    seg = kb / "segmente" / "E00000001.dzc"
    seg.write_text(seg.read_text("utf-8").replace('"betrag_minor":"1250"', '"betrag_minor":"1251"', 1), "utf-8")

    # (2) Merkle-Wurzel weicht ab: falsche Wurzel, aber KORREKT nachsigniert ⇒ Siegel-Signatur trägt,
    #     der Merkle-Vergleich in `pruefe` schlägt an (genau dieser Code-Pfad wird getestet)
    mw = ok.parent / "merkle_wurzel_falsch"
    _kopiere(ok, mw)
    chronist = _det_jwk(b"\x22" * 32)
    sf = mw / "siegel" / "S00000001.json"
    s = json.loads(sf.read_text("utf-8"))
    s["wurzel"] = "sha256:" + "00" * 32
    kern = {k: v for k, v in s.items() if k != "zeugen"}
    basis = hashlib.sha256(C.kanon(kern).encode("utf-8")).digest()
    s["zeugen"] = [{"id": "chronist", "kid": chronist["kid"],
                    "sig": f"ed25519:{chronist['kid']}:{_b64u(C._priv_von_jwk(chronist).sign(basis))}"}]
    sf.write_text(C.kanon(s), "utf-8")

    # (3) Siegel-Ketten-Bruch: prev_siegel eines Folge-Siegels verfälschen
    kbs = ok.parent / "siegel_kette_bruch"
    _kopiere(ok, kbs)
    sf2 = kbs / "siegel" / "S00000002.json"
    s2 = json.loads(sf2.read_text("utf-8"))
    s2["prev_siegel"] = "sha256:" + "ff" * 32
    sf2.write_text(C.kanon(s2), "utf-8")


def main() -> None:
    ok = GOLDEN / "ok"
    _erzeuge_ok(ok)
    _erzeuge_varianten(ok)
    print(f"Golden-Fixtures erzeugt unter {GOLDEN}")


if __name__ == "__main__":
    main()
