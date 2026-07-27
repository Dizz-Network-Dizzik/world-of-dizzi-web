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
   - initUpload(root): verdrahtet jede <label class="dz-upload" data-dz-upload> mit
     ihrem <input type=file> — Klick öffnet die Dateiwahl (native Label-Mechanik),
     Drag&Drop setzt die Datei, der gewählte Name/Größe wird angezeigt, ✕ entfernt.
     Feuert das native 'change'-Event ⇒ die App macht den eigentlichen Upload.
   - initControls(root=document): ruft alle drei. Idempotent (data-dz-bereit-Marker).
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
      // Norm v2 (docs/70 §3.3, F-3 — Opt-in): traegt ein Panel `data-dz-offen`,
      // startet ES offen — „pro App EINE Default-offene Kern-Sektion", damit die
      // App beim Oeffnen ihren Inhalt zeigt (docs/60 NE-1). Ohne Attribut: wie bisher.
      setze(panel.hasAttribute("data-dz-offen"));
      kopf.addEventListener("click", function (e) {
        // NUR der Toggle-Knopf vorne klappt (Maus); Tastatur (detail===0) togglet immer.
        // Norm v2 (docs/70 §3.3, F-3 — Opt-in): traegt das Panel ODER ein Vorfahre
        // `data-dz-kopf-klick` (z. B. <body> = App-weit), klappt der GANZE Kopf —
        // echte Aktions-Elemente im Kopf (Links/Buttons/Inputs, nicht der Kopf
        // selbst) werden dabei nicht gekapert. Ohne Attribut: exakt wie bisher.
        if (e.detail !== 0 && !(e.target.closest && e.target.closest(".dz-chevron"))) {
          if (!(panel.closest && panel.closest("[data-dz-kopf-klick]"))) return;
          var akt = e.target.closest && e.target.closest("a,button,input,select,label,[data-dz-act]");
          if (akt && akt !== kopf) return;
        }
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

  function initUpload(root) {
    root = root || document;
    root.querySelectorAll("[data-dz-upload]").forEach(function (wrap) {
      if (wrap.dataset.dzBereit) return;
      wrap.dataset.dzBereit = "1";
      var input = wrap.querySelector('input[type="file"]');
      if (!input) return;
      var nameEl = wrap.querySelector(".dz-upload-name");
      var fileRow = wrap.querySelector(".dz-upload-file");
      function kb(n) { return n < 1024 ? n + " B" : (n < 1048576 ? Math.round(n / 1024) + " KB" : (n / 1048576).toFixed(1) + " MB"); }
      function zeige() {
        var f = input.files && input.files[0];
        if (f) {
          if (nameEl) nameEl.textContent = f.name + " · " + kb(f.size);
          if (fileRow) fileRow.hidden = false;
          wrap.classList.add("dz-has-file");
        } else {
          if (fileRow) fileRow.hidden = true;
          wrap.classList.remove("dz-has-file");
        }
      }
      input.addEventListener("change", zeige);
      // Drag & Drop (der gewrappte <input> öffnet die Dateiwahl per nativem Label-Klick).
      ["dragenter", "dragover"].forEach(function (ev) {
        wrap.addEventListener(ev, function (e) { e.preventDefault(); wrap.classList.add("dz-drag"); });
      });
      ["dragleave", "dragend", "drop"].forEach(function (ev) {
        wrap.addEventListener(ev, function (e) {
          if (ev !== "drop" && wrap.contains(e.relatedTarget)) return;
          wrap.classList.remove("dz-drag");
        });
      });
      wrap.addEventListener("drop", function (e) {
        e.preventDefault();
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
          try { input.files = e.dataTransfer.files; } catch (_) {}
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
      // ✕ entfernen (preventDefault, sonst öffnet der Label-Klick die Dateiwahl erneut).
      var clear = wrap.querySelector(".dz-upload-clear");
      if (clear) clear.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        input.value = ""; input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  }

  // --- Event-Delegation für CSP-strikt (ersetzt inline onclick=) --------------
  // Eine strikte Nonce-CSP (script-src 'self' 'nonce-…') BLOCKT inline-Handler
  // (onclick="fn(arg)"). Ersatz ohne UI-Bruch:
  //   <button data-dz-act="fn" data-dz-arg="…">      (Klick)
  //   <select data-dz-act="fn" data-dz-on="change">  (anderes Event)
  // EIN delegierter Listener (document-Ebene, überlebt Re-Renders) ruft
  //   (DzControls.registerAction-Handler ODER window[fn])(arg, el, event).
  // Migration: onclick="setBereich('b1')"  ->  data-dz-act="setBereich" data-dz-arg="b1".
  // Mehr-Argument-Handler: in der App einen Wrapper registrieren oder data-dz-arg
  // als JSON + im Handler parsen.
  var _actsGebunden = false;
  var _actHandlers = {};
  function _actDispatch(ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest("[data-dz-act]") : null;
    if (!el) return;
    if ((el.getAttribute("data-dz-on") || "click") !== ev.type) return;
    var name = el.getAttribute("data-dz-act");
    var fn = _actHandlers[name] || (typeof window !== "undefined" ? window[name] : null);
    if (typeof fn !== "function") return;
    ev.preventDefault();
    var arg = el.getAttribute("data-dz-arg");
    fn(arg == null ? undefined : arg, el, ev);
  }
  function initActions() {
    if (_actsGebunden || typeof document === "undefined") return;
    _actsGebunden = true;                       // EIN Mal global delegieren
    document.addEventListener("click", _actDispatch, false);
    document.addEventListener("change", _actDispatch, false);
  }
  function registerAction(name, fn) { _actHandlers[name] = fn; }

  function initControls(root) {
    initCollapse(root);
    initStepper(root);
    initUpload(root);
    initActions();
  }

  var api = { initCollapse: initCollapse, initStepper: initStepper, initUpload: initUpload,
              initActions: initActions, registerAction: registerAction, initControls: initControls };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else { global.DzControls = api; }

  // Auto-Init beim Laden (idempotent; bei dynamischem Markup erneut initControls()).
  if (typeof document !== "undefined") {
    if (document.readyState === "loading")
      document.addEventListener("DOMContentLoaded", function () { initControls(document); });
    else initControls(document);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
