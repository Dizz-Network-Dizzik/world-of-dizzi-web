/* ============================================================================
   DzHalter — Float-Andock-Schale (ui-kit, Single-Source) · Spin-Physik v4.4
   Davids Idee 12.07.2026: die schwebenden Knöpfe sind STANDARDMÄSSIG in einer
   kleinen Halterung oben rechts befestigt; ein Frei/Fix-Schalter lässt sie
   driften (heutiges Verhalten) oder ruft sie zügig zurück (Rückflug + Einrasten).

   WAS: globaler Modus `dz_floats_modus ∈ { angedockt, frei }` (localStorage,
   Desktop-Default = angedockt) + Halterungs-DOM (Andock-Slots je Float + der
   Frei/Fix-Schalter). Die Physik selbst wohnt weiter in floats.js /
   FloatingSettings.tsx — beide hören auf `dizzi:floatsmodus` und holen sich
   ihr Andock-Ziel über die hier vergebene Slot-Sonde.

   Self-contained + CSP-konform: externes Skript (script-src 'self'), DOM rein
   per createElement, nur CSSOM-Zuweisungen (keine style="…"-Attribute im Markup).
   Token-/design-farbig über float_dock.css (folgt --cy/--mg + data-design).
   Öffnen ist Pflicht, Physik ist Kür (docs/19 §2b): der Tap aufs angedockte
   Icon öffnet weiter sein Ziel — floats.js blockt im Dock nur das Greifen.
   reduced-motion: Floats sind heute schon statisch ⇒ DzHalter bleibt inert
   (keine Halterung, anmelden() liefert null) — konsistent ruhig.

   ── ANBINDUNG (macht floats.js/FloatingSettings selbst) ─────────────────────
     var dock = window.DzHalter && DzHalter.anmelden('floatAcct', el);
     dock.ziel()        → {x,y} Slot-MITTELPUNKT (Viewport) | null (noch kein Layout)
     dock.belegt(bool)  → Mulden-Optik „eingerastet" an/aus
     DzHalter.modus()   → 'angedockt' | 'frei'
     DzHalter.setzen(m) → schaltet um (localStorage + body[data-floats] +
                          CustomEvent 'dizzi:floatsmodus' {detail:{modus}})
   Mobile/App-Fassung = später eigene Sache (Gate G-HALTER-MOBILE); bis dahin
   gilt der eine Default überall.
   ============================================================================ */
