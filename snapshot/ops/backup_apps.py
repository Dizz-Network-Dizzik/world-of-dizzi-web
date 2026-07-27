"""backup_apps.py — Netzweiter Daten-Backup-Service (WAL-safe, kein Live-Stop noetig).

Vereinheitlicht das Backup ALLER Apps (vorher hatte nur der Trading Bot eines, ueber
programm/scripts/backup_kern.py — dessen bewaehrte Hot-Copy-Logik ist hier generalisiert).

Pro App:
  • alle SQLite-DBs aus  C:\\Dizzik\\data\\apps\\<id>\\   per sqlite3-Backup-API (WAL-safe, hot)
  • alle uebrigen Dateien dort (vault.key, session-secret, JSON-State) direkt kopiert
  • app-spezifische EXTRAS (z. B. TB: 154 Trade-DBs + programm/data + strategies aus dem Repo)
  -> Staging (ausserhalb OneDrive) -> ein ZIP/LZMA je App -> OUT -> Retention je App.

Zusaetzlich EINMAL pro Lauf:
  • ein Monorepo-git-Bundle (komplette Code-History aller Apps in einer Datei)
  • ein lesbarer Schnappschuss der Gesamtsystem-Karte (_netzwerk/ als ZIP — SYSTEM_KARTE.html
    direkt oeffenbar, ohne Repo/Server; der git-Bundle deckt nur die History ab)

VERSCHLUESSELUNG (B-1, 09.07.): Die App-Archive tragen Finanz- (money), HOECHST-
Gesundheits- (health) und private Notiz-Daten (memory) und landen in OneDrive (cloud-
synchronisiert) — der eine Bruch der local-first-Linie. Sie werden daher AES-256-
verschluesselt (pyzipper/WZ_AES, weiterhin echte ZIPs: von JEDEM Geraet mit 7-Zip/WinZip
+ Passphrase oeffenbar = Disaster-Recovery bleibt geraeteunabhaengig).
  • Passphrase EINMAL setzen:  backup_apps.py --set-passphrase   (nie in Repo/Chat;
    liegt DPAPI-gewickelt in data\\tools — ausserhalb OneDrive — fuer den Nightly-Task)
  • Archiv pruefen:            backup_apps.py --verify <id|zip-pfad>
  • OHNE gesetzte Passphrase laeuft das Backup UNVERSCHLUESSELT weiter (Verfuegbarkeit
    schlaegt Vertraulichkeit — ein stilles Nicht-Backup waere schlimmer) und legt eine
    laute Marker-Datei ins Backup-Ziel. Ist die Passphrase gesetzt, wird NIE still auf
    Klartext zurueckgefallen (Fehler = Lauf-Fehler, kein Klartext-Archiv).
  • git-Bundle + Systemkarte bleiben bewusst KLARTEXT: kein Personen-/Finanzinhalt
    (Secrets sind nie im Repo, Gesetz 7) und das Bundle ist der Code-DR-Pfad, der ohne
    Zusatzwissen funktionieren soll.

Aufruf (Netz-venv):
  C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe ops\\backup_apps.py
      [--only <id>] [--dry-run] [--set-passphrase] [--verify <id|zip>]
Nightly via Scheduled Task "DizzNetwork-AppBackup".
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# --- Pfade -------------------------------------------------------------------
MONO         = Path(__file__).resolve().parent.parent          # …\dizz-network
DATA_APPS    = Path(r"C:\Dizzik\data\apps")                     # je App: <id>\<id>.sqlite + State
CORE_DATA    = Path(r"C:\Dizzik\data")                          # Core: db/id/models
CHRONIK_DATA = Path(r"C:\Dizzik\data\chronik")                  # DzChronik-Aufbewahrungs-Verbund (docs/80 §4.6)
STAGING_ROOT = Path(r"C:\Dizzik\data\tools\backup_staging\net")  # ausserhalb OneDrive
OUT          = Path(r"%USERPROFILE%\OneDrive\Backups\dizz-network")
RETENTION    = 7                                                # letzte N je App
# B-1: Passphrasen-Slot fuer die Archiv-Verschluesselung — DPAPI-gewickelt (appkit.
# secrets_os, CurrentUser) und BEWUSST ausserhalb von OneDrive: der Slot ist nur der
# unbeaufsichtigte Zugriff fuer den Nightly-Task; die Wahrheit ist die Passphrase in
# Davids Kopf (Restore auf fremdem Geraet = 7-Zip + eingetippte Passphrase).
PASS_SLOT    = Path(r"C:\Dizzik\data\tools\backup_zip_pass.bin")
MARKER       = "_ACHTUNG_BACKUPS_UNVERSCHLUESSELT.txt"          # Warn-Datei im Backup-Ziel

# Live-Apps (Daten-Ordner-id). refapp = Template -> ausgelassen. leading/plans = in admin
# aufgegangen, Daten als Provenienz mitgesichert (schadet nicht). core = Hub (Sonder-Datenlayout
# in data\db / data\id, NICHT data\apps\core) -> komplett ueber EXTRAS; models (Ollama) NIE (riesig,
# re-downloadbar).
APPS = ["core", "news", "finanzen", "kommunikation", "creator", "memory", "management",
        "health", "admin", "leading", "plans", "tradingbot"]

# App-spezifische EXTRAS: (Quell-Ordner, glob, Ziel-Unterordner-im-ZIP, hot_sqlite?)
_TB = MONO / "apps" / "trading" / "programm"
EXTRAS: dict[str, list[tuple[Path, str, str, bool]]] = {
    "core": [
        (CORE_DATA / "db", "*", "core_db", True),    # dizzi.sqlite + rag.sqlite (hot); Sidecars gefiltert
        (CORE_DATA / "id", "*", "core_id", False),   # idp_key.json (SSO-/Dizzi-ID-Signing-Key!)
    ],
    "tradingbot": [
        (_TB / "engine" / "user_data", "tradesv3_*.sqlite", "trades", True),   # 154 Trade-DBs (hot)
        (_TB / "data", "*", "programm_data", True),                            # bots.json/stats.sqlite/State
        (_TB / "engine" / "user_data" / "strategies", "*.py", "strategies", False),
    ],
}


def _log(m: str) -> None:
    print(f"  {m}", flush=True)


# --- Passphrase (B-1) ----------------------------------------------------------

def _secrets_os():
    """appkit.secrets_os (DPAPI) laden — packages/ liegt im Monorepo neben ops/."""
    pkg = MONO / "packages"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    from appkit import secrets_os
    return secrets_os


def lade_passphrase() -> bytes | None:
    """Backup-Passphrase aus dem DPAPI-Slot; None = nicht gesetzt (oder fremdes
    Konto — DPAPI CurrentUser entschluesselt nur fuer den Besitzer)."""
    try:
        raw = _secrets_os().lese_geheim(PASS_SLOT)
    except Exception:
        return None
    raw = (raw or b"").strip()
    return raw or None


def set_passphrase() -> None:
    """EINMALIGE Einrichtung (interaktiv, kein Echo): Passphrase in den DPAPI-Slot.
    Nie als CLI-Argument/im Repo/Chat. Die Passphrase selbst MUSS David sich merken —
    sie ist der geraeteunabhaengige Restore-Schluessel (7-Zip + Passphrase)."""
    import getpass
    p1 = getpass.getpass("Neue Backup-Passphrase (min. 10 Zeichen): ")
    p2 = getpass.getpass("Wiederholen: ")
    if p1 != p2:
        sys.exit("[set-passphrase] Eingaben stimmen nicht ueberein — nichts geaendert.")
    if len(p1) < 10:
        sys.exit("[set-passphrase] Zu kurz (min. 10 Zeichen) — nichts geaendert.")
    _secrets_os().schreibe_geheim(PASS_SLOT, p1.encode("utf-8"))
    print(f"[set-passphrase] OK -> {PASS_SLOT} (DPAPI, CurrentUser).\n"
          "  Passphrase MERKEN: verloren = Backups unlesbar. Naechster Nightly-Lauf "
          "verschluesselt automatisch; Kontrolle: backup_apps.py --verify <app-id>.")


def _hot_sqlite(src: Path, dst: Path) -> None:
    """WAL-sicherer Hot-Copy via sqlite3-Backup-API (kein Stop noetig)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(str(src)); d = sqlite3.connect(str(dst))
    try:
        with d:
            s.backup(d, pages=256)
    finally:
        s.close(); d.close()


