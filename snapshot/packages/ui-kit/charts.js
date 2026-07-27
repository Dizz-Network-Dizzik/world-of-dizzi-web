/* ============================================================================
   Dizz Mini-Chart-Kit  ·  DzCharts  ·  app-neutral, tokenbasiert, 0 Abhängigkeiten
   ----------------------------------------------------------------------------
   KANONISCH (the world of dizzi/shared/charts.js) — Master-Quelle. Basis aus dem
   health-App-Chat (sparkline/rings/line/scatter/gauge); Balken/Donut/Heatmap aus dem
   Management-App-Chat eingeschmolzen (20.06., World-Admin-Chat). Änderungen NUR hier
   am Master + in die App-ui-kit/ vendoren (docs/06 §6, Referenz Apple Health/Bevel).

   Reine SVG-Bausteine — Farben kommen über CSS-Klassen aus charts.css (Tokens):
     · DzCharts.sparkline(values, opts) -> SVG-String (Mini-Linie für Metrik-Karten)
     · DzCharts.activityRings(ringe, opts) -> SVG-String (Apple-Health-Tagesringe)
     · DzCharts.mountLine(el, series, opts) -> Einzweck-Linienchart MIT Klartext-
       Tooltips (mountet in ein position:relative-Element)
   Keine medizinische Logik hier — nur Darstellung. (Disclaimer/Badges: charts.css.)
   ============================================================================ */