(function (global) {
  'use strict';

  var KEY = 'dz_floats_modus';            // localStorage (je App-Origin)
  var STANDARD = 'angedockt';             // Desktop-Default (Davids Wort 12.07.)
  var reduziert = !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);

  function lesen() {
    try {
      var v = global.localStorage.getItem(KEY);
      if (v === 'frei' || v === 'angedockt') return v;
    } catch (_) { /* Privacy-Modus o. Ä. — Default gilt */ }
    return STANDARD;
  }

  var modus = lesen();
  var wrap = null, slots = null, schalter = null, flschicht = null;

  /* Schloss zu (angedockt) / Schloss auf (frei) — currentColor, Farbe kommt
     aus float_dock.css (token-getrieben, design-treu). */
  var SVG_ZU = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4.5" y="10.5" width="15" height="9.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/></svg>';
  var SVG_AUF = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4.5" y="10.5" width="15" height="9.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 7.6-1.8"/></svg>';

  function zeichnen() {
    if (!wrap) return;
    var an = (modus === 'angedockt');
    wrap.dataset.modus = modus;
    schalter.innerHTML = an ? SVG_ZU : SVG_AUF;
    schalter.setAttribute('aria-checked', an ? 'true' : 'false');
    schalter.setAttribute('aria-label', 'Schwebe-Knöpfe ' + (an ? 'freilassen' : 'andocken'));
    schalter.title = an ? 'Angedockt — Klick lässt die Knöpfe frei driften'
                        : 'Frei — Klick holt die Knöpfe in die Halterung zurück';
  }

  /* Halterung erst bauen, wenn der erste Float andockt — Apps ohne Floats
     bekommen kein leeres Möbelstück oben rechts. */
  function bauen() {
    if (wrap || reduziert || !document.body) return;
    wrap = document.createElement('div');
    wrap.className = 'dz-halter';
    slots = document.createElement('div');
    slots.className = 'dzh-slots';
    schalter = document.createElement('button');
    schalter.type = 'button';
    schalter.className = 'dzh-schalter';
    schalter.setAttribute('role', 'switch');
    schalter.addEventListener('click', function () {
      setzen(modus === 'angedockt' ? 'frei' : 'angedockt');
    });
    wrap.appendChild(slots);
    wrap.appendChild(schalter);
    document.body.appendChild(wrap);
    zeichnen();
  }

  function setzen(m) {
    if (m !== 'frei' && m !== 'angedockt') return;
    modus = m;
    try { global.localStorage.setItem(KEY, m); } catch (_) { /* Default beim nächsten Laden */ }
    if (document.body) document.body.dataset.floats = m;
    zeichnen();
    global.dispatchEvent(new CustomEvent('dizzi:floatsmodus', { detail: { modus: m } }));
  }

  /* ── Icon-Fix netzweit (docs/14 v4.5) ─────────────────────────────────────
     Body-fixe Float-SCHICHT über der Schale (z --dzh-z-floats > --dzh-z-schale).
     DzHalter hebt jedes angemeldete Float hier hinein und ERZWINGT so den
     Body-Ebene-Invariant (floats.js), statt ihn pro App zu hoffen: die Schicht
     ist ein sauberer Stapel-Kontext (kein transform/filter, float_dock.css) ⇒
     das Icon liegt garantiert OBEN auf der Mulde und bleibt klickbar — egal was
     die App-DOM drumherum tut. Erst bei Bedarf gebaut (wie die Schale). */
  function schicht() {
    if (flschicht || !document.body) return flschicht;
    flschicht = document.createElement('div');
    flschicht.className = 'dzh-floatlayer';
    document.body.appendChild(flschicht);
    return flschicht;
  }
  /* Float garantiert auf Body-Ebene in die Schicht heben. Idempotent. React-/
     Eigen-Mount-Floats (data-dzh-hoist="off") behalten ihren Platz und portalen
     bei Bedarf selbst via DzHalter.schicht(). */
  function heben(el) {
    if (!el || el.dataset.dzhHoist === 'off') return;
    var s = schicht();
    if (s && el.parentNode !== s) s.appendChild(el);
  }

  /* Ein Float meldet sich an: bekommt einen Slot (Mulde) in der Schale und eine
     ziel()-Sonde auf dessen Mittelpunkt. reduced-motion ⇒ null (statisch, kein Dock). */
  function anmelden(key, el) {
    if (reduziert || !el) return null;
    bauen();
    if (!wrap) return null;
    heben(el);                    // Icon-Fix: garantiert auf Body-Ebene in die Schicht ÜBER der Schale
    var slot = document.createElement('div');
    slot.className = 'dzh-slot';
    slot.dataset.fuer = String(key || '');
    var w = el.offsetWidth || 96, h = el.offsetHeight || 96;   // 96 = Doppelicon-Norm (docs/14 v4.1)
    slot.style.width = w + 'px';
    slot.style.height = h + 'px';
    slots.appendChild(slot);
    return {
      ziel: function () {
        var r = slot.getBoundingClientRect();
        if (!r.width) return null;
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      },
      belegt: function (ja) {
        if (ja) {   // beim Einrasten Maß nachziehen (Anmeldung kann vor dem Layout liegen)
          var w2 = el.offsetWidth, h2 = el.offsetHeight;
          if (w2 && slot.style.width !== w2 + 'px') { slot.style.width = w2 + 'px'; slot.style.height = h2 + 'px'; }
        }
        slot.dataset.belegt = ja ? '1' : '0';
      }
    };
  }

  // Modus-Hook für CSS sofort am <body> hinterlegen (auch ohne angemeldete Floats).
  function start() { if (document.body) document.body.dataset.floats = modus; }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();

  global.DzHalter = {
    anmelden: anmelden,
    schicht: schicht,             // Icon-Fix: Ziel-Schicht für React-/Eigen-Mount-Floats (Portal)
    modus: function () { return modus; },
    setzen: setzen
  };
})(window);
