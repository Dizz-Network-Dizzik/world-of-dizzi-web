/* Spin-Physik v4 — Pendel an harter Achse, sofortiges Loslassen (Spec docs/14).
 *
 * HALTEN = Pendel an starrem, bewegtem Drehpunkt:
 *   - Griffpunkt RIGIDE am Cursor (Pose jede Frame exakt aus Pin + θ; einziger
 *     Freiheitsgrad ist die Drehung) — null Wobble am Griff.
 *   - Schwerpunkt wird beim Greifen vom Griff weg ins Panel-Innere verlagert;
 *     Gravitation + Hebel bauen sich über GRAB_EASE_S sanft auf (kein Start-Zappeln),
 *     dann baumelt/schwingt das Panel; Achsen-Beschleunigung schaukelt auf.
 *   - Trifft das SCHWINGENDE Panel das schwebende Element, wird die Oberflächen-
 *     Geschwindigkeit am Kontaktpunkt übertragen (Icon-Kick — passiert beim Schwingen).
 *
 * LOSLASSEN = SOFORT Schluss (Nutzer-Entscheid 11.06., v4): Achse/Schwerpunkt
 * verschwinden augenblicklich — über einem anderen Panel ⇒ direkter PLATZ-TAUSCH,
 * sonst ⇒ direkt zurück auf den eigenen Platz. Kein Nachflug, kein Restmoment.
 *
 * Unterkanten-Bug-Fix: Während des Haltens ist das Dokument-Scrolling GESPERRT
 * (overflow hidden auf html/body) — ein schräges Panel am unteren Rand kann die
 * Seite nicht mehr vergrößern/verschieben, die Viewport-Koordinaten bleiben stabil.
 *
 * Einheiten: px und Sekunden (dt-basiert, dt geklemmt).
 */

export interface SpinFlingOptions {
  gridSelector: string;
  cardSelector: string;
  floatSelector: string;
  onReorder: (draggedId: string, targetId: string) => void;
}

// --- Feel-Parameter (justierbar) --------------------------------------------
const G = 2400;                 // Gravitation px/s² (Baumel-Tempo)
const COM_PUSH = 1.8;           // Schwerpunkt-Verlagerung: Griff→Mitte-Vektor × Faktor
const COM_INSET = 0.12;         // Schwerpunkt bleibt mind. so weit im Panel (Anteil)
const GRAB_EASE_S = 0.7;        // s — Gravitation/Hebel bauen sich nach dem Greifen sanft auf
const HOLD_ANG_DAMP = 1.1;      // Winkel-Dämpfung beim Halten (1/s) — baumelt lange nach
const OMEGA_MAX = 14;           // rad/s
const LIFT_THRESH = 5;          // px bis zum Greifen (darunter = Klick)
const TRANSFER = 1.0;           // Impuls-Kopie beim Icon-Treffer
const KICK_MIN = 60;            // px/s — minimale Kontakt-Geschwindigkeit für einen Kick
const DT_MAX = 0.032;

interface Vec { x: number; y: number }

interface Body {
  el: HTMLElement; pid: string;
  cx0: number; cy0: number; w: number; h: number;   // Flow-Center + Maße
  th: number; om: number;                            // Winkel, Winkelgeschwindigkeit
  gripL: Vec; comL: Vec;                             // lokal, relativ zur Panel-Mitte (θ=0)
  px: number; py: number;                            // Cursor (Achse)
  mx: number; my: number;                            // aktuelle Panel-Mitte (Welt)
  pvx: number; pvy: number; pax: number; pay: number;
  lifted: boolean; startX: number; startY: number;
  cool: number; lastT: number; liftT: number;
  lx: number; ly: number;
}

const clamp = (v: number, m: number) => (v > m ? m : v < -m ? -m : v);
const finite = (v: number, fb = 0) => (Number.isFinite(v) ? v : fb);
const rot = (p: Vec, th: number): Vec => {
  const c = Math.cos(th), s = Math.sin(th);
  return { x: p.x * c - p.y * s, y: p.x * s + p.y * c };
};

