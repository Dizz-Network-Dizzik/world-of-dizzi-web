/* DzBereichBar — geteilte Bereichs-Filter-Leiste (Chip-Leiste) für das ui-kit.
 * Single-Source der „Area"-Filterleiste der Satelliten-Apps (Money · Memory · Management);
 * vereinheitlicht W4 (docs/33) das vorher 3× divergente Markup (bereichbar/bereich-bar/…),
 * die Klassennamen, die Begriffe („Alle Bereiche") und die Typ-Farben.
 *
 * Admin behält bewusst seine Bereich-first-KARTEN-Navigation (docs/49 — die Filterzeile
 * wurde dort entfernt); diese Leiste ist die FILTER-Achse der lose gekoppelten Satelliten.
 *
 *   const bar = DzBereichBar.mount(host, cfg);   bar.set(bereiche, aktiv);   bar.aktiv();
 *
 * cfg = {
 *   bereiche:  [{id, name, art, farbe?}],   // aktive Bereiche
 *   aktiv:     '',                          // aktiver Bereich-id ('' = Alle)
 *   typMeta:   { <art>: {icon, farbe} },    // app-eigener art-Katalog → Icon + TYP-Farbe (Nutzer-Wahl 2/3)
 *   onWaehl:   (id) => {},                  // Klick auf einen Chip (Filter setzen)
 *   titel:     'Bereich',                   // Leisten-Titel
 *   alleLabel: 'Alle Bereiche',             // Reset-Chip-Text (netzweit gleich)
 *   alleIcon:  '⊛',                         // Icon des Reset-Chips
 *   neu:       {label, run} | null,         // optionaler „+ Neuer Bereich"-Chip
 * }
 *
 * CSP-konform: Klick-Handler werden in JS gebunden (kein inline onclick); reine UI.
 * Styles: /ui-kit/bereichbar.css (nutzt die Kit-Tokens aus tokens.css).
 */
(function () {
  "use strict";

  // Farb-NAME → (CSS-Wert, RGB-Tripel). Zentralisiert die vorher je App divergenten
  // Mappings; violett hat kein Token (Literal wie in Admin), Rest = theme-aware Tokens.
  const FARBEN = {
    cyan:    { c: "var(--cy)",   rgb: "var(--cy-rgb)" },
    magenta: { c: "var(--mg)",   rgb: "var(--mg-rgb)" },
    gruen:   { c: "var(--ok)",   rgb: "var(--ok-rgb)" },
    amber:   { c: "var(--warn)", rgb: "var(--warn-rgb)" },
    rot:     { c: "var(--bad)",  rgb: "var(--bad-rgb)" },
    violett: { c: "#b18cff",     rgb: "177,140,255" },
  };

  function esc(s) {
    return (s || "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  // Typ-Farbe eines Bereichs: zuerst aus dem art-Katalog (Nutzer-Wahl „Farbe je Typ"),
  // sonst aus dem gespeicherten ``farbe``-Feld, sonst cyan.
  function farbeVon(b, typMeta) {
    const tm = (typMeta && typMeta[b.art]) || null;
    const name = (tm && tm.farbe) || b.farbe || "cyan";
    return FARBEN[name] || FARBEN.cyan;
  }
  function iconVon(b, typMeta) {
    const tm = (typMeta && typMeta[b.art]) || null;
    return (tm && tm.icon) || "📁";
  }

  function mount(host, cfg) {
    if (!host) return null;
    cfg = cfg || {};
    const state = {
      bereiche: cfg.bereiche || [],
      aktiv: cfg.aktiv || "",
      typMeta: cfg.typMeta || {},
      onWaehl: cfg.onWaehl || function () {},
      titel: cfg.titel || "Bereich",
      alleLabel: cfg.alleLabel || "Alle Bereiche",
      alleIcon: ("alleIcon" in cfg) ? cfg.alleIcon : "⊛",
      neu: cfg.neu || null,
    };
    host.classList.add("dz-berbar");
    host.setAttribute("role", "tablist");
    host.setAttribute("aria-label", "Bereiche");

    function chip(id, label, farbe, icon, aktiv, extraCls) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "dz-berchip" + (aktiv ? " on" : "") + (extraCls ? " " + extraCls : "");
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", aktiv ? "true" : "false");
      if (id !== null) b.dataset.bid = id;
      if (farbe) b.style.cssText = "--acc:" + farbe.c + ";--acc-rgb:" + farbe.rgb;
      let inner = "";
      if (farbe) inner += '<span class="bc-dot" aria-hidden="true"></span>';
      if (icon) inner += '<span class="bc-ic" aria-hidden="true">' + esc(icon) + "</span>";
      inner += '<span class="bc-lab">' + esc(label) + "</span>";
      b.innerHTML = inner;
      return b;
    }

    function render() {
      host.textContent = "";
      if (state.titel) {
        const t = document.createElement("span");
        t.className = "dz-berbar-titel";
        t.textContent = state.titel;
        host.appendChild(t);
      }
      // Reset-Chip „Alle Bereiche" (netzweit identische Affordanz)
      const alle = chip("", state.alleLabel, null, state.alleIcon, !state.aktiv, "alle");
      alle.onclick = () => waehl("");
      host.appendChild(alle);
      // ein Chip je Bereich (Typ-Farbe + Typ-Icon)
      (state.bereiche || []).forEach(b => {
        const c = chip(b.id, b.name, farbeVon(b, state.typMeta), iconVon(b, state.typMeta),
                       state.aktiv === b.id, null);
        c.title = b.name + (b.art ? " · " + b.art : "");
        c.onclick = () => waehl(b.id);
        host.appendChild(c);
      });
      // optionaler „+ Neuer Bereich"-Chip (gestrichelt)
      if (state.neu) {
        const n = chip(null, state.neu.label || "+ Neuer Bereich", null, "", false, "neu");
        n.onclick = () => { try { state.neu.run && state.neu.run(); } catch (e) {} };
        host.appendChild(n);
      }
    }

    function waehl(id) {
      state.aktiv = id || "";
      render();
      try { state.onWaehl(state.aktiv); } catch (e) {}
    }

    render();
    return {
      set(bereiche, aktiv) {
        if (bereiche !== undefined) state.bereiche = bereiche || [];
        if (aktiv !== undefined) state.aktiv = aktiv || "";
        render();
      },
      aktiv() { return state.aktiv; },
      el: host,
    };
  }

  window.DzBereichBar = { mount, FARBEN };
})();
