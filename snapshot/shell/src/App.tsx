import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchPanels, fetchSettings, putSetting, type PanelManifest } from "./api";
import { DizziConsole } from "./ChatDock";
import { FloatingSettings } from "./FloatingSettings";
import { PanelCard } from "./PanelCard";
import { initSpinFling } from "./spinFling";

// Standard-Reihenfolge (Vision docs/00); Nutzer-Sortierung übersteuert sie
// und wird user-scoped im Core gespeichert (Setting "panel_order").
// Top-2 = Detail: standardmäßig die zwei aktiven Panels.
const DEFAULT_ORDER = [
  "systeminfo", "tradingbot", "health", "finanzen", "admin",
  "memory", "news", "kommunikation", "management", "creator",
];

function sortByOrder(panels: PanelManifest[], order: string[]): PanelManifest[] {
  const pos = (id: string) => {
    const i = order.indexOf(id);
    return i === -1 ? order.length + DEFAULT_ORDER.indexOf(id) : i;
  };
  return [...panels].sort((a, b) => pos(a.id) - pos(b.id));
}

export default function App() {
  const { t, i18n } = useTranslation();
  const [panels, setPanels] = useState<PanelManifest[] | null>(null);
  const [error, setError] = useState(false);
  const panelsRef = useRef<PanelManifest[] | null>(null);
  panelsRef.current = panels;

  useEffect(() => {
    Promise.all([fetchPanels(), fetchSettings().catch(() => ({}))])
      .then(([p, s]) => {
        const cfg = s as { panel_order?: string[]; lang?: string; design_vorlage?: string; farb_schema?: string };
        setPanels(sortByOrder(p, cfg.panel_order ?? DEFAULT_ORDER));
        if (cfg.lang) void i18n.changeLanguage(cfg.lang);
        // K2.2: Theme-Stand des Servers anwenden (überschreibt den localStorage-Anti-FOUC).
        const dh = document.documentElement;
        if (cfg.design_vorlage) { dh.dataset.design = cfg.design_vorlage;
          try { localStorage.setItem("dizzi_design", cfg.design_vorlage); } catch { /* kein localStorage */ } }
        if (cfg.farb_schema) { dh.dataset.farbe = cfg.farb_schema;
          try { localStorage.setItem("dizzi_farbe", cfg.farb_schema); } catch { /* kein localStorage */ } }
      })
      .catch(() => setError(true));
  }, [i18n]);

  // Panel über einem anderen losgelassen ⇒ die beiden TAUSCHEN die Plätze
  // (Nutzer-Wunsch 11.06.); Reihenfolge wird persistiert.
  const reorder = (draggedId: string, targetId: string) => {
    const cur = panelsRef.current;
    if (!cur || draggedId === targetId) return;
    const ia = cur.findIndex((p) => p.id === draggedId);
    const ib = cur.findIndex((p) => p.id === targetId);
    if (ia < 0 || ib < 0) return;
    const next = [...cur];
    [next[ia], next[ib]] = [next[ib], next[ia]];
    setPanels(next);
    void putSetting("panel_order", next.map((p) => p.id));
  };

  // Spin-Physik (Spec docs/14): greifen → schwingen → schleudern → Impuls aufs schwebende
  // Element; sanftes Ablegen = Reorder. Erst aktiv, wenn Panels gerendert sind.
  useEffect(() => {
    if (!panels) return;
    const dispose = initSpinFling({
      gridSelector: "main",
      cardSelector: ".grid .card",
      floatSelector: ".floatset",
      onReorder: reorder,
    });
    return dispose;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panels !== null]);

  const renderCard = (detailed: boolean) => (p: PanelManifest) => (
    <PanelCard key={p.id} panel={p} detailed={detailed} />
  );

  return (
    <>
      <div className="bgfx" />
      <div className="bgbrush" />
      <FloatingSettings />
      <header className="apphead">
        <h1>the world of dizzi</h1>
        <span className="sub">{t("subtitle")}</span>
        <span className="spacer" />
        {/* Netz-Ansichten (same-origin über Core-Route /netz/*): Gesamtsystem-Karte + Projektplan,
            im selben Stil, immer erreichbar. Öffnen in neuem Tab. */}
        <nav className="headnav" aria-label="Netz-Ansichten">
          <a className="headlink" href="/netz/SYSTEM_KARTE.html" target="_blank" rel="noopener">🗺️ Systemkarte</a>
          <a className="headlink" href="/netz/PROJEKT_STAND.html" target="_blank" rel="noopener">📊 Projektplan</a>
        </nav>
      </header>
      <div className="headline"><i /></div>
      <DizziConsole />
      {error && <div className="errbox">{t("core_error")}</div>}
      {!error && !panels && <div className="loading">{t("loading")}</div>}
      {panels && (
        <main>
          {/* Oben zwei breite Detail-Panels; darunter alle übrigen als Zweierraster.
              Panels sind greif-/schleuderbar (Spin-Physik); sanftes Ablegen = Reorder. */}
          <div className="grid detailed">
            {panels.slice(0, 2).map(renderCard(true))}
          </div>
          {panels.length > 2 && (
            <div className="grid compact">
              {panels.slice(2).map(renderCard(false))}
            </div>
          )}
        </main>
      )}
    </>
  );
}