/* --- Exakte Panel-Hitbox (v4.1, Nutzer-Entscheid 12.06.) --------------------
 * Kollisionen rechnen gegen das ECHTE Panel-Rechteck — auch wenn es gedreht
 * ist. Vorher diente die Achsen-AABB des gedrehten Panels als Hitbox; die ist
 * größer als das Panel selbst und traf „durch die Luft". */

/** Rotationswinkel eines Elements aus seiner computed transform-Matrix. */
export function panelWinkel(el: HTMLElement): number {
  const tr = getComputedStyle(el).transform;
  if (!tr || tr === "none") return 0;
  const m = tr.match(/matrix\(([^)]+)\)/);
  if (!m) return 0;
  const v = m[1].split(",");
  return Math.atan2(parseFloat(v[1]), parseFloat(v[0]));
}

export interface KreisStoss { nx: number; ny: number; pen: number; px: number; py: number }

/** Kreis (cx,cy,rad) gegen das ECHTE (ggf. gedrehte) Rechteck eines Panels.
 *  null = keine Berührung; sonst Welt-Normale + Eindringtiefe + Kontaktpunkt.
 *  Mathe: Kreis-Zentrum ins Panel-System drehen (Rotation um die Mitte —
 *  getBoundingClientRect-Zentrum bleibt dabei die wahre Mitte), dort gegen
 *  die UNGEDREHTEN Halbmaße klemmen, Ergebnis zurückdrehen. */
export function kreisVsPanel(el: HTMLElement, cx: number, cy: number,
                             rad: number): KreisStoss | null {
  const r = el.getBoundingClientRect();
  if (r.width < 2) return null;
  const th = panelWinkel(el);
  const pcx = r.left + r.width / 2, pcy = r.top + r.height / 2;
  const hw = (el.offsetWidth || r.width) / 2, hh = (el.offsetHeight || r.height) / 2;
  const c = Math.cos(-th), s = Math.sin(-th);
  const dx = cx - pcx, dy = cy - pcy;
  const lx = dx * c - dy * s, ly = dx * s + dy * c;
  const qx = Math.max(-hw, Math.min(lx, hw)), qy = Math.max(-hh, Math.min(ly, hh));
  const ddx = lx - qx, ddy = ly - qy, dist = Math.hypot(ddx, ddy);
  if (dist >= rad) return null;
  let nlx: number, nly: number, pen: number;
  if (dist > 1e-6) { nlx = ddx / dist; nly = ddy / dist; pen = rad - dist; }
  else {                                  // Zentrum IM Panel: kürzeste Achse raus
    const ax = hw - Math.abs(lx), ay = hh - Math.abs(ly);
    if (ax < ay) { nlx = lx < 0 ? -1 : 1; nly = 0; pen = ax + rad; }
    else { nlx = 0; nly = ly < 0 ? -1 : 1; pen = ay + rad; }
  }
  const c2 = Math.cos(th), s2 = Math.sin(th);
  return { nx: nlx * c2 - nly * s2, ny: nlx * s2 + nly * c2, pen,
           px: pcx + (qx * c2 - qy * s2), py: pcy + (qx * s2 + qy * c2) };
}

