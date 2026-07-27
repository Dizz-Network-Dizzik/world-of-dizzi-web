"""DzChronik-Kern (V-BIZZI-1, B1) — Formate, Outbox-Schreiber, Merkle, Schlüssel.

Das beweisende Rückgrat der Bizzi-Säule als **netzweiter appkit-Baustein** (docs/79 D1):
Kanon (RFC-8785-Subset) · Datenklassen-Zwang · Outbox-Schreiber (atomar in der App-Txn) ·
Hash-Kette · Merkle mit Domain-Separation · Ed25519-Schlüssel + Schlüsselbrief + Feld-Hash-Pfeffer.

Reine Bibliothek: KEINE App-Kopplung, KEIN ``bizzikit``-Import (das Paket existiert noch nicht — D1
ist genau dafür da). stdlib + ``cryptography`` (Roh-Signaturen/Verify) + ``joserfc`` (nur JWK-Erzeugung,
lazy importiert, damit der reine Prüf-/Verify-Pfad ohne joserfc auskommt — „an Prüfer herausgebbar").

Vertrag: ``docs/80_CHRONIK_VERTRAG.md`` (§2 Formate · §3 Datenklassen · §6.1 API), gehärtet um die
G-BZ-DELTA-Befunde (C-15 Pfeffer · C-16 Fork · C-17 ASCII-Keys/Format-Evolution).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .db import now_iso

# ─────────────────────────────────────────────────────────────────────────────
# Fehler + Konstanten
# ─────────────────────────────────────────────────────────────────────────────


class ChronikFehler(Exception):
    """Fail-loud VOR Commit: Kanon-/Klassen-/Schlüssel-Verletzung (C-2/C-3/C-17)."""


MAX_SAFE_INT = 2**53 - 1          # C-2: über 2^53 wären RFC-8785-Zahlen verlustbehaftet
_KANON_KEY_RE = re.compile(r"^[a-z0-9_.]+$")   # C-17: nur ASCII-Objekt-Schlüssel
_GENESIS_PREV = "sha256:" + "0" * 64
NULL_HASH = b"\x00" * 32
FORMAT_VERSION = "1"              # Zeilen-/Siegel-Format; Wechsel = chronik.format-Ereignis (C-17)

# Outbox-Schema (§2.2) — die App hängt es an ihr ``extra_schema`` (KEIN _BASE_SCHEMA-Eingriff).
# Bewusst KEINE user_id-Spalte (C-10) ⇒ retention_lauf/soft_delete_user fassen die Chronik nie an.
AUSGANG_SCHEMA = """
CREATE TABLE IF NOT EXISTS chronik_ausgang (
  i             INTEGER PRIMARY KEY AUTOINCREMENT,
  art           TEXT NOT NULL,
  nutzlast      TEXT NOT NULL,
  nutzlast_hash TEXT NOT NULL,
  entscheid_id  TEXT NOT NULL DEFAULT '',
  subjekt       TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  epoche        INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chronik_ausgang_offen ON chronik_ausgang (epoche) WHERE epoche IS NULL;
"""

# Datenklassen-Registry (§3). Wert = Nutzlast-Behandlung:
#   "klar"      → kanonische Nutzlast in der Kette, nutzlast_hash = sha256 (voll + struktur)
#   "hash_only" → nutzlast = '', nutzlast_hash = gepfefferter hmac256 (C-15)
# voll/struktur unterscheiden sich nur dokumentarisch (welche Felder) — mechanisch = "klar".
KLASSEN: dict[str, str] = {
    "chronik.genesis": "klar",
    "chronik.format": "klar",
    "money.uebernahme": "klar",       # BZ-C-1
    "money.buchung": "klar",          # struktur (Freitexte als gepfefferte feld_hash)
    "money.storno": "klar",
    "money.umklassung": "klar",       # BZ-C-2
    "money.beleg": "klar",            # BZ-C-2
    "money.festschreibung": "klar",
    "money.ustva_freigabe": "klar",   # Slot (verdrahtet erst mit M-2-Bau)
    "charta.version": "klar",         # reserviert B2
}
# Präfix-Klassen (reserviert): hash_only ⇒ Personendaten bleiben löschbar (Gate #3).
_HASH_ONLY_PRAEFIXE = ("verzeichnis.", "botschaft.")


def _klasse(art: str) -> str:
    if art in KLASSEN:
        return KLASSEN[art]
    if any(art.startswith(p) for p in _HASH_ONLY_PRAEFIXE):
        return "hash_only"
    raise ChronikFehler(f"unbekannte Datenklasse: {art!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Kanon (RFC-8785 durch Subset-Disziplin, §2.1 / C-2 / C-17)
# ─────────────────────────────────────────────────────────────────────────────


def _pruefe_kanon(obj: Any, _tiefe: int = 0) -> None:
    """Rekursive Validierung des erlaubten Subsets — fail-loud VOR jeder Serialisierung."""
    if _tiefe > 64:
        raise ChronikFehler("Kanon: zu tief verschachtelt")
    if obj is None or isinstance(obj, str):
        return
    if isinstance(obj, bool):        # bool VOR int prüfen (bool ⊂ int in Python)
        return
    if isinstance(obj, int):
        if abs(obj) > MAX_SAFE_INT:
            raise ChronikFehler(f"Kanon: int {obj} > 2^53-1 (Geld gehört als Dezimal-String)")
        return
    if isinstance(obj, float):
        raise ChronikFehler("Kanon: float verboten (NaN/Inf/Rundung) — Geld ist Dezimal-String")
    if isinstance(obj, list):
        for x in obj:
            _pruefe_kanon(x, _tiefe + 1)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or not _KANON_KEY_RE.match(k):
                raise ChronikFehler(f"Kanon: Objekt-Schlüssel muss ASCII [a-z0-9_.] sein: {k!r}")
            _pruefe_kanon(v, _tiefe + 1)
        return
    raise ChronikFehler(f"Kanon: Typ {type(obj).__name__} nicht erlaubt")


def kanon(obj: Any) -> str:
    """RFC-8785-kanonisches JSON auf dem erlaubten Subset (UTF-8, sortierte ASCII-Keys,
    keine Whitespaces). Auf diesem Subset ist ``json.dumps(...)`` bit-genau RFC-8785."""
    _pruefe_kanon(obj)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Schlüssel + Schlüsselbrief + Feld-Hash-Pfeffer (§2.6 / C-12 / C-15)
# ─────────────────────────────────────────────────────────────────────────────


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _priv_von_jwk(jwk: dict) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_b64u_dec(jwk["d"]))


def _pub_von_jwk(jwk: dict) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64u_dec(jwk["x"]))


def _oeffentlich(jwk: dict) -> dict:
    """Öffentlicher Teil eines OKP-JWK (kty, crv, x, kid) — nie d."""
    return {k: jwk[k] for k in ("kty", "crv", "x", "kid") if k in jwk}


@dataclass
class ChronikSchluessel:
    """Geladenes Schlüssel-Material einer Instanz (privat — nur im Chronist-Konto)."""
    stamm: dict           # Stamm-JWK (privat)
    chronist: dict        # Chronist-Arbeits-JWK (privat)
    pfeffer: bytes        # 32 B Feld-Hash-Pfeffer (C-15)


def chronik_dir(data_root: Path | None = None) -> Path:
    """Laufzeit-Verzeichnis ``<root>/chronik`` (außerhalb Repo). Env ``DIZZ_CHRONIK_DIR``
    übersteuert (Tests/Editionen); sonst ``C:\\Dizzik\\data\\chronik``."""
    env = os.environ.get("DIZZ_CHRONIK_DIR")
    if env:
        return Path(env)
    root = data_root or Path(r"C:\Dizzik\data")
    return root / "chronik"


def _neues_okp_jwk() -> dict:
    """Erzeugt ein Ed25519-JWK (kid = Thumbprint) — joserfc lazy, damit der Verify-Pfad
    (Prüfer) ohne joserfc läuft. Format-konsistent mit ``core/app/id/keys.py``."""
    from joserfc.jwk import OKPKey
    key = OKPKey.generate_key("Ed25519", {"alg": "Ed25519", "use": "sig"})
    data = key.as_dict(private=True)
    data["kid"] = key.thumbprint()
    return data


def _brief_pfad(cdir: Path) -> Path:
    return cdir / "schluesselbrief.json"


def _stamm_pub_pfad(cdir: Path) -> Path:
    return cdir / "stamm_pub.json"


def lade_oder_erzeuge_schluessel(cdir: Path | None = None) -> ChronikSchluessel:
    """Lädt Stamm-/Chronist-Schlüssel + Pfeffer (secrets_os/DPAPI); erzeugt sie beim ersten
    Start (C-12). Schreibt zusätzlich ``stamm_pub.json`` + ``schluesselbrief.json`` als
    Klartext, damit der Prüfer OHNE DPAPI verifizieren kann."""
    from . import secrets_os
    from .io_safe import atomic_write_text

    cdir = cdir or chronik_dir()
    cdir.mkdir(parents=True, exist_ok=True)
    stamm_p, chronist_p, pfeffer_p = (
        cdir / "stamm_key.json", cdir / "chronist_key.json", cdir / "pfeffer.bin")

    roh_stamm = secrets_os.lese_geheim(stamm_p)
    roh_chronist = secrets_os.lese_geheim(chronist_p)
    roh_pfeffer = secrets_os.lese_geheim(pfeffer_p)

    if roh_stamm and roh_chronist and roh_pfeffer:
        return ChronikSchluessel(
            stamm=json.loads(roh_stamm.decode("utf-8")),
            chronist=json.loads(roh_chronist.decode("utf-8")),
            pfeffer=roh_pfeffer)

    # Erst-Erzeugung (atomar; Brief beglaubigt Chronist unter dem Stamm)
    stamm = _neues_okp_jwk()
    chronist = _neues_okp_jwk()
    pfeffer = os.urandom(32)
    secrets_os.schreibe_geheim(stamm_p, json.dumps(stamm).encode("utf-8"))
    secrets_os.schreibe_geheim(chronist_p, json.dumps(chronist).encode("utf-8"))
    secrets_os.schreibe_geheim(pfeffer_p, pfeffer)

    atomic_write_text(_stamm_pub_pfad(cdir), kanon(_oeffentlich(stamm)))
    brief_kern = {
        "modul": "chronist",
        "kid": chronist["kid"],
        "pubkey": _oeffentlich(chronist),
        "gueltig_ab": now_iso(),
    }
    brief_sig = _priv_von_jwk(stamm).sign(hashlib.sha256(kanon(brief_kern).encode("utf-8")).digest())
    brief = {**brief_kern, "brief_sig": f"ed25519:{stamm['kid']}:{_b64u(brief_sig)}"}
    atomic_write_text(_brief_pfad(cdir), kanon(brief))
    return ChronikSchluessel(stamm=stamm, chronist=chronist, pfeffer=pfeffer)


@dataclass
class PruefMaterial:
    """Öffentliches Material für die Offline-Prüfung (nie DPAPI): Stamm-Pub + beglaubigter
    Chronist-Pub. ``lade_pruefmaterial`` verifiziert den Schlüsselbrief beim Laden."""
    stamm_pub: dict
    chronist_pub: dict


def lade_pruefmaterial(cdir: Path | None = None) -> PruefMaterial:
    cdir = cdir or chronik_dir()
    stamm_pub = json.loads(_stamm_pub_pfad(cdir).read_text("utf-8"))
    brief = json.loads(_brief_pfad(cdir).read_text("utf-8"))
    kern = {k: brief[k] for k in ("modul", "kid", "pubkey", "gueltig_ab")}
    if not _verify_roh(brief["brief_sig"], hashlib.sha256(kanon(kern).encode("utf-8")).digest(),
                       {stamm_pub["kid"]: stamm_pub}):
        raise ChronikFehler("Schlüsselbrief-Signatur ungültig (Stamm beglaubigt Chronist nicht)")
    return PruefMaterial(stamm_pub=stamm_pub, chronist_pub=brief["pubkey"])


# ─────────────────────────────────────────────────────────────────────────────
# Feld-Hash (gepfeffert, C-15) — Modul-Kontext (lazy, wie keys.py-Cache)
# ─────────────────────────────────────────────────────────────────────────────

_KONTEXT: ChronikSchluessel | None = None
_KONTEXT_DIR: Path | None = None


def konfiguriere(cdir: Path | None = None) -> ChronikSchluessel:
    """Setzt den Modul-Kontext (Schlüssel + Pfeffer) für ``schreibe``/``feld_hash``.
    In der App implizit lazy; Tests rufen es mit einem tmp-Verzeichnis."""
    global _KONTEXT, _KONTEXT_DIR
    _KONTEXT_DIR = cdir or chronik_dir()
    _KONTEXT = lade_oder_erzeuge_schluessel(_KONTEXT_DIR)
    return _KONTEXT


def reset_kontext() -> None:
    """Für Tests (frisches chronik_dir ⇒ frische Schlüssel)."""
    global _KONTEXT, _KONTEXT_DIR
    _KONTEXT, _KONTEXT_DIR = None, None


def _kontext() -> ChronikSchluessel:
    global _KONTEXT
    if _KONTEXT is None:
        konfiguriere()
    assert _KONTEXT is not None
    return _KONTEXT


def feld_hash(text: str | None) -> str | None:
    """Gepfefferter Feld-Hash für Freitexte (C-15). ``None``/leer ⇒ ``None`` (Feld entfällt).
    ``"hmac256:" + HMAC-SHA-256(pfeffer, UTF8(text))`` — ohne Pfeffer kein Wörterbuch-Angriff."""
    if not text:
        return None
    return _hmac_hex(_kontext().pfeffer, text.encode("utf-8"))


def _hmac_hex(pfeffer: bytes, daten: bytes) -> str:
    return "hmac256:" + hmac.new(pfeffer, daten, hashlib.sha256).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Outbox-Schreiber (§6.1 / C-1 / C-3) — atomar in der offenen App-Txn
# ─────────────────────────────────────────────────────────────────────────────


def schreibe(conn: sqlite3.Connection, *, art: str, nutzlast: dict,
             subjekt: str, entscheid_id: str = "") -> None:
    """Schreibt EIN Chronik-Ereignis in ``chronik_ausgang`` — **auf der übergebenen offenen
    Verbindung, ohne Commit** (C-1: dieselbe ``db.transaktion()`` wie die Tabellen-Mutation).

    Validiert Datenklasse (C-3) + Kanon (C-2/C-17), berechnet den ``nutzlast_hash``
    (voll/struktur: sha256 über den kanonischen Klartext; hash_only: gepfefferter hmac256, C-15).
    """
    klasse = _klasse(art)                       # C-3: unbekannte art ⇒ ChronikFehler
    _pruefe_subjekt(subjekt)                    # BZ-C-10: opake Kennung, nie Klartext-Name
    if not isinstance(nutzlast, dict):
        raise ChronikFehler("nutzlast muss ein dict sein")
    kanon_str = kanon(nutzlast)                 # fail-loud VOR INSERT

    if klasse == "hash_only":
        gespeicherte_last, nutzlast_hash = "", _hmac_hex(_kontext().pfeffer, kanon_str.encode("utf-8"))
    else:
        gespeicherte_last, nutzlast_hash = kanon_str, _sha256_hex(kanon_str)

    conn.execute(
        "INSERT INTO chronik_ausgang (art, nutzlast, nutzlast_hash, entscheid_id, subjekt, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (art, gespeicherte_last, nutzlast_hash, entscheid_id, subjekt, now_iso()))


_SUBJEKT_RE = re.compile(r"^(system|u:[0-9a-fA-F-]{8,}|agent:[0-9a-fA-F:-]+)$")


def _pruefe_subjekt(subjekt: str) -> None:
    """BZ-C-10: ``subjekt`` trägt ausschließlich eine opake Kennung (``system`` |
    ``u:<uuid>`` | ``agent:<id>``) — nie einen Login-/Anzeigenamen (der käme unlöschbar
    in die Kette und kollabierte das Pseudonymitäts-Argument aus §3)."""
    if not _SUBJEKT_RE.match(subjekt):
        raise ChronikFehler(f"subjekt {subjekt!r}: nur opake Kennung erlaubt (u:<uuid>|system|agent:<id>)")


# ─────────────────────────────────────────────────────────────────────────────
# Hash-Kette + Signatur (§2.3 / C-4)
# ─────────────────────────────────────────────────────────────────────────────


def kette_hash(prev_h: bytes, zeile_ohne_sig: dict) -> bytes:
    """``h_n = SHA-256( h_{n-1} ‖ UTF8(kanon(zeile_ohne_sig)) )`` — prev als 32 Roh-Bytes."""
    return hashlib.sha256(prev_h + kanon(zeile_ohne_sig).encode("utf-8")).digest()


def signiere(h: bytes, priv_jwk: dict) -> str:
    """Roh-Ed25519-Signatur über den 32-Byte-Digest ``h`` ⇒ ``ed25519:<kid>:<b64url>``."""
    return f"ed25519:{priv_jwk['kid']}:{_b64u(_priv_von_jwk(priv_jwk).sign(h))}"


def _verify_roh(sig_str: str, h: bytes, pub_registry: dict[str, dict]) -> bool:
    """Prüft ``ed25519:<kid>:<b64url>`` gegen den öffentlichen JWK mit passendem kid."""
    try:
        schema, kid, b64 = sig_str.split(":", 2)
    except ValueError:
        return False
    if schema != "ed25519" or kid not in pub_registry:
        return False
    try:
        _pub_von_jwk(pub_registry[kid]).verify(_b64u_dec(b64), h)
        return True
    except (InvalidSignature, ValueError):
        return False


def verifiziere_zeile(zeile: dict, prev_h: bytes, chronist_pub: dict) -> bytes:
    """Verifiziert eine Segment-Zeile: prev-Konsistenz + Signatur; liefert ``h_n`` zurück
    (für die Weiterkettung). Wirft ``ChronikFehler`` bei Bruch (mit Grund)."""
    ohne_sig = {k: v for k, v in zeile.items() if k != "sig"}
    erwartet_prev = "sha256:" + prev_h.hex()
    if zeile.get("prev") != erwartet_prev:
        raise ChronikFehler(f"prev-Bruch bei n={zeile.get('n')}: {zeile.get('prev')} != {erwartet_prev}")
    h_n = kette_hash(prev_h, ohne_sig)
    if not _verify_roh(zeile.get("sig", ""), h_n, {chronist_pub["kid"]: chronist_pub}):
        raise ChronikFehler(f"Signatur-Bruch bei n={zeile.get('n')}")
    return h_n


# ─────────────────────────────────────────────────────────────────────────────
# Merkle (§2.4 / C-7) — Domain-Separation 0x00/0x01, odd-promote (CVE-2012-2459-Klasse)
# ─────────────────────────────────────────────────────────────────────────────


def _blatt(h_n: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + h_n).digest()


def _knoten(links: bytes, rechts: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + links + rechts).digest()


def merkle_wurzel(h_liste: list[bytes]) -> bytes:
    """Wurzel über die ``h_n`` einer Epoche. Ungerades Element steigt **unverändert** auf
    (kein Duplizieren). Leere Epochen entstehen nie (C-6) ⇒ hier ≥ 1 vorausgesetzt."""
    if not h_liste:
        raise ChronikFehler("Merkle über leere Epoche (verboten, C-6)")
    ebene = [_blatt(h) for h in h_liste]
    while len(ebene) > 1:
        naechste: list[bytes] = []
        for j in range(0, len(ebene), 2):
            if j + 1 < len(ebene):
                naechste.append(_knoten(ebene[j], ebene[j + 1]))
            else:
                naechste.append(ebene[j])          # odd-promote
        ebene = naechste
    return ebene[0]


def merkle_beweis(h_liste: list[bytes], index: int) -> list[dict]:
    """Einschluss-Pfad für Blatt ``index`` als ``[{"seite":"L|R","hash":"sha256:…"}]``."""
    if not 0 <= index < len(h_liste):
        raise ChronikFehler("Merkle-Beweis: Index außerhalb der Epoche")
    ebene = [_blatt(h) for h in h_liste]
    pfad: list[dict] = []
    idx = index
    while len(ebene) > 1:
        naechste, paar_index = [], idx // 2
        for j in range(0, len(ebene), 2):
            if j + 1 < len(ebene):
                if j == idx:
                    pfad.append({"seite": "R", "hash": "sha256:" + ebene[j + 1].hex()})
                elif j + 1 == idx:
                    pfad.append({"seite": "L", "hash": "sha256:" + ebene[j].hex()})
                naechste.append(_knoten(ebene[j], ebene[j + 1]))
            else:
                naechste.append(ebene[j])          # odd-promote: kein Geschwister
        ebene, idx = naechste, paar_index
    return pfad


def merkle_pruefe_beweis(blatt_h_n: bytes, pfad: list[dict], wurzel: bytes) -> bool:
    """Rekonstruiert die Wurzel aus Blatt + Pfad und vergleicht (verify)."""
    akt = _blatt(blatt_h_n)
    for schritt in pfad:
        geschwister = bytes.fromhex(schritt["hash"].split(":", 1)[1])
        akt = _knoten(geschwister, akt) if schritt["seite"] == "L" else _knoten(akt, geschwister)
    return akt == wurzel


# ─────────────────────────────────────────────────────────────────────────────
# Siegel (§2.5 / C-8) — quorum-parametrisch; v1 aktiv = quorum=1 Selbstsiegel
# ─────────────────────────────────────────────────────────────────────────────

GENESIS_PREV_SIEGEL = "sha256:" + "0" * 64


def _siegel_basis(siegel_ohne_zeugen: dict) -> bytes:
    """Signatur-/Ketten-Basis eines Siegels: ``SHA-256(UTF8(kanon(siegel_ohne_zeugen)))``."""
    return hashlib.sha256(kanon(siegel_ohne_zeugen).encode("utf-8")).digest()


def siegel_hash(siegel: dict) -> str:
    """Der ``prev_siegel``-Wert, den ein Nachfolge-Siegel trägt (Siegel-Kette)."""
    kern = {k: v for k, v in siegel.items() if k != "zeugen"}
    return "sha256:" + _siegel_basis(kern).hex()


def baue_siegel(*, epoche: int, wurzel: bytes, prev_siegel: str, ereignisse: int,
                von_n: int, bis_n: int, quorum: int, chronist_jwk: dict) -> dict:
    """Erzeugt das quorum=1-Selbstsiegel (§2.5). Das Format trägt Mehr-Zeugen ab Tag 1
    (B7 ergänzt nur die Zeugen-Prozesse) — hier signiert der Chronist selbst."""
    kern = {
        "epoche": epoche, "wurzel": "sha256:" + wurzel.hex(), "prev_siegel": prev_siegel,
        "ereignisse": ereignisse, "von_n": von_n, "bis_n": bis_n,
        "zeit": now_iso(), "quorum": quorum,
    }
    basis = _siegel_basis(kern)
    sig = f"ed25519:{chronist_jwk['kid']}:{_b64u(_priv_von_jwk(chronist_jwk).sign(basis))}"
    return {**kern, "zeugen": [{"id": "chronist", "kid": chronist_jwk["kid"], "sig": sig}]}


def verifiziere_siegel(siegel: dict, prev_siegel: str, pub_registry: dict[str, dict]) -> str:
    """Prüft prev_siegel-Kette, Zeugen-Signaturen (über die Basis) und Quorum-Erfüllung.
    Liefert den ``siegel_hash`` für die Weiterkettung. Wirft ``ChronikFehler`` bei Bruch."""
    if siegel.get("prev_siegel") != prev_siegel:
        raise ChronikFehler(f"Siegel-Kette gebrochen bei Epoche {siegel.get('epoche')}: "
                            f"{siegel.get('prev_siegel')} != {prev_siegel}")
    kern = {k: v for k, v in siegel.items() if k != "zeugen"}
    basis = _siegel_basis(kern)
    gueltige = 0
    for zeuge in siegel.get("zeugen", []):
        kid = zeuge.get("kid")
        if kid in pub_registry and _verify_roh(zeuge.get("sig", ""), basis, {kid: pub_registry[kid]}):
            gueltige += 1
    if gueltige < siegel.get("quorum", 1):
        raise ChronikFehler(f"Siegel Epoche {siegel.get('epoche')}: Quorum nicht erfüllt "
                            f"({gueltige} < {siegel.get('quorum')})")
    return "sha256:" + basis.hex()
