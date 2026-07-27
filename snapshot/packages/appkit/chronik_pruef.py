"""chronik_pruef.py — der Prüfkern (CLI ``bizzi-pruef``). Ein Modul, drei Einstiege (C-13).

Offline lauffähig, auch an Prüfer herausgebbar: liest NUR ``segmente/``, ``siegel/``,
``stamm_pub.json`` + ``schluesselbrief.json`` (nie DPAPI, kein privater Schlüssel).
Verifiziert Kette (h-Rechnung Zeile für Zeile) · Signaturen (Schlüsselbrief → Chronist) ·
Merkle-Wurzeln · Siegel-Kette · Quorum · n/i-Monotonie je App.

B1-Runde-1-Umfang (Vertrag §11): ``pruefe`` + ``beweis`` sind vollständig; ``salden-replay``
(Runde 3, braucht money.uebernahme+Buchungen) · ``acl-probe`` (Runde 2) · ``bericht`` (Runde 2/3)
sind als Einstiege angelegt und melden ehrlich ihren Ausbaustand, statt Grün vorzutäuschen.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from . import chronik as C

# Exit-Codes (Vertrag §5): 0 grün · 2 Ketten-/Siegel-Bruch · 3 Salden-Divergenz · 4 ACL nicht aktiv
EXIT_GRUEN, EXIT_BRUCH, EXIT_DIVERGENZ, EXIT_ACL_INAKTIV = 0, 2, 3, 4

_SEG_RE = re.compile(r"^E(\d{8})\.dzc$")
_SIE_RE = re.compile(r"^S(\d{8})\.json$")


class Bruch(Exception):
    """Erste gefundene Bruchstelle — trägt Epoche/n/Grund für die CLI-Ausgabe."""
    def __init__(self, grund: str, *, epoche: int | None = None, n: int | None = None):
        super().__init__(grund)
        self.grund, self.epoche, self.n = grund, epoche, n

    def __str__(self) -> str:
        wo = []
        if self.epoche is not None:
            wo.append(f"Epoche {self.epoche}")
        if self.n is not None:
            wo.append(f"n={self.n}")
        return (", ".join(wo) + ": " if wo else "") + self.grund


def _segment_dateien(cdir: Path) -> list[tuple[int, Path]]:
    seg = cdir / "segmente"
    treffer = []
    if seg.is_dir():
        for p in seg.iterdir():
            m = _SEG_RE.match(p.name)
            if m:
                treffer.append((int(m.group(1)), p))
    return sorted(treffer)


def _siegel_dateien(cdir: Path) -> dict[int, dict]:
    sie = cdir / "siegel"
    out: dict[int, dict] = {}
    if sie.is_dir():
        for p in sie.iterdir():
            m = _SIE_RE.match(p.name)
            if m:
                out[int(m.group(1))] = json.loads(p.read_text("utf-8"))
    return out


def _money_db_aus_quellen(cdir: Path) -> Path | None:
    """money-DB-Pfad aus der Quellen-Registry ``quellen.json`` (für die CLI-Bequemlichkeit)."""
    p = cdir / "quellen.json"
    if p.is_file():
        for e in json.loads(p.read_text("utf-8")):
            if e.get("app") == "money":
                return Path(e["db"])
    return None


def pruefe(cdir: Path, von: int | None = None, bis: int | None = None) -> None:
    """Verifiziert Kette + Merkle + Siegel-Kette über alle Segmente/Siegel. Wirft ``Bruch``
    bei der ERSTEN Inkonsistenz (mit Epoche/n/Grund), sonst return = grün."""
    material = C.lade_pruefmaterial(cdir)
    chronist_pub = material.chronist_pub
    pub_reg = {chronist_pub["kid"]: chronist_pub}

    prev_h = C.NULL_HASH
    letztes_n = 0
    letztes_i: dict[str, int] = {}
    h_je_epoche: dict[int, list[bytes]] = {}
    n_grenzen: dict[int, tuple[int, int]] = {}   # epoche -> (von_n, bis_n)

    for epoche, pfad in _segment_dateien(cdir):
        if (von and epoche < von) or (bis and epoche > bis):
            continue
        for roh in pfad.read_text("utf-8").splitlines():
            if not roh.strip():
                continue
            try:
                zeile = json.loads(roh)
            except json.JSONDecodeError:
                raise Bruch("kein vollständiges JSON (torn write?)", epoche=epoche)
            n = zeile.get("n")
            if n != letztes_n + 1:
                raise Bruch(f"n nicht lückenlos (erwartet {letztes_n + 1}, ist {n})", epoche=epoche, n=n)
            try:
                prev_h = C.verifiziere_zeile(zeile, prev_h, chronist_pub)
            except C.ChronikFehler as e:
                raise Bruch(str(e), epoche=epoche, n=n)
            app = zeile.get("app", "")
            i = zeile.get("i", 0)
            if app in letztes_i and i <= letztes_i[app] and not (app == "chronik" and i == 0):
                raise Bruch(f"i nicht monoton je App '{app}' (ist {i} <= {letztes_i[app]})", epoche=epoche, n=n)
            letztes_i[app] = i
            letztes_n = n
            h_je_epoche.setdefault(epoche, []).append(prev_h)
            vn, bn = n_grenzen.get(epoche, (n, n))
            n_grenzen[epoche] = (min(vn, n), max(bn, n))

    # Siegel-Kette + Merkle-Wurzeln
    siegel = _siegel_dateien(cdir)
    prev_siegel = C.GENESIS_PREV_SIEGEL
    for epoche in sorted(siegel):
        if (von and epoche < von) or (bis and epoche > bis):
            continue
        s = siegel[epoche]
        try:
            prev_siegel = C.verifiziere_siegel(s, prev_siegel, pub_reg)
        except C.ChronikFehler as e:
            raise Bruch(str(e), epoche=epoche)
        h_liste = h_je_epoche.get(epoche, [])
        if not h_liste:
            raise Bruch("Siegel ohne zugehörige Segment-Zeilen", epoche=epoche)
        erwartet = "sha256:" + C.merkle_wurzel(h_liste).hex()
        if s.get("wurzel") != erwartet:
            raise Bruch(f"Merkle-Wurzel weicht ab ({s.get('wurzel')} != {erwartet})", epoche=epoche)
        vn, bn = n_grenzen[epoche]
        if (s.get("von_n"), s.get("bis_n"), s.get("ereignisse")) != (vn, bn, len(h_liste)):
            raise Bruch("von_n/bis_n/ereignisse inkonsistent zur Epoche", epoche=epoche)


def beweis(cdir: Path, n: int) -> dict:
    """Erzeugt + verifiziert den Merkle-Einschluss-Beweis für Zeile ``n`` gegen ihr Siegel.
    Liefert das Beweis-Objekt (§2.4). Wirft ``Bruch`` wenn n fehlt oder der Beweis nicht trägt."""
    material = C.lade_pruefmaterial(cdir)
    chronist_pub = material.chronist_pub
    prev_h = C.NULL_HASH
    ziel_epoche: int | None = None
    ziel_h: bytes | None = None
    h_je_epoche: dict[int, list[bytes]] = {}

    for epoche, pfad in _segment_dateien(cdir):
        for roh in pfad.read_text("utf-8").splitlines():
            if not roh.strip():
                continue
            zeile = json.loads(roh)
            prev_h = C.verifiziere_zeile(zeile, prev_h, chronist_pub)
            h_je_epoche.setdefault(epoche, []).append(prev_h)
            if zeile.get("n") == n:
                ziel_epoche, ziel_h = epoche, prev_h

    if ziel_epoche is None or ziel_h is None:
        raise Bruch(f"n={n} in keinem Segment gefunden")
    siegel = _siegel_dateien(cdir).get(ziel_epoche)
    if not siegel:
        raise Bruch("Siegel der deckenden Epoche fehlt", epoche=ziel_epoche, n=n)
    h_liste = h_je_epoche[ziel_epoche]
    index = h_liste.index(ziel_h)
    pfad_proof = C.merkle_beweis(h_liste, index)
    wurzel = bytes.fromhex(siegel["wurzel"].split(":", 1)[1])
    if not C.merkle_pruefe_beweis(ziel_h, pfad_proof, wurzel):
        raise Bruch("Einschluss-Beweis verifiziert nicht gegen das Siegel", epoche=ziel_epoche, n=n)
    return {"epoche": ziel_epoche, "n": n, "blatt": "sha256:" + ziel_h.hex(),
            "pfad": pfad_proof, "wurzel": siegel["wurzel"]}


# ─────────────────────────────────────────────────────────────────────────────
# salden-replay (§5 / §6.0) — die Kette deckt die heutige money-DB
# ─────────────────────────────────────────────────────────────────────────────


def _money_ereignisse(cdir: Path, bis_siegel: int | None) -> list[tuple[str, dict]]:
    """Liest die money-Ereignisse (uebernahme/buchung/storno/festschreibung) aus den Segmenten
    in Ketten-Reihenfolge. ``bis_siegel`` begrenzt optional auf Epochen ≤ S."""
    arten = {"money.uebernahme", "money.buchung", "money.storno", "money.festschreibung"}
    ereignisse: list[tuple[str, dict]] = []
    for epoche, pfad in _segment_dateien(cdir):
        if bis_siegel is not None and epoche > bis_siegel:
            break
        for roh in pfad.read_text("utf-8").splitlines():
            if not roh.strip():
                continue
            z = json.loads(roh)
            if z.get("art") in arten and isinstance(z.get("nutzlast"), dict):
                ereignisse.append((z["art"], z["nutzlast"]))
    return ereignisse


def salden_replay(cdir: Path, money_db: Path, bis_siegel: int | None = None) -> tuple[int, list[str]]:
    """§5/§6.0: rechnet die Konto-Salden aus ``money.uebernahme`` (Anker) + ``money.buchung/storno``
    nach und vergleicht gegen die money-DB (je Konto + Summe = 0). ``money.festschreibung`` mit
    Beweisgrad ``voll`` wird gegen ihren ``salden_hash`` gegengeprüft (Ketten-Deckung). Exit 0 grün ·
    2 Ketten-Bruch · 3 Salden-Divergenz (Konto + Differenz)."""
    try:
        pruefe(cdir)                                  # Integrität zuerst — ohne Kette kein Replay
    except (Bruch, C.ChronikFehler) as e:
        return EXIT_BRUCH, [f"BRUCH: {e}"]

    ereignisse = _money_ereignisse(cdir, bis_siegel)
    salden: dict[str, int] = {}
    buchung_zeitraum: dict[str, str] = {}
    for art, nutz in ereignisse:
        if art == "money.uebernahme":
            for k in nutz.get("konten", []):
                salden[k["konto_id"]] = salden.get(k["konto_id"], 0) + int(k["saldo_minor"])
        elif art == "money.buchung":
            buchung_zeitraum[nutz["buchung_id"]] = str(nutz.get("datum", ""))[:7]
            for p in nutz.get("postings", []):
                salden[p["konto_id"]] = salden.get(p["konto_id"], 0) + int(p["betrag_minor"])
        elif art == "money.storno":
            for p in nutz.get("postings", []):
                salden[p["konto_id"]] = salden.get(p["konto_id"], 0) + int(p["betrag_minor"])

    conn = sqlite3.connect(money_db)
    try:
        hat_postings = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='postings'").fetchone()
        db_salden = {r[0]: int(r[1]) for r in conn.execute(
            "SELECT konto_id, SUM(betrag) FROM postings WHERE deleted_at IS NULL "
            "GROUP BY konto_id").fetchall()} if hat_postings else {}
    finally:
        conn.close()

    zeilen: list[str] = []
    for konto in sorted(set(salden) | set(db_salden)):
        kette, db = salden.get(konto, 0), db_salden.get(konto, 0)
        if kette != db:
            zeilen.append(f"DIVERGENZ Konto {konto}: Kette {kette} != DB {db} (Delta {kette - db})")
    if zeilen:
        return EXIT_DIVERGENZ, zeilen
    if sum(salden.values()) != 0:
        return EXIT_DIVERGENZ, [f"DIVERGENZ: Summe aller Ketten-Salden ist {sum(salden.values())}, muss 0 sein"]

    # Festschreibungs-Gegenprobe (nur beweisgrad=voll — db-stand ist ehrlich nicht ketten-deckbar, §6.0)
    voll = 0
    for art, nutz in ereignisse:
        if art != "money.festschreibung" or nutz.get("beweisgrad") != "voll":
            continue
        zeitraum = nutz["zeitraum"]
        netto: dict[str, int] = {}
        for a2, n2 in ereignisse:
            if a2 == "money.buchung" and str(n2.get("datum", ""))[:7] == zeitraum:
                for p in n2.get("postings", []):
                    netto[p["konto_id"]] = netto.get(p["konto_id"], 0) + int(p["betrag_minor"])
            elif a2 == "money.storno" and buchung_zeitraum.get(n2.get("buchung_id", ""), "") == zeitraum:
                for p in n2.get("postings", []):
                    netto[p["konto_id"]] = netto.get(p["konto_id"], 0) + int(p["betrag_minor"])
        liste = [{"konto_id": k, "saldo_minor": str(v)} for k, v in sorted(netto.items()) if v != 0]
        if C._sha256_hex(C.kanon(liste)) != nutz.get("salden_hash"):
            return EXIT_DIVERGENZ, [f"DIVERGENZ Festschreibung {zeitraum}: salden_hash deckt die Kette nicht"]
        voll += 1

    zeilen.append(f"grün — {len(set(salden) | set(db_salden))} Konten: Ketten-Salden = DB-Salden (Summe=0)")
    if voll:
        zeilen.append(f"{voll} voll-Festschreibung(en) gegen die Kette bestätigt")
    return EXIT_GRUEN, zeilen


# ─────────────────────────────────────────────────────────────────────────────
# acl-probe (§4.5c) — Stufe-1-Härtung am lebenden System
# ─────────────────────────────────────────────────────────────────────────────


def acl_probe(cdir: Path) -> int:
    """Prüft, ob der aufrufende Prozess ``segmente/`` NICHT beschreiben kann (Datei-ACL-Härtung,
    §4.5b). Kann er schreiben ⇒ Stufe-1 **nicht aktiv** (ehrlich, Ein-Konto-Edition) ⇒ Exit 4.
    PermissionError ⇒ gehärtet ⇒ Exit 0. Kein Bau-Test — eine Aussage über das lebende System."""
    seg = cdir / "segmente"
    seg.mkdir(parents=True, exist_ok=True)
    probe = seg / ".acl_probe.tmp"
    try:
        probe.write_text("probe", "utf-8")
    except PermissionError:
        return EXIT_GRUEN
    probe.unlink(missing_ok=True)
    return EXIT_ACL_INAKTIV


# ─────────────────────────────────────────────────────────────────────────────
# bericht (§5) — menschenlesbarer Prüfbericht + Restore-Wächter (§4.6)
# ─────────────────────────────────────────────────────────────────────────────


def _lies_genesis(cdir: Path) -> dict | None:
    """Nutzlast der Genesis-Zeile (n=1) — für die Genesis-Plausibilität (BZ-C-11)."""
    segs = _segment_dateien(cdir)
    if not segs:
        return None
    for roh in segs[0][1].read_text("utf-8").splitlines():
        if roh.strip():
            z = json.loads(roh)
            return z.get("nutzlast") if z.get("art") == "chronik.genesis" else None
    return None


def _fehlende_festschreibungs_referenzen(cdir: Path, money_db: Path) -> list[dict]:
    """Restore-Wächter §4.6 Fall (b): jede ``festschreibungen.siegel_hash``-Referenz muss als
    Siegel-Datei existieren UND passen — eine zurückgerollte Chronik (älter als die DB) fällt so auf."""
    if not Path(money_db).is_file():
        return []
    conn = sqlite3.connect(money_db)
    try:
        hat = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='festschreibungen'").fetchone()
        if not hat:
            return []
        rows = conn.execute(
            "SELECT zeitraum, siegel_epoche, siegel_hash FROM festschreibungen "
            "WHERE status='versiegelt' AND siegel_hash IS NOT NULL").fetchall()
    finally:
        conn.close()
    fehlend = []
    for zeitraum, siegel_epoche, siegel_hash in rows:
        pfad = cdir / "siegel" / f"S{int(siegel_epoche):08d}.json"
        if not pfad.is_file():
            fehlend.append({"zeitraum": zeitraum, "grund": "Siegel-Datei fehlt", "siegel_hash": siegel_hash})
            continue
        if C.siegel_hash(json.loads(pfad.read_text("utf-8"))) != siegel_hash:
            fehlend.append({"zeitraum": zeitraum, "grund": "Siegel-Hash weicht ab", "siegel_hash": siegel_hash})
    return fehlend


def bericht(cdir: Path, money_db: Path | None = None) -> tuple[int, list[str]]:
    """Menschenlesbarer Prüfbericht (§5): Kette + Bestand (Epochen/Zeitraum/Siegel-Zeiten) +
    Genesis-Plausibilität + Restore-Wächter. Exit wie ``pruefe`` (0 grün · 2 Bruch)."""
    zeilen: list[str] = []
    try:
        pruefe(cdir)
    except (Bruch, C.ChronikFehler) as e:
        return EXIT_BRUCH, [f"BRUCH: {e}"]
    zeilen.append("Kette · Merkle · Siegel-Kette · Monotonie: grün")

    segs = _segment_dateien(cdir)
    siegel = _siegel_dateien(cdir)
    zeilen.append(f"Bestand: {len(segs)} Segment(e) · {len(siegel)} Siegel")
    zeiten = [siegel[e].get("zeit", "") for e in sorted(siegel)]
    if zeiten:
        zeilen.append(f"Siegel-Zeitraum: {zeiten[0]} … {zeiten[-1]}")
        if any(zeiten[k] < zeiten[k - 1] for k in range(1, len(zeiten))):
            zeilen.append("HINWEIS: nicht-monotone Siegel-Zeiten — mögliche Uhr-Anomalie (BZ-C-11)")

    gen = _lies_genesis(cdir)
    if gen:
        zeilen.append(f"Genesis: angelegt {gen.get('angelegt', '?')} · Stamm {str(gen.get('stamm_kid', '?'))[:12]}…")

    if money_db is not None:
        fehlend = _fehlende_festschreibungs_referenzen(cdir, Path(money_db))
        if fehlend:
            for f in fehlend:
                zeilen.append(f"BRUCH: Festschreibung {f['zeitraum']}: {f['grund']} ({f['siegel_hash']})")
            return EXIT_BRUCH, zeilen
        zeilen.append("Restore-Wächter: alle Festschreibungs-Siegel vorhanden und passend")
        conn = sqlite3.connect(Path(money_db))
        hat_buchungen = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='postings'").fetchone()
        conn.close()
        if hat_buchungen:
            rc, rz = salden_replay(cdir, Path(money_db))
            zeilen.extend(rz)
            if rc != EXIT_GRUEN:
                return rc, zeilen
        else:
            zeilen.append("Salden-Replay: keine Buchungsdaten in der DB (übersprungen)")
    return EXIT_GRUEN, zeilen


# ─────────────────────────────────────────────────────────────────────────────
# CLI (bizzi-pruef)
# ─────────────────────────────────────────────────────────────────────────────


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bizzi-pruef", description="DzChronik-Prüfkern (V-BIZZI-1)")
    p.add_argument("--dir", type=Path, default=None, help="chronik-Verzeichnis (Default: data/chronik)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("pruefe", help="Kette/Merkle/Siegel/Quorum/Monotonie")
    sp.add_argument("--von", type=int, default=None)
    sp.add_argument("--bis", type=int, default=None)
    sb = sub.add_parser("beweis", help="Merkle-Einschluss-Beweis für Zeile n")
    sb.add_argument("--n", type=int, required=True)
    ssr = sub.add_parser("salden-replay", help="Salden aus der Kette nachrechnen (§5)")
    ssr.add_argument("--money-db", type=Path, default=None, help="money-DB (Default: aus quellen.json)")
    ssr.add_argument("--bis-siegel", type=int, default=None, help="nur Epochen <= S beruecksichtigen")
    sub.add_parser("acl-probe", help="Stufe-1-Härtung am lebenden System (§4.5c)")
    sbe = sub.add_parser("bericht", help="menschenlesbarer Prüfbericht + Restore-Wächter")
    sbe.add_argument("--money-db", type=Path, default=None, help="money-DB für den Restore-Wächter (§4.6)")
    spr = sub.add_parser("policy-replay", help="Charta-Entscheide neu bewerten (V-BIZZI-2 §B6)")
    spr.add_argument("--host-db", type=Path, required=True, help="App-DB mit charta_entscheide/-versionen")
    ser = sub.add_parser("erreichbarkeit", help="wer-kann / tote Artikel (V-BIZZI-2 CH-14)")
    ser.add_argument("--host-db", type=Path, required=True, help="App-DB mit charta_versionen + Verzeichnis")
    args = p.parse_args(argv)
    cdir = args.dir or C.chronik_dir()

    if args.cmd == "pruefe":
        try:
            pruefe(cdir, args.von, args.bis)
        except C.ChronikFehler as e:
            print(f"FEHLER: {e}"); return EXIT_BRUCH
        except Bruch as e:
            print(f"BRUCH: {e}"); return EXIT_BRUCH
        print("grün — Kette, Merkle, Siegel-Kette und Monotonie verifiziert."); return EXIT_GRUEN
    if args.cmd == "beweis":
        try:
            b = beweis(cdir, args.n)
        except Bruch as e:
            print(f"BRUCH: {e}"); return EXIT_BRUCH
        print(json.dumps(b, ensure_ascii=False)); return EXIT_GRUEN
    if args.cmd == "acl-probe":
        rc = acl_probe(cdir)
        print("Stufe-1-ACL-Härtung aktiv (Segmente nicht beschreibbar)." if rc == EXIT_GRUEN
              else "ehrlich: Stufe-1-ACL-Härtung NICHT aktiv (Ein-Konto-Edition, §9).")
        return rc
    if args.cmd == "bericht":
        rc, zeilen = bericht(cdir, args.money_db)
        print("\n".join(zeilen))
        return rc
    if args.cmd == "salden-replay":
        money_db = args.money_db or _money_db_aus_quellen(cdir)
        if money_db is None:
            print("keine money-DB gefunden — --money-db angeben oder quellen.json pflegen")
            return EXIT_BRUCH
        rc, zeilen = salden_replay(cdir, Path(money_db), args.bis_siegel)
        print("\n".join(zeilen))
        return rc
    if args.cmd in ("policy-replay", "erreichbarkeit"):
        from . import charta_pruef
        conn = sqlite3.connect(args.host_db)
        conn.row_factory = sqlite3.Row
        try:
            if args.cmd == "policy-replay":
                rc, zeilen = charta_pruef.policy_replay(conn, cdir=cdir)
            else:
                rc, zeilen = charta_pruef.erreichbarkeit(conn)
        finally:
            conn.close()
        print("\n".join(zeilen))
        return rc
    return EXIT_GRUEN


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Prüfer-CLI: Unicode-Ausgabe auf jeder Konsole (nie Crash)
    except (AttributeError, ValueError):
        pass
    sys.exit(_cli())