export function initSpinFling(opts: SpinFlingOptions): () => void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return () => {};

  let body: Body | null = null;
  let raf = 0;
  let savedOverflow: [string, string] | null = null;

  // Unterkanten-Fix: Scroll-Geometrie während des Haltens einfrieren.
  const lockScroll = () => {
    if (savedOverflow) return;
    savedOverflow = [document.documentElement.style.overflow, document.body.style.overflow];
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
  };
  const unlockScroll = () => {
    if (!savedOverflow) return;
    [document.documentElement.style.overflow, document.body.style.overflow] = savedOverflow;
    savedOverflow = null;
  };

  const apply = (b: Body) => {
    const g = rot(b.gripL, b.th);
    b.mx = b.px - g.x; b.my = b.py - g.y;            // Mitte so, dass Griff exakt am Cursor
    b.el.style.transform =
      `translate(${(b.mx - b.cx0).toFixed(2)}px, ${(b.my - b.cy0).toFixed(2)}px) rotate(${b.th.toFixed(4)}rad)`;
  };

  // Sofortiges Zurück/Stillstehen: Transition kurz & knackig, Mechanik ist bereits aus.
  const reset = (b: Body) => {
    b.el.style.transition = "transform 180ms cubic-bezier(.2,.8,.2,1)";
    b.el.style.transform = "";
    b.el.style.zIndex = "";
    b.el.style.cursor = "";
    setTimeout(() => { b.el.style.transition = ""; }, 200);
  };

  const stop = (b: Body) => {
    reset(b); body = null; unlockScroll();
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
  };

  const floatEl = () => document.querySelector<HTMLElement>(opts.floatSelector);

  const onDown = (e: PointerEvent) => {
    if (body) return;
    const target = e.target as HTMLElement;
    if (target.closest("a, button, input, textarea, select")) return;
    const el = target.closest<HTMLElement>(opts.cardSelector);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const mid = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    const gripL: Vec = { x: e.clientX - mid.x, y: e.clientY - mid.y };
    const comL: Vec = {
      x: clamp(gripL.x - COM_PUSH * gripL.x, (0.5 - COM_INSET) * r.width),
      y: clamp(gripL.y - COM_PUSH * gripL.y, (0.5 - COM_INSET) * r.height),
    };
    body = {
      el, pid: el.dataset.pid || "",
      cx0: mid.x, cy0: mid.y, w: r.width, h: r.height,
      th: 0, om: 0, gripL, comL,
      px: e.clientX, py: e.clientY, mx: mid.x, my: mid.y,
      pvx: 0, pvy: 0, pax: 0, pay: 0,
      lifted: false, startX: e.clientX, startY: e.clientY,
      cool: 0, lastT: performance.now(), liftT: 0,
      lx: e.clientX, ly: e.clientY,
    };
    try { el.setPointerCapture(e.pointerId); } catch { /* optional */ }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    window.addEventListener("pointercancel", onUp, { once: true });
  };

  const onMove = (e: PointerEvent) => {
    if (!body) return;
    body.px = e.clientX; body.py = e.clientY;
    if (!body.lifted && Math.hypot(e.clientX - body.startX, e.clientY - body.startY) > LIFT_THRESH) {
      body.lifted = true;
      body.el.style.zIndex = "50";
      body.el.style.cursor = "grabbing";
      body.lastT = performance.now();
      body.liftT = performance.now();
      lockScroll();
      if (!raf) raf = requestAnimationFrame(tick);
    }
  };

  // LOSLASSEN = sofort aus: tauschen ODER zurück — nie Nachflug.
  const onUp = (e: PointerEvent) => {
    if (!body) return;
    window.removeEventListener("pointermove", onMove);
    const b = body;
    if (!b.lifted) { body = null; return; } // Klick
    if (Number.isFinite(e.clientX)) { b.px = e.clientX; b.py = e.clientY; }
    const target = cardUnder(b.px, b.py, b.el);
    if (target && target.dataset.pid && target.dataset.pid !== b.pid) {
      opts.onReorder(b.pid, target.dataset.pid);
    }
    stop(b);
  };

  const cardUnder = (x: number, y: number, exclude: HTMLElement): HTMLElement | null => {
    for (const el of document.querySelectorAll<HTMLElement>(opts.cardSelector)) {
      if (el === exclude) continue;
      const r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return el;
    }
    return null;
  };

  // Icon-Kick BEIM SCHWINGEN: Oberflächen-Geschwindigkeit des gehaltenen Panels am
  // Kontaktpunkt = v_Achse + ω × (Kontakt − Achse) → Impuls-Kopie ans schwebende Element.
  // v4.1: Hitbox = das GEDREHTE Panel selbst (Float-Zentrum ins Panel-System
  // drehen, dort klemmen) — die alte Achsen-AABB traf zu früh „durch die Luft".
  const collideFloat = (b: Body) => {
    if (b.cool > 0) { b.cool--; return; }
    const f = floatEl();
    if (!f) return;
    const fr = f.getBoundingClientRect();
    const fcx = fr.left + fr.width / 2, fcy = fr.top + fr.height / 2, frad = fr.width / 2;
    const hw = b.w / 2, hh = b.h / 2;
    const c = Math.cos(-b.th), s = Math.sin(-b.th);
    const dx = fcx - b.mx, dy = fcy - b.my;
    const lx = dx * c - dy * s, ly = dx * s + dy * c;      // Float im Panel-System
    const qx = Math.max(-hw, Math.min(lx, hw)), qy = Math.max(-hh, Math.min(ly, hh));
    if (Math.hypot(lx - qx, ly - qy) >= frad) return;
    const c2 = Math.cos(b.th), s2 = Math.sin(b.th);
    const nx = b.mx + (qx * c2 - qy * s2);                  // Kontaktpunkt (Welt)
    const ny = b.my + (qx * s2 + qy * c2);
    const rx = nx - b.px, ry = ny - b.py;                   // Kontakt relativ zur Achse
    const ux = b.pvx - b.om * ry, uy = b.pvy + b.om * rx;
    if (Math.hypot(ux, uy) < KICK_MIN) return;              // sanfte Berührung = kein Kick
    f.dispatchEvent(new CustomEvent("dizzi:fling",
      { detail: { vx: (ux / 60) * TRANSFER, vy: (uy / 60) * TRANSFER } })); // Legenden-Physik: px/Frame
    b.cool = 12;
  };

  const tick = (now: number) => {
    raf = requestAnimationFrame(tick);
    const b = body;
    if (!b) { cancelAnimationFrame(raf); raf = 0; return; }
    const dt = Math.min(DT_MAX, Math.max(0.001, (now - b.lastT) / 1000));
    b.lastT = now;

    // Achsen-Geschwindigkeit/-Beschleunigung aus der Cursor-Bewegung (geglättet)
    const nvx = (b.px - b.lx) / dt, nvy = (b.py - b.ly) / dt;
    const navx = (nvx - b.pvx) / dt, navy = (nvy - b.pvy) / dt;
    b.pax += (navx - b.pax) * 0.35; b.pay += (navy - b.pay) * 0.35;
    b.pvx += (nvx - b.pvx) * 0.5; b.pvy += (nvy - b.pvy) * 0.5;
    b.lx = b.px; b.ly = b.py;

    // Sanfter Start: Hebel + Gravitation wachsen über GRAB_EASE_S (smoothstep).
    const tHeld = Math.min(1, (now - b.liftT) / (GRAB_EASE_S * 1000));
    const ease = tHeld * tHeld * (3 - 2 * tHeld);
    const r = rot({
      x: (b.comL.x - b.gripL.x) * ease,
      y: (b.comL.y - b.gripL.y) * ease,
    }, b.th);
    const I = r.x * r.x + r.y * r.y + (b.w * b.w + b.h * b.h) / 12;
    const alpha = (r.x * G * ease + (r.y * b.pax - r.x * b.pay)) / Math.max(I, 400);
    b.om = clamp(finite(b.om + alpha * dt) * Math.exp(-HOLD_ANG_DAMP * dt), OMEGA_MAX);
    b.th = finite(b.th + b.om * dt);

    apply(b);
    collideFloat(b);
  };

  const onHidden = () => {
    if (document.visibilityState === "hidden" && body) stop(body);
  };

  const container = document.querySelector<HTMLElement>(opts.gridSelector) || document.body;
  container.addEventListener("pointerdown", onDown);
  document.addEventListener("visibilitychange", onHidden);

  return () => {
    container.removeEventListener("pointerdown", onDown);
    window.removeEventListener("pointermove", onMove);
    document.removeEventListener("visibilitychange", onHidden);
    if (raf) cancelAnimationFrame(raf);
    unlockScroll();
    body = null;
  };
}
