import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { putSetting } from "./api";
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
   Kurzer Tap aufs Doppelicon öffnet Einstellungen & Konto.

   v4.4 (DzHalter, 15.07.2026): ist float_dock.js geladen (window.DzHalter),
   dockt der Knopf in der Halterung oben rechts an — Modus 'angedockt'
   (Default: fest in der Mulde, Physik aus, Klick öffnet weiter) | 'frei'
   (heutiges Driften). Rückflug per Federzug (K_HOME/FR_HOME/SNAP), hört auf
   'dizzi:floatsmodus'. GLEICHE Semantik wie floats.js — beide syncen! */

// v4.4 DzHalter: Rückflug-Feder, Homing-Dämpfung, Einrast-Radius (docs/14 v4.4).
const K_HOME = 0.02, FR_HOME = 0.85, SNAP = 6;
type DzDock = { ziel(): { x: number; y: number } | null; belegt(ja: boolean): void };
type DzHalterApi = {
  anmelden(key: string, el: HTMLElement): DzDock | null;
  modus(): string; setzen(m: string): void;
};
const dzHalter = (): DzHalterApi | undefined =>
  (window as unknown as { DzHalter?: DzHalterApi }).DzHalter;

// FR höher = Momentum-Verlust langsamer & gleichmäßiger (Nutzer-Feinschliff 11.06.).
const FR = 0.994, REST = 0.74, MAXV = 150, M = 8;
// Drift v2: statt Zufalls-Gezitter eine STEUER-RICHTUNG, die alle paar Sekunden neu gewählt
// und weich angefahren wird → sanfte Kurven-Etappen; etwas schneller & weiter als vorher.
const DRIFT_STEER = 0.006;      // Schub pro Frame Richtung Steuer-Vektor (Terminal ≈ 1 px/Frame)
const DRIFT_TURN = 0.012;       // wie weich die Richtung wechselt (kleiner = längere Kurven)
const DRIFT_EPOCH_MS: [number, number] = [2600, 5200]; // Zeit-Etappen zwischen Richtungswechseln
const CHARGE_REF = 420; // Zug-Distanz fürs volle Aufladen ≈ Breite einer Kachel
const TAP_DIST = 6;

export function FloatingSettings() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef(false);
  openRef.current = open;

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

  const setLang = (lng: "de" | "en") => {
    void i18n.changeLanguage(lng);
    void putSetting("lang", lng);
  };

  return (
    <>
      {/* Icon-Fix v4.5: data-dzh-hoist="off" — DzHalter darf diesen REACT-Knoten NICHT
          in die .dzh-floatlayer heben (bräche die Reconciliation). Der Float rendert
          ohnehin wurzel-nah auf z 60 ÜBER der Schale (--dzh-z-schale 59), ist also
          bereits korrekt; bei Bedarf portalt er selbst via DzHalter.schicht(). */}
      <button ref={btnRef} className="floatset" aria-label="Einstellungen & Konto"
        data-dzh-hoist="off"
        onClick={() => {
          // Klick-Fallback (docs/19 §2b): bei reduced-motion läuft keine Physik, im
          // DzHalter-Dock (v4.4) startet kein Greifen — in beiden Fällen öffnet DIESER
          // Klick; bei freier Physik öffnet der Tap in onUp (hier dann no-op).
          if (window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
              dzHalter()?.modus() === "angedockt") setOpen(true);
        }}>
        <span className="duo">
          <Icon name="gear" />
          <Icon name="shield" />
        </span>
      </button>
      {open && (
        <div className="modalwrap" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="head">
              <Icon name="gear" />
              <span className="name">{t("settings_title")}</span>
              <button className="x" onClick={() => setOpen(false)} aria-label={t("close")}>×</button>
            </div>
            <div className="mrow">
              <span>{t("settings_lang")}</span>
              <span className="langbtns">
                <button className={i18n.language === "de" ? "on" : ""} onClick={() => setLang("de")}>DE</button>
                <button className={i18n.language === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
              </span>
            </div>
            <div className="mrow">
              <span>Konto &amp; Sicherheit (Dizzi-ID)</span>
              <span className="langbtns">
                <button onClick={() => window.open("/id/login", "_blank", "noopener")}>Konto</button>
                <button onClick={() => window.open("/id/geraete", "_blank", "noopener")}>Geräte</button>
              </span>
            </div>
            <p className="hint">{t("settings_hint")}</p>
          </div>
        </div>
      )}
    </>
  );
}
