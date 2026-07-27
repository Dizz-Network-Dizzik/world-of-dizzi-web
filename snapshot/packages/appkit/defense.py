"""Dizz Defense — das Per-App-Immunsystem (F-DEF1, Vertrag 1.4, docs/20).

Jede App verteidigt sich SELBST (standalone verkaufbar); im Verbund teilt
Dizzi die Signale (F-DEF2). Architektur-Linie aus der Recherche (docs/20 §3):
**die Regel-Engine entscheidet, die KI bewertet** — autonome Gegenmaßnahmen
kommen aus einem deterministischen, testbaren Stufenwerk; die LLM-Triage
(F-DEF2-Hook) erklärt/korreliert, löst aber nie selbst scharfe Aktionen aus.

Vier Schichten:
1. SENSORIK   — ASGI-Middleware sieht jeden Request (Client/Pfad/Methode/
                Status) VOR der App (auch Local-Guard-Abweisungen, H1).
2. DETEKTION  — Fenster-Zähler je Client (Brute-Force, Pfad-Scan, Raten,
                Guard-Verstöße) + Köder-Pfade (RASP-Prinzip: kein legitimer
                Client ruft /wp-login.php) + Injektions-Signaturen +
                statistische Last-Basislinie (EWMA/EW-Varianz, stdlib-pur).
3. REAKTION   — Eskalations-Stufenwerk S0–S5 (docs/18 §7) mit AUTONOMIE-
                POLITIK (Nutzer-Entscheid 12.06.): S1 drosseln / S2 befristet
                sperren / S3 Step-up-Pflicht laufen AUTONOM (reversibel, TTL,
                exponentiell bei Wiederholungstätern); S4 Lockdown / S5
                Not-Aus verlangen Freigabe (HITL via K4-Aktionen) — nur der
                „panik"-Modus darf S4 selbst schalten, S5 nie.
4. GEDÄCHTNIS — Vorfalls-Journal + Maßnahmen persistiert (überleben Neustart),
                Audit, best-effort Event-Push an Dizzi (Glocke/L4).

EHRLICHE GRENZEN (docs/20 §1e): volumetrische DDoS stoppt nur der Edge-Pfad
(Cloudflare/CrowdSec vor dem Server) — diese Schicht beherrscht den
ANWENDUNGS-Missbrauch (L7) autonom. LOKAL-SCHONUNG: Loopback-Clients werden
autonom höchstens gedrosselt (S1), nie gesperrt — sonst sperrte ein lokaler
Fehlalarm den einzigen Nutzer aus (Sperren von Loopback nur manuell/HITL).
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from .auth import DEFAULT_USER_ID as DEFAULT_USER
from .db import Database, new_id, now_iso

# Stufenwerk (docs/18 §7) — Namen sind Teil der API/UI.
STUFEN = {0: "beobachten", 1: "drosseln", 2: "sperren",
          3: "stepup_pflicht", 4: "lockdown", 5: "notaus"}
GLOBAL_CLIENT = "*"          # Träger für Lockdown/Not-Aus (gilt für alle)
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "testclient", ""})

# Köder-Pfade: kein legitimer Client einer Dizz-App ruft diese je auf —
# ein Treffer ist ein nahezu falsch-positiv-freier Scanner-Beweis (RASP).
DECOY_PATHS = frozenset({
    "/wp-login.php", "/wp-admin", "/xmlrpc.php", "/.env", "/.git/config",
    "/admin.php", "/phpinfo.php", "/config.php", "/backup.zip", "/shell.php",
    "/.aws/credentials", "/etc/passwd", "/actuator/env", "/boaform/admin/formLogin",
})

# Injektions-Signaturen (Pfad+Query, lowercase): bewusst KONSERVATIV —
# lieber wenige, harte Muster als Falsch-Positive auf legitime Daten.
_SIGNATUREN = [
    ("sql_injection", re.compile(r"union\s+select|'\s*or\s+1\s*=\s*1|;\s*drop\s+table")),
    ("pfad_traversal", re.compile(r"\.\./\.\.|%2e%2e%2f|etc/passwd|windows\\system32")),
    ("xss", re.compile(r"<script[\s>]|javascript:\s*[a-z]|onerror\s*=")),
    ("nullbyte", re.compile(r"%00")),
]


@dataclass(frozen=True)
class DefenseConfig:
    """Schwellen der Regel-Engine (pro Minute, je Client) + Politik."""
    brute_n: int = 6            # 401/403-Antworten ⇒ Brute-Force
    scan_n: int = 15            # 404-Antworten ⇒ Pfad-Scan
    rate_n: int = 240           # Requests ⇒ Raten-Missbrauch (S1)
    guard_n: int = 3            # Local-Guard-Abweisungen (400/403) ⇒ Angriff
    drossel_budget: int = 30    # erlaubte Requests/min unter S1
    s1_ttl_s: float = 300.0     # Drossel-Dauer
    s2_ttl_s: float = 900.0     # Sperr-Dauer (Basis; ×4 je Wiederholung, Deckel 24 h)
    s2_ttl_max_s: float = 86400.0
    wiederholer_fenster_s: float = 6 * 3600.0
    sturm_clients: int = 10     # ≥ n gesperrte Clients in 5 min ⇒ Lockdown-Lage
    sturm_fenster_s: float = 300.0
    basis_z: float = 8.0        # Robust-Z der Last-Basislinie ⇒ Lastspitzen-Vorfall
    basis_min: int = 50         # Mindest-Requests/Takt, bevor z überhaupt zählt
    lokal_schonung: bool = True # Loopback autonom max. S1 (s. Modul-Docstring)


@dataclass
class _ClientFenster:
    """Minuten-Fenster-Zähler eines Clients (aktuelle + vorige Minute —
    konstanter Speicher, das Fenster „gleitet" minutengenau)."""
    minute: int = 0
    reqs: int = 0
    auth: int = 0
    nf: int = 0
    guard: int = 0
    prev: dict[str, int] = field(default_factory=dict)
    zuletzt: float = 0.0

    def rolle(self, minute: int) -> None:
        if minute == self.minute:
            return
        self.prev = ({"reqs": self.reqs, "auth": self.auth,
                      "nf": self.nf, "guard": self.guard}
                     if minute == self.minute + 1 else {})
        self.minute, self.reqs, self.auth, self.nf, self.guard = minute, 0, 0, 0, 0

    def summe(self, art: str) -> int:
        return getattr(self, art) + self.prev.get(art, 0)


def signatur_befund(pfad_query: str) -> str | None:
    """Pure: erster Signatur-Treffer in Pfad+Query (lowercase) oder None."""
    low = pfad_query.lower()
    for name, rx in _SIGNATUREN:
        if rx.search(low):
            return name
    return None


def ist_koeder(pfad: str) -> bool:
    """Pure: Köder-Pfad getroffen? (exakt oder als Präfix, z. B. /wp-admin/x)"""
    low = pfad.lower().rstrip("/") or "/"
    return low in DECOY_PATHS or any(low.startswith(d + "/") for d in DECOY_PATHS)


def ermittle_client(peer: str, xff: str | None, hops: int) -> str:
    """Pure: effektive Client-Adresse für die Sensorik (F4).

    ``hops`` = Zahl KONFIGURIERTER vertrauenswürdiger Reverse-Proxy-Hops
    (Setting ``defense_trusted_proxy_hops``, Default 0).
    - hops<=0 ⇒ X-Forwarded-For wird IGNORIERT (fail-closed auf den TCP-Peer);
      der linkeste XFF-Eintrag ist Angreifer-Text und war nie ein Beweis.
    - hops>0 UND der TCP-Peer ist Loopback (= der lokale Proxy, Server-Gang)
      ⇒ es zählt der ``hops``-te Eintrag VON RECHTS — den hat der erste
      vertraute Proxy angehängt; alles links davon bleibt fälschbar.
    - Ein aus XFF gewonnener Wert erbt NIE Loopback-Privilegien (Lokal-
      Schonung, Lockdown-Durchlass, Cockpit-Lese-Garantie gelten nur dem
      echten TCP-Peer): sieht er wie Loopback aus, wird er als
      ``xff:<wert>`` geführt — sperrbar wie jeder externe Client."""
    peer = (peer or "").strip()
    if hops <= 0 or not xff or peer not in LOOPBACK:
        return peer
    teile = [t.strip() for t in xff.split(",") if t.strip()]
    if not teile:
        return peer
    # MITTEL-Fix: bei mehr konfigurierten Hops als tatsächlichen XFF-Einträgen (Unterlauf)
    # NICHT auf teile[0] (linkester = frei fälschbarer Angreifer-Text) klemmen, sondern
    # fail-closed auf teile[-1] (rechtester = vom nächsten vertrauten Proxy angehängt, am
    # wenigsten fälschbar). Verhindert, dass ein Angreifer mit zu wenigen XFF-Einträgen
    # seinen Wunsch-Client unterschiebt.
    idx = len(teile) - hops
    echt = teile[idx] if idx >= 0 else teile[-1]
    return f"xff:{echt}" if echt in LOOPBACK else echt


class Defense:
    """Zustand + Stufenwerk einer App. Threadsicher (ein Lock, kurze Pfade);
    Maßnahmen sind DB-persistiert und überleben Neustarts. ``clock``
    injizierbar (netzfreie Tests)."""

    def __init__(self, db: Database, app_id: str,
                 config: DefenseConfig | None = None,
                 clock: Callable[[], float] = time.time,
                 event_hook: Callable[[str, str, dict], None] | None = None,
                 propose_hook: Callable[[str, dict], None] | None = None) -> None:
        self.db = db
        self.app_id = app_id
        self.cfg = config or DefenseConfig()
        self.clock = clock
        self.event_hook = event_hook          # F-DEF2: Glocke/Verbund (best-effort)
        self.propose_hook = propose_hook      # K4: S4/S5 als HITL-Vorschlag
        self.triage_hook: Callable[[dict[str, Any]], None] | None = None  # LLM-Triage
        self._lock = threading.Lock()
        self._fenster: dict[str, _ClientFenster] = {}
        self._massnahmen: dict[str, dict[str, Any]] = {}   # client -> aktive Maßnahme
        self._sperr_historie: dict[str, list[float]] = {}  # client -> Sperr-Zeitpunkte
        self._sturm: list[float] = []                      # Zeitpunkte neuer Sperren
        self._sturm_gemeldet = 0.0
        self._vorfall_dedupe: dict[tuple[str, str], float] = {}
        # Basislinie: EWMA + EW-Varianz über 10-s-Takte (Welford-artig, stdlib).
        self._takt = 0
        self._takt_n = 0
        self._ewma = 0.0
        self._ewvar = 0.0
        self._basis_takte = 0
        db.get_conn().executescript(DEFENSE_SCHEMA)
        self._lade_massnahmen()

    # ------------------------------------------------------------- Persistenz
    def _lade_massnahmen(self) -> None:
        rows = self.db.get_conn().execute(
            "SELECT id, client, stufe, grund, bis FROM defense_massnahmen "
            "WHERE status='aktiv' AND deleted_at IS NULL").fetchall()
        now = self.clock()
        for r in rows:
            if 0 < r["bis"] <= now:
                self._beende_massnahme(r["id"], "abgelaufen")
                continue
            self._massnahmen[r["client"]] = dict(
                id=r["id"], stufe=r["stufe"], grund=r["grund"], bis=r["bis"])

    def _beende_massnahme(self, mid: str, status: str) -> None:
        conn = self.db.get_conn()
        conn.execute("UPDATE defense_massnahmen SET status=?, updated_at=? WHERE id=?",
                     (status, now_iso(), mid))
        conn.commit()

    def _setze_massnahme(self, client: str, stufe: int, grund: str,
                         ttl_s: float, quelle: str) -> dict[str, Any]:
        """Aktiviert/erhöht eine Maßnahme (nie absenken durch Automatik)."""
        alt = self._massnahmen.get(client)
        if alt and alt["stufe"] >= stufe and (alt["bis"] <= 0 or alt["bis"] > self.clock()):
            return alt
        if alt:
            self._beende_massnahme(alt["id"], "ersetzt")
        bis = self.clock() + ttl_s if ttl_s > 0 else 0.0
        mid = new_id()
        ts = now_iso()
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO defense_massnahmen (id, user_id, client, stufe, grund, bis,"
            " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, DEFAULT_USER, client, stufe, grund, bis, "aktiv", ts, ts))
        conn.commit()
        m = dict(id=mid, stufe=stufe, grund=grund, bis=bis)
        self._massnahmen[client] = m
        self.db.audit(DEFAULT_USER, "system", "defense_massnahme",
                      {"client": client, "stufe": STUFEN[stufe], "grund": grund,
                       "ttl_s": ttl_s, "quelle": quelle})
        if self.event_hook:
            try:
                self.event_hook("warn", f"Dizz Defense: {STUFEN[stufe]} für {client}",
                                {"grund": grund, "stufe": stufe, "ttl_s": ttl_s})
            except Exception:
                pass
        return m

    def aufheben(self, massnahme_id: str) -> bool:
        """Nutzer-Aufhebung (Cockpit/API): beendet die Maßnahme sofort."""
        with self._lock:
            for client, m in list(self._massnahmen.items()):
                if m["id"] == massnahme_id:
                    self._beende_massnahme(massnahme_id, "aufgehoben")
                    del self._massnahmen[client]
                    self.db.audit(DEFAULT_USER, "user", "defense_aufgehoben",
                                  {"client": client, "stufe": STUFEN[m["stufe"]]})
                    return True
        return False

    def _vorfall(self, client: str, art: str, stufe: int,
                 detail: dict[str, Any]) -> None:
        """Journal-Eintrag mit 60-s-Dedupe je (client, art) — kein Fluten."""
        now = self.clock()
        key = (client, art)
        if now - self._vorfall_dedupe.get(key, 0.0) < 60.0:
            return
        self._vorfall_dedupe[key] = now
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO defense_vorfaelle (id, user_id, client, art, detail,"
            " stufe, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_id(), DEFAULT_USER, client, art,
             json.dumps(detail, ensure_ascii=False), stufe, now_iso()))
        conn.commit()

    # ---------------------------------------------------------------- Gate
    def gate(self, client: str, methode: str, pfad: str) -> tuple[int, str] | None:
        """VOR der App: aktive Maßnahmen durchsetzen.
        None = durchlassen, sonst (HTTP-Status, Fehlertext).
        Loopback behält IMMER lesenden Zugriff auf das Defense-Cockpit —
        man darf sich nie aus der eigenen Verteidigung aussperren."""
        with self._lock:
            now = self.clock()
            # HOCH-Fix (P0): Loopback behält IMMER vollen Zugriff (ALLE Methoden) aufs
            # Defense-Cockpit — sonst sperrt der Not-Aus (S5) den eigenen Schreibpfad zum
            # Aufheben aus (POST .../lockdown?an=false / .../massnahmen/{id}/aufheben → 503),
            # überlebt den Neustart und ließe sich nur per DB-Chirurgie lösen. Exakte Grenze
            # (== oder '/'-Präfix) statt startswith, damit '/api/defense-x' NICHT mitmatcht.
            if client in LOOPBACK and (pfad == "/api/defense"
                                       or pfad.startswith("/api/defense/")):
                return None
            g = self._massnahmen.get(GLOBAL_CLIENT)
            if g:
                if 0 < g["bis"] <= now:
                    self._beende_massnahme(g["id"], "abgelaufen")
                    self._massnahmen.pop(GLOBAL_CLIENT, None)
                elif g["stufe"] >= 5:
                    return 503, "Dizz Defense: Not-Aus aktiv"
                elif g["stufe"] == 4 and client not in LOOPBACK:
                    return 503, "Dizz Defense: Lockdown — nur lokale Bedienung"
            m = self._massnahmen.get(client)
            if not m:
                return None
            if 0 < m["bis"] <= now:
                self._beende_massnahme(m["id"], "abgelaufen")
                del self._massnahmen[client]
                return None
            if m["stufe"] >= 2:
                return 403, f"Dizz Defense: Client gesperrt ({m['grund']})"
            if m["stufe"] == 1 and client not in LOOPBACK:
                # Lokale Poller (Desktop-Monitor, Core-Health-Watch/-Panels, Admin-
                # Aggregator) sind vertrauenswürdig und werden NIE gedrosselt — sonst
                # flackert das Netzwerk-Cockpit (429), obwohl die App läuft. Externe
                # Clients bleiben bei S1 unverändert gedrosselt. (Loopback wird autonom
                # ohnehin nie über S1 eskaliert; jetzt auch innerhalb S1 nicht gedrosselt.)
                f = self._fenster.get(client)
                if f and f.summe("reqs") >= self.cfg.drossel_budget:
                    return 429, "Dizz Defense: gedrosselt — Tempo reduzieren"
        return None

    # ------------------------------------------------------------ Beobachtung
    def beobachte(self, client: str, methode: str, pfad: str, query: str,
                  status: int, autonomie: str = "standard") -> list[str]:
        """NACH der Antwort: Zähler + Regel-Engine + Eskalation.
        Liefert die Befund-Namen (für Tests/Triage)."""
        cfg = self.cfg
        with self._lock:
            now = self.clock()
            minute = int(now // 60)
            f = self._fenster.get(client)
            if f is None:
                if len(self._fenster) > 5000:  # Speicher-Deckel: Inaktive raus
                    grenze = now - 600
                    self._fenster = {c: w for c, w in self._fenster.items()
                                     if w.zuletzt > grenze}
                    # Gleiche Hygiene für die Neben-Gedächtnisse (Review 12.06.:
                    # wuchsen sonst unbegrenzt mit der Client-Vielfalt):
                    self._vorfall_dedupe = {
                        k: t for k, t in self._vorfall_dedupe.items()
                        if now - t < 3600}
                    fenster_s = self.cfg.wiederholer_fenster_s
                    self._sperr_historie = {
                        c: [t for t in ts if now - t < fenster_s]
                        for c, ts in self._sperr_historie.items()
                        if any(now - t < fenster_s for t in ts)}
                f = self._fenster[client] = _ClientFenster(minute=minute)
            f.rolle(minute)
            f.zuletzt = now
            f.reqs += 1
            if status in (401, 403):
                f.auth += 1
            if status == 404:
                f.nf += 1
            if status == 400:
                f.guard += 1  # Local-Guard weist Rebinding mit 400 ab (H1)
            self._basislinie(now)

            befunde: list[tuple[str, int]] = []
            if ist_koeder(pfad):
                befunde.append(("koeder", 2))
            sig = signatur_befund(f"{pfad}?{query}" if query else pfad)
            if sig:
                befunde.append((sig, 2))
            if f.summe("auth") >= cfg.brute_n:
                befunde.append(("brute_force", 2))
            if f.summe("nf") >= cfg.scan_n:
                befunde.append(("pfad_scan", 2))
            if f.summe("guard") >= cfg.guard_n:
                befunde.append(("guard_verstoesse", 2))
            if f.summe("reqs") >= cfg.rate_n:
                befunde.append(("raten_missbrauch", 1))
            if not befunde:
                return []

            ziel = max(s for _, s in befunde)
            namen = [n for n, _ in befunde]
            grund = "+".join(sorted(set(namen)))
            if autonomie == "beobachten":
                self._vorfall(client, grund, 0, {"befunde": namen, "pfad": pfad,
                                                 "nur_beobachtet": True})
                return namen
            if ziel >= 2 and cfg.lokal_schonung and client in LOOPBACK:
                ziel = 1  # Lokal-Schonung: nie autonom den eigenen Nutzer sperren
            if ziel == 1:
                self._setze_massnahme(client, 1, grund, cfg.s1_ttl_s, "auto")
            elif ziel >= 2:
                ttl = self._sperr_ttl(client, now)
                self._setze_massnahme(client, 2, grund, ttl, "auto")
                self._sturm.append(now)
            self._vorfall(client, grund, min(ziel, 2),
                          {"befunde": namen, "pfad": pfad, "status": status})
            self._sturm_pruefen(now, autonomie)
            if ziel >= 2 and self.triage_hook:
                try:  # Bewertung läuft nebenher — blockiert nie die Abwehr
                    self.triage_hook({"client": client, "art": grund,
                                      "befunde": namen, "pfad": pfad,
                                      "status": status})
                except Exception:
                    pass
            return namen

    def _sperr_ttl(self, client: str, now: float) -> float:
        """Wiederholungstäter exponentiell länger: Basis ×4 je Sperre in 6 h."""
        hist = [t for t in self._sperr_historie.get(client, [])
                if now - t < self.cfg.wiederholer_fenster_s]
        hist.append(now)
        self._sperr_historie[client] = hist
        return min(self.cfg.s2_ttl_s * (4 ** (len(hist) - 1)), self.cfg.s2_ttl_max_s)

    def _sturm_pruefen(self, now: float, autonomie: str) -> None:
        """Angriffs-STURM (viele Sperren in kurzer Zeit) ⇒ Lockdown-Lage:
        'panik' schaltet S4 selbst (befristet 30 min), sonst HITL-Vorschlag
        + Glocke (höchstens alle 10 min)."""
        self._sturm = [t for t in self._sturm if now - t < self.cfg.sturm_fenster_s]
        if len(self._sturm) < self.cfg.sturm_clients:
            return
        if autonomie == "panik":
            self._setze_massnahme(GLOBAL_CLIENT, 4, "angriffs_sturm", 1800.0, "auto_panik")
            return
        if now - self._sturm_gemeldet < 600.0:
            return
        self._sturm_gemeldet = now
        self._vorfall(GLOBAL_CLIENT, "angriffs_sturm", 2,
                      {"sperren_5min": len(self._sturm), "empfehlung": "lockdown"})
        if self.propose_hook:
            try:
                self.propose_hook("defense_lockdown",
                                  {"grund": "angriffs_sturm",
                                   "sperren_5min": len(self._sturm)})
            except Exception:
                pass

    # ------------------------------------------------------------- Basislinie
    def _basislinie(self, now: float, alpha: float = 0.1) -> None:
        """EWMA + EW-Varianz der Requests je 10-s-Takt; Robust-Z meldet
        Lastspitzen als Vorfall (NUR Signal — globale Auto-Drosselung träfe
        den eigenen Nutzer; per-Client-Maßnahmen treffen die Verursacher)."""
        takt = int(now // 10)
        if takt != self._takt:
            if self._basis_takte > 0:
                n = float(self._takt_n)
                d = n - self._ewma
                self._ewma += alpha * d
                self._ewvar = (1 - alpha) * (self._ewvar + alpha * d * d)
                z = ((n - self._ewma) / math.sqrt(self._ewvar)
                     if self._ewvar > 1e-9 else 0.0)
                if (self._basis_takte > 30 and n >= self.cfg.basis_min
                        and z >= self.cfg.basis_z):
                    self._vorfall(GLOBAL_CLIENT, "lastspitze", 0,
                                  {"takt_requests": int(n), "z": round(z, 1),
                                   "ewma": round(self._ewma, 1)})
            self._takt = takt
            self._takt_n = 0
            self._basis_takte += 1
        self._takt_n += 1

    # ----------------------------------------------------------------- Status
    def status(self) -> dict[str, Any]:
        with self._lock:
            now = self.clock()
            aktive = [
                {"id": m["id"], "client": c, "stufe": m["stufe"],
                 "stufe_name": STUFEN[m["stufe"]], "grund": m["grund"],
                 "rest_s": max(0, int(m["bis"] - now)) if m["bis"] > 0 else None}
                for c, m in self._massnahmen.items()
                if m["bis"] <= 0 or m["bis"] > now]
            g = self._massnahmen.get(GLOBAL_CLIENT, {"stufe": 0})
            return {
                "name": "Dizz Defense", "app": self.app_id,
                "stufenwerk": STUFEN,
                "lockdown": g["stufe"] == 4, "notaus": g["stufe"] >= 5,
                "massnahmen": aktive,
                "clients_beobachtet": len(self._fenster),
                "basislinie": {"ewma_pro_10s": round(self._ewma, 2),
                               "takte": self._basis_takte},
            }

    def vorfaelle(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.get_conn().execute(
            "SELECT client, art, detail, stufe, created_at FROM defense_vorfaelle "
            "WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
            (min(limit, 200),)).fetchall()
        return [{"client": r["client"], "art": r["art"],
                 "detail": json.loads(r["detail"]), "stufe": r["stufe"],
                 "created_at": r["created_at"]} for r in rows]

    # --------------------------------------------- manuelle/HITL-Schaltungen
    def lockdown(self, an: bool, grund: str = "manuell") -> dict[str, Any] | None:
        with self._lock:
            if an:
                return self._setze_massnahme(GLOBAL_CLIENT, 4, grund, 0.0, "hitl")
            m = self._massnahmen.pop(GLOBAL_CLIENT, None)
            if m:
                self._beende_massnahme(m["id"], "aufgehoben")
            return m

    def notaus(self, grund: str = "manuell") -> dict[str, Any]:
        with self._lock:
            return self._setze_massnahme(GLOBAL_CLIENT, 5, grund, 0.0, "hitl")

    # ------------------------------------------ Verbund-Immunität (F-DEF2)
    def verbund_sperren(self, sperren: list[dict[str, Any]],
                        ttl_default: float = 900.0) -> int:
        """Übernimmt geteilte Sperren aus dem Verbund (Dizzi = SOC-Dach):
        ein Angriff auf EINE App immunisiert alle. Echo-Schutz: übernommene
        Sperren tragen das Präfix ``verbund:`` im Grund — der Sammler oben
        lässt sie aus, sonst hielte sich der Verbund selbst ewig am Leben.
        Loopback wird nie übernommen (Lokal-Schonung gilt verbund-weit)."""
        n = 0
        with self._lock:
            for s in sperren:
                client = str(s.get("client", ""))
                if not client or client in LOOPBACK or client == GLOBAL_CLIENT:
                    continue
                grund = str(s.get("grund", "unbekannt"))
                if grund.startswith("verbund:"):
                    continue
                ttl = float(s.get("ttl_s") or ttl_default)
                self._setze_massnahme(client, 2, f"verbund:{grund}",
                                      ttl, "verbund")
                n += 1
        return n


# ====================================================================== Einbau
# install_defense(): EIN Aufruf rüstet jede FastAPI-App aus (create_app macht
# das automatisch; Bestands-Apps wie Dizz Trading rufen es in ihrem
# Vertrags-Modul). Reihenfolge: NACH install_local_guard registrieren —
# Starlette macht die zuletzt registrierte Middleware zur ÄUSSERSTEN, damit
# sieht die Sensorik auch die Guard-Abweisungen (Rebinding-Versuche zählen!).

def defense_settings() -> list[Any]:
    """K2-Settings von Dizz Defense (Kategorie Sicherheit)."""
    from .settings_core import SettingDef
    return [
        SettingDef(key="defense_aktiv", category="sicherheit", type="bool",
                   default=True, label="Dizz Defense aktiv",
                   description="Per-App-Immunsystem: erkennt Angriffe und wehrt sie gestuft ab (docs/20)"),
        SettingDef(key="defense_autonomie", category="sicherheit", type="choice",
                   choices=["beobachten", "standard", "panik"], default="standard",
                   label="Defense-Autonomie",
                   description="beobachten = nur Journal · standard = S1–S3 autonom, Lockdown/Not-Aus mit Freigabe · panik = auch Lockdown autonom"),
        SettingDef(key="defense_trusted_proxy_hops", category="sicherheit",
                   type="int", default=0, min=0, max=5,
                   label="Vertraute Proxy-Hops",
                   description="0 = X-Forwarded-For ignorieren (Direktbetrieb, fail-closed auf den TCP-Peer). Hinter n EIGENEN Reverse-Proxys auf n setzen — dann zählt der n-te XFF-Eintrag von rechts als Client; XFF-Werte erben nie Loopback-Rechte"),
        SettingDef(key="defense_triage_aktiv", category="ki", type="bool",
                   default=True, label="KI-Triage von Vorfällen",
                   description="Lokales Modell (Ollama) stuft Vorfälle ein und erklärt sie in Klartext — entscheidet NIE selbst über Maßnahmen"),
    ]


# ------------------------------------------------------ LLM-Triage (F-DEF2)
# Forschungs-Lehre (docs/20 §1c): die Regel-Engine ENTSCHEIDET, das Modell
# BEWERTET/ERKLÄRT. Die Triage schreibt einen Klartext-Bericht ins Journal —
# sie kann Maßnahmen weder setzen noch aufheben. Ollama-Gotcha: ``format``
# MUSS ein JSON-SCHEMA sein (bloßes "json" bricht bei großen Eingaben aus).

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "einstufung": {"type": "string",
                       "enum": ["harmlos", "verdaechtig", "angriff"]},
        "erklaerung": {"type": "string"},
        "empfehlung": {"type": "string"},
    },
    "required": ["einstufung", "erklaerung", "empfehlung"],
}


def llm_triage(defense: Defense, vorfall: dict[str, Any], *,
               url: str = "http://127.0.0.1:11434", model: str = "qwen3:4b",
               http_post: Callable[..., Any] | None = None) -> dict[str, Any] | None:
    """Bewertet EINEN Vorfall lokal (Ollama). Ehrlicher Fallback: ohne
    erreichbares Modell gibt es KEINE Triage (None) statt erfundener Inhalte.
    Erfolg ⇒ Journal-Eintrag ``ki_triage`` (Stufe 0, reine Bewertung)."""
    prompt = (
        "Du bist die Sicherheits-Triage einer lokalen App (Dizz Defense). "
        "Bewerte NUR den folgenden Vorfall. Antworte deutsch, knapp, ehrlich.\n"
        f"App: {defense.app_id}\nVorfall: {json.dumps(vorfall, ensure_ascii=False)}")
    try:
        if http_post is None:
            import httpx
            http_post = lambda u, json, timeout: httpx.post(u, json=json, timeout=timeout)  # noqa: E731
        r = http_post(f"{url}/api/chat", json={
            "model": model, "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "format": TRIAGE_SCHEMA,                      # JSON-SCHEMA, nie "json"!
            "options": {"temperature": 0.1},
        }, timeout=60.0)
        data = r.json()
        out = json.loads(data["message"]["content"])
        if out.get("einstufung") not in ("harmlos", "verdaechtig", "angriff"):
            return None
    except Exception:
        return None
    detail = {"bezug": {"client": vorfall.get("client"), "art": vorfall.get("art")},
              **{k: out[k] for k in ("einstufung", "erklaerung", "empfehlung")}}
    conn = defense.db.get_conn()
    conn.execute(
        "INSERT INTO defense_vorfaelle (id, user_id, client, art, detail, stufe,"
        " created_at) VALUES (?,?,?,?,?,?,?)",
        (new_id(), DEFAULT_USER, str(vorfall.get("client", "?")), "ki_triage",
         json.dumps(detail, ensure_ascii=False), 0, now_iso()))
    conn.commit()
    return detail


# -------------------------------------------- KI-Selbstschutz (F-DEF2)
# Prompt-Injection-Prüfer vor Agenten-/LLM-Aufrufen (PromptArmor-Muster,
# docs/20 §1d): Heuristik-Stufe hier (stdlib, 0 ms); die optionale
# LLM-Wächter-Stufe ist ein O-Fill-Slot. Apps rufen pruefe_prompt() auf
# NUTZER-/FREMD-Text, BEVOR er in einen LLM-Kontext wandert.
_PROMPT_MUSTER = [
    ("anweisungs_override", re.compile(
        r"ignor(e|iere)\s+(all\s+|alle\s+)?(previous|prior|vorherigen?|bisherigen?)\s+"
        r"(instructions|anweisungen)|disregard\s+(all\s+)?(previous|above)", re.I)),
    ("rollen_uebernahme", re.compile(
        r"\b(you\s+are\s+now|du\s+bist\s+(ab\s+)?jetzt)\b|\bdeveloper\s+mode\b|\bjailbreak\b", re.I)),
    ("system_prompt_zugriff", re.compile(
        r"(reveal|show|verrate|zeige?)\s+(your|dein[e]?)\s+"
        r"(system\s*prompt|instructions|anweisungen)|<\s*/?\s*system\s*>", re.I)),
    ("werkzeug_missbrauch", re.compile(
        r"(rufe?|call)\s+(das\s+)?(tool|werkzeug|function)\s+\w+\s+(mit|with)\b.*"
        r"(passwort|password|token|secret|api[_-]?key)", re.I | re.S)),
]


# Optionaler ML-Klassifikator (F-DEF2 O-Fill-Slot, docs/50 P4.2): die zweite Stufe
# nach der Heuristik. INJIZIERBAR wie embed_fn/rerank_fn (Memory-RAG) — Signatur
# ``(text) -> float`` = Injektions-Wahrscheinlichkeit 0..1. Prod hängt z. B. den
# ``Llama-Prompt-Guard-2-86M``-ONNX (gravitee-io/Llama-Prompt-Guard-2-86M-onnx) via
# ``lade_prompt_guard`` ein; FEHLT er oder wirft er ⇒ **fail-OPEN** (nur Heuristik,
# nie ein Block/Crash — Defense darf den Chat nie brechen).
PromptGuardFn = Callable[[str], float]
PROMPT_GUARD_SCHWELLE = 0.5
_prompt_guard_fn: PromptGuardFn | None = None


def set_prompt_guard(fn: PromptGuardFn | None) -> None:
    """Injiziert (oder entfernt mit ``None``) den ML-Prompt-Injection-Klassifikator
    für ``pruefe_prompt``. Idempotent; threadsicher genug (einfache Referenz)."""
    global _prompt_guard_fn
    _prompt_guard_fn = fn


def pruefe_prompt(text: str) -> str | None:
    """Erster Injektions-Befund in Fremd-/Nutzertext, sonst ``None``.

    Zwei Stufen: 1) **Heuristik** (Regex, stdlib, 0 ms) — deckt die bekannten
    Override-/Jailbreak-Muster ab. 2) **ML-Klassifikator** (falls via
    ``set_prompt_guard`` injiziert) für paraphrasierte/unbekannte Angriffe ⇒ Befund
    ``"klassifikator"`` ab ``PROMPT_GUARD_SCHWELLE``. **Fail-OPEN:** ohne Hook oder
    bei Hook-Fehler bleibt es bei der Heuristik (nie Block/Crash)."""
    for name, rx in _PROMPT_MUSTER:
        if rx.search(text or ""):
            return name
    fn = _prompt_guard_fn
    if fn is not None and (text or "").strip():
        try:
            score = float(fn(text))
        except Exception:
            return None                       # fail-open: Klassifikator-Fehler ⇒ kein Block
        if score >= PROMPT_GUARD_SCHWELLE:
            return "klassifikator"
    return None


def lade_prompt_guard(modell_pfad: Any, *, schwelle: float = PROMPT_GUARD_SCHWELLE
                      ) -> PromptGuardFn | None:
    """Best-effort-Factory für den ONNX-Prompt-Injection-Klassifikator
    (Llama-Prompt-Guard-2-86M, ``gravitee-io/Llama-Prompt-Guard-2-86M-onnx``).

    Lädt ``onnxruntime`` + Tokenizer + ``model.onnx`` aus ``modell_pfad`` und gibt
    eine ``guard(text)->score``-Funktion zurück — ODER ``None``, wenn etwas fehlt
    (onnxruntime/tokenizers nicht installiert, Modell-Dateien nicht da). **Wirft
    NIE** (Defense fail-OPEN). Verdrahtung über ``set_prompt_guard(lade_prompt_guard(...))``
    ist ein gegateter Prod-Schritt (Modell-Download nötig).

    HINWEIS: Eingabe-Namen + Label-Index (binär: 0=benign, 1=injection) sind beim
    gegateten Anschluss EINMAL gegen das konkrete Modell zu verifizieren — die
    Inferenz unten folgt dem Standard-Sequenzklassifikator (Logits→Softmax)."""
    try:
        from pathlib import Path

        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        p = Path(modell_pfad)
        sess = ort.InferenceSession(str(p / "model.onnx"),
                                    providers=["CPUExecutionProvider"])
        tok = Tokenizer.from_file(str(p / "tokenizer.json"))
        eingang = {i.name for i in sess.get_inputs()}

        def _guard(text: str) -> float:
            enc = tok.encode(text or "")
            ids = np.array([enc.ids], dtype=np.int64)
            feed: dict[str, Any] = {"input_ids": ids}
            if "attention_mask" in eingang:
                feed["attention_mask"] = np.array([enc.attention_mask], dtype=np.int64)
            logits = sess.run(None, feed)[0][0]
            ex = np.exp(logits - np.max(logits))        # numerisch stabiles Softmax
            probs = ex / ex.sum()
            return float(probs[-1])                      # letzte Klasse = „injection"

        return _guard
    except Exception:
        return None                                      # fail-open: kein Modell/keine Deps


def journal_prompt_befund(defense: Defense, quelle: str, text: str) -> str | None:
    """Komfort: prüfen + bei Befund als Vorfall journalisieren (Stufe 0 —
    die App entscheidet selbst, ob sie den Text trotzdem verarbeitet)."""
    befund = pruefe_prompt(text)
    if befund:
        defense._vorfall(quelle, f"prompt_injection:{befund}", 0,
                         {"quelle": quelle, "auszug": (text or "")[:200]})
    return befund


class _VerbundIn(BaseModel):  # Modul-Ebene zwingend (PEP-563-Falle, s. app.py)
    sperren: list[dict[str, Any]] = []
    quelle: str = "dizzi"


def defense_router(defense: Defense) -> Any:
    """Cockpit-API: Status/Vorfälle lesen, Maßnahmen aufheben, Lockdown/Not-Aus
    schalten. Stufe 'lokal' reicht: localhost-Vertrauensgrenze + Guard (H1);
    alles Defensive — es gibt hier nichts zu stehlen, nur zu schützen."""
    from fastapi import APIRouter, Depends
    from fastapi.responses import JSONResponse
    from .auth import UserContext, current_user

    r = APIRouter(tags=["defense"])

    @r.get("/api/defense")
    def get_defense(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        out = defense.status()
        out["vorfaelle"] = defense.vorfaelle()
        return out

    @r.post("/api/defense/massnahmen/{massnahme_id}/aufheben")
    def post_aufheben(massnahme_id: str,
                      user: UserContext = Depends(current_user)):
        if not defense.aufheben(massnahme_id):
            return JSONResponse({"error": "Maßnahme unbekannt/inaktiv"},
                                status_code=404)
        return {"ok": True}

    @r.post("/api/defense/lockdown")
    def post_lockdown(an: bool = True,
                      user: UserContext = Depends(current_user)):
        defense.db.audit(user.user_id, "user", "defense_lockdown_geschaltet",
                         {"an": an})
        defense.lockdown(an, grund="manuell")
        return {"ok": True, "lockdown": an}

    @r.post("/api/defense/verbund")
    def post_verbund(body: _VerbundIn,
                     user: UserContext = Depends(current_user)) -> dict[str, Any]:
        """F-DEF2: geteilte Sperren aus dem Verbund übernehmen (Dizzi-Hub).
        Localhost-Vertrauensgrenze + Guard; Loopback/Echos werden ignoriert."""
        n = defense.verbund_sperren(body.sperren)
        if n:
            defense.db.audit(user.user_id, "system", "defense_verbund_uebernommen",
                             {"quelle": body.quelle, "anzahl": n})
        return {"ok": True, "uebernommen": n}

    return r


def register_defense_actions(registry: Any, defense: Defense) -> None:
    """S4/S5 als K4-HITL-Aktionen: die Automatik SCHLÄGT VOR (propose_hook),
    der Mensch gibt frei. Stufe 'lokal': defensiv + muss auch in der
    Standalone-App (ohne Dizzi-ID, max. Stufe 'lokal') freigebbar sein."""
    registry.register(
        "defense_lockdown",
        handler=lambda p: defense.lockdown(True, grund=p.get("grund", "hitl")),
        level="lokal",
        beschreibung="Lockdown: nur noch lokale Bedienung, bis zur Aufhebung")
    registry.register(
        "defense_notaus",
        handler=lambda p: defense.notaus(grund=p.get("grund", "hitl")),
        level="lokal",
        beschreibung="Not-Aus: Dienst antwortet nur noch dem Defense-Cockpit")


def install_defense(app: Any, db: Database, app_id: str, *,
                    config: DefenseConfig | None = None,
                    registry: Any | None = None,
                    clock: Callable[[], float] = time.time) -> Defense:
    """Sensorik-Middleware + Cockpit-Router + HITL-Aktionen in eine
    FastAPI-App einbauen. Settings-Gate je Request (5-s-Cache):
    ``defense_aktiv`` aus / ``defense_autonomie`` steuert die Politik."""
    from .events import push_event

    def _event(severity: str, title: str, detail: dict) -> None:
        if db.setting_get(DEFAULT_USER, "event_push", False):
            push_event(app_id, severity, title, detail)

    defense = Defense(db, app_id, config=config, clock=clock, event_hook=_event)
    if registry is not None:
        register_defense_actions(registry, defense)

        def _propose(name: str, params: dict) -> None:
            from .actions import propose
            propose(db, registry, DEFAULT_USER, name, params, source="ki")
        defense.propose_hook = _propose

    def _triage(vorfall: dict) -> None:
        """LLM-Triage NEBENHER (Daemon-Thread): erklärt den Vorfall in
        Klartext, entscheidet nichts. Gate: Setting defense_triage_aktiv."""
        if not db.setting_get(DEFAULT_USER, "defense_triage_aktiv", True):
            return
        threading.Thread(target=llm_triage, args=(defense, vorfall),
                         daemon=True).start()
    defense.triage_hook = _triage

    _cache = {"bis": 0.0, "aktiv": True, "autonomie": "standard", "hops": 0}

    def _politik() -> tuple[bool, str, int]:
        now = clock()
        if now >= _cache["bis"]:
            _cache["aktiv"] = bool(db.setting_get(DEFAULT_USER, "defense_aktiv", True))
            _cache["autonomie"] = str(db.setting_get(
                DEFAULT_USER, "defense_autonomie", "standard"))
            try:  # fail-closed: kaputter Wert ⇒ 0 = XFF ignorieren
                _cache["hops"] = max(0, int(db.setting_get(
                    DEFAULT_USER, "defense_trusted_proxy_hops", 0)))
            except (TypeError, ValueError):
                _cache["hops"] = 0
            _cache["bis"] = now + 5.0
        return _cache["aktiv"], _cache["autonomie"], _cache["hops"]

    @app.middleware("http")
    async def _defense_sensorik(request, call_next):
        from fastapi.responses import JSONResponse
        aktiv, autonomie, hops = _politik()
        if not aktiv:
            return await call_next(request)
        peer = (request.client.host if request.client else "") or ""
        # F4: XFF zählt NUR bei konfigurierten vertrauten Proxy-Hops und dann
        # von RECHTS (der linkeste Eintrag ist Angreifer-Text); ohne Konfig
        # fail-closed auf den TCP-Peer. XFF-Werte erben nie Loopback-Rechte
        # (Details: ermittle_client).
        client = ermittle_client(peer, request.headers.get("x-forwarded-for"), hops)
        block = defense.gate(client, request.method, request.url.path)
        if block is not None:
            status, text = block
            return JSONResponse({"error": text}, status_code=status)
        response = await call_next(request)
        try:
            defense.beobachte(client, request.method, request.url.path,
                              request.url.query or "", response.status_code,
                              autonomie=autonomie)
        except Exception:
            pass  # die Verteidigung darf die App nie zu Fall bringen
        return response

    app.state.defense = defense
    app.include_router(defense_router(defense))
    return defense


# Öffentlich, damit ein Host mit EIGENER DB-Schicht (z. B. der Core-Hub, der nicht
# appkit.Database nutzt) diese Tabellen in sein pro-Verbindung angelegtes Schema
# aufnehmen kann — statt sich allein auf die einmalige Anlage in Defense.__init__ zu
# verlassen. Rein additiv (CREATE … IF NOT EXISTS), idempotent.
DEFENSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS defense_massnahmen (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    client      TEXT NOT NULL,
    stufe       INTEGER NOT NULL,        -- 1..5 (STUFEN)
    grund       TEXT NOT NULL,
    bis         REAL NOT NULL,           -- Unix-Zeit; <=0 = bis zur Aufhebung
    status      TEXT NOT NULL,           -- aktiv|abgelaufen|ersetzt|aufgehoben
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_defense_m ON defense_massnahmen (status, client);
CREATE TABLE IF NOT EXISTS defense_vorfaelle (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    client      TEXT NOT NULL,
    art         TEXT NOT NULL,
    detail      TEXT NOT NULL,           -- JSON (Befunde, Pfad, Zähler)
    stufe       INTEGER NOT NULL,        -- angewandte Stufe (0 = nur beobachtet)
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_defense_v ON defense_vorfaelle (created_at);
"""
