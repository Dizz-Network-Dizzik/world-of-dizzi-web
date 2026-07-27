/* ============================================================================
   Dizz Floats — schwebende Knöpfe (app-neutrales KOPIER-MUSTER, vanilla)
   Spin-Physik-Spec docs/14 v4.4. Quelle der Wahrheit dieses Auszugs:
   news/static/index.html (live erprobt). Erst-Extraktion 13.06.2026.

   WAS: gemeinsamer Treiber für frei driftende Knöpfe (Settings-Doppelicon,
   Mini-Dizzi u. a.) — Drift v2 (weiche Kurven), Wurf-Zwille, Panel-Abprall
   (exakte gedrehte Hitbox), Screen-Wrap, dizzi:fling-Empfang (Kick vom
   schwingenden Panel), Float↔Float-Abprall (v4.3, generalisiert über FLOATREG).

   v4.4 (DzHalter, 15.07.2026): ist float_dock.js geladen (window.DzHalter),
   meldet jeder Float sich dort an und gehorcht dem globalen Modus
   `dz_floats_modus` — 'angedockt' (Default: sitzt fest in seiner Mulde, Physik
   aus, Tap öffnet weiter) | 'frei' (heutiges Driften). Umschalten frei→angedockt
   löst den RÜCKFLUG aus: Federzug zum Slot-Mittelpunkt (K_HOME), stärkere
   Dämpfung (FR_HOME), Einrasten unter SNAP px + lgshoot-Puls; der Heimflug
   ignoriert Panel-/Float-Abprall, Drift und Wrap, respektiert aber paused().
   Ohne float_dock.js (oder bei reduced-motion) bleibt ALLES wie v4.3.

   ABHÄNGIGKEITSFREI (kein Import). Lädt als <script src> oder inline; hängt
   sich an `window.DizzFloats`. Der Algorithmus ist IDENTISCH zur erprobten
   Inline-Fassung — nur Selektor/Callbacks sind Parameter. Bei Mechanik-
   Änderungen beide syncen (Inline = Live-Instanz).

   ── ANBINDUNG ────────────────────────────────────────────────────────────────
     DizzFloats.initFloat('floatAcct', {
        regKey: 'floatAcct',                 // FLOATREG-Schlüssel (Float↔Float)
        onTap:  openKontoModal,              // Tipp (<6px) = öffnen
        paused: () => kontoFensterOffen,     // Physik ruht, solange true
        panelSelector: '.wrap > .card'       // Panels, an denen abgeprallt wird
     });
   Floats müssen `position:fixed` + auf BODY-EBENE liegen (kein Vorfahr mit
   transform/backdrop-filter ⇒ sonst Scrollbar-Flackern, docs/14 §2 v4.3).
   v4.5 (Icon-Fix netzweit, 20.07.2026): ist float_dock.js geladen, ERZWINGT
   DzHalter das beim Andocken — jedes angemeldete Float wird in die body-fixe
   .dzh-floatlayer ÜBER der Schale gehoben (kein transform-Vorfahr kappt es mehr,
   z --dzh-z-floats > --dzh-z-schale). Ohne DzHalter gilt der Invariant wie gehabt.
   ============================================================================ */
