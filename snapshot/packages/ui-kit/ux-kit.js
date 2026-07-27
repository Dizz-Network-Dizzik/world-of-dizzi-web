/* ============================================================================
   ux-kit.js — UX-Konsolidierungs-Bausteine (docs/70 §3 · F-1…F-8 + MG-1)
   KANONISCH (Architektur-KI-Vertrag 04.07.2026). Optik: ui-kit/ux-kit.css.

   API (window.DzUx):
   - netzleiste(el?)                      F-1: ⌂-Netz-Knopf + App-Popover in den .dz-appkopf
   - gesperrt(el, {grund, loginUrl, zurueck})   F-2: 🔒-Fläche mit Anmelde-CTA
   - gesperrtKpis(el, labels)             F-2: KPI-Zeile als „🔒 •••"-Masken
   - leer(el, {text, cta:{label, act, arg}})    F-7: Leer-Zustand MIT nächstem Schritt
   - toast(text, {art:'ok'|'warn'|'fehler'})    F-7: Quittung, aria-live, auto-dismiss
   - bestaetigen({aktion, objekt, gefahr, knopf}) -> Promise<bool>   F-7: Kontext-Confirm
   - agentchip({name, rolle, status, ki, titel}) -> HTML             MG-1 / AI-Act 50(1)
   - oeffnePanel(panelOderSelector)       F-3/ME-1: Ziel-Panel öffnen + hinscrollen
   - pruefeTooltips(root?) -> Element[]   F-5: Dev-Lint „interaktiv ohne Label/Tooltip"
   - format.datum(wert, {mitZeit, jetzt}) F-8: deutsch-relativ (regelgleich mit
     appkit/sprachregister.datum_de — bei Regeländerung BEIDE anfassen!)
   - format.kuerzel('K')                  F-6: plattformrichtig „Strg K" / „⌘K"
   - format.ANREDE / ANMELDE_PILL         F-8-Norm-Konstanten

   CSP-strikt-tauglich: keine Inline-Handler, keine eval-Nutzung, kein Inline-CSS.
   Stufe-0: nichts läuft automatisch — jede Wirkung ist ein expliziter Aufruf.
   ============================================================================ */
