/* ============================================================================
   Dizz SpinFling — Panel-Spin-Mechanik (app-neutrales KOPIER-MUSTER, vanilla)
   Spin-Physik-Spec docs/14 v4.3. Quelle der Wahrheit dieses Auszugs:
   news/static/index.html (live erprobt). Erst-Extraktion 13.06.2026.

   HALTEN = Starrkörper-Pendel an harter, bewegter Achse: der Griffpunkt klebt
   RIGIDE am Cursor (einziger Freiheitsgrad ist die Drehung). Schwerpunkt wird
   beim Greifen ins Panel-Innere verlagert; Gravitation + Hebel bauen sich über
   GRAB_EASE_S sanft auf → Panel baumelt/schwingt. Trifft das schwingende Panel
   einen schwebenden Knopf, wird die Oberflächen-Geschwindigkeit am Kontaktpunkt
   (v_Achse + ω×r) als Impuls kopiert (dizzi:fling). LOSLASSEN = SOFORT Schluss:
   über einem anderen Panel ⇒ PLATZ-TAUSCH (swap) + localStorage; sonst ⇒ zurück
   (180 ms). Unterkanten-Fix: Scrolling während des Haltens gesperrt.
   v4.2-Klappzeilen-Norm: nur das 30px-Toggle-Icon vorne (FOLDZONE) klappt, der
   Rest der Klappzeile ist Greiffläche.

   ABHÄNGIGKEITSFREI (kein Import; dispatcht nur `dizzi:fling` an die Floats —
   die empfangen es via DizzFloats). Hängt sich an `window.DizzSpin`. Algorithmus
   IDENTISCH zur erprobten Inline-Fassung; nur Selektoren/Keys sind Parameter.

   ── ANBINDUNG ────────────────────────────────────────────────────────────────
     DizzSpin.initSpinFling({
        gridSelector:  '.wrap',                 // Container der Panels
        panelSelector: '.card',                 // Panel-Klasse (direkte Kinder des Grids)
        floatSelector: '.floatacct,.floatdizzi',// Floats, die der Kick trifft (dizzi:fling)
        storageKey:    'panelOrder',            // localStorage-Schlüssel der Reihenfolge —
                                                //   String ODER Funktion (je Aufruf frisch ausgewertet,
                                                //   z. B. () => 'order_'+modul ⇒ Persistenz pro Modul)
        layoutKey:     'layoutVer',             // localStorage-Schlüssel der Layout-Version
        layoutVer:     '2026-06-13-a'           // bei Struktur-Umbau hochzählen ⇒ Reihenfolge 1× verwerfen
     });
   Panels brauchen kein data-pid — der Schlüssel wird aus h2/summary abgeleitet.
   ============================================================================ */
