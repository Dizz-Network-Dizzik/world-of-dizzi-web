export interface PanelManifest {
  id: string;
  name: string;            // Funktionsname (z. B. "Finanzmanagement")
  brand?: string | null;   // Marke (z. B. "Dizz Money") — Marken-Lockup, docs/06 §5
  icon: string;
  status: "aktiv" | "platzhalter";
  description: string;
  actions: { id: string; label: string }[];
  mcp: string | null;
}

export interface GpuStats {
  name: string;
  util_pct: number;
  vram_used_mb: number;
  vram_total_mb: number;
  temp_c: number;
}

export interface TradingbotGroup {
  name: string;
  bots: number;
  running: number;
  profit_pct: number;
  profit_abs: number;
}

export interface TradingbotBotRow {
  name: string;
  category: string;
  running: boolean;
  dry_run: boolean;
  mode: string | null;
  profit_abs: number;
  profit_pct: number | null;
  trades_closed: number;
  win_rate: number;
}

export interface TradingbotMeta {
  name: string;
  running: boolean;
  profit_abs: number;
  profit_pct: number | null;
  win_rate: number;
  regime: string | null;
  autopilot?: Record<string, unknown> | null;
  optimization?: Record<string, unknown> | null;
}

export interface TradingbotStats {
  status: string;
  online: boolean;
  url: string;
  bots?: number;
  running?: number;
  trades_open?: number;
  trades_closed?: number;
  win_rate?: number;
  profit_abs?: number;
  profit_pct?: number;
  avg_profit_pct?: number | null;
  groups?: TradingbotGroup[];
  bot_rows?: TradingbotBotRow[];
  categories?: string[];
  meta?: TradingbotMeta | null;
}

export interface ContractKpi {
  id?: string;
  label: string;
  value: string | number;
}

export interface ContractStats {
  status: string;
  online: boolean;
  url: string;
  contract?: string | null;
  summary_status?: string;
  kpis?: ContractKpi[];
  note?: string | null;
}

export interface HealthStats {
  status: string;
  version: string;
  uptime_s: number;
  db_ok: boolean;
  db_size_mb: number;
  audit_count: number;
  panels_active: number;
  panels_total: number;
}

export interface DizziStatus {
  version: string;
  uptime_s: number;
  db_ok: boolean;
  db_size_mb: number;
  audit_count: number;
  panels_active: number;
  panels_total: number;
}

export interface SysteminfoStats {
  status: string;
  cpu_pct: number;
  cpu_ghz: number | null;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_pct: number;
  disk_free_gb: number;
  disk_total_gb: number;
  disk_pct: number;
  machine_uptime_s: number;
  gpu: GpuStats | null;
  cpu_name: string;
  cpu_cores: number;
  cpu_threads: number;
  os: string;
  hostname: string;
  data_dir: string;
  dizzi: DizziStatus;
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export const fetchPanels = () => getJson<PanelManifest[]>("/api/panels");
export const fetchStats = <T = Record<string, unknown>>(id: string) =>
  getJson<T>(`/api/panels/${id}/stats`);
export const fetchSettings = () => getJson<Record<string, unknown>>("/api/settings");

// --- Konto-/Einstellungs-Fenster (Norm docs/19 §2b) -----------------------

/** Anmelde-Status der Dizzi-ID-Session (Core ist selbst der IdP, GET /id/status). */
export interface IdStatus {
  angemeldet: boolean;
  user_id: string | null;
  level: string | null;
  amr: string[];
  via: string;
  lokales_passwort?: boolean;
  google_konfiguriert?: boolean;
  mfa?: { confirmed?: boolean } | null;
}
export const fetchIdStatus = () => getJson<IdStatus>("/id/status");

/** Core-Health-Watch: je Ziel (Vertrags-Apps + Ollama) online/offline.
 *  Leer, bis der erste Wächter-Lauf (~45 s nach Core-Start) durch ist. */
export interface HealthWatch {
  ziele: Record<string, boolean>;
  ts: string;
}
export const fetchHealthWatch = () => getJson<HealthWatch>("/api/health/watch");

// --- KI-Kern ---------------------------------------------------------------

export interface AiStatus {
  ollama_ok: boolean;
  models: string[];
  active_model: string;
  providers: { id: string; label: string; kind: string; available: boolean }[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  created_at?: string;
}

export interface MemoryFact {
  id: string;
  fact: string;
  source: string;
  created_at: string;
}

export type ChatEvent =
  | { t: string }
  | { done: true; provider: string; tools?: string[] }
  | { error: string }
  | { memory_saved: string }
  | { tool: string; args?: Record<string, unknown> };

export const fetchAiStatus = () => getJson<AiStatus>("/api/ai/status");
export const fetchAiHistory = () => getJson<ChatMessage[]>("/api/ai/history");
export const fetchMemory = () => getJson<MemoryFact[]>("/api/ai/memory");
export const deleteMemory = (id: string) =>
  fetch(`/api/ai/memory/${id}`, { method: "DELETE" });

export interface Notice {
  id: string;
  source: string;
  severity: "info" | "warn" | "vorschlag";
  title: string;
  detail: string;
  created_at: string;
  read_at: string | null;
}

export const fetchNotices = () => getJson<Notice[]>("/api/ai/notices");
export const markNoticesRead = () =>
  fetch("/api/ai/notices/read", { method: "POST" });

/** Spracheingabe: Audio-Blob → Text (lokales Whisper im Core). */
export async function transcribe(blob: Blob): Promise<string> {
  const fd = new FormData();
  fd.append("audio", blob, "aufnahme.webm");
  const r = await fetch("/api/ai/transcribe", { method: "POST", body: fd });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return ((await r.json()) as { text: string }).text;
}

/** Sprachausgabe: Text → abspielbares WAV (lokales Piper im Core). */
export async function speak(text: string): Promise<Blob> {
  const r = await fetch("/api/ai/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.blob();
}

/** Streamt eine Chat-Antwort (SSE über fetch); ruft onEvent je Ereignis. */
export async function streamChat(
  message: string,
  sensitive: boolean,
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const r = await fetch("/api/ai/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, sensitive }),
  });
  if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5)));
    }
  }
}

export async function putSetting(key: string, value: unknown): Promise<void> {
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}