def _grab_dir(src: Path, staging: Path, sub: str, pattern: str = "*", hot: bool = True) -> int:
    """Sichert <pattern>-Dateien aus src nach staging/sub. SQLite -> hot, sonst copy. -> Anzahl."""
    if not src.exists():
        return 0
    dst = staging / sub
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob(pattern)):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        # WAL-Sidecars NICHT mitnehmen: der Hot-Copy der .sqlite konsolidiert den WAL bereits
        # in einen konsistenten Snapshot; die rohen -wal/-shm waeren redundant + evtl. inkonsistent.
        if f.suffix in (".sqlite-wal", ".sqlite-shm") or f.name.endswith("-journal"):
            continue
        if hot and f.suffix == ".sqlite":
            _hot_sqlite(f, dst / f.name)
        else:
            shutil.copy2(str(f), str(dst / f.name))
        n += 1
    return n


def backup_app(app_id: str, ts: str, dry: bool,
               passphrase: bytes | None = None) -> Path | None:
    staging = STAGING_ROOT / ts / app_id
    if not dry:
        staging.mkdir(parents=True, exist_ok=True)
    _log(f"[{app_id}] sichere …")

    files = 0
    # 1 — Standard: data\apps\<id>\ (DBs hot + Begleitdateien)
    src = DATA_APPS / app_id
    if dry:
        files += len([f for f in src.glob("*") if f.is_file()]) if src.exists() else 0
    else:
        files += _grab_dir(src, staging, "app_data", "*", hot=True)

    # 2 — EXTRAS (app-spezifisch, z. B. TB-Repo-Daten)
    for (esrc, pat, sub, hot) in EXTRAS.get(app_id, []):
        if dry:
            files += len(list(esrc.glob(pat))) if esrc.exists() else 0
        else:
            files += _grab_dir(esrc, staging, sub, pat, hot=hot)

    if files == 0:
        _log(f"[{app_id}] keine Daten gefunden — uebersprungen")
        if not dry and staging.exists():
            shutil.rmtree(str(staging), ignore_errors=True)
        return None

    if dry:
        _log(f"[{app_id}] (dry-run) {files} Datei(en) wuerden gesichert")
        return None

    # 3 — ZIP/LZMA -> OUT\<id>\<id>_<ts>.zip (AES-256, wenn Passphrase gesetzt — B-1).
    # Mit gesetzter Passphrase gibt es KEINEN stillen Klartext-Fallback: schlaegt die
    # Verschluesselung fehl (z. B. pyzipper fehlt), wirft das hier und der Lauf meldet
    # FEHLER statt sensible DBs doch unverschluesselt nach OneDrive zu legen.
    out_dir = OUT / app_id
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"{app_id}_{ts}.zip"
    if passphrase:
        import pyzipper                      # AES-ZIP (WZ_AES) — bleibt ein echtes ZIP
        with pyzipper.AESZipFile(str(archive), "w", compression=zipfile.ZIP_LZMA,
                                 encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(passphrase)
            for f in staging.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(staging))
    else:
        with zipfile.ZipFile(str(archive), "w", compression=zipfile.ZIP_LZMA) as zf:
            for f in staging.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(staging))
    shutil.rmtree(str(staging), ignore_errors=True)

    # 4 — Retention je App
    olds = sorted(out_dir.glob(f"{app_id}_*.zip"))
    for o in olds[:-RETENTION]:
        o.unlink(); _log(f"[{app_id}] alt entfernt: {o.name}")

    mb = archive.stat().st_size / 1_048_576
    enc = ", AES" if passphrase else ", KLARTEXT"
    _log(f"[{app_id}] OK -> {archive.name} ({mb:.1f} MB, {files} Datei(en){enc})")
    return archive


