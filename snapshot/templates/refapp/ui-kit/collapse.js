/* ============================================================================
   Dizz UI-Kit · K2.4 — Collapse + Stepper (vanilla, app-neutral, 0 Imports)
   the world of dizzi/docs/06 §6 · 13.06.2026

   Verhalten zu ui-kit/controls.css. KOPIEREN, nicht neu bauen.

   - initCollapse(root): macht alle [data-dz-collapsible]-Panels einklappbar
     (Klick/Tastatur über den <button class="dz-panel-kopf">, aria-expanded,
     prefers-reduced-motion respektiert). Die Kurzanzeige (.dz-panel-kurz) blendet
     das CSS automatisch je Zustand ein/aus. Startzustand: IMMER eingeklappt
     (Auto-Collapse beim Seiten-Laden, Nutzer-Norm 18.06. — uebersichtlich auf
     den ersten Blick; bewusst per Toggle aufklappen).
   - initStepper(root): verdrahtet die ▾/▴-Knöpfe (data-dz-step="-1|1") eines
     .dz-stepper auf sein <input type=number> (Grenzen min/max/step nativ; feuert
     ein 'input'-Event, damit App-Listener greifen). ↑/↓ im Feld bleibt nativ.
   - initControls(root=document): ruft beide. Idempotent (data-dz-bereit-Marker).
   ============================================================================ */
(function (global) {
  "use strict";

  function initCollapse(root) {
    root = root || document;
    root.querySelectorAll("[data-dz-collapsible]").forEach(function (panel) {
      var kopf = panel.querySelector(".dz-panel-kopf");
      if (!kopf || kopf.dataset.dzBereit) return;
      kopf.dataset.dzBereit = "1";
      if (kopf.tagName !== "BUTTON") kopf.setAttribute("role", "button"), kopf.tabIndex = 0;
      var setze = function (offen) {
        if (offen) panel.removeAttribute("data-dz-collapsed");
        else panel.setAttribute("data-dz-collapsed", "");
        kopf.setAttribute("aria-expanded", offen ? "true" : "false");
      };
      // Auto-Collapse (Nutzer-Norm 18.06.): beim Seiten-Laden starten ALLE Panels
      // EINGEKLAPPT (uebersichtlich; Kurzanzeige .dz-panel-kurz zeigt schon Kennzahlen).
      // Markup-Attribut data-dz-collapsed ist damit egal — Aufklappen nur per Toggle.
      setze(false);
      kopf.addEventListener("click", function (e) {
        // NUR der Toggle-Knopf vorne klappt (Maus); Tastatur (detail===0) togglet immer.
        if (e.detail !== 0 && !(e.target.closest && e.target.closest(".dz-chevron"))) return;
        setze(panel.hasAttribute("data-dz-collapsed"));
      });
      // Tastatur, falls kopf kein <button> ist:
      kopf.addEventListener("keydown", function (e) {
        if (kopf.tagName === "BUTTON") return;
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); kopf.click(); }
      });
    });
  }

  function initStepper(root) {
    root = root || document;
    root.querySelectorAll(".dz-stepper").forEach(function (stepper) {
      if (stepper.dataset.dzBereit) return;
      stepper.dataset.dzBereit = "1";
      var feld = stepper.querySelector('input[type="number"]');
      if (!feld) return;
      stepper.querySelectorAll("[data-dz-step]").forEach(function (knopf) {
        knopf.addEventListener("click", function () {
          var n = parseInt(knopf.getAttribute("data-dz-step"), 10) || 0;
          if (n > 0) feld.stepUp(n); else feld.stepDown(-n);
          feld.dispatchEvent(new Event("input", { bubbles: true }));
          feld.dispatchEvent(new Event("change", { bubbles: true }));
        });
      });
    });
  }

  function initControls(root) {
    initCollapse(root);
    initStepper(root);
  }

  var api = { initCollapse: initCollapse, initStepper: initStepper, initControls: initControls };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else { global.DzControls = api; }

  // Auto-Init beim Laden (idempotent; bei dynamischem Markup erneut initControls()).
  if (typeof document !== "undefined") {
    if (document.readyState === "loading")
      document.addEventListener("DOMContentLoaded", function () { initControls(document); });
    else initControls(document);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