(function (global) {
  'use strict';

  const SF = { G: 2400, COM_PUSH: 1.8, COM_INSET: 0.12, GRAB_EASE_S: 0.7, HOLD_ANG_DAMP: 1.1, OMEGA_MAX: 14, LIFT_THRESH: 5, TRANSFER: 1.0, KICK_MIN: 60, DT_MAX: 0.032 };
  const INTERACTIVE = 'button,input,select,textarea,a,label,option,[contenteditable],[onclick]';
  const FOLDZONE = 44;  // px ab Zeilen-Anfang = Hitbox des 30px-Toggle-Knopfs (+Luft)
  let _foldInstalled = false;

  const sfClamp = (v, m) => (v > m ? m : (v < -m ? -m : v));
  const sfFinite = (v, fb = 0) => (Number.isFinite(v) ? v : fb);
  const sfRot = (p, th) => { const c = Math.cos(th), s = Math.sin(th); return { x: p.x * c - p.y * s, y: p.x * s + p.y * c }; };
  function inFoldZone(e) { const s = e.target.closest && e.target.closest('summary'); if (!s) return false;
    return (e.clientX - s.getBoundingClientRect().left) <= FOLDZONE; }
  function pkeyOf(p, i) { const h = p.querySelector('h2, summary, .dz-panel-titel');
    return (h ? h.textContent.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 24).replace(/^-|-$/g, '') : '') || ('p' + i); }

  function initSpinFling(opts) {
    opts = opts || {};
    const gridSel = opts.gridSelector || '.wrap';
    const panelSel = opts.panelSelector || '.card';
    const floatSel = opts.floatSelector || '';
    const cardSel = gridSel + ' > ' + panelSel;
    const storageKey = opts.storageKey || 'panelOrder';
    const layoutKey = opts.layoutKey || 'layoutVer';
    const layoutVer = opts.layoutVer || '';
    // storageKey darf eine FUNKTION sein (frisch je Speichern/Wiederherstellen ausgewertet) — so
    // persistiert z. B. Dizz Admin die Panel-Reihenfolge PRO MODUL, obwohl der Grab-Listener bei
    // dynamischem Re-Render nur 1x gebunden wird: die Funktion liest beim Speichern den LIVE-Zustand
    // (z. B. das aktive Modul). String bleibt voll unterstuetzt (rueckwaerts-kompatibel).
    const skey = () => { const k = (typeof storageKey === 'function') ? storageKey() : storageKey; return k || 'panelOrder'; };

    let SPIN = null, SRAF = 0, SOVF = null, SUNLK = 0;
    const panelsList = () => [...document.querySelectorAll(cardSel)];

    // Toggle NUR am Icon (v4.2): Klicks auf den Rest der Klappzeile klappen nichts;
    // Tastatur (detail===0) togglet weiter. Einmal global installieren.
    if (!_foldInstalled) {
      _foldInstalled = true;
      document.addEventListener('click', e => {
        const s = e.target.closest('summary'); if (!s || e.detail === 0) return;
        if (e.target.closest(INTERACTIVE)) return;
        if (!inFoldZone(e)) e.preventDefault();
      }, true);
    }

    const grid = document.querySelector(gridSel); if (!grid) return;
    panelsList().forEach((p, i) => { if (!p.dataset.pkey) p.dataset.pkey = pkeyOf(p, i); });
    restorePanelOrder(grid);
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return; // statisch: nur Reihenfolge
    if (!grid._spin) { grid._spin = 1; grid.addEventListener('pointerdown', sfDown); }
    document.addEventListener('visibilitychange', sfHidden);

    function restorePanelOrder(grid) {
      try { if (localStorage.getItem(layoutKey) !== layoutVer) { localStorage.removeItem(skey()); localStorage.setItem(layoutKey, layoutVer); return; } } catch (e) {}
      let order; try { order = JSON.parse(localStorage.getItem(skey()) || '[]'); } catch (e) { return; }
      if (!order || !order.length) return;
      const map = {}; panelsList().forEach(p => map[p.dataset.pkey] = p);
      order.forEach(k => { if (map[k]) grid.appendChild(map[k]); });
    }
    function savePanelOrder(grid) {
      try { localStorage.setItem(skey(), JSON.stringify(panelsList().map(p => p.dataset.pkey))); } catch (e) {}
    }
    function sfDown(e) {
      if (SPIN || (e.button != null && e.button !== 0)) return;
      // GREIFFLÄCHE (Nutzer 14.06.): der Kopf ist greifbar ⇒ auch ZUGEKLAPPTE Panels (die nur den
      // Kopf zeigen) lassen sich schleudern. NUR der Toggle-Knopf vorne bleibt klick-only; echte
      // Controls (Buttons/Inputs/Links im Körper) blocken das Greifen weiterhin.
      if (e.target.closest('.dz-chevron')) return;             // Toggle-Knopf = nur Klick, NIE greifen
      const ia = e.target.closest(INTERACTIVE);
      if (ia && !ia.classList.contains('dz-panel-kopf')) return; // echte Controls blocken; Kopf-Button NICHT
      if (inFoldZone(e)) return;                               // (alte <summary>-Klappzeilen, falls vorhanden)
      const el = e.target.closest(panelSel);
      if (!el || el.parentElement !== grid) return;            // nur direkte Grid-Panels sind greifbar
      const r = el.getBoundingClientRect(), mid = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      const gripL = { x: e.clientX - mid.x, y: e.clientY - mid.y };
      const comL = { x: sfClamp(gripL.x - SF.COM_PUSH * gripL.x, (0.5 - SF.COM_INSET) * r.width),
                     y: sfClamp(gripL.y - SF.COM_PUSH * gripL.y, (0.5 - SF.COM_INSET) * r.height) };
      SPIN = { el, pid: el.dataset.pkey || '', pointerId: e.pointerId, cx0: mid.x, cy0: mid.y, w: r.width, h: r.height, th: 0, om: 0, gripL, comL,
               px: e.clientX, py: e.clientY, mx: mid.x, my: mid.y, pvx: 0, pvy: 0, pax: 0, pay: 0,
               lifted: false, startX: e.clientX, startY: e.clientY, cool: 0, lastT: performance.now(), liftT: 0, lx: e.clientX, ly: e.clientY };
      // KEIN setPointerCapture beim pointerdown — würde Klicks auf Inhalte schlucken.
      window.addEventListener('pointermove', sfMove);
      window.addEventListener('pointerup', sfUp, { once: true });
      window.addEventListener('pointercancel', sfUp, { once: true });
    }
    // Scroll-Sperre beim Halten: IMMER html + body (wie News ⇒ die Panels schwingen über den
    // GANZEN Viewport, ohne Seiten-Scrollbar, auflösungs-adaptiv). Das GRID wird NUR gesperrt,
    // wenn es SELBST ein Scroll-Container ist (overflowX/Y ∈ {auto,scroll}, z. B. main{overflow:auto})
    // — dort verhindert der Lock das Scrollbar-Flackern beim Aus-dem-Bild-Schwingen. Ein schmaler
    // overflow:visible-Container (.wrap, zentriert) wird NICHT gesperrt, sonst würde overflow:hidden
    // die schwingenden Panels in den schmalen Kasten clippen (Regression 18.06.).
    // SUNLK = ausstehende Entsperrung nach dem Snap-Zurück.
    // ALLE Scroll-Container vom Grid aufwärts bis <body> (inkl. Grid selbst) sammeln — aber NUR die,
    // die ohnehin auto/scroll sind. Ein overflow:visible-Wrapper (.wrap, zentriert) bleibt unberührt
    // (sonst clippt overflow:hidden die schwingenden Panels — Regression 18.06.). Deckt zwischen-
    // liegende Scroll-Container ab (z. B. main{overflow:auto}), deren Scrollbar sonst beim
    // Aus-dem-Bild-Schwingen flackert (Fix 26.06.: vorher nur html/body/grid gesperrt).
    function sfScrollAncestors() { const out = []; let n = grid;
      while (n && n !== document.body && n !== document.documentElement) {
        try { const cs = getComputedStyle(n);
          if (/(auto|scroll)/.test(cs.overflowY) || /(auto|scroll)/.test(cs.overflowX)) out.push(n);
        } catch (e) {}
        n = n.parentElement; }
      return out; }
    function sfLock() { if (SUNLK) { clearTimeout(SUNLK); SUNLK = 0; } if (SOVF) return;
      const els = [document.documentElement, document.body, ...sfScrollAncestors()];
      SOVF = els.map(n => [n, n.style.overflow]);
      els.forEach(n => { n.style.overflow = 'hidden'; }); }
    function sfUnlock() { SUNLK = 0; if (!SOVF) return;
      SOVF.forEach(p => { p[0].style.overflow = p[1]; }); SOVF = null; }
    function sfMove(e) {
      const b = SPIN; if (!b) return; b.px = e.clientX; b.py = e.clientY;
      if (!b.lifted && Math.hypot(e.clientX - b.startX, e.clientY - b.startY) > SF.LIFT_THRESH) {
        b.lifted = true; b.el.classList.add('spinlift'); b.el.style.cursor = 'grabbing';
        try { b.el.setPointerCapture(b.pointerId); } catch (_) {}
        b.lastT = performance.now(); b.liftT = performance.now(); sfLock();
        if (!SRAF) SRAF = requestAnimationFrame(sfTick);
      }
    }
    function sfApply(b) { const g = sfRot(b.gripL, b.th); b.mx = b.px - g.x; b.my = b.py - g.y;
      b.el.style.transform = `translate(${(b.mx - b.cx0).toFixed(2)}px,${(b.my - b.cy0).toFixed(2)}px) rotate(${b.th.toFixed(4)}rad)`; }
    function sfReset(b) { b.el.style.transition = 'transform 180ms cubic-bezier(.2,.8,.2,1)'; b.el.style.transform = '';
      b.el.classList.remove('spinlift'); b.el.style.cursor = ''; setTimeout(() => { b.el.style.transition = ''; }, 200); }
    function sfStop(b) { try { b.el.releasePointerCapture(b.pointerId); } catch (_) {}
      sfReset(b); SPIN = null; if (SRAF) { cancelAnimationFrame(SRAF); SRAF = 0; }
      // Entsperren erst NACH dem 180ms-Snap-Zurueck ⇒ auch beim Zurueckschnappen kein Flackern.
      SUNLK = setTimeout(sfUnlock, 220); }
    function sfUp(e) {
      const b = SPIN; if (!b) return; window.removeEventListener('pointermove', sfMove);
      if (!b.lifted) { SPIN = null; return; }                  // Klick
      // Nach echtem Drag den nachlaufenden click schlucken (v4.2).
      const sup = ev => { ev.preventDefault(); ev.stopPropagation(); window.removeEventListener('click', sup, true); };
      window.addEventListener('click', sup, true); setTimeout(() => window.removeEventListener('click', sup, true), 250);
      if (Number.isFinite(e.clientX)) { b.px = e.clientX; b.py = e.clientY; }
      const target = sfCardUnder(b.px, b.py, b.el);
      if (target && target.dataset.pkey && target.dataset.pkey !== b.pid) { sfSwap(b.el, target); }
      sfStop(b);
    }
    function sfCardUnder(x, y, exclude) {
      for (const el of panelsList()) { if (el === exclude) continue;
        const r = el.getBoundingClientRect(); if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return el; }
      return null;
    }
    function sfSwap(a, b) {
      if (!grid || a === b) return;
      const aNext = a.nextElementSibling, bNext = b.nextElementSibling;
      if (aNext === b) { grid.insertBefore(b, a); }
      else if (bNext === a) { grid.insertBefore(a, b); }
      else { const mark = document.createComment('sf'); grid.insertBefore(mark, a); grid.insertBefore(a, bNext); grid.insertBefore(b, mark); mark.remove(); }
      savePanelOrder(grid);
    }
    // Icon-Kick BEIM SCHWINGEN: Oberflächen-Geschwindigkeit am Kontaktpunkt → Impuls an die Floats.
    // v4.1: Hitbox = das GEDREHTE Panel selbst (Float-Zentrum ins Panel-System drehen, dort klemmen).
    function sfCollide(b) {
      if (b.cool > 0) { b.cool--; return; }
      if (!floatSel) return;
      const c = Math.cos(-b.th), s = Math.sin(-b.th), hw = b.w / 2, hh = b.h / 2;
      for (const f of document.querySelectorAll(floatSel)) {
        if (!f || !f.offsetWidth) continue;
        const fr = f.getBoundingClientRect(), fcx = fr.left + fr.width / 2, fcy = fr.top + fr.height / 2, frad = fr.width / 2;
        const dx = fcx - b.mx, dy = fcy - b.my;
        const lx = dx * c - dy * s, ly = dx * s + dy * c;       // Float im Panel-System
        const qx = Math.max(-hw, Math.min(lx, hw)), qy = Math.max(-hh, Math.min(ly, hh));
        if (Math.hypot(lx - qx, ly - qy) >= frad) continue;
        const c2 = Math.cos(b.th), s2 = Math.sin(b.th);
        const nx = b.mx + (qx * c2 - qy * s2), ny = b.my + (qx * s2 + qy * c2);   // Kontaktpunkt (Welt)
        const rx = nx - b.px, ry = ny - b.py, ux = b.pvx - b.om * ry, uy = b.pvy + b.om * rx;
        if (Math.hypot(ux, uy) < SF.KICK_MIN) continue;         // sanfte Berührung = kein Kick
        f.dispatchEvent(new CustomEvent('dizzi:fling', { detail: { vx: (ux / 60) * SF.TRANSFER, vy: (uy / 60) * SF.TRANSFER } })); // px/Frame
        b.cool = 12; return;
      }
    }
    function sfTick(now) {
      SRAF = requestAnimationFrame(sfTick); const b = SPIN;
      if (!b) { cancelAnimationFrame(SRAF); SRAF = 0; return; }
      const dt = Math.min(SF.DT_MAX, Math.max(0.001, (now - b.lastT) / 1000)); b.lastT = now;
      const nvx = (b.px - b.lx) / dt, nvy = (b.py - b.ly) / dt, navx = (nvx - b.pvx) / dt, navy = (nvy - b.pvy) / dt;
      b.pax += (navx - b.pax) * 0.35; b.pay += (navy - b.pay) * 0.35;
      b.pvx += (nvx - b.pvx) * 0.5; b.pvy += (nvy - b.pvy) * 0.5; b.lx = b.px; b.ly = b.py;
      const tHeld = Math.min(1, (now - b.liftT) / (SF.GRAB_EASE_S * 1000)), ease = tHeld * tHeld * (3 - 2 * tHeld);
      const r = sfRot({ x: (b.comL.x - b.gripL.x) * ease, y: (b.comL.y - b.gripL.y) * ease }, b.th);
      const I = r.x * r.x + r.y * r.y + (b.w * b.w + b.h * b.h) / 12;
      const alpha = (r.x * SF.G * ease + (r.y * b.pax - r.x * b.pay)) / Math.max(I, 400);
      b.om = sfClamp(sfFinite(b.om + alpha * dt) * Math.exp(-SF.HOLD_ANG_DAMP * dt), SF.OMEGA_MAX);
      b.th = sfFinite(b.th + b.om * dt);
      sfApply(b); sfCollide(b);
    }
    function sfHidden() { if (document.visibilityState === 'hidden' && SPIN) sfStop(SPIN); }
  }

  global.DizzSpin = { initSpinFling, SF };
})(window);
