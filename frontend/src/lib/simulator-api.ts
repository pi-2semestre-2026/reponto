import { getToken } from "@/lib/token";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SimProduct {
  key: string;
  name: string;
  category: string;
  price: number;
  cost: number;
  stock: number;
  max_stock: number;
  min_stock: number;
  final_rate: number;
  confidence: "baixa" | "media" | "alta";
  seasonal_factor: number | null;
  today_sold: number;
  today_lost: number;
  restocked: number;
}

export interface SimSummary {
  mae: number | null;
  wape_pct: number | null;
  bias_pct: number | null;
  service_pct: number | null;
  samples: number;
  wape_clean_pct?: number | null;
  bias_clean_pct?: number | null;
  rate_wape_pct?: number | null;
}

export interface SimEvent {
  kind: string;
  emoji_kind: string;
  starts_on: string;
  ends_on: string;
  day?: number;
  date?: string;
}

export interface SimScenario {
  key: string;
  name: string;
  description: string;
  customers_per_day: number;
  products: number;
}

export interface SimSnapshot {
  day_index: number;
  total_days: number;
  date: string;
  done: boolean;
  scenario: { key: string; name: string; customers_per_day: number; cycle_days: number; seed: number };
  cash: { revenue: number; cost: number; profit: number; lost_r: number; stock_value?: number };
  products: SimProduct[];
  summary: SimSummary;
  last_events: SimEvent[];
}

export interface SimDayReport {
  day_index: number;
  date: string;
  weekday: number;
  events: SimEvent[];
  restocked: string[];
  stockouts: string[];
  revenue: number;
  cost: number;
  lost_r: number;
  sold_units: number;
  lost_units: number;
  demand_units: number;
  product_deltas: { key: string; sold: number; lost: number; demand: number; restocked: number; stock: number }[];
}

export interface SimVerdict {
  level: "acertivo" | "parcial" | "fora" | "sem_dados";
  direction: "superestima" | "subestima" | null;
  score: number | null;
  waste_r?: number;
}

export interface SimReport {
  summary: SimSummary;
  verdict: SimVerdict;
  per_category: { category: string; mae: number; wape_pct: number | null; bias_pct: number | null; wape_clean_pct?: number | null; bias_clean_pct?: number | null; rate_wape_pct?: number | null; stockout_pct: number; samples: number }[];
  daily_compare: { date: string; predicted: number; actual: number }[];
  daily_cash: { date: string; revenue: number; cost: number; lost_r: number }[];
  totals: { days: number; revenue: number; cost: number; profit: number; lost_r: number; demand_units: number; avg_daily_demand: number };
  events: SimEvent[];
  config: { scenario: string; customers_per_day: number; days: number; cycle_days: number; seed: number };
}

export interface SimCoach {
  verdict: string;
  headline: string;
  observations: string[];
  recommendations: string[];
  source: string;
}

export interface CustomProductIn {
  name: string;
  quantity: number;
  price?: number | null;
}

export interface CreateSessionIn {
  scenario: string;
  days: number;
  cycle_days: number;
  seed?: number | null;
  products?: CustomProductIn[] | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/admin/simulator${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const simApi = {
  scenarios: () => request<SimScenario[]>("/scenarios"),
  createSession: (payload: CreateSessionIn) =>
    request<{ sid: string; snapshot: SimSnapshot }>("/sessions", { method: "POST", body: JSON.stringify(payload) }),
  step: (sid: string, days: number) =>
    request<{ reports: SimDayReport[]; snapshot: SimSnapshot }>(`/sessions/${sid}/step`, {
      method: "POST",
      body: JSON.stringify({ days }),
    }),
  getSession: (sid: string) => request<{ sid: string; snapshot: SimSnapshot }>(`/sessions/${sid}`),
  report: (sid: string) => request<{ report: SimReport; coach: SimCoach }>(`/sessions/${sid}/report`),
  deleteSession: (sid: string) => request<{ ok: boolean }>(`/sessions/${sid}`, { method: "DELETE" }),
};
// ---------------------------------------------------------------- laboratório da banca

export interface LabDay {
  day: number;
  date: string;
  weekday: number;
  label: string;
  demand: number;
  ai_forecast: number;
  noai_forecast: number;
  ai_sold: number;
  noai_sold: number;
  ai_stockout: boolean;
  noai_stockout: boolean;
  ai_stock: number;
  noai_stock: number;
  source: "modelo" | "regra";
}

export interface LabProduct {
  key: string;
  name: string;
  category: string;
  story: string;
  cycle_days: number;
  perishable: boolean;
  labels: string[];
  true_index: number[];
  learned_index: number[];
  pattern_error_pp: number | null;
  pattern_error_series: { day: number; error_pp: number }[];
  source: "modelo" | "regra";
  switched_day: number | null;
  model_weeks: number;
  final_rate: number;
  recommended: number;
  confidence: string;
  stock_ai: number;
  stock_noai: number;
  history: LabDay[];
  wape_ai_28: number | null;
  wape_noai_28: number | null;
  stockouts_ai: number;
  stockouts_noai: number;
}

export interface LabStore {
  fill_pct: number | null;
  stockout_days: number;
  revenue: number;
  cost: number;
  lost_r: number;
  waste_r: number;
  avg_stock_value: number;
}

export interface LabSnapshot {
  kind: "lab";
  seed: number;
  day_index: number;
  total_days: number;
  date: string;
  weekday: string;
  done: boolean;
  customers_per_day: number;
  products: LabProduct[];
  stores: { ai: LabStore; noai: LabStore };
  shifts: { kind: string; label: string; day: number; date: string; product: string }[];
  available_shifts: { kind: string; label: string }[];
}

export const labApi = {
  create: (seed?: number | null) =>
    request<{ sid: string; snapshot: LabSnapshot }>("/lab", { method: "POST", body: JSON.stringify({ seed: seed ?? null }) }),
  step: (sid: string, days: number) =>
    request<{ snapshot: LabSnapshot }>(`/lab/${sid}/step`, { method: "POST", body: JSON.stringify({ days }) }),
  shift: (sid: string, kind: string) =>
    request<{ snapshot: LabSnapshot }>(`/lab/${sid}/shift`, { method: "POST", body: JSON.stringify({ kind }) }),
  remove: (sid: string) => request<{ ok: boolean }>(`/lab/${sid}`, { method: "DELETE" }),
};