(function (global) {
  'use strict';

  /* Rotationswinkel eines Panels aus seiner computed transform-Matrix. */
  function panelWinkel(p) {
    const tr = getComputedStyle(p).transform; if (!tr || tr === 'none') return 0;
    const m = tr.match(/matrix\(([^)]+)\)/); if (!m) return 0; const v = m[1].split(',');
    return Math.atan2(parseFloat(v[1]), parseFloat(v[0]));
  }
  /* Kreis (cx,cy,rad) gegen das ECHTE (ggf. gedrehte) Panel-Rechteck:
     null oder {nx,ny,pen} (Welt-Normale + Eindringtiefe). */
  function panelKreisStoss(p, cx, cy, rad) {
    const r = p.getBoundingClientRect(); if (r.width < 2) return null;
    const th = panelWinkel(p), pcx = r.left + r.width / 2, pcy = r.top + r.height / 2;
    const hw = (p.offsetWidth || r.width) / 2, hh = (p.offsetHeight || r.height) / 2;
    const c = Math.cos(-th), s = Math.sin(-th), dx = cx - pcx, dy = cy - pcy;
    const lx = dx * c - dy * s, ly = dx * s + dy * c;
    const qx = Math.max(-hw, Math.min(lx, hw)), qy = Math.max(-hh, Math.min(ly, hh));
    const ddx = lx - qx, ddy = ly - qy, dist = Math.hypot(ddx, ddy);
    if (dist >= rad) return null;
    let nlx, nly, pen;
    if (dist > 1e-6) { nlx = ddx / dist; nly = ddy / dist; pen = rad - dist; }
    else {
      const ax = hw - Math.abs(lx), ay = hh - Math.abs(ly);
      if (ax < ay) { nlx = lx < 0 ? -1 : 1; nly = 0; pen = ax + rad; } else { nlx = 0; nly = ly < 0 ? -1 : 1; pen = ay + rad; }
    }
    const c2 = Math.cos(th), s2 = Math.sin(th);
    return { nx: nlx * c2 - nly * s2, ny: nlx * s2 + nly * c2, pen: pen };
  }

  /* Registry aller schwebenden Elemente — jeder initFloat meldet hier seine
     Zugriffs-Funktionen an; floatAbprall läuft paarweise über ALLE (v4.3). */
  const FLOATREG = {};
  const FLOAT_SEP = 0.9; // v4.3: LEICHTER Abstoß (px/Frame) gegen Dauer-Klappern
  function floatAbprall() {
    // v4.4: angedockte/heimfliegende Floats stoßen nicht (sonst klappern sie
    // beim Rückflug aneinander); alte Registry-Einträge ohne frei-Hook = frei.
    const fs = Object.values(FLOATREG).filter(f => f && f.aktiv() && (!f.frei || f.frei()));
    for (let i = 0; i < fs.length; i++) for (let j = i + 1; j < fs.length; j++) floatPaarStoss(fs[i], fs[j]);
  }
  function floatPaarStoss(A, B) {
    const a = A.rect(), b = B.rect();
    if (!(a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y)) return;
    let nx = (b.x + b.w / 2) - (a.x + a.w / 2), ny = (b.y + b.h / 2) - (a.y + a.h / 2);
    const d = Math.hypot(nx, ny) || 1; nx /= d; ny /= d;
    const pen = Math.min(a.x + a.w - b.x, b.x + b.w - a.x, a.y + a.h - b.y, b.y + b.h - a.y);
    const aH = A.held(), bH = B.held();
    if (aH && bH) return;
    if (aH || bH) {
      const frei = aH ? B : A, dir = aH ? 1 : -1;
      frei.shift(nx * pen * dir, ny * pen * dir);
      const v = frei.vel(); frei.setVel(v.vx + nx * pen * 0.3 * dir, v.vy + ny * pen * 0.3 * dir); frei.flash(); return;
    }
    const va = A.vel(), vb = B.vel(), an = va.vx * nx + va.vy * ny, bn = vb.vx * nx + vb.vy * ny;
    if (an - bn > 0.05) {
      const anNeu = 0.5 * bn - 0.5 * an, bnNeu = 0.5 * an - 0.5 * bn;
      A.setVel(va.vx + (anNeu - an) * nx, va.vy + (anNeu - an) * ny);
      B.setVel(vb.vx + (bnNeu - bn) * nx, vb.vy + (bnNeu - bn) * ny);
      A.flash(); B.flash();
    }
    A.shift(-nx * pen / 2, -ny * pen / 2); B.shift(nx * pen / 2, ny * pen / 2);
    const va2 = A.vel(), vb2 = B.vel();                       // v4.3: IMMER leichter Schubs auseinander
    A.setVel(va2.vx - nx * FLOAT_SEP, va2.vy - ny * FLOAT_SEP);
    B.setVel(vb2.vx + nx * FLOAT_SEP, vb2.vy + ny * FLOAT_SEP);
  }

  /* Ein driftender Knopf. elOrId = Element oder dessen id. */
  function initFloat(elOrId, opts) {
    opts = opts || {};
    const el = (typeof elOrId === 'string') ? document.getElementById(elOrId) : elOrId;
    if (!el) return;
    const regKey = opts.regKey || el.id || ('f' + Math.random().toString(36).slice(2));
    const onTap = opts.onTap || function () {};
    const paused = opts.paused || function () { return false; };
    const panelSelector = opts.panelSelector || '.card';
    // ÖFFNEN ist Pflicht, Physik ist Kür (docs/19 §2b): Klick-Fallback öffnet auch bei reduced-motion.
    el.addEventListener('click', () => { if (!el._wurf) onTap(); el._wurf = false; });
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let x = 0, y = 0, vx = 0, vy = 0, placed = false, drag = null;
    const FR = 0.994, REST = 0.74, MAXV = 150, M = 8, CHARGE_REF = 460, TAP = 6;
    // v4.4 DzHalter: Rückflug-Feder (K_HOME), Homing-Dämpfung (FR_HOME), Einrast-Radius (SNAP px).
    const K_HOME = 0.02, FR_HOME = 0.85, SNAP = 6;
    let dTX = 1, dTY = 0, dX = 0, dY = 0, dNext = 0;
    // v4.4: an der DzHalter-Schale anmelden (falls float_dock.js geladen ist).
    // dockung: 'fest' (sitzt in der Mulde) | 'homing' (Rückflug) | 'frei' (v4.3-Drift).
    const dock = (window.DzHalter && window.DzHalter.anmelden) ? window.DzHalter.anmelden(regKey, el) : null;
    let dockung = (dock && window.DzHalter.modus() === 'angedockt') ? 'fest' : 'frei';
    if (dock) window.addEventListener('dizzi:floatsmodus', e => {
      const m = e.detail && e.detail.modus;
      if (m === 'frei' && dockung !== 'frei') {          // losdriften: sanfter Zufalls-Impuls (wie rel())
        dockung = 'frei'; dock.belegt(false);
        const a = Math.random() * 6.283; vx = Math.cos(a) * 5; vy = Math.sin(a) * 2.5;
      } else if (m === 'angedockt' && dockung === 'frei') { dockung = 'homing'; }
    });
    FLOATREG[regKey] = {
      rect: () => ({ x: x, y: y, w: el.offsetWidth, h: el.offsetHeight }),
      vel: () => ({ vx: vx, vy: vy }), setVel: (a, b) => { vx = a; vy = b; },
      shift: (dx, dy) => { x += dx; y += dy; place(); }, held: () => !!drag,
      aktiv: () => placed && el.offsetWidth > 0,
      flash: () => { el.classList.add('lgshoot'); setTimeout(() => el.classList.remove('lgshoot'), 360); },
      frei: () => dockung === 'frei'                     // v4.4: nur freie Floats stoßen einander
    };
    function place() { el.style.left = x.toFixed(1) + 'px'; el.style.top = y.toFixed(1) + 'px'; el.style.right = 'auto'; el.style.bottom = 'auto'; }
    function ensure() { if (placed) return; const r = el.getBoundingClientRect(); x = r.left || (innerWidth - 160); y = r.top || 78; placed = true; place(); }
    function panels() { return document.querySelectorAll(panelSelector); }
    function overlaps() {
      const w = el.offsetWidth, h = el.offsetHeight;
      for (const p of panels()) { const r = p.getBoundingClientRect(); if (r.width < 2) continue;
        if (x < r.right && x + w > r.left && y < r.bottom && y + h > r.top) return true; } return false;
    }
    function step() {
      requestAnimationFrame(step);
      if (!el.offsetWidth) { placed = false; return; }
      ensure();
      if (dock && dockung === 'fest') {                        // v4.4: sitzt in der Mulde — folgt ihr (auch bei Resize)
        const z = dock.ziel(); if (!z) return;
        const zx = z.x - el.offsetWidth / 2, zy = z.y - el.offsetHeight / 2;
        if (x !== zx || y !== zy) { x = zx; y = zy; vx = 0; vy = 0; place(); dock.belegt(true); }
        return;
      }
      if (dock && dockung === 'homing') {                      // v4.4: Rückflug — Federzug frei übers Feld
        if (paused()) return;                                  // (kein Abprall/Drift/Wrap, aber paused gilt)
        const z = dock.ziel(); if (!z) return;
        const zx = z.x - el.offsetWidth / 2, zy = z.y - el.offsetHeight / 2;
        vx += (zx - x) * K_HOME; vy += (zy - y) * K_HOME;
        vx *= FR_HOME; vy *= FR_HOME;
        x += vx; y += vy;
        if (Math.hypot(zx - x, zy - y) < SNAP) {               // einrasten: Physik aus + Klick-Puls
          x = zx; y = zy; vx = 0; vy = 0; dockung = 'fest'; dock.belegt(true);
          el.classList.add('lgshoot'); setTimeout(() => el.classList.remove('lgshoot'), 360);
        }
        place(); return;
      }
      floatAbprall();                                          // VOR dem Drag-Return: der Gehaltene schiebt den freien
      if (drag || paused()) return;                            // beim Halten / offenem Fenster ruht die Physik
      const vw = innerWidth, vh = innerHeight, w = el.offsetWidth, h = el.offsetHeight, now = performance.now();
      if (now >= dNext) { const a = Math.random() * 6.283; dTX = Math.cos(a); dTY = Math.sin(a) * 0.6; dNext = now + 2600 + Math.random() * 2600; }
      dX += (dTX - dX) * 0.012; dY += (dTY - dY) * 0.012; vx += dX * 0.006; vy += dY * 0.006;
      vx *= FR; vy *= FR;
      const sp = Math.hypot(vx, vy); if (sp > MAXV) { vx *= MAXV / sp; vy *= MAXV / sp; }
      x += vx; y += vy;
      if (x + w < 0) { x = vw; } else if (x > vw) { x = -w; }  // seitlich: Screen-Wrap
      if (y < M) { y = M; vy = Math.abs(vy) * REST; }          // vertikal: Decke/Boden abprallen
      if (y + h > vh - M) { y = vh - M - h; vy = -Math.abs(vy) * REST; }
      panels().forEach(p => {
        if (Math.abs(panelWinkel(p)) > 0.02) {                 // gedrehte Karte (Spin): echtes Rechteck
          const st = panelKreisStoss(p, x + w / 2, y + h / 2, Math.min(w, h) / 2);
          if (!st) return;
          x += st.nx * st.pen; y += st.ny * st.pen;
          const dot = vx * st.nx + vy * st.ny;
          if (dot < 0) { vx = (vx - 2 * dot * st.nx) * REST; vy = (vy - 2 * dot * st.ny) * REST; }
          return;
        }
        const r = p.getBoundingClientRect(); if (r.width < 2) return;
        if (x < r.right && x + w > r.left && y < r.bottom && y + h > r.top) {
          const dl = r.right - x, dr = (x + w) - r.left, dt = r.bottom - y, db = (y + h) - r.top, mn = Math.min(dl, dr, dt, db), k = 0.16;
          if (mn === dl) { vx = Math.abs(vx) * REST + dl * k; } else if (mn === dr) { vx = -Math.abs(vx) * REST - dr * k; }
          else if (mn === dt) { vy = Math.abs(vy) * REST + dt * k; } else { vy = -Math.abs(vy) * REST - db * k; }
        }
      });
      place();
    }
    el.addEventListener('pointerdown', e => {
      if (dock && dockung !== 'frei') return;                  // v4.4 angedockt: befestigt — kein Greifen, Tap öffnet (click-Fallback)
      e.preventDefault(); ensure();
      drag = { ox: e.clientX - x, oy: e.clientY - y, entry: null, vec: { x: 0, y: 0 }, charge: 0, sx: e.clientX, sy: e.clientY, moved: 0 };
      vx = 0; vy = 0; try { el.setPointerCapture(e.pointerId); } catch (_) { }
      el.style.cursor = 'grabbing'; el.classList.add('spinlift'); });
    el.addEventListener('pointermove', e => { if (!drag) return;
      x = e.clientX - drag.ox; y = e.clientY - drag.oy; place();
      drag.moved = Math.max(drag.moved, Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy));
      if (overlaps()) { if (!drag.entry) drag.entry = { x: e.clientX, y: e.clientY };
        drag.vec = { x: e.clientX - drag.entry.x, y: e.clientY - drag.entry.y };
        drag.charge = Math.min(1, Math.hypot(drag.vec.x, drag.vec.y) / CHARGE_REF);
      } else { drag.entry = null; drag.vec = { x: 0, y: 0 }; drag.charge = 0; }
      el.style.setProperty('--charge', drag.charge.toFixed(3)); });
    const rel = () => { if (!drag) return;
      el._wurf = true;                                         // Physik übernimmt — Klick-Fallback schweigt
      const o = drag; drag = null;
      el.style.cursor = 'grab'; el.style.setProperty('--charge', '0'); el.classList.remove('spinlift');
      if (o.moved < TAP) { onTap(); return; }                  // Tipp = öffnen
      const mag = Math.hypot(o.vec.x, o.vec.y);
      if (mag > 10 && o.charge > 0.03) { const speed = 14 + o.charge * 150;
        vx = -(o.vec.x / mag) * speed; vy = -(o.vec.y / mag) * speed;  // exakter Gegen-Vektor (Zwille)
        el.classList.add('lgshoot'); setTimeout(() => el.classList.remove('lgshoot'), 360);
      } else { const a = Math.random() * 6.283; vx = Math.cos(a) * 5; vy = Math.sin(a) * 2.5; } };
    el.addEventListener('pointerup', rel); el.addEventListener('pointercancel', rel);
    el.addEventListener('dizzi:fling', e => {
      if (dock && dockung !== 'frei') return;                  // v4.4: in der Halterung kickt kein Panel den Knopf los
      const d = e.detail; if (!d) return; ensure();
      vx += d.vx; vy += d.vy; const sp = Math.hypot(vx, vy); if (sp > MAXV) { vx *= MAXV / sp; vy *= MAXV / sp; }
      el.classList.add('lgshoot'); setTimeout(() => el.classList.remove('lgshoot'), 360); });
    el.style.cursor = 'grab';
    requestAnimationFrame(step);
  }

  global.DizzFloats = { initFloat, FLOATREG, floatAbprall, floatPaarStoss, panelWinkel, panelKreisStoss };
})(window);
