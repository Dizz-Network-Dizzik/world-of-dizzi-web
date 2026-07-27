import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  fetchHealthWatch, fetchIdStatus, fetchNotices, fetchPanels, fetchSettings,
  putSetting, type HealthWatch, type IdStatus, type Notice, type PanelManifest,
} from "./api";
import { Icon } from "./icons";
import { kreisVsPanel, panelWinkel } from "./spinFling";

/* Frei schwebender DOPPEL-Knopf (Nutzer-Entscheid 12.06.): Einstellungen +
   Konto/Sicherheit VERSCHMOLZEN zu einem Element (Zahnrad + Schild als ein
   Doppelicon). Physik 1:1 vom Trading Bot (initLegendFloat) portiert:
   Momentum-Wurf, Abprall an Decke/Boden + Panel-Kacheln (v4.1: Hitbox =
   das ECHTE Panel-Rechteck, auch gedreht), Screen-Wrap links/rechts,
   Reibung + sanftes Auto-Drift. Echte Zwille: Eintrittspunkt in eine
   Kachel = Bezugspunkt; Zug lädt --charge (Cyan→Magenta-Glow), Loslassen
   schießt EXAKT entgegen der Zugrichtung. Reduced-Motion: statisch.
   Kurzer Tap aufs Doppelicon öffnet das Einstellungs-/Konto-FENSTER.

   Das FENSTER selbst ist der netzwerkweite „rote Faden" (Norm docs/19 §2b,
   Referenz news/static/index.html): großes Overlay, fünf Sektionen, K2.4-
   Controls, im Mattglanz-Metall der Shell. Core ist selbst der Hub + IdP —
   die Sektionen sind auf seine eigenen Endpunkte gemappt (kein appkit). */

// FR höher = Momentum-Verlust langsamer & gleichmäßiger (Nutzer-Feinschliff 11.06.).
const FR = 0.994, REST = 0.74, MAXV = 150, M = 8;
// Drift v2: statt Zufalls-Gezitter eine STEUER-RICHTUNG, die alle paar Sekunden neu gewählt
// und weich angefahren wird → sanfte Kurven-Etappen; etwas schneller & weiter als vorher.
const DRIFT_STEER = 0.006;      // Schub pro Frame Richtung Steuer-Vektor (Terminal ≈ 1 px/Frame)
const DRIFT_TURN = 0.012;       // wie weich die Richtung wechselt (kleiner = längere Kurven)
const DRIFT_EPOCH_MS: [number, number] = [2600, 5200]; // Zeit-Etappen zwischen Richtungswechseln
const CHARGE_REF = 420; // Zug-Distanz fürs volle Aufladen ≈ Breite einer Kachel
const TAP_DIST = 6;

// v4.4 DzHalter (docs/14): Andocken in der Float-Schale (float_dock.js, /ui-kit).
// Rückflug-Feder, Homing-Dämpfung, Einrast-Radius — GLEICHE Semantik wie floats.js.
const K_HOME = 0.02, FR_HOME = 0.85, SNAP = 6;
type DzDock = { ziel(): { x: number; y: number } | null; belegt(ja: boolean): void };
type DzHalterApi = {
  anmelden(key: string, el: HTMLElement): DzDock | null;
  modus(): string; setzen(m: string): void;
};
const dzHalter = (): DzHalterApi | undefined =>
  (window as unknown as { DzHalter?: DzHalterApi }).DzHalter;

