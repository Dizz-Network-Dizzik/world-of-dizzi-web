import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  fetchStats, type ContractStats, type PanelManifest, type SysteminfoStats,
  type TradingbotMeta, type TradingbotStats,
} from "./api";
import { Icon } from "./icons";

function Bar({ pct }: { pct: number }) {
  const lvl = pct >= 90 ? "badlvl" : pct >= 70 ? "warnlvl" : "";
  return (
    <div className={`bar ${lvl}`}>
      <i style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}

function fmtUptime(s: number): string {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d} d ${h} h`;
  return h > 0 ? `${h} h ${m} min` : `${m} min`;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="inforow">
      <span className="ik">{label}</span>
      <span className="iv">{value}</span>
    </div>
  );
}

function SysteminfoBody({ detail }: { detail: boolean }) {
  const { t } = useTranslation();
  const [s, setS] = useState<SysteminfoStats | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => fetchStats<SysteminfoStats>("systeminfo").then((d) => alive && setS(d)).catch(() => {});
    load();
    const iv = setInterval(load, detail ? 2000 : 8000); // im Detail häufiger
    return () => { alive = false; clearInterval(iv); };
  }, [detail]);

  if (!s) return null;
  if (!detail) {
    return (
      <div className="compactline num">
        CPU {s.cpu_pct.toFixed(0)} % · RAM {s.ram_pct.toFixed(0)} %
        {s.gpu && ` · GPU ${s.gpu.util_pct.toFixed(0)} %`}
      </div>
    );
  }
  const vramPct = s.gpu ? (s.gpu.vram_used_mb / s.gpu.vram_total_mb) * 100 : 0;
  const dz = s.dizzi;
  return (
    <>
      <div className="stats num">
        <div className="stat">
          <div className="lbl">{t("cpu")}</div>
          <div className="val">{s.cpu_pct.toFixed(0)} %</div>
          <Bar pct={s.cpu_pct} />
        </div>
        <div className="stat">
          <div className="lbl">{t("ram")}</div>
          <div className="val">{s.ram_used_gb.toFixed(0)} <small>/ {s.ram_total_gb.toFixed(0)} GB</small></div>
          <Bar pct={s.ram_pct} />
        </div>
        {s.gpu && (
          <>
            <div className="stat">
              <div className="lbl">{t("gpu")} · {s.gpu.temp_c.toFixed(0)} °C</div>
              <div className="val">{s.gpu.util_pct.toFixed(0)} %</div>
              <Bar pct={s.gpu.util_pct} />
            </div>
            <div className="stat">
              <div className="lbl">{t("vram")}</div>
              <div className="val">
                {(s.gpu.vram_used_mb / 1024).toFixed(1)} <small>/ {(s.gpu.vram_total_mb / 1024).toFixed(0)} GB</small>
              </div>
              <Bar pct={vramPct} />
            </div>
          </>
        )}
        <div className="stat">
          <div className="lbl">{t("disk")}</div>
          <div className="val">{s.disk_free_gb.toFixed(0)} <small>/ {s.disk_total_gb.toFixed(0)} GB</small></div>
          <Bar pct={s.disk_pct} />
        </div>
      </div>
      <div className="sysapp num">
        <div className="sysapp-h">{t("sys_hardware")}</div>
        <InfoRow label={t("cpu")} value={`${s.cpu_name}${s.cpu_ghz ? ` · ${s.cpu_ghz} GHz` : ""}`} />
        <InfoRow label={t("sys_cores")} value={`${s.cpu_cores} / ${s.cpu_threads}`} />
        {s.gpu && <InfoRow label={t("gpu")} value={s.gpu.name} />}
        {s.gpu && <InfoRow label={t("vram")} value={`${(s.gpu.vram_total_mb / 1024).toFixed(0)} GB`} />}
        <InfoRow label={t("ram")} value={`${s.ram_total_gb.toFixed(0)} GB`} />
        <InfoRow label={t("disk")} value={`${s.disk_free_gb.toFixed(0)} / ${s.disk_total_gb.toFixed(0)} GB`} />
        <div className="sysapp-h">{t("sys_machine")}</div>
        <InfoRow label={t("sys_os")} value={s.os} />
        <InfoRow label={t("sys_host")} value={s.hostname} />
        <InfoRow label={t("sys_machine_uptime")} value={fmtUptime(s.machine_uptime_s)} />
        <InfoRow label={t("sys_data_dir")} value={s.data_dir} />
        <div className="sysapp-h">{t("dizzi_status")}</div>
        <InfoRow label={t("uptime")} value={fmtUptime(dz.uptime_s)} />
        <InfoRow label={t("db")} value={`${dz.db_ok ? "OK" : "✗"} · ${dz.db_size_mb.toFixed(2)} MB`} />
        <InfoRow label={t("audit")} value={String(dz.audit_count)} />
        <InfoRow label={`${t("panels")} · v${dz.version}`} value={`${dz.panels_active} / ${dz.panels_total} ${t("status_aktiv")}`} />
      </div>
    </>
  );
}

interface CardProps {
  panel: PanelManifest;
  detailed: boolean;  // Top-2 = Detail-Ansicht, Rest = kompakt
}

function pnl(v: number | undefined): string {
  const n = v ?? 0;
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
}

/** „Letzte Meta-Entscheidung" defensiv aus Autopilot/Optimierung (Form unbekannt). */
function metaLast(m: TradingbotMeta): string {
  const ap = (m.autopilot ?? {}) as Record<string, unknown>;
  const opt = (m.optimization ?? {}) as Record<string, unknown>;
  const raw = ap.last_action ?? ap.last_result ?? ap.last_run ?? ap.last
    ?? opt.note ?? opt.summary ?? opt.updated_at ?? opt.ts ?? opt.version;
  return (typeof raw === "string" || typeof raw === "number") ? String(raw) : "";
}

function TradingbotBody({ detail }: { detail: boolean }) {
  const { t } = useTranslation();
  const [s, setS] = useState<TradingbotStats | null>(null);
  const [sortKey, setSortKey] = useState<"profit" | "winrate">("profit");
  const [cat, setCat] = useState<string>("all");
  const [runningOnly, setRunningOnly] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => fetchStats<TradingbotStats>("tradingbot").then((d) => alive && setS(d)).catch(() => {});
    load();
    const iv = setInterval(load, detail ? 5000 : 8000);
    return () => { alive = false; clearInterval(iv); };
  }, [detail]);

  if (!s) return null;
  const profitCls = (s.profit_pct ?? 0) >= 0 ? "ok" : "bad";
  if (!detail) {
    return (
      <div className="compactline num">
        {s.online
          ? <>{s.running}/{s.bots} Bots · ROI <span className={profitCls}>{pnl(s.profit_pct)} %</span></>
          : t("tb_offline")}
      </div>
    );
  }
  if (!s.online) {
    return (
      <>
        <div className="desc">{t("tb_offline")}</div>
        <a className="tblink" href={s.url} target="_blank" rel="noreferrer"
          onClick={(e) => e.stopPropagation()}>
          <Icon name="link" /> {t("tb_open")}
        </a>
      </>
    );
  }

  // Top-5 nach Filter/Sortierung (clientseitig; alle vier Filter).
  const rows = (s.bot_rows ?? [])
    .filter((b) => cat === "all" || b.category === cat)
    .filter((b) => !runningOnly || b.running)
    .sort((a, b) => (sortKey === "profit" ? b.profit_abs - a.profit_abs : b.win_rate - a.win_rate))
    .slice(0, 5);
  const cats = s.categories ?? [];
  const meta = s.meta;
  const last = meta ? metaLast(meta) : "";

  return (
    <>
      <div className="stats num">
        <div className="stat">
          <div className="lbl">{t("tb_fleet")}</div>
          <div className="val">{s.running} <small>/ {s.bots}</small></div>
        </div>
        <div className="stat">
          <div className="lbl">{t("tb_roi")}</div>
          <div className={`val ${profitCls}`}>{pnl(s.profit_pct)} %</div>
        </div>
        <div className="stat">
          <div className="lbl">{t("tb_open_trades")}</div>
          <div className="val">{s.trades_open}</div>
        </div>
        <div className="stat">
          <div className="lbl">{t("tb_winrate")}</div>
          <div className="val">{(s.win_rate ?? 0).toFixed(0)} %</div>
        </div>
      </div>

      <div className="tbtop">
        <div className="tbtop-bar">
          <span className="tbtop-h">{t("tb_top5")}</span>
          <button className={`tbf ${sortKey === "profit" ? "on" : ""}`}
            onClick={(e) => { e.stopPropagation(); setSortKey("profit"); }}>{t("tb_sort_profit")}</button>
          <button className={`tbf ${sortKey === "winrate" ? "on" : ""}`}
            onClick={(e) => { e.stopPropagation(); setSortKey("winrate"); }}>{t("tb_sort_winrate")}</button>
          <button className={`tbf ${runningOnly ? "on" : ""}`}
            onClick={(e) => { e.stopPropagation(); setRunningOnly((v) => !v); }}>{t("tb_only_running")}</button>
          {cats.length > 0 && (
            <select className="tbf sel" value={cat}
              onChange={(e) => setCat(e.target.value)} onClick={(e) => e.stopPropagation()}>
              <option value="all">{t("tb_cat_all")}</option>
              {cats.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          )}
        </div>
        {rows.length === 0 ? (
          <div className="tbtop-empty">{t("tb_no_bots")}</div>
        ) : (
          <table className="tbtbl num"><tbody>
            {rows.map((b, i) => (
              <tr key={b.name + i}>
                <td className="tbn">
                  <span className={`dot ${b.running ? "on" : "off"}`} />
                  {b.name}
                  <span className={b.dry_run ? "demo" : "live"}>{b.dry_run ? "demo" : "live"}</span>
                </td>
                <td className="tbc">{b.category}</td>
                <td className={`tbp ${b.profit_abs >= 0 ? "ok" : "bad"}`}>
                  {pnl(b.profit_abs)}{b.profit_pct != null && <small> {pnl(b.profit_pct)} %</small>}
                </td>
                <td className="tbw">{b.win_rate.toFixed(0)} %</td>
              </tr>
            ))}
          </tbody></table>
        )}
      </div>

      <div className="sysapp num">
        <div className="sysapp-h">{t("tb_meta")}</div>
        <div className="inforow">
          <span className="ik">{t("tb_meta_total")}</span>
          <span className={`iv ${profitCls}`}>{pnl(s.profit_pct)} % · {(s.win_rate ?? 0).toFixed(0)} % WR</span>
        </div>
        {meta ? (
          <>
            <div className="inforow">
              <span className="ik">{meta.name}{meta.regime ? ` · ${t("tb_meta_regime")} ${meta.regime}` : ""}</span>
              <span className={`iv ${meta.profit_abs >= 0 ? "ok" : "bad"}`}>{pnl(meta.profit_abs)} USDT</span>
            </div>
            {last && (
              <div className="inforow">
                <span className="ik">{t("tb_meta_last")}</span>
                <span className="iv">{last}</span>
              </div>
            )}
          </>
        ) : <div className="desc small">{t("tb_meta_none")}</div>}
        <a className="tblink" href={s.url} target="_blank" rel="noreferrer"
          onClick={(e) => e.stopPropagation()}>
          <Icon name="link" /> {t("tb_open")}
        </a>
      </div>
    </>
  );
}

/** Netzwerk-App-Kachel (vertragskonform): Online-Status + KPIs + Direkt-Link-Icon. */
function ContractAppBody({ id, detail }: { id: string; detail: boolean }) {
  const { t } = useTranslation();
  const [s, setS] = useState<ContractStats | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => fetchStats<ContractStats>(id).then((d) => alive && setS(d)).catch(() => {});
    load();
    const iv = setInterval(load, detail ? 6000 : 10000);
    return () => { alive = false; clearInterval(iv); };
  }, [id, detail]);

  if (!s) return null;
  const online = !!s.online;
  const linkIcon = s.url ? (
    <a className="neticon" href={s.url} target="_blank" rel="noreferrer"
      title={t("net_open")} aria-label={t("net_open")} onClick={(e) => e.stopPropagation()}>
      <Icon name="link" />
    </a>
  ) : null;
  const dot = <span className={`dot ${online ? "on" : "off"}`} />;

  if (!detail) {
    const k0 = online && s.kpis && s.kpis.length > 0 ? s.kpis[0] : null;
    return (
      <div className="compactline netline">
        {dot}<span className="mut">{online ? t("net_online") : t("net_offline")}</span>
        {k0 && <span className="netkpi num">{String(k0.value)} {k0.label}</span>}
        <span className="spacer" />
        {linkIcon}
      </div>
    );
  }
  return (
    <>
      <div className="netstat">
        {dot}<span className="mut">{online ? t("net_online") : t("net_offline")}</span>
        <span className="spacer" />
        {linkIcon}
      </div>
      {online && s.kpis && s.kpis.length > 0 && (
        <div className="sysapp num">
          {s.kpis.map((k, i) => (
            <div key={k.id ?? i} className="inforow">
              <span className="ik">{k.label}</span>
              <span className="iv">{String(k.value)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export function PanelCard({ panel, detailed }: CardProps) {
  const { t } = useTranslation();
  // §3.4 Auto-Collapse (Norm 18.06.): jedes Panel klappt auf seinen Kopf, beim Laden EINGEKLAPPT.
  // Der Kopf bleibt greifbar (Spin); nur das Chevron (ein <button>) togglet — die Spin-Greiflogik
  // (spinFling onDown) überspringt <button>, also greift ein Chevron-Klick nie das Panel.
  const [collapsed, setCollapsed] = useState(true);
  const placeholder = panel.status === "platzhalter";

  // Aktive Panels bekommen eine eigene Body-Komponente (Detail oder Kompakt-Zeile);
  // Platzhalter/übrige zeigen ihre Beschreibung.
  let body;
  if (panel.id === "systeminfo") body = <SysteminfoBody detail={detailed} />;
  else if (panel.id === "tradingbot") body = <TradingbotBody detail={detailed} />;
  else if (panel.status === "aktiv") body = <ContractAppBody id={panel.id} detail={detailed} />;
  else body = <div className="desc">{panel.description}</div>;

  return (
    <section
      className={`card ${detailed ? "detailed" : "compact"} ${placeholder ? "placeholder" : ""}`}
      data-pid={panel.id}
      data-dz-collapsed={collapsed ? "" : undefined}
    >
      <div className="accent" />
      <div className="head">
        {/* Kanonischer Aufklapp-Toggle aus dem UI-Kit (.dz-chevron, controls.css): glühender
            Akzent-Kasten, zu = Cyan ▶ / offen = Magenta ▼. <button> ⇒ Spin greift ihn nie. */}
        <button
          type="button"
          className="dz-chevron"
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Aufklappen" : "Einklappen"}
          title={collapsed ? "Aufklappen" : "Einklappen"}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => setCollapsed((c) => !c)}
        />
        <Icon name={panel.icon} />
        {/* Marken-Lockup (docs/06 §5): Marke betont vorne, Funktion dezent dahinter. */}
        <span className="lockup">
          <span className="name">{panel.brand ?? panel.name}</span>
          {panel.brand && <span className="fn">{panel.name}</span>}
        </span>
        <span className={`pill ${panel.status}`}>{t(`status_${panel.status}`)}</span>
      </div>
      {!collapsed && body}
    </section>
  );
}
