/* ============================================================================
   Dizz Background — background.js  v1.0  (D5-Slot · 14.06.2026)
   the world of dizzi/docs/24 D5

   ZWECK: Renderer-Register für den #bg-stage-Slot (hinter .bgfx).
   Aktuell: NUR die Infrastruktur (Register + Activate); keine Renderer gebaut.
   Spätere Renderer: registerBackground('name', stageEl => { ... canvas/webgl-init ... });

   ANBINDUNG:
     <script src="/ui-kit/background.js?v=20260614d" defer></script>
   Dann: DizzBackground.activate('name') oder 'none' um zu deaktivieren.
   Settings-Hook: beim design_vorlage-Wechsel activate(newDesign) aufrufen
   (opt-in, reduced-motion-geprüft).
   ============================================================================ */
(function (global) {
  'use strict';

  const _registry = {};
  let _active = null;
  let _stage = null;

  function _getStage() {
    if (!_stage) _stage = document.getElementById('bg-stage');
    return _stage;
  }

  /* Renderer registrieren: registerBackground('myEffect', stageEl => { … }) */
  function register(name, initFn) {
    _registry[name] = initFn;
  }

  /* Renderer aktivieren (name = null/'none' zum Deaktivieren). */
  function activate(name) {
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const stage = _getStage();
    if (!stage) return;
    /* Vorherigen Renderer aufräumen */
    if (_active) {
      stage.innerHTML = '';
      stage.style.display = 'none';
      _active = null;
    }
    if (!name || name === 'none' || !_registry[name]) return;
    stage.style.display = 'block';
    _registry[name](stage);
    _active = name;
  }

  function deactivate() { activate(null); }

  function isActive() { return _active; }

  global.DizzBackground = { register, activate, deactivate, isActive };

})(window);