def backup_chronik(ts: str, dry: bool, passphrase: bytes | None = None) -> Path | None:
    """DzChronik-Aufbewahrungs-Verbund (V-BIZZI-1, docs/80 §4.6/§9): segmente/ · siegel/ ·
    stamm_pub · schluesselbrief · pfeffer · Schlüssel · status/quellen. Gehört zum SELBEN
    Snapshot (``ts``) wie die money-DB — **nur paarweise zurückspielen**, sonst schlägt
    ``bizzi-pruef`` an (DB älter als Kette ⇒ Fork-Stopp C-16 · Kette älter als DB ⇒ bericht-Befund).
    Die transiente ``chronist.lock`` bleibt außen vor (WAL-Sidecars gibt es hier nicht)."""
    src = CHRONIK_DATA
    if not src.exists():
        _log("[_chronik] kein data\\chronik — uebersprungen (Chronik noch nicht gezündet)")
        return None
    dateien = [f for f in sorted(src.rglob("*"))
               if f.is_file() and f.name != "chronist.lock" and f.suffix != ".lock"]
    if dry:
        _log(f"[_chronik] (dry-run) {len(dateien)} Datei(en) wuerden gesichert")
        return None
    if not dateien:
        return None
    staging = STAGING_ROOT / ts / "_chronik"
    for f in dateien:
        dst = staging / f.relative_to(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(f), str(dst))          # append-only Segmente/Siegel: einfacher File-Copy genügt
    out_dir = OUT / "_chronik"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"_chronik_{ts}.zip"
    if passphrase:
        import pyzipper                          # AES-ZIP: Schlüssel/Pfeffer NIE unverschlüsselt nach OneDrive
        with pyzipper.AESZipFile(str(archive), "w", compression=zipfile.ZIP_LZMA,
                                 encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(passphrase)
            for f in staging.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(staging))
    else:
        with zipfile.ZipFile(str(archive), "w", compression=zipfile.ZIP_LZMA) as zf:
            for f in staging.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(staging))
    shutil.rmtree(str(staging), ignore_errors=True)
    for o in sorted(out_dir.glob("_chronik_*.zip"))[:-RETENTION]:
        o.unlink(); _log(f"[_chronik] alt entfernt: {o.name}")
    mb = archive.stat().st_size / 1_048_576
    _log(f"[_chronik] OK -> {archive.name} ({mb:.1f} MB, {len(dateien)} Datei(en)"
         f"{', AES' if passphrase else ', KLARTEXT'})")
    return archive