// K2.2 Zwei-Achsen-Design (Katalog v1.1; Werte = die <html data-design|farbe>-Attribute,
// mappingsfrei aus dizz-tokens.css). Der Core ist eine App wie jede andere → voller Switcher.
const DESIGNS: [string, string][] = [
  ["metall", "Mattglanz-Metall (Standard)"], ["neon", "Neon / Retro-Chrome"],
  ["flach", "Flach (minimal-dunkel)"], ["tag", "Tag / Hell"],
  ["carbon", "Carbon (OLED-Schwarz)"], ["pergament", "Pergament (hell-warm)"],
  ["synthwave", "Synthwave (Neon-Sunset)"], ["lagune", "Lagune (Tropical-Aqua)"],
  ["inferno", "Inferno (Magma-Rot)"], ["kobalt", "Kobalt (Royalblau)"],
];
const FARBEN: [string, string][] = [
  ["cyan-magenta", "Cyan–Magenta (Standard)"], ["smaragd-gold", "Smaragd–Gold"],
  ["violett-eis", "Violett–Eis"], ["bernstein", "Bernstein"], ["arktis", "Arktis"],
  ["koralle", "Koralle"], ["limette", "Limette"], ["feuer", "Feuer"],
  ["toxic", "Toxic (Neon-Acid)"], ["voltage", "Voltage (Elektro)"],
];

// Einstellungen — client-seitiges 6-Kategorien-Schema (Core führt einen flachen
// Settings-Speicher, kein typisiertes /api/settings/schema wie die appkit-Apps;
// die Achsen design_vorlage/farb_schema haben ihre eigene Live-Preview-Sektion).
type SettingType = "bool" | "choice" | "int" | "text";
interface SettingDef {
  key: string; label: string; type: SettingType;
  choices?: string[]; min?: number; max?: number; step?: number;
  default: boolean | string | number; description?: string;
}
const SCHEMA: { cat: string; label: string; defs: SettingDef[] }[] = [
  { cat: "konto", label: "Konto & Identität", defs: [
    { key: "anzeigename", label: "Anzeigename", type: "text", default: "",
      description: "Dein Name in Dizzi (Personalisierung)." },
  ] },
  { cat: "sicherheit", label: "Sicherheit", defs: [
    { key: "auto_logout_min", label: "Auto-Abmeldung (Min.)", type: "int", min: 0, max: 240, step: 5, default: 30,
      description: "0 = nie automatisch abmelden." },
    { key: "reauth_sensibel", label: "Re-Auth für Sensibles", type: "bool", default: true,
      description: "MFA erneut vor sensiblen Aktionen — auch in aktiver Sitzung." },
    { key: "login_benachrichtigung", label: "Login-Benachrichtigung", type: "bool", default: false,
      description: "Bei jeder Anmeldung eine Meldung in der Glocke." },
  ] },
  { cat: "ki", label: "KI", defs: [
    { key: "ki_routing", label: "KI-Routing", type: "choice", choices: ["auto", "lokal_only"], default: "auto",
      description: "lokal_only = nie Cloud-Boost, alles auf dem Gerät." },
    { key: "ki_vorschlaege_aktiv", label: "KI-Vorschläge", type: "bool", default: true,
      description: "Darf die KI im Hintergrund Vorschläge erzeugen (Wirkung nur nach Freigabe)." },
  ] },
  { cat: "vernetzung", label: "Vernetzung & Dienste", defs: [
    { key: "event_push", label: "App-Ereignisse empfangen", type: "bool", default: true,
      description: "Angedockte Apps melden Ereignisse an die Glocke." },
    { key: "mcp_freigegeben", label: "MCP-Tools freigegeben", type: "bool", default: true,
      description: "Erlaubt Dizzi die Lese-Werkzeuge der angedockten Apps." },
    { key: "cross_app_zugriff", label: "App-übergreifender Zugriff", type: "choice",
      choices: ["fragen", "erlauben", "aus"], default: "fragen",
      description: "Ob eine App auf Daten einer anderen zugreifen darf." },
  ] },
  { cat: "darstellung", label: "Darstellung & Sprache", defs: [
    { key: "lang", label: "Sprache", type: "choice", choices: ["de", "en"], default: "de",
      description: "Sprache der Oberfläche." },
    { key: "dichte", label: "Dichte", type: "choice", choices: ["normal", "kompakt"], default: "normal",
      description: "Kompakt spart Platz." },
    { key: "reduzierte_bewegung", label: "Reduzierte Bewegung", type: "bool", default: false,
      description: "Schwebe-/Spin-Physik ruhiger (zusätzlich zur System-Einstellung)." },
  ] },
  { cat: "daten", label: "Daten & Backup", defs: [
    { key: "backup_aktiv", label: "Backups aktiv", type: "bool", default: false,
      description: "Regelmäßige lokale Sicherung." },
    { key: "aufbewahrung_tage", label: "Aufbewahrung (Tage)", type: "int", min: 1, max: 3650, step: 30, default: 365,
      description: "Audit-Log & gelesene Meldungen, die älter sind, werden bereinigt." },
    { key: "export_format", label: "Export-Format", type: "choice", choices: ["json", "csv"], default: "json",
      description: "Format für Daten-Exporte." },
  ] },
];

