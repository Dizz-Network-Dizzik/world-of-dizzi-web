/* ============================================================================
   netkit.js — Netzwerk-Kit-Verhalten (Verknüpfungs-Chip · Ansicht-Umschalter ·
   Command-Palette). Pionier: Dizz Plans (docs/27 §Cross-App-Synthese).
   EXTRAHIERBAR — FÜR WORLD-CHAT ins zentrale shared/ heben + netzwerkweit vendoren.

   API (window.DzNetKit):
   - fuzzy(query, text) -> score (>=0 Treffer, -1 kein Subsequence-Match)
   - linkchip({icon,label,count,title,kind,onclick}) -> HTML-String (Verknüpfungs-Chip)
   - viewSwitch(el, {views:[{id,label,icon}], value, onChange}) -> {set(id)}
   - initCmdPalette({getCommands}) -> {open,close,toggle}   (Ctrl/Cmd+K)
       getCommands() liefert [{group,label,hint,icon,keywords,run}] (dynamisch).
   Token-only; niemals auf stdout/Konsole — reine UI.
   ============================================================================ */
window.DzNetKit = (function () {
  const esc = s => (s == null ? '' : String(s)).replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // --- Fuzzy: Subsequence-Match mit Konsekutiv- + Wortanfang-Bonus ----------
  function fuzzy(query, text) {
    query = (query || '').toLowerCase().trim();
    text = (text || '').toLowerCase();
    if (!query) return 0;                       // leere Eingabe ⇒ alles behalten
    let qi = 0, score = 0, prev = -2;
    for (let ti = 0; ti < text.length && qi < query.length; ti++) {
      if (text[ti] === query[qi]) {
        score += (ti === prev + 1) ? 3 : 1;     // aufeinanderfolgend = stärker
        if (ti === 0 || /[\s·/:\-]/.test(text[ti - 1])) score += 2;  // Wortanfang
        prev = ti; qi++;
      }
    }
    return qi === query.length ? score : -1;    // alle Query-Zeichen getroffen?
  }

  // --- Verknüpfungs-Chip ----------------------------------------------------
  function linkchip(o) {
    o = o || {};
    const cls = 'dz-linkchip' + (o.kind ? ' lc-' + o.kind : '') + (o.onclick ? ' klick' : '');
    const ic = o.icon ? '<svg class="lc-ic" aria-hidden="true"><use href="#' + o.icon + '"/></svg>' : '';
    const n = (o.count != null && o.count !== '') ? '<span class="lc-n">' + esc(o.count) + '</span>' : '';
    const act = o.onclick
      ? ' role="button" tabindex="0" onclick="' + esc(o.onclick) +
        '" onkeydown="if(event.key===\'Enter\'){' + esc(o.onclick) + '}"'
      : '';
    return '<span class="' + cls + '" title="' + esc(o.title || o.label || '') + '"' + act + '>'
      + ic + '<span>' + esc(o.label || '') + '</span>' + n + '</span>';
  }

  // --- Ansicht-Umschalter ---------------------------------------------------
  function viewSwitch(el, opts) {
    opts = opts || {}; const views = opts.views || [];
    let value = opts.value || (views[0] && views[0].id);
    function paint() {
      el.classList.add('dz-viewswitch');
      el.innerHTML = views.map(v =>
        '<button type="button" data-v="' + v.id + '" class="' + (v.id === value ? 'active' : '') + '">'
        + (v.icon ? '<svg class="vs-ic" aria-hidden="true"><use href="#' + v.icon + '"/></svg>' : '')
        + esc(v.label) + '</button>').join('');
      el.querySelectorAll('button').forEach(b =>
        b.addEventListener('click', () => set(b.dataset.v)));
    }
    function set(id) {
      if (id === value) return; value = id; paint();
      if (opts.onChange) opts.onChange(id);
    }
    paint();
    return { set, get: () => value };
  }

  // --- Command-Palette (Ctrl/Cmd+K) -----------------------------------------
  function initCmdPalette(opts) {
    opts = opts || {};
    const getCommands = opts.getCommands || (() => []);
    let wrap, input, list, items = [], sel = 0;

    function build() {
      wrap = document.createElement('div');
      wrap.className = 'dz-cmdk-wrap'; wrap.hidden = true;
      wrap.innerHTML =
        '<div class="dz-cmdk" role="dialog" aria-modal="true" aria-label="Befehle">'
        + '<div class="dz-cmdk-top"><svg class="lc-ic" aria-hidden="true"><use href="#ic-cmdk"/></svg>'
        + '<input class="dz-cmdk-input" placeholder="Befehl oder Sprung … (tippen zum Filtern)" aria-label="Befehl suchen">'
        + '<span class="dz-cmdk-kbd">Esc</span></div>'
        + '<div class="dz-cmdk-list" role="listbox"></div></div>';
      document.body.appendChild(wrap);
      input = wrap.querySelector('.dz-cmdk-input');
      list = wrap.querySelector('.dz-cmdk-list');
      input.addEventListener('input', render);
      input.addEventListener('keydown', onKey);
      wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
    }
    function open() { if (!wrap) build(); wrap.hidden = false; input.value = ''; sel = 0; render(); setTimeout(() => input.focus(), 20); }
    function close() { if (wrap) wrap.hidden = true; }
    function toggle() { (wrap && !wrap.hidden) ? close() : open(); }
    function render() {
      const q = input.value;
      const scored = (getCommands() || [])
        .map(c => ({ c, s: fuzzy(q, (c.label || '') + ' ' + (c.keywords || '')) }))
        .filter(x => x.s >= 0);
      if (q.trim()) scored.sort((a, b) => b.s - a.s);
      items = scored.map(x => x.c);
      sel = Math.min(sel, Math.max(0, items.length - 1));
      if (!items.length) { list.innerHTML = '<div class="dz-cmdk-empty">Kein Treffer.</div>'; return; }
      let html = '', grp = null;
      items.forEach((c, i) => {
        if ((c.group || '') !== grp) { grp = c.group || ''; if (grp) html += '<div class="dz-cmdk-grp">' + esc(grp) + '</div>'; }
        const ic = c.icon ? '<svg class="ci-ic" aria-hidden="true"><use href="#' + c.icon + '"/></svg>' : '<span class="ci-ic"></span>';
        html += '<div class="dz-cmdk-item' + (i === sel ? ' sel' : '') + '" role="option" data-i="' + i + '">'
          + ic + '<span class="ci-label">' + esc(c.label) + '</span>'
          + (c.hint ? '<span class="ci-hint">' + esc(c.hint) + '</span>' : '') + '</div>';
      });
      list.innerHTML = html;
      list.querySelectorAll('.dz-cmdk-item').forEach(el => {
        el.addEventListener('mousemove', () => { if (sel !== +el.dataset.i) { sel = +el.dataset.i; mark(); } });
        el.addEventListener('click', () => { sel = +el.dataset.i; run(); });
      });
    }
    function mark() { list.querySelectorAll('.dz-cmdk-item').forEach(el => el.classList.toggle('sel', +el.dataset.i === sel)); }
    function scrollSel() { const el = list.querySelector('.dz-cmdk-item.sel'); if (el) el.scrollIntoView({ block: 'nearest' }); }
    function onKey(e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, items.length - 1); mark(); scrollSel(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); mark(); scrollSel(); }
      else if (e.key === 'Enter') { e.preventDefault(); run(); }
      else if (e.key === 'Escape') { e.preventDefault(); close(); }
    }
    function run() { const c = items[sel]; if (!c) return; close(); try { c.run && c.run(); } catch (e) { } }

    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); toggle(); }
    });
    return { open, close, toggle };
  }

  // --- Facetten-Filter (P1a Admin; FÜR WORLD-CHAT → in den Pionier-netkit promoten)
  //  facets(el, {groups:[{id,label,icon,items:[{wert,anzahl}]}], selected:{id:wert}, onPick})
  //  Stateless-Render: die App hält die Auswahl + re-rendert; Klick ⇒ onPick(groupId, wert).
  function facets(el, opts) {
    opts = opts || {};
    const groups = opts.groups || [], sel = opts.selected || {}, onPick = opts.onPick || function () {};
    el.classList.add('dz-facets');
    el.innerHTML = groups.filter(g => (g.items || []).length).map(function (g) {
      const aktiv = sel[g.id] || '';
      const chips = (g.items || []).map(function (it) {
        const on = String(it.wert) === String(aktiv);
        return '<button type="button" class="dz-facet' + (on ? ' on' : '') + '" data-g="' + esc(g.id)
          + '" data-w="' + esc(it.wert) + '">' + esc(it.wert) + '<span class="fc-n">' + esc(it.anzahl) + '</span></button>';
      }).join('');
      const ic = g.icon ? '<svg class="fc-gic" aria-hidden="true"><use href="#' + g.icon + '"/></svg>' : '';
      return '<div class="dz-facet-grp"><div class="dz-facet-h">' + ic + esc(g.label) + '</div>'
        + '<div class="dz-facet-row">' + chips + '</div></div>';
    }).join('');
    el.querySelectorAll('.dz-facet').forEach(function (b) {
      b.addEventListener('click', function () { onPick(b.dataset.g, b.dataset.w); });
    });
  }

  return { fuzzy, linkchip, viewSwitch, initCmdPalette, facets };
})();