window.DzCharts = (function () {
  const NS = 'http://www.w3.org/2000/svg';
  const esc = s => (s == null ? '' : String(s)).replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function fmt(v) {
    if (v == null || isNaN(v)) return '—';
    const n = Number(v);
    return (Math.abs(n) >= 100 || Number.isInteger(n)) ? String(Math.round(n)) : n.toFixed(1);
  }

  // ── Sparkline: kompakte Verlaufslinie (älteste→neueste) ────────────────────
  // opts.cls hängt eine Zusatzklasse an das <svg> (z. B. 'mg' für Magenta-Variante).
  function sparkline(values, opts) {
    opts = opts || {};
    const w = opts.width || 132, h = opts.height || 30, pad = 3;
    const sc = 'dz-spark' + (opts.cls ? ' ' + opts.cls : '');
    const vals = (values || []).map(Number).filter(v => !isNaN(v));
    if (vals.length < 2)
      return '<svg class="' + sc + '" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" aria-hidden="true"></svg>';
    let min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    if (opts.refMin != null) min = Math.min(min, opts.refMin);
    if (opts.refMax != null) max = Math.max(max, opts.refMax);
    if (max === min) { max += 1; min -= 1; }
    const X = i => pad + i * (w - 2 * pad) / (vals.length - 1);
    const Y = v => h - pad - (v - min) / (max - min) * (h - 2 * pad);
    let band = '';
    if (opts.refMin != null || opts.refMax != null) {
      const y1 = Y(opts.refMax != null ? opts.refMax : max);
      const y2 = Y(opts.refMin != null ? opts.refMin : min);
      band = '<rect class="dz-spark-band" x="0" y="' + Math.min(y1, y2).toFixed(1) +
        '" width="' + w + '" height="' + Math.abs(y2 - y1).toFixed(1) + '"/>';
    }
    const pts = vals.map((v, i) => X(i).toFixed(1) + ',' + Y(v).toFixed(1)).join(' ');
    const lx = X(vals.length - 1).toFixed(1), ly = Y(vals[vals.length - 1]).toFixed(1);
    return '<svg class="' + sc + '" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
      '" preserveAspectRatio="none" aria-hidden="true">' + band +
      '<polyline class="dz-spark-line" points="' + pts + '"/>' +
      '<circle class="dz-spark-dot" cx="' + lx + '" cy="' + ly + '" r="2.3"/></svg>';
  }

  // ── Aktivitätsringe: bis zu 3 verschachtelte Ringe (Apple-Health-Muster) ───
  function activityRings(ringe, opts) {
    opts = opts || {};
    const size = opts.size || 132, cx = size / 2, cy = size / 2, sw = opts.stroke || 10, gap = 4;
    let svg = '<svg class="dz-rings" width="' + size + '" height="' + size + '" viewBox="0 0 ' +
      size + ' ' + size + '" role="img" aria-label="Tages-Aktivitätsringe">';
    (ringe || []).slice(0, 3).forEach((rg, i) => {
      const r = cx - sw / 2 - i * (sw + gap);
      if (r <= 0) return;
      const c = 2 * Math.PI * r;
      const p = Math.max(0, Math.min(100, Number(rg.prozent) || 0));
      const off = c * (1 - p / 100);
      svg += '<circle class="dz-ring-bg dz-ring-' + (i + 1) + '" cx="' + cx + '" cy="' + cy +
        '" r="' + r.toFixed(1) + '" stroke-width="' + sw + '" fill="none"/>';
      svg += '<circle class="dz-ring-prog dz-ring-' + (i + 1) + '" cx="' + cx + '" cy="' + cy +
        '" r="' + r.toFixed(1) + '" stroke-width="' + sw + '" fill="none" stroke-linecap="round" ' +
        'stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) +
        '" transform="rotate(-90 ' + cx + ' ' + cy + ')"><title>' + esc(rg.label || '') + ': ' +
        p + '%</title></circle>';
    });
    return svg + '</svg>';
  }

  // ── Einzweck-Linienchart mit Klartext-Tooltip (keine Jargon) ───────────────
  // series = { werte:[…], labels:[…]?, einheit?, refMin?, refMax?, label? }
  function mountLine(el, series, opts) {
    if (!el) return;
    opts = opts || {}; series = series || {};
    const werte = (series.werte || []).map(Number);
    const labels = series.labels || [];
    el.classList.add('dz-chart'); el.innerHTML = '';
    if (!werte.length) { el.innerHTML = '<div class="dz-chart-leer">Noch zu wenig Daten für ein Diagramm.</div>'; return; }
    const w = Math.max(160, el.clientWidth || 320), h = opts.height || 140;
    const padL = 32, padR = 8, padT = 10, padB = 18;
    let min = Math.min.apply(null, werte), max = Math.max.apply(null, werte);
    if (series.refMin != null) min = Math.min(min, series.refMin);
    if (series.refMax != null) max = Math.max(max, series.refMax);
    if (max === min) { max += 1; min -= 1; }
    const span = max - min;
    const X = i => padL + (werte.length < 2 ? (w - padL - padR) / 2 : i * (w - padL - padR) / (werte.length - 1));
    const Y = v => padT + (1 - (v - min) / span) * (h - padT - padB);
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('class', 'dz-chart-svg'); svg.setAttribute('width', '100%'); svg.setAttribute('height', h);
    const add = (tag, attrs, cls, txt) => {
      const e = document.createElementNS(NS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      if (cls) e.setAttribute('class', cls);
      if (txt != null) e.textContent = txt;
      svg.appendChild(e); return e;
    };
    if (series.refMin != null || series.refMax != null) {
      const y1 = Y(series.refMax != null ? series.refMax : max);
      const y2 = Y(series.refMin != null ? series.refMin : min);
      add('rect', { x: padL, y: Math.min(y1, y2), width: w - padL - padR, height: Math.abs(y2 - y1) }, 'dz-chart-band');
    }
    add('text', { x: 2, y: Y(max) + 3 }, 'dz-chart-tick', fmt(max));
    add('text', { x: 2, y: Y(min) + 3 }, 'dz-chart-tick', fmt(min));
    if (werte.length > 1) add('polyline', { points: werte.map((v, i) => X(i) + ',' + Y(v)).join(' '), fill: 'none' }, 'dz-chart-line');
    werte.forEach((v, i) => add('circle', { cx: X(i), cy: Y(v), r: 2.4 }, 'dz-chart-dot'));
    const cross = add('line', { x1: 0, y1: padT, x2: 0, y2: h - padB }, 'dz-chart-cross'); cross.style.display = 'none';
    const cursor = add('circle', { cx: 0, cy: 0, r: 3.6 }, 'dz-chart-cursor'); cursor.style.display = 'none';
    el.appendChild(svg);
    const tip = document.createElement('div'); tip.className = 'dz-chart-tip'; tip.style.display = 'none'; el.appendChild(tip);
    svg.addEventListener('mousemove', ev => {
      const rect = svg.getBoundingClientRect();
      const mx = (ev.clientX - rect.left) / rect.width * w;
      const step = (w - padL - padR) / Math.max(1, werte.length - 1);
      let i = Math.round((mx - padL) / step);
      i = Math.max(0, Math.min(werte.length - 1, i));
      const x = X(i), y = Y(werte[i]);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.display = '';
      cursor.setAttribute('cx', x); cursor.setAttribute('cy', y); cursor.style.display = '';
      const datum = labels[i] ? '<span class="dz-chart-tipd">' + esc(labels[i]) + '</span>' : '';
      tip.innerHTML = '<b>' + fmt(werte[i]) + '</b> ' + esc(series.einheit || '') + datum;
      tip.style.display = ''; tip.style.left = (x / w * 100) + '%'; tip.style.top = '0px';
    });
    svg.addEventListener('mouseleave', () => { cross.style.display = 'none'; cursor.style.display = 'none'; tip.style.display = 'none'; });
  }

  // ── Streudiagramm mit Klartext-Tooltip (Korrelation, P2) ───────────────────
  // points = [{ x, y, datum? }]; opts = { xLabel, yLabel, height? }
  function mountScatter(el, points, opts) {
    if (!el) return;
    opts = opts || {};
    points = (points || []).filter(p => p && p.x != null && p.y != null);
    el.classList.add('dz-chart'); el.innerHTML = '';
    if (!points.length) { el.innerHTML = '<div class="dz-chart-leer">Noch zu wenig gepaarte Tage für ein Streudiagramm.</div>'; return; }
    const w = Math.max(180, el.clientWidth || 320), h = opts.height || 180;
    const padL = 36, padR = 10, padT = 10, padB = 26;
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    let xmin = Math.min.apply(null, xs), xmax = Math.max.apply(null, xs);
    let ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys);
    if (xmax === xmin) { xmax += 1; xmin -= 1; }
    if (ymax === ymin) { ymax += 1; ymin -= 1; }
    const X = x => padL + (x - xmin) / (xmax - xmin) * (w - padL - padR);
    const Y = y => padT + (1 - (y - ymin) / (ymax - ymin)) * (h - padT - padB);
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('class', 'dz-chart-svg'); svg.setAttribute('width', '100%'); svg.setAttribute('height', h);
    const add = (tag, attrs, cls, txt) => {
      const e = document.createElementNS(NS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      if (cls) e.setAttribute('class', cls);
      if (txt != null) e.textContent = txt;
      svg.appendChild(e); return e;
    };
    add('line', { x1: padL, y1: h - padB, x2: w - padR, y2: h - padB }, 'dz-axis');
    add('line', { x1: padL, y1: padT, x2: padL, y2: h - padB }, 'dz-axis');
    add('text', { x: 2, y: Y(ymax) + 3 }, 'dz-chart-tick', fmt(ymax));
    add('text', { x: 2, y: h - padB }, 'dz-chart-tick', fmt(ymin));
    add('text', { x: w - padR, y: h - padB + 11, 'text-anchor': 'end' }, 'dz-axis-lbl', opts.xLabel || 'X');
    add('text', { x: padL - 2, y: padT, 'text-anchor': 'start' }, 'dz-axis-lbl', opts.yLabel || 'Y');
    const dots = points.map(p => add('circle', { cx: X(p.x), cy: Y(p.y), r: 3.4 }, 'dz-scatter-dot'));
    el.appendChild(svg);
    const tip = document.createElement('div'); tip.className = 'dz-chart-tip'; tip.style.display = 'none'; el.appendChild(tip);
    dots.forEach((dot, i) => {
      const p = points[i];
      dot.addEventListener('mouseenter', () => {
        tip.innerHTML = (p.datum ? '<b>' + esc(p.datum) + '</b>' : '') +
          '<span class="dz-chart-tipd">' + esc(opts.xLabel || 'X') + ' ' + fmt(p.x) + ' · ' +
          esc(opts.yLabel || 'Y') + ' ' + fmt(p.y) + '</span>';
        tip.style.display = ''; tip.style.left = (X(p.x) / w * 100) + '%'; tip.style.top = (Y(p.y) - 6) + 'px';
      });
      dot.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  // ── Segmentleiste: gestapelte Anteils-/Aging-Leiste ────────────────────────
  // parts = [{ wert, cls, label }]; rendert eine schlanke Balken-Pille (HTML-String).
  // Farben kommen über die cls-Modifier (z. B. Aging-Buckets ag-nf/ag-30 … in netkit.css).
  function segments(parts, opts) {
    opts = opts || {};
    parts = (parts || []);
    const total = parts.reduce((a, p) => a + Math.max(0, Number(p.wert) || 0), 0);
    if (total <= 0) return '<div class="dz-seg dz-seg-leer"></div>';
    const teile = parts.map(p => {
      const v = Math.max(0, Number(p.wert) || 0);
      if (!v) return '';
      return '<span class="dz-seg-teil ' + esc(p.cls || '') + '" style="flex:' + v +
        '" title="' + esc((p.label || '') + ': ' + v) + '"></span>';
    }).join('');
    return '<div class="dz-seg">' + teile + '</div>';
  }

  // ── Score-Gauge: 270°-Bogen mit Mittelwert (Composite-Scores, P3) ──────────
  function gauge(prozent, opts) {
    opts = opts || {};
    const size = opts.size || 124, cx = size / 2, cy = size / 2, sw = opts.stroke || 11;
    const r = cx - sw / 2 - 2, start = 135, sweep = 270;
    const p = Math.max(0, Math.min(100, Number(prozent) || 0));
    const pt = ang => { const a = ang * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
    const arc = (a0, a1) => {
      const [x0, y0] = pt(a0), [x1, y1] = pt(a1), large = (a1 - a0) > 180 ? 1 : 0;
      return 'M' + x0.toFixed(1) + ' ' + y0.toFixed(1) + ' A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x1.toFixed(1) + ' ' + y1.toFixed(1);
    };
    const cls = opts.band ? (' ' + opts.band) : '';
    const mitte = opts.label != null ? opts.label : Math.round(p);
    return '<svg class="dz-gauge" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size +
      '" role="img" aria-label="Score ' + Math.round(p) + '">' +
      '<path class="dz-gauge-bg" d="' + arc(start, start + sweep) + '" fill="none" stroke-width="' + sw + '" stroke-linecap="round"/>' +
      '<path class="dz-gauge-fg' + cls + '" d="' + arc(start, start + sweep * p / 100) + '" fill="none" stroke-width="' + sw + '" stroke-linecap="round"/>' +
      '<text class="dz-gauge-val" x="' + cx + '" y="' + (cy + 3) + '" text-anchor="middle">' + esc(mitte) + '</text>' +
      (opts.sub ? '<text class="dz-gauge-sub" x="' + cx + '" y="' + (cy + 18) + '" text-anchor="middle">' + esc(opts.sub) + '</text>' : '') +
      '</svg>';
  }

  // ══════════════════════════════════════════════════════════════════════════
  // Kategorische Bausteine (aus dem Management-App-Chat, P2) — rein additiv,
  // sparkline/line/scatter/rings/gauge oben unverändert:
  //   · barChart(data, opts)  -> HTML (horizontale Kategorie-Balken)
  //   · donut(segments, opts) -> SVG (Verteilungs-Donut)
  //   · heatmap(matrix, opts) -> HTML (Wochentag×Stunde, Intensität via --a)
  // ══════════════════════════════════════════════════════════════════════════

  // ── Horizontale Balken (kategorisch: z. B. Posts je Plattform) ─────────────
  function barChart(data, opts) {
    opts = opts || {};
    const items = (data || []).map(d => ({ label: d.label, value: Number(d.value) || 0, kind: d.kind }));
    if (!items.length) return '<div class="dz-chart-leer">Noch keine Daten.</div>';
    const max = Math.max.apply(null, items.map(i => i.value)) || 1;
    return '<div class="dz-bars">' + items.map(i =>
      '<div class="dz-bar-row"><span class="dz-bar-label" title="' + esc(i.label) + '">' + esc(i.label) + '</span>'
      + '<span class="dz-bar-track"><span class="dz-bar-fill' + (i.kind ? ' ' + i.kind : '')
      + '" style="width:' + (i.value / max * 100).toFixed(1) + '%"></span></span>'
      + '<span class="dz-bar-val">' + fmt(i.value) + '</span></div>').join('') + '</div>';
  }

  // ── Donut: Verteilung (Segmente via stroke-dasharray) ──────────────────────
  function donut(segments, opts) {
    opts = opts || {};
    const size = opts.size || 132, cx = size / 2, cy = size / 2, sw = opts.stroke || 16;
    const r = cx - sw / 2 - 2, c = 2 * Math.PI * r;
    const segs = (segments || []).map(s => ({ label: s.label, value: Math.max(0, Number(s.value) || 0), kind: s.kind })).filter(s => s.value > 0);
    const total = segs.reduce((a, s) => a + s.value, 0);
    let svg = '<svg class="dz-donut" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="Verteilung">';
    if (!total) {
      svg += '<circle class="dz-donut-bg" cx="' + cx + '" cy="' + cy + '" r="' + r.toFixed(1) + '" fill="none" stroke-width="' + sw + '"/>';
    } else {
      let off = 0;
      segs.forEach((s, i) => {
        const len = c * (s.value / total);
        svg += '<circle class="dz-donut-seg dz-seg-' + ((i % 5) + 1) + (s.kind ? ' ' + s.kind : '') + '" cx="' + cx + '" cy="' + cy + '" r="' + r.toFixed(1) +
          '" fill="none" stroke-width="' + sw + '" stroke-dasharray="' + len.toFixed(1) + ' ' + (c - len).toFixed(1) +
          '" stroke-dashoffset="' + (-off).toFixed(1) + '" transform="rotate(-90 ' + cx + ' ' + cy + ')"><title>' + esc(s.label) + ': ' + s.value + '</title></circle>';
        off += len;
      });
    }
    svg += '<text class="dz-donut-total" x="' + cx + '" y="' + (cy + 5) + '" text-anchor="middle">' + (opts.label != null ? esc(opts.label) : total) + '</text></svg>';
    return svg;
  }

  // ── Heatmap: Wochentag (Zeilen) × Stunde (Spalten), Intensität via --a ─────
  function heatmap(matrix, opts) {
    opts = opts || {};
    const rows = opts.rows || ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    const m = matrix || [], hours = 24;
    let max = 0; m.forEach(r => r.forEach(v => { if (v > max) max = v; }));
    let html = '<div class="dz-heat"><div class="dz-heat-grid" style="grid-template-columns:auto repeat(' + hours + ',1fr)">';
    html += '<span class="dz-heat-corner"></span>';
    for (let h = 0; h < hours; h++) html += '<span class="dz-heat-h">' + (h % 3 === 0 ? h : '') + '</span>';
    for (let wd = 0; wd < rows.length; wd++) {
      html += '<span class="dz-heat-wd">' + esc(rows[wd]) + '</span>';
      for (let h = 0; h < hours; h++) {
        const vv = (m[wd] && m[wd][h]) || 0, a = max ? (vv / max) : 0;
        html += '<span class="dz-heat-cell" style="--a:' + a.toFixed(2) + '" title="' + esc(rows[wd]) + ' ' + (h < 10 ? '0' : '') + h + ':00 — ' + vv + ' Posts"></span>';
      }
    }
    return html + '</div></div>';
  }

  return { sparkline, segments, activityRings, mountLine, mountScatter, gauge, barChart, donut, heatmap, fmt };
})();