def backup_code_bundle(ts: str, dry: bool) -> None:
    """EIN Monorepo-git-Bundle (Code-History aller Apps) -> OUT\\_code\\."""
    if dry:
        _log("[_code] (dry-run) Monorepo-git-Bundle wuerde erzeugt")
        return
    code_dir = OUT / "_code"; code_dir.mkdir(parents=True, exist_ok=True)
    bundle = code_dir / f"dizz-network_{ts}.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"],
                   cwd=str(MONO), check=True, capture_output=True)
    for o in sorted(code_dir.glob("dizz-network_*.bundle"))[:-RETENTION]:
        o.unlink(); _log(f"[_code] alt entfernt: {o.name}")
    _log(f"[_code] OK -> {bundle.name} ({bundle.stat().st_size/1_048_576:.1f} MB)")


def backup_systemkarte(ts: str, dry: bool) -> None:
    """Lesbarer Schnappschuss der Gesamtsystem-Karte (_netzwerk\\) -> OUT\\_systemkarte\\.

    Die interaktive SYSTEM_KARTE.html ist self-contained ⇒ aus dem ZIP direkt im Browser
    oeffenbar (ohne Repo/Server). Ergaenzt das git-Bundle, das nur die History sichert.
    """
    src = MONO / "_netzwerk"
    if not src.exists():
        _log("[_systemkarte] _netzwerk/ fehlt — uebersprungen"); return
    files = [f for f in src.rglob("*") if f.is_file() and f.name != ".gitkeep"]
    if dry:
        _log(f"[_systemkarte] (dry-run) {len(files)} Datei(en) aus _netzwerk/ wuerden gesichert")
        return
    if not files:
        _log("[_systemkarte] _netzwerk/ leer — uebersprungen"); return
    sk_dir = OUT / "_systemkarte"; sk_dir.mkdir(parents=True, exist_ok=True)
    archive = sk_dir / f"systemkarte_{ts}.zip"
    with zipfile.ZipFile(str(archive), "w", compression=zipfile.ZIP_LZMA) as zf:
        for f in files:
            zf.write(f, f.relative_to(src))
    for o in sorted(sk_dir.glob("systemkarte_*.zip"))[:-RETENTION]:
        o.unlink(); _log(f"[_systemkarte] alt entfernt: {o.name}")
    _log(f"[_systemkarte] OK -> {archive.name} ({archive.stat().st_size/1024:.0f} KB, {len(files)} Datei(en))")


