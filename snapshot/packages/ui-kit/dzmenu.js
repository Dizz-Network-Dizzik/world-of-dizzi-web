/* DzMenu — generisches Rechtsklick-„Dizzi"-Kontextmenü (netzweites ui-kit).
 * Single-Source des wiederverwendbaren Mini-Menüs (promotet 26.06. aus Dizz Memory,
 * docs/49-Welle / docs/33). Self-contained + app-neutral; CSP-konform: Klick-Handler
 * werden in JS gebunden (kein inline onclick), reine UI.
 *
 *   DzMenu.open(x, y, items, kopf?)   ·   DzMenu.close()
 *   items = [{label, icon?, run, danger?} | {trenner:true}]
 *
 * Styles: /ui-kit/dzmenu.css (nutzt die Kit-Tokens aus tokens.css).
 * Jede App liefert ihre eigenen Item-Fabriken + bindet einen `contextmenu`-Listener,
 * der das passende Menü ermittelt und `DzMenu.open(...)` aufruft.
 */
(function () {
  "use strict";

  function esc(s) {
    return (s || "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  let el = null;

  function close() {
    if (!el) return;
    el.remove(); el = null;
    document.removeEventListener("pointerdown", onDoc, true);
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("blur", close);
  }

  function onDoc(e) { if (el && !el.contains(e.target)) close(); }

  function eintraege() { return [...el.querySelectorAll(".dzmi")]; }

  function nav(d) {
    const its = eintraege(); if (!its.length) return;
    let i = its.findIndex(x => x.classList.contains("fokus"));
    i = (i + d + its.length) % its.length;
    its.forEach(x => x.classList.remove("fokus")); its[i].classList.add("fokus");
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); nav(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); nav(-1); }
    else if (e.key === "Enter") { const a = el && el.querySelector(".dzmi.fokus"); if (a) { e.preventDefault(); a.click(); } }
  }

  function open(x, y, items, kopf) {
    close();
    el = document.createElement("div"); el.className = "dzmenu"; el.setAttribute("role", "menu");
    if (kopf) { const h = document.createElement("div"); h.className = "dzm-kopf"; h.textContent = kopf; el.appendChild(h); }
    items.forEach(it => {
      if (it.trenner) { const s = document.createElement("div"); s.className = "dzmi-sep"; el.appendChild(s); return; }
      const b = document.createElement("button"); b.type = "button";
      b.className = "dzmi" + (it.danger ? " gefahr" : ""); b.setAttribute("role", "menuitem");
      b.innerHTML = `<span class="dzmi-ic">${it.icon || ""}</span><span class="dzmi-lab">${esc(it.label)}</span>`;
      b.onclick = () => { close(); try { it.run && it.run(); } catch (e) {} };
      el.appendChild(b);
    });
    document.body.appendChild(el);
    const r = el.getBoundingClientRect();
    el.style.left = Math.max(6, Math.min(x, innerWidth - r.width - 8)) + "px";
    el.style.top = Math.max(6, Math.min(y, innerHeight - r.height - 8)) + "px";
    document.addEventListener("pointerdown", onDoc, true);
    document.addEventListener("keydown", onKey, true);
    window.addEventListener("blur", close);
  }

  window.DzMenu = { open, close };
})();
