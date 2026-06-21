// 後端 API 的型別與封裝（對應 ai_archive/api.py）

export type Platform = "chatgpt" | "grok" | "gemini";

export interface Stats {
  conversations: number;
  messages: number;
  per_platform: Record<string, number>;
  roles: Record<string, number>;
  distribution: { platform: string; month: string; n: number }[];
}

export interface SearchHit {
  conv_id: string;
  idx: number;
  role: "user" | "assistant";
  text: string;
  time: number | null;
  platform: Platform;
  title: string;
}

export interface ConvSummary {
  id: string;
  platform: Platform;
  title: string;
  create_time: number | null;
  update_time: number | null;
  n_messages: number;
}

export interface Message {
  idx: number;
  role: "user" | "assistant";
  text: string;
  time: number | null;
}

export interface Conversation extends ConvSummary {
  messages: Message[];
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  stats: () => get<Stats>("/api/stats"),

  search: (q: string, platform?: string, limit = 30, offset = 0) => {
    const p = new URLSearchParams({ q, limit: String(limit), offset: String(offset) });
    if (platform) p.set("platform", platform);
    return get<{ query: string; count: number; results: SearchHit[] }>(
      `/api/search?${p}`,
    );
  },

  conversations: (opts: {
    platform?: string;
    month?: string;
    order?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const p = new URLSearchParams({
      order: opts.order ?? "recent",
      limit: String(opts.limit ?? 30),
      offset: String(opts.offset ?? 0),
    });
    if (opts.platform) p.set("platform", opts.platform);
    if (opts.month) p.set("month", opts.month);
    return get<{ total: number; count: number; items: ConvSummary[] }>(
      `/api/conversations?${p}`,
    );
  },

  conversation: (id: string) =>
    get<Conversation>(`/api/conversations/${encodeURIComponent(id)}`),
};

// ---- 平台外觀（color 為資料色，承載「哪個 AI」語意）----
export const PLATFORMS: Platform[] = ["chatgpt", "grok", "gemini"];

// color 用 CSS 變數，深色模式會自動翻轉（見 index.css 的 .dark 覆寫）
export const platformMeta: Record<Platform, { label: string; color: string }> = {
  chatgpt: { label: "ChatGPT", color: "var(--color-chatgpt)" },
  grok: { label: "Grok", color: "var(--color-grok)" },
  gemini: { label: "Gemini", color: "var(--color-gemini)" },
};

export function fmtDate(t: number | null): string {
  if (!t) return "—";
  return new Date(t * 1000).toLocaleDateString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

const MONTH_TW = [
  "1月", "2月", "3月", "4月", "5月", "6月",
  "7月", "8月", "9月", "10月", "11月", "12月",
];

export function fmtMonth(ym: string): string {
  // "2025-08" → "2025年 8月"
  const [y, m] = ym.split("-");
  return `${y}年 ${MONTH_TW[Number(m) - 1] ?? m}`;
}