def run(only: str | None = None, dry: bool = False) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    passphrase = lade_passphrase()
    modus = "AES-verschluesselt" if passphrase else "KLARTEXT (!)"
    print(f"[backup_apps] {ts}  ziel={OUT}  archive={modus}"
          f"{'  (DRY-RUN)' if dry else ''}", flush=True)
    if not dry:
        # Marker-Datei im Backup-Ziel: laut sichtbar (auch in OneDrive), solange ohne
        # Passphrase gesichert wird; verschwindet mit dem ersten verschluesselten Lauf.
        marker = OUT / MARKER
        if passphrase:
            marker.unlink(missing_ok=True)
        else:
            print("  WARNUNG: keine Backup-Passphrase gesetzt — App-Archive (Finanz-/"
                  "Gesundheits-/Notiz-DBs) gehen UNVERSCHLUESSELT nach OneDrive.\n"
                  "  Einmalig beheben:  backup_apps.py --set-passphrase",
                  file=sys.stderr, flush=True)
            try:
                OUT.mkdir(parents=True, exist_ok=True)
                marker.write_text(
                    f"Stand {ts}: Diese App-Backups sind UNVERSCHLUESSELT (Finanz-/"
                    "Gesundheits-/Notiz-DBs im Klartext in OneDrive).\n"
                    "Beheben (einmalig, am Rechner):\n"
                    "  C:\\Dizzik\\data\\tools\\venv\\Scripts\\python.exe "
                    "C:\\Dizzik\\code\\dizz-network\\ops\\backup_apps.py --set-passphrase\n"
                    "Danach verschluesselt der naechste Nightly-Lauf automatisch (AES-ZIP);\n"
                    "diese Datei verschwindet dann von selbst.\n", encoding="utf-8")
            except OSError:
                pass                          # Marker ist best-effort, nie Lauf-Abbruch
    targets = [only] if only else APPS
    ok = 0
    for app_id in targets:
        try:
            if backup_app(app_id, ts, dry, passphrase):
                ok += 1
        except Exception as exc:  # ein App-Fehler darf den Lauf nie abbrechen
            print(f"  [{app_id}] FEHLER: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    # DzChronik ist der Restore-Verbund der money-DB (docs/80 §4.6) ⇒ SELBER Snapshot (ts):
    # bei einem gezielten „finanzen"-Lauf muss die Chronik mit, sonst driften DB und Kette.
    if (not only) or only == "finanzen":
        try:
            backup_chronik(ts, dry, passphrase)
        except Exception as exc:
            print(f"  [_chronik] FEHLER: {exc}", file=sys.stderr, flush=True)
    if not only:
        try:
            backup_code_bundle(ts, dry)
        except Exception as exc:
            print(f"  [_code] FEHLER: {exc}", file=sys.stderr, flush=True)
        try:
            backup_systemkarte(ts, dry)
        except Exception as exc:
            print(f"  [_systemkarte] FEHLER: {exc}", file=sys.stderr, flush=True)
    print(f"[backup_apps] FERTIG ({ok} App-Backups){'  (dry-run)' if dry else ''}", flush=True)


def verify_archive(ziel: str) -> None:
    """Beweist Integritaet + Entschluesselbarkeit EINES Archivs (ohne Extraktion):
    ``ziel`` = App-id (juengstes Archiv) oder direkter Pfad zu einer .zip.
    testzip() liest + prueft jede Datei per CRC — mit AES nur mit korrekter Passphrase
    moeglich ⇒ ein 'OK' heisst: das Archiv ist vollstaendig UND wiederherstellbar."""
    p = Path(ziel)
    if p.suffix.lower() != ".zip":
        cands = sorted((OUT / ziel).glob(f"{ziel}_*.zip"))
        if not cands:
            sys.exit(f"[verify] kein Archiv fuer '{ziel}' unter {OUT / ziel}")
        p = cands[-1]
    if not p.is_file():
        sys.exit(f"[verify] Datei fehlt: {p}")
    import pyzipper
    pw = lade_passphrase()
    with pyzipper.AESZipFile(str(p)) as zf:
        infos = zf.infolist()
        enc = any(i.flag_bits & 0x1 for i in infos)
        if enc and not pw:
            sys.exit(f"[verify] {p.name} ist verschluesselt, aber keine Passphrase im "
                     "Slot — erst --set-passphrase (oder auf fremdem Geraet: 7-Zip).")
        if pw:
            zf.setpassword(pw)
        try:
            bad = zf.testzip()
        except RuntimeError as exc:           # falsche Passphrase
            sys.exit(f"[verify] Entschluesselung fehlgeschlagen ({exc}) — Passphrase "
                     "im Slot passt nicht zu diesem Archiv.")
    if bad:
        sys.exit(f"[verify] KORRUPT: erste defekte Datei = {bad} in {p.name}")
    art = "AES-verschluesselt" if enc else "KLARTEXT"
    print(f"[verify] OK — {p.name}: {len(infos)} Datei(en), {art}, alle CRCs gueltig.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="nur diese App-id sichern")
    ap.add_argument("--dry-run", action="store_true", help="nur zaehlen, nichts schreiben")
    ap.add_argument("--set-passphrase", action="store_true",
                    help="Backup-Passphrase einmalig setzen (DPAPI-Slot, interaktiv)")
    ap.add_argument("--verify", metavar="ID|ZIP",
                    help="juengstes App-Archiv (oder ZIP-Pfad) auf Integritaet + "
                         "Entschluesselbarkeit pruefen")
    a = ap.parse_args()
    try:
        if a.set_passphrase:
            set_passphrase()
        elif a.verify:
            verify_archive(a.verify)
        else:
            run(only=a.only, dry=a.dry_run)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[backup_apps] FEHLER: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