export function FloatingSettings() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef(false);
  openRef.current = open;

  // K2.2 Theme-Switcher: Quelle der Wahrheit ist das <html data-design|farbe>.
  const [design, setDesignS] = useState(() => document.documentElement.dataset.design || "metall");
  const [farbe, setFarbeS] = useState(() => document.documentElement.dataset.farbe || "cyan-magenta");

  // Fenster-Daten (Norm docs/19 §2b): Anmelde-Status · Settings-Werte · Netzwerk-
  // Gesundheit · KI-Glocke. Erst beim Öffnen geladen (kein Dauer-Polling).
  const [auth, setAuth] = useState<IdStatus | null>(null);
  const [vals, setVals] = useState<Record<string, unknown>>({});
  const [health, setHealth] = useState<HealthWatch | null>(null);
  const [panels, setPanels] = useState<PanelManifest[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);

  // Beim Öffnen: DOM-Theme nachsynchronisieren + alle Sektions-Daten laden.
  useEffect(() => {
    if (!open) return;
    setDesignS(document.documentElement.dataset.design || "metall");
    setFarbeS(document.documentElement.dataset.farbe || "cyan-magenta");
    let abbruch = false;
    void (async () => {
      const [st, sv, hw, pn, nt] = await Promise.all([
        fetchIdStatus().catch(() => null),
        fetchSettings().catch(() => ({}) as Record<string, unknown>),
        fetchHealthWatch().catch(() => null),
        fetchPanels().catch(() => [] as PanelManifest[]),
        fetchNotices().catch(() => [] as Notice[]),
      ]);
      if (abbruch) return;
      setAuth(st); setVals(sv); setHealth(hw); setPanels(pn); setNotices(nt);
    })();
    return () => { abbruch = true; };
  }, [open]);

  // Escape schließt das Fenster (Norm-Gotcha).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const setDesign = (d: string) => {
    setDesignS(d); document.documentElement.dataset.design = d;
    try { localStorage.setItem("dizzi_design", d); } catch { /* kein localStorage */ }
    void putSetting("design_vorlage", d);
  };
  const setFarbe = (f: string) => {
    setFarbeS(f); document.documentElement.dataset.farbe = f;
    try { localStorage.setItem("dizzi_farbe", f); } catch { /* kein localStorage */ }
    void putSetting("farb_schema", f);
  };

  // Sofort-Speichern (wie die kanonische Fassung). lang zieht zusätzlich i18n nach.
  const saveSetting = (key: string, value: unknown) => {
    setVals((prev) => ({ ...prev, [key]: value }));
    void putSetting(key, value);
    if (key === "lang" && (value === "de" || value === "en")) void i18n.changeLanguage(value);
  };
  const valOf = (d: SettingDef): boolean | string | number => {
    if (d.key in vals) return vals[d.key] as boolean | string | number;
    if (d.key === "lang") return i18n.language.startsWith("en") ? "en" : "de";
    return d.default;
  };
  const stepInt = (d: SettingDef, dir: number) => {
    const cur = Number(valOf(d)) || 0;
    let next = cur + dir * (d.step ?? 1);
    if (d.min != null) next = Math.max(d.min, next);
    if (d.max != null) next = Math.min(d.max, next);
    saveSetting(d.key, next);
  };

  const logout = async () => {
    try { await fetch("/id/logout", { method: "POST", headers: { Accept: "application/json" } }); } catch { /* egal */ }
    setAuth(await fetchIdStatus().catch(() => null));
  };

  useEffect(() => {
    const el = btnRef.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let x = 0, y = 0, vx = 0, vy = 0, placed = false, raf = 0;
    let driftX = 0, driftY = 0, driftTX = 1, driftTY = 0, driftNext = 0;
    let drag: {
      ox: number; oy: number;
      entry: { x: number; y: number } | null;
      vec: { x: number; y: number };
      charge: number;
      start: { x: number; y: number };
      moved: number;
      onIcon: boolean; // nur ein Tap EXAKT aufs Icon öffnet das Menü
    } | null = null;

    // v4.4: an der DzHalter-Schale anmelden (falls float_dock.js geladen ist).
    // dockung: 'fest' (sitzt in der Mulde) | 'homing' (Rückflug) | 'frei' (Drift).
    const dock = dzHalter()?.anmelden("floatset", el) ?? null;
    let dockung: "fest" | "homing" | "frei" =
      dock && dzHalter()?.modus() === "angedockt" ? "fest" : "frei";
    const onModus = (ev: Event) => {
      if (!dock) return;
      const m = (ev as CustomEvent<{ modus?: string }>).detail?.modus;
      if (m === "frei" && dockung !== "frei") {          // losdriften: sanfter Zufalls-Impuls
        dockung = "frei"; dock.belegt(false);
        const a = Math.random() * 6.283; vx = Math.cos(a) * 5; vy = Math.sin(a) * 2.5;
      } else if (m === "angedockt" && dockung === "frei") { dockung = "homing"; }
    };
    window.addEventListener("dizzi:floatsmodus", onModus);

    const place = () => {
      el.style.left = `${x.toFixed(1)}px`;
      el.style.top = `${y.toFixed(1)}px`;
      el.style.right = "auto";
      el.style.bottom = "auto";
    };
    const ensurePlaced = () => {
      if (placed) return;
      const r = el.getBoundingClientRect();
      x = r.left || innerWidth - el.offsetWidth - 18;
      y = r.top || 92;
      placed = true;
      place();
    };
    const cards = () => document.querySelectorAll<HTMLElement>(".grid > .card");
    const overlapsCard = () => {
      const w = el.offsetWidth, h = el.offsetHeight;
      for (const p of cards()) {
        const r = p.getBoundingClientRect();
        if (r.width < 2) continue;
        if (x < r.right && x + w > r.left && y < r.bottom && y + h > r.top) return true;
      }
      return false;
    };

    const step = () => {
      raf = requestAnimationFrame(step);
      if (el.offsetWidth === 0) { placed = false; return; }
      ensurePlaced();
      if (dock && dockung === "fest") {                  // v4.4: sitzt in der Mulde — folgt ihr (auch bei Resize)
        const z = dock.ziel(); if (!z) return;
        const zx = z.x - el.offsetWidth / 2, zy = z.y - el.offsetHeight / 2;
        if (x !== zx || y !== zy) { x = zx; y = zy; vx = 0; vy = 0; place(); dock.belegt(true); }
        return;
      }
      if (dock && dockung === "homing") {                // v4.4: Rückflug — frei übers Feld, paused gilt
        if (openRef.current) return;
        const z = dock.ziel(); if (!z) return;
        const zx = z.x - el.offsetWidth / 2, zy = z.y - el.offsetHeight / 2;
        vx += (zx - x) * K_HOME; vy += (zy - y) * K_HOME;
        vx *= FR_HOME; vy *= FR_HOME;
        x += vx; y += vy;
        if (Math.hypot(zx - x, zy - y) < SNAP) {         // einrasten: Physik aus + Puls
          x = zx; y = zy; vx = 0; vy = 0; dockung = "fest"; dock.belegt(true);
          el.classList.add("shoot");
          setTimeout(() => el.classList.remove("shoot"), 360);
        }
        place(); return;
      }
      if (drag || openRef.current) return; // beim Halten/offenem Dialog ruht die Physik
      const vw = innerWidth, vh = innerHeight, w = el.offsetWidth, h = el.offsetHeight;
      // Drift v2: weiche Kurven — Steuer-Vektor dreht träge auf ein Etappen-Ziel zu.
      const nowT = performance.now();
      if (nowT >= driftNext) {
        const a = Math.random() * 6.283;
        driftTX = Math.cos(a); driftTY = Math.sin(a) * 0.6; // horizontale Bahnen bevorzugen
        driftNext = nowT + DRIFT_EPOCH_MS[0] + Math.random() * (DRIFT_EPOCH_MS[1] - DRIFT_EPOCH_MS[0]);
      }
      driftX += (driftTX - driftX) * DRIFT_TURN;
      driftY += (driftTY - driftY) * DRIFT_TURN;
      vx += driftX * DRIFT_STEER;
      vy += driftY * DRIFT_STEER;
      vx *= FR; vy *= FR;
      const sp = Math.hypot(vx, vy);
      if (sp > MAXV) { vx *= MAXV / sp; vy *= MAXV / sp; }
      x += vx; y += vy;
      // Seitlich Screen-Wrap, vertikal Decke/Boden-Abprall (wie Trading Bot)
      if (x + w < 0) x = vw; else if (x > vw) x = -w;
      if (y < M) { y = M; vy = Math.abs(vy) * REST; }
      if (y + h > vh - M) { y = vh - M - h; vy = -Math.abs(vy) * REST; }
      cards().forEach((p) => {
        // v4.1: NUR das Panel selbst ist die Hitbox. Ungedreht = exakter
        // AABB-Abprall (wie gehabt); gedreht (Spin-Physik) = Kreis gegen das
        // ECHTE gedrehte Rechteck statt gegen dessen aufgeblähte AABB.
        if (Math.abs(panelWinkel(p)) > 0.02) {
          const st = kreisVsPanel(p, x + w / 2, y + h / 2, Math.min(w, h) / 2);
          if (!st) return;
          x += st.nx * st.pen; y += st.ny * st.pen;
          const dot = vx * st.nx + vy * st.ny;
          if (dot < 0) { vx = (vx - 2 * dot * st.nx) * REST; vy = (vy - 2 * dot * st.ny) * REST; }
          return;
        }
        const r = p.getBoundingClientRect();
        if (r.width < 2) return;
        if (x < r.right && x + w > r.left && y < r.bottom && y + h > r.top) {
          const dl = r.right - x, dr = x + w - r.left, dt = r.bottom - y, db = y + h - r.top;
          const mn = Math.min(dl, dr, dt, db), k = 0.16;
          if (mn === dl) vx = Math.abs(vx) * REST + dl * k;
          else if (mn === dr) vx = -Math.abs(vx) * REST - dr * k;
          else if (mn === dt) vy = Math.abs(vy) * REST + dt * k;
          else vy = -Math.abs(vy) * REST - db * k;
        }
      });
      place();
    };

    const onDown = (e: PointerEvent) => {
      if (dock && dockung !== "frei") return;  // v4.4 angedockt: befestigt — Klick öffnet via onClick-Fallback
      e.preventDefault();
      ensurePlaced();
      drag = {
        ox: e.clientX - x, oy: e.clientY - y, entry: null,
        vec: { x: 0, y: 0 }, charge: 0,
        start: { x: e.clientX, y: e.clientY }, moved: 0,
        onIcon: !!(e.target as Element).closest(".duo"),
      };
      vx = 0; vy = 0;
      try { el.setPointerCapture(e.pointerId); } catch { /* optional */ }
      el.style.cursor = "grabbing";
      el.classList.add("spinlift");   // Greif-Glow sofort (wie Vanilla-Floats), vor der Zwille-Ladung
    };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      x = e.clientX - drag.ox; y = e.clientY - drag.oy;
      drag.moved = Math.max(drag.moved, Math.hypot(e.clientX - drag.start.x, e.clientY - drag.start.y));
      place();
      if (overlapsCard()) {
        if (!drag.entry) drag.entry = { x: e.clientX, y: e.clientY };
        drag.vec = { x: e.clientX - drag.entry.x, y: e.clientY - drag.entry.y };
        drag.charge = Math.min(1, Math.hypot(drag.vec.x, drag.vec.y) / CHARGE_REF);
      } else {
        drag.entry = null; drag.vec = { x: 0, y: 0 }; drag.charge = 0;
      }
      el.style.setProperty("--charge", drag.charge.toFixed(3));
    };
    const onUp = () => {
      if (!drag) return;
      const { vec, charge, moved, onIcon } = drag;
      drag = null;
      el.style.cursor = "grab";
      el.classList.remove("spinlift");
      el.style.setProperty("--charge", "0");
      if (moved < TAP_DIST) {
        if (onIcon) setOpen(true); // nur Icon-Tap öffnet; Rest = Greiffläche
        return;
      }
      const mag = Math.hypot(vec.x, vec.y);
      if (mag > 10 && charge > 0.03) {
        const speed = 14 + charge * 150;
        vx = -(vec.x / mag) * speed; // exakter Gegen-Vektor: Zug ↗ ⇒ Abschuss ↙
        vy = -(vec.y / mag) * speed;
        el.classList.add("shoot");
        setTimeout(() => el.classList.remove("shoot"), 360);
      } else {
        const a = Math.random() * 6.283;
        vx = Math.cos(a) * 5; vy = Math.sin(a) * 2.5;
      }
    };

    // Impuls-Treffer durch ein schleuderndes Panel (Spin-Physik, Spec docs/14):
    // übernimmt die Oberflächen-Geschwindigkeit am Kontaktpunkt → wird weggeschleudert.
    const onFling = (ev: Event) => {
      if (dock && dockung !== "frei") return;  // v4.4: in der Halterung kickt kein Panel den Knopf los
      const d = (ev as CustomEvent<{ vx: number; vy: number }>).detail;
      if (!d) return;
      ensurePlaced();
      vx += d.vx; vy += d.vy;
      const sp = Math.hypot(vx, vy);
      if (sp > MAXV) { vx *= MAXV / sp; vy *= MAXV / sp; }
      el.classList.add("shoot");
      setTimeout(() => el.classList.remove("shoot"), 360);
    };

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    el.addEventListener("dizzi:fling", onFling);
    el.style.cursor = "grab";
    el.style.touchAction = "none";
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
      el.removeEventListener("dizzi:fling", onFling);
      window.removeEventListener("dizzi:floatsmodus", onModus);
    };
  }, []);

  // --- Control-Renderer (K2.4: .dz-check/.dz-field+.dz-select/.dz-stepper) ----
  const control = (d: SettingDef) => {
    const v = valOf(d);
    if (d.type === "bool")
      return (
        <label className="dz-check">
          <input type="checkbox" checked={!!v} onChange={(e) => saveSetting(d.key, e.target.checked)} />
        </label>
      );
    if (d.type === "choice")
      return (
        <span className="dz-field">
          <select className="dz-select" value={String(v)} onChange={(e) => saveSetting(d.key, e.target.value)}>
            {(d.choices ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </span>
      );
    if (d.type === "int")
      return (
        <span className="dz-stepper">
          <button type="button" data-dz-step="-1" aria-label="weniger" onClick={() => stepInt(d, -1)}>▾</button>
          <input type="number" value={Number(v)} min={d.min} max={d.max} step={d.step}
            onChange={(e) => saveSetting(d.key, parseInt(e.target.value, 10) || 0)} />
          <button type="button" data-dz-step="1" aria-label="mehr" onClick={() => stepInt(d, 1)}>▴</button>
        </span>
      );
    return (
      <input type="text" value={String(v ?? "")} style={{ width: 180 }}
        onChange={(e) => saveSetting(d.key, e.target.value)} />
    );
  };

  const hoch = auth?.level === "hochsicher";
  const amr = auth?.amr ?? [];                       // defensiv (alter Core-Stand: kein amr)
  const zieleEintraege = Object.entries(health?.ziele ?? {});

  return (
    <>
      {/* Icon-Fix v4.5: data-dzh-hoist="off" — DzHalter darf diesen REACT-Knoten NICHT
          in die .dzh-floatlayer heben (bräche die Reconciliation). Der Float rendert
          ohnehin wurzel-nah auf z 60 ÜBER der Schale (--dzh-z-schale 59), ist also
          bereits korrekt; bei Bedarf portalt er selbst via DzHalter.schicht(). */}
      <button ref={btnRef} className="floatset" aria-label="Einstellungen & Konto"
        data-dzh-hoist="off"
        onClick={() => {
          // Klick-Fallback (Norm-Gotcha 3, docs/19 §2b): bei reduced-motion läuft keine
          // Physik, im DzHalter-Dock (v4.4) startet kein Greifen — in beiden Fällen
          // öffnet DIESER Klick. Bei freier Physik öffnet der Tap in onUp (hier no-op).
          if (window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
              dzHalter()?.modus() === "angedockt") setOpen(true);
        }}>
        <span className="duo">
          <Icon name="gear" />
          <Icon name="shield" />
        </span>
      </button>
      {open && (
        <div className="kmwrap" onClick={() => setOpen(false)}>
          <div className="kmwin" role="dialog" aria-label="Einstellungen & Konto" onClick={(e) => e.stopPropagation()}>
            <div className="kmhead">
              <span className="duo duo-sm"><Icon name="gear" /><Icon name="shield" /></span>
              <h2>{t("settings_title")}</h2>
              <span className="pill">Dizzi-ID</span>
              <span className="spacer" />
              <button className="x" onClick={() => setOpen(false)} aria-label={t("close")}>×</button>
            </div>
            <div className="kmbody">

              {/* 1 — Identität & Sicherheit (Core BESITZT Dizzi-ID) */}
              <div className="kmsec">
                <div className="kmsech">Identität &amp; Sicherheit</div>
                {auth?.angemeldet ? (
                  <>
                    <div className="kmrow" style={{ flexWrap: "wrap", gap: 10 }}>
                      <span className="pill aktiv">✓ Angemeldet</span>
                      <span className="desc small">
                        via <b>{auth.via || "?"}</b> · Stufe <b>{auth.level}</b>
                        {amr.length ? ` (${amr.join(", ")})` : ""}
                      </span>
                      <span className="spacer" />
                      {hoch ? (
                        <span className="pill aktiv">✓ Echtgeld-Stufe</span>
                      ) : (
                        <a className="tblink" href="/id/stepup?next=" target="_blank" rel="noopener"
                          title="Per MFA/Passkey auf die Stufe hochsicher hochstufen.">Hochstufen (MFA)</a>
                      )}
                      <button className="x" style={{ width: "auto", padding: "0 10px" }} onClick={() => void logout()}>Abmelden</button>
                    </div>
                    <div className="desc small" style={{ marginTop: 8 }}>
                      Identität <b>{auth.user_id ?? "dizzi"}</b> · MFA {auth.mfa?.confirmed ? "aktiv" : "nicht eingerichtet"}.
                    </div>
                  </>
                ) : (
                  <div className="kmrow" style={{ flexWrap: "wrap", gap: 10 }}>
                    <span className="pill">Nicht angemeldet</span>
                    <span className="desc small">Einmal über Dizzi-ID anmelden ⇒ in allen Dizz-Apps angemeldet (SSO).</span>
                    <span className="spacer" />
                    <a className="tblink" href="/id/login" target="_blank" rel="noopener">Mit Dizzi-ID anmelden</a>
                  </div>
                )}
                <div className="kmrow" style={{ flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                  <a className="tblink" href="/id/geraete" target="_blank" rel="noopener"
                    title="Aktive Sitzungen sehen, einzeln widerrufen oder überall abmelden.">Sitzungen &amp; Geräte</a>
                  <a className="tblink" href="/id/login" target="_blank" rel="noopener">Konto-Seite</a>
                </div>
              </div>

              {/* 2 — Design (Live-Preview, K2.2 zwei Achsen) */}
              <div className="kmsec">
                <div className="kmsech"><Icon name="wand" /> Design</div>
                <div className="desc small" style={{ marginBottom: 6 }}>
                  Grund-Thematik bleibt — Design-Theme und Farbschema sind GETRENNT wählbar; die Vorschau ist sofort live.
                </div>
                <div className="kmrow">
                  <label title="Material/Form der Oberfläche — in jeder App auf jedes Theme umschaltbar.">Design-Theme</label>
                  <span className="dz-field">
                    <select className="dz-select" value={design} aria-label="Design-Theme" onChange={(e) => setDesign(e.target.value)}>
                      {DESIGNS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </span>
                </div>
                <div className="kmrow">
                  <label title="Farbpalette — unabhängig vom Design-Theme.">Farbschema</label>
                  <span className="dz-field">
                    <select className="dz-select" value={farbe} aria-label="Farbschema" onChange={(e) => setFarbe(e.target.value)}>
                      {FARBEN.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </span>
                </div>
              </div>

              {/* 3 — Verbundene Dienste (Hub-Variante: zentral via Dizzi-ID) */}
              <div className="kmsec">
                <div className="kmsech">Verbundene Dienste</div>
                <div className="kmdienst">
                  <Icon name="lock" />
                  <b>Dizzi-ID (SSO)</b>
                  <span className="desc small">zentrale Identität des Netzwerks{auth?.google_konfiguriert ? " · Google verknüpfbar" : ""}</span>
                  <span className="spacer" />
                  <a className="tblink" href="/id/geraete" target="_blank" rel="noopener">Verwalten</a>
                </div>
                <div className="desc small" style={{ marginTop: 6 }}>
                  Token/Keys einzelner Dienste liegen im verschlüsselten Tresor der jeweiligen App — Dizzi sieht sie nie im Klartext.
                </div>
              </div>

              {/* 4 — Vernetzung & KI-Aktivität (Core = Hub: Netzwerk + Glocke) */}
              <div className="kmsec">
                <div className="kmsech"><Icon name="share" /> Vernetzung &amp; KI-Aktivität</div>
                <div className="desc small" style={{ marginBottom: 6 }}>
                  Der Verbund auf einen Blick — und was die KIs im Hintergrund melden. Wirkung gibt es NUR nach deiner Freigabe (HITL).
                </div>
                <div className="kmrow" style={{ flexWrap: "wrap", gap: 6 }}>
                  {zieleEintraege.length ? zieleEintraege.map(([name, on]) => (
                    <span key={name} className="netchip"><span className={`dot ${on ? "on" : "off"}`} />{name}</span>
                  )) : (
                    <span className="desc small">Netzwerk-Status wird beim nächsten Wächter-Lauf sichtbar (~1 Min. nach Start).</span>
                  )}
                </div>
                <div className="desc small" style={{ margin: "8px 0 4px" }}>
                  {panels.length} App-Kacheln registriert · {notices.length} offene KI-Meldung(en):
                </div>
                {notices.length ? notices.slice(0, 8).map((n) => (
                  <div key={n.id} className="kmdienst">
                    <b>{n.title}</b>
                    <span className={`pill sev-${n.severity}`}>{n.severity}</span>
                    <span className="desc small">{n.source} · {n.created_at?.slice(0, 16).replace("T", " ")}</span>
                  </div>
                )) : (
                  <div className="desc small">Keine offenen KI-Vorschläge.</div>
                )}
              </div>

              {/* 5 — Einstellungen (6 Kategorien, K2.4-Controls, Sofort-Speichern) */}
              <div className="kmsec">
                <div className="kmsech">Einstellungen</div>
                <div className="desc small" style={{ margin: "2px 0 2px" }}>
                  6 Kategorien — Änderungen werden sofort gespeichert.
                </div>
                {SCHEMA.map((c) => (
                  <div className="kmcat" key={c.cat}>
                    <div className="kmcath">{c.label}</div>
                    {c.defs.map((d) => (
                      <div className="kmrow" key={d.key}>
                        <label title={d.description}>{d.label}</label>
                        {control(d)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>

              <p className="hint">{t("settings_hint")}</p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