window.DzUx = (function () {
  "use strict";

  var esc = function (s) {
    return (s == null ? "" : String(s)).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  // ── F-8 · Format-Normen ────────────────────────────────────────────────────
  var WOCHENTAGE = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"]; // getDay()-Ordnung
  function p2(n) { return (n < 10 ? "0" : "") + n; }
  function parseDatum(w) {
    if (w instanceof Date) return isNaN(w.getTime()) ? null : w;
    if (typeof w !== "string" || !w.trim()) return null;
    var d = new Date(w.trim());                 // Browser parsen ISO-8601 UND RFC-822
    return isNaN(d.getTime()) ? null : d;
  }
  function datum(wert, o) {
    o = o || {};
    var d = parseDatum(wert);
    if (!d) return String(wert);                // ehrlich: Rohstring, nie "Invalid Date"
    var mitZeit = o.mitZeit !== false;
    var jetzt = (o.jetzt instanceof Date) ? o.jetzt : new Date();
    var heute = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate());
    var tag = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var alter = Math.round((heute - tag) / 86400000);
    var zeit = mitZeit ? (" " + p2(d.getHours()) + ":" + p2(d.getMinutes())) : "";
    var dm = p2(d.getDate()) + "." + p2(d.getMonth() + 1) + ".";
    if (alter === 0) return "heute" + zeit;
    if (alter === 1) return "gestern" + zeit;
    if (alter > 1 && alter <= 6) return WOCHENTAGE[d.getDay()] + " " + dm;
    if (d.getFullYear() === jetzt.getFullYear()) return dm;
    return dm + d.getFullYear();
  }
  function kuerzel(taste) {                     // F-6: nie ⌘ auf Windows (docs/60 KO-6)
    var mac = /mac|iphone|ipad|ipod/i.test(navigator.platform || navigator.userAgent || "");
    return mac ? "⌘" + taste : "Strg " + taste;
  }
  var format = {
    datum: datum, kuerzel: kuerzel,
    ANREDE: "du",                                          // Gate G-UX-ANREDE (docs/70 §3.8)
    ANMELDE_PILL_ABGEMELDET: "Anmelden (Dizzi-ID)",        // EIN Wortlaut netzweit
    ANMELDE_PILL_ANGEMELDET: "{anzeigename} · {stufe}"
  };

  // ── F-7 · Toast ────────────────────────────────────────────────────────────
  function toast(text, o) {
    o = o || {};
    var wrap = document.querySelector(".dz-toasts");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "dz-toasts";
      wrap.setAttribute("role", "status");
      wrap.setAttribute("aria-live", "polite");
      document.body.appendChild(wrap);
    }
    var t = document.createElement("div");
    t.className = "dz-toast" + (o.art ? " " + o.art : "");
    t.textContent = String(text == null ? "" : text);
    wrap.appendChild(t);
    var dauer = o.dauer || 4000;
    setTimeout(function () {
      t.classList.add("weg");
      setTimeout(function () { t.remove(); }, 260);
    }, dauer);
    return t;
  }

  // ── F-7 · Leer-Zustand (Norm-Formel: „Noch kein X — nächster Schritt") ─────
  function leer(el, o) {
    o = o || {};
    var cta = o.cta ? ('<button type="button" class="dz-btn" data-dz-act="' + esc(o.cta.act) + '"'
      + (o.cta.arg != null ? ' data-dz-arg="' + esc(o.cta.arg) + '"' : "")
      + ">" + esc(o.cta.label) + "</button>") : "";
    el.innerHTML = '<div class="dz-leer">'
      + '<span class="le-glyph" aria-hidden="true">' + esc(o.glyph || "◌") + "</span>"
      + '<span class="le-text">' + esc(o.text || "Noch nichts hier.") + "</span>" + cta + "</div>";
  }

  // ── F-2 · Gesperrt-Zustand (🔒 statt stiller Leere; G-UX-AUTH) ─────────────
  function loginHref(loginUrl, zurueck) {
    var basis = loginUrl || "/id/login";
    var z = encodeURIComponent(zurueck || window.location.href);
    return basis + (basis.indexOf("?") < 0 ? "?" : "&") + "zurueck=" + z;
  }
  function gesperrt(el, o) {
    o = o || {};
    el.innerHTML = '<div class="dz-gesperrt">'
      + '<span class="gs-glyph" aria-hidden="true">🔒</span>'
      + '<span class="gs-text">' + esc(o.grund || "Dieser Bereich ist gesperrt.") + "</span>"
      + '<a class="dz-btn" href="' + esc(loginHref(o.loginUrl, o.zurueck)) + '">'
      + esc(format.ANMELDE_PILL_ABGEMELDET) + "</a>"
      + (o.hinweis ? '<span class="gs-hinweis">' + esc(o.hinweis) + "</span>" : "")
      + "</div>";
  }
  function gesperrtKpis(el, labels) {
    el.innerHTML = (labels || []).map(function (l) {
      return '<span class="dz-kpi-gesperrt"><span class="kg-label">' + esc(l)
        + '</span><span class="kg-wert">🔒 •••</span></span>';
    }).join(" ");
  }

  // ── F-7 · Kontext-Confirm (nennt IMMER das echte Objekt — docs/60 ME-2) ────
  function bestaetigen(o) {
    o = o || {};
    return new Promise(function (loese) {
      var wrap = document.createElement("div");
      wrap.className = "dz-confirm-wrap";
      wrap.innerHTML = '<div class="dz-confirm' + (o.gefahr ? " gefahr" : "") + '" role="alertdialog" aria-modal="true">'
        + '<h2 class="cf-titel">' + esc(o.titel || "Bist du sicher?") + "</h2>"
        + '<p class="cf-text">' + esc(o.aktion || "Aktion ausführen")
        + (o.objekt ? ": <b>" + esc(o.objekt) + "</b>" : "") + "?</p>"
        + '<div class="cf-knoepfe">'
        + '<button type="button" class="dz-btn" data-cf="nein">Abbrechen</button>'
        + '<button type="button" class="dz-btn' + (o.gefahr ? " gefahr" : "") + '" data-cf="ja">'
        + esc(o.knopf || o.aktion || "OK") + "</button></div></div>";
      document.body.appendChild(wrap);
      function fertig(ja) { wrap.remove(); document.removeEventListener("keydown", aufEsc); loese(ja); }
      function aufEsc(e) { if (e.key === "Escape") { e.preventDefault(); fertig(false); } }
      wrap.addEventListener("click", function (e) {
        if (e.target === wrap) return fertig(false);            // Backdrop = Abbruch
        var k = e.target.closest && e.target.closest("[data-cf]");
        if (k) fertig(k.getAttribute("data-cf") === "ja");
      });
      document.addEventListener("keydown", aufEsc);
      // Gefahr: Fokus auf „Abbrechen" (bewusster Klick nötig, kein Enter-Unfall).
      var fokus = wrap.querySelector(o.gefahr ? '[data-cf="nein"]' : '[data-cf="ja"]');
      if (fokus) fokus.focus();
    });
  }

  // ── MG-1 · Agenten-Chip („Wer hat das getan?" + AI-Act-50(1)-Label) ────────
  function agentchip(o) {
    o = o || {};
    var punkt = { laeuft: "an", wartet: "wartet", aus: "aus" }[o.status] || "aus";
    var titel = o.titel || (o.ki
      ? "Du sprichst mit einer KI (läuft lokal auf deinem Rechner)."
      : "Von einem KI-Agenten erstellt" + (o.rolle ? " — Rolle: " + o.rolle : "")
        + " · arbeitet nur mit deiner Freigabe.");
    return '<span class="dz-agentchip" data-dz-tip="' + esc(titel) + '" title="' + esc(titel)
      + '" aria-label="' + esc(titel) + '">'
      + '<span class="ac-dot ' + punkt + '" aria-hidden="true"></span>'
      + esc(o.ki ? "KI" : (o.name || "Agent"))
      + (o.rolle && !o.ki ? '<span class="ac-rolle">· ' + esc(o.rolle) + "</span>" : "")
      + "</span>";
  }

  // ── F-3/ME-1 · Ziel-Panel öffnen (Aktionen in eingeklappte Panels) ─────────
  function oeffnePanel(ziel) {
    var panel = typeof ziel === "string" ? document.querySelector(ziel) : ziel;
    if (!panel) return null;
    panel.removeAttribute("data-dz-collapsed");
    var kopf = panel.querySelector(".dz-panel-kopf");
    if (kopf) kopf.setAttribute("aria-expanded", "true");
    if (panel.scrollIntoView) panel.scrollIntoView({ block: "nearest" });
    if (kopf && kopf.focus) kopf.focus({ preventScroll: true });
    return panel;
  }

  // ── F-5 · Dev-Lint: interaktive Elemente ohne Label/Tooltip ────────────────
  function pruefeTooltips(root) {
    root = root || document;
    var kandidaten = root.querySelectorAll(
      'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"]');
    var funde = [];
    kandidaten.forEach(function (el) {
      var text = (el.textContent || "").trim();
      var beschriftet = text || el.getAttribute("title") || el.getAttribute("aria-label")
        || el.getAttribute("aria-labelledby")
        || (el.labels && el.labels.length) || (el.closest && el.closest("label"));
      if (!beschriftet) funde.push(el);
    });
    if (funde.length && window.console && console.warn) {
      console.warn("DzUx.pruefeTooltips: " + funde.length
        + " interaktive Elemente ohne Label/title/aria-label (F-5-Norm docs/70 §3.5):", funde);
    }
    return funde;
  }

  // ── F-1 · Netz-Leiste (⌂-Knopf + App-Popover im dz-appkopf) ────────────────
  var _netzDaten = null;
  function holeNetz() {
    if (_netzDaten) return Promise.resolve(_netzDaten);
    return fetch("/api/netz/apps").then(function (r) {
      if (!r.ok) throw new Error("netz " + r.status);
      return r.json();
    }).then(function (d) { _netzDaten = d; return d; }).catch(function () {
      // Ehrlicher Fallback (docs/70 §3.1): nur der Zentrale-Link, nie ein leeres Popover.
      return { core_url: "http://127.0.0.1:8200", apps: [] };
    });
  }
  function baueNetzPop(knopf, d) {
    var pop = document.createElement("nav");
    pop.className = "dz-netz-pop";
    pop.setAttribute("aria-label", "Netz: Zentrale und Apps");
    var aktuellerPort = window.location.port;
    var html = '<div class="nz-titel">the world of dizzi</div>'
      + '<a class="dz-netz-item zentrale" href="' + esc(d.core_url) + '">'
      + '<span class="nz-brand">⌂ Zur Zentrale</span><span class="nz-fn">Dizzi-Core</span></a>';
    (d.apps || []).forEach(function (a) {
      if (a.id === "core") return;                       // Zentrale steht schon oben
      var aktiv = String(a.port) === aktuellerPort;
      html += '<a class="dz-netz-item' + (aktiv ? " aktiv" : "") + '" href="' + esc(a.url) + '">'
        + '<span class="nz-brand">' + esc(a.brand) + "</span>"
        + '<span class="nz-fn">' + esc(a.name) + "</span>"
        + (a.sensitivity === "hoechst"
          ? '<span class="nz-schild" title="Höchst sensibel — lokal-only">🛡</span>' : "")
        + "</a>";
    });
    pop.innerHTML = html;
    var r = knopf.getBoundingClientRect();
    pop.style.top = Math.round(r.bottom + 8) + "px";
    pop.style.right = Math.max(8, Math.round(window.innerWidth - r.right)) + "px";
    return pop;
  }
  function netzleiste(el) {
    var kopf = el || document.querySelector(".dz-appkopf");
    if (!kopf || kopf.querySelector(".dz-netzknopf")) return null;
    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "dz-netzknopf";
    knopf.textContent = "⌂ Netz";
    knopf.title = "Zur Zentrale und zu den anderen Apps";
    knopf.setAttribute("aria-haspopup", "menu");
    knopf.setAttribute("aria-expanded", "false");
    var pille = kopf.querySelector(".pill");
    kopf.insertBefore(knopf, pille || null);             // vor der Auth-Pille (docs/70 §3.1)
    var pop = null;
    function zu() {
      if (pop) { pop.remove(); pop = null; }
      knopf.setAttribute("aria-expanded", "false");
      document.removeEventListener("click", draussen, true);
      document.removeEventListener("keydown", aufEsc);
    }
    function draussen(e) { if (pop && !pop.contains(e.target) && e.target !== knopf) zu(); }
    function aufEsc(e) { if (e.key === "Escape") { zu(); knopf.focus(); } }
    knopf.addEventListener("click", function () {
      if (pop) return zu();
      holeNetz().then(function (d) {
        if (pop) return;                                  // Doppelklick-Schutz
        pop = baueNetzPop(knopf, d);
        document.body.appendChild(pop);
        knopf.setAttribute("aria-expanded", "true");
        document.addEventListener("click", draussen, true);
        document.addEventListener("keydown", aufEsc);
        var erster = pop.querySelector("a");
        if (erster) erster.focus();
      });
    });
    return knopf;
  }

  return { netzleiste: netzleiste, gesperrt: gesperrt, gesperrtKpis: gesperrtKpis,
           leer: leer, toast: toast, bestaetigen: bestaetigen, agentchip: agentchip,
           oeffnePanel: oeffnePanel, pruefeTooltips: pruefeTooltips, format: format };
})();
