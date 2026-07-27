/* DzWave — netzweiter Klick-Wellen-Effekt (ui-kit, Single-Source).
 * Bei jedem Linksklick ploppt an der Mausposition eine Energie-Welle auf.
 * FARB-/DESIGN-ABHÄNGIG: die Optik kommt rein aus clickwave.css — token-getrieben
 * (folgt --cy/--mg je `farb_schema`) + pro `data-design` eine eigene Variante; neue
 * Designs erben automatisch die Basis-Variante.
 *
 * Self-contained + CSP-konform: externes Skript (kein inline-Handler), die Welle setzt
 * nur `left/top` als Style-Attribut (style-src erlaubt Attribute), Animation rein per CSS.
 * Auto-Init beim Laden. Steuerung: window.DzWave.an() / .aus().
 *
 * Styles: /ui-kit/clickwave.css (nutzt die Kit-Tokens aus tokens.css).
 */
(function () {
  "use strict";

  var AN = true;

  function reduziert() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function welle(e) {
    if (!AN || reduziert()) return;
    if (e.pointerType === "touch") return;           // kein Effekt bei Touch
    if (e.button != null && e.button !== 0) return;   // nur linke Maustaste
    var w = document.createElement("span");
    w.className = "dz-wave";
    w.style.left = e.clientX + "px";
    w.style.top = e.clientY + "px";
    document.body.appendChild(w);
    var t = setTimeout(function () { if (w.parentNode) w.remove(); }, 900);
    w.addEventListener("animationend", function () { clearTimeout(t); if (w.parentNode) w.remove(); });
  }

  function start() {
    if (!document.body) return;
    window.addEventListener("pointerdown", welle, { passive: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();

  window.DzWave = {
    an: function () { AN = true; },
    aus: function () { AN = false; },
    welle: welle,
  };
})();
