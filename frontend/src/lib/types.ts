export interface User {
  id: string;
  name: string;
  email: string;
}

export interface Category {
  id: string;
  name: string;
  description: string;
  keywords: string;
  is_seed: boolean;
}

export interface Market {
  id: string;
  name: string;
  location: string;
  customers_per_day: number;
  replenishment_cycle_days: number;
  cycle_unit: string;
  created_at: string;
}

export interface Product {
  id: string;
  market_id: string;
  name: string;
  sku: string | null;
  unit: string;
  price: string;
  cost: string;
  stock: string;
  min_stock: string;
  max_stock: string;
  recommended_quantity: string;
  learned_rate: number;
  prior_rate: number;
  observed_rate: number;
  alpha: number;
  confidence: "baixa" | "media" | "alta";
  status: "processing" | "ready" | "error";
  category_id: string | null;
  category_name: string | null;
  created_at: string;
}

export interface SaleItem {
  id: number;
  product_id: string;
  product_name: string;
  quantity: string;
  unit: string;
  unit_price: string;
  subtotal: string;
}

export interface Sale {
  id: string;
  market_id: string;
  total: string;
  status: "completed" | "cancelled";
  source: "app" | "import" | string;
  sold_at: string;
  created_at: string;
  cancelled_at: string | null;
  items: SaleItem[];
}

export interface SalePage {
  items: Sale[];
  total: number;
  page: number;
  page_size: number;
}

export interface LearningLog {
  id: number;
  trigger: string;
  prior_rate: number;
  observed_rate: number;
  alpha: number;
  final_rate: number;
  safety_stock: string;
  min_stock: string;
  max_stock: string;
  recommended_quantity: string;
  window_start: string | null;
  window_end: string | null;
  n_sales: number;
  source: string;
  details: string;
  created_at: string;
}

export interface LearningPanel {
  product_id: string;
  product_name: string;
  category_name: string | null;
  final_rate: number;
  prior_rate: number;
  observed_rate: number;
  alpha: number;
  data_share_pct: number;
  dataset_share_pct: number;
  n_sales: number;
  confidence: string;
  window_start: string | null;
  window_end: string | null;
  source: string;
  min_stock: string;
  max_stock: string;
  recommended_quantity: string;
  formula: string;
  evolution: { t: string; final_rate: number; prior_rate: number; observed_rate: number }[];
  logs: LearningLog[];
  profile: WeekProfile | null;
}

export interface WeekProfile {
  source: "produto" | "loja" | "padrao";
  days_observed: number;
  index: number[];
  store_index: number[];
  labels: string[];
  next_days: { date: string; weekday: number; label: string; qty: number }[];
  cycle_demand: number;
  reorder_days: number;
  reorder_demand: number;
  safety_method: "erro" | "regra";
  sigma_daily: number | null;
  service_level_pct: number;
  peak_weekday: number;
  peak_name: string;
  peak_phrase: string;
  peak_pct: number;
  low_weekday: number;
  low_name: string;
  low_pct: number;
}

export interface PeriodStats {
  revenue: string;
  sales_count: number;
  items_sold: string;
  avg_ticket: string;
}

export interface Analytics {
  from_date: string;
  to_date: string;
  stats: PeriodStats;
  previous: PeriodStats;
  revenue_change_pct: number | null;
  sales_change_pct: number | null;
  top_products: { product_name: string; category_name: string | null; quantity: string; revenue: string }[];
  revenue_by_category: { category_name: string; revenue: string; quantity: string }[];
  daily_series: { date: string; revenue: string; sales_count: number }[];
  stock_by_category: { category_name: string; revenue: string; quantity: string }[];
  low_stock_alerts: {
    product_id: string;
    product_name: string;
    market_id: string;
    market_name: string;
    stock: string;
    min_stock: string;
    status: string;
  }[];
  markets_overview: {
    market_id: string;
    name: string;
    customers_per_day: number;
    replenishment_cycle_days: number;
    products_count: number;
    stock_value: string;
    low_stock_count: number;
    processing_count: number;
  }[];
}
export type ImportField =
  | "date" | "time" | "receipt" | "sku" | "product" | "quantity"
  | "unit_price" | "total" | "value" | "stock" | "cost" | "unit";

export interface ImportPreview {
  filename: string;
  kind: "sales" | "catalog";
  encoding: string;
  delimiter: string;
  columns: { header: string; field: ImportField | null; label: string | null }[];
  total_rows: number;
  valid_rows: number;
  products: number;
  date_from: string | null;
  date_to: string | null;
  sample: {
    line: number;
    product: string;
    sku: string | null;
    date: string | null;
    quantity: string | null;
    unit_price: string | null;
    stock: string | null;
    cost: string | null;
    receipt: string | null;
  }[];
  errors: { line: number; message: string }[];
  warnings: string[];
}

export interface ImportResult {
  kind: "sales" | "catalog";
  rows_imported: number;
  rows_skipped: number;
  products_created: number;
  products_updated: number;
  sales_created: number;
  items_created: number;
  date_from: string | null;
  date_to: string | null;
  errors: { line: number; message: string }[];
}

export interface PurchaseItem {
  product_id: string;
  name: string;
  sku: string | null;
  unit: string;
  category_name: string | null;
  status: "esgotado" | "comprar" | "atencao";
  stock: number;
  min_stock: number;
  target_stock: number;
  daily_rate: number;
  coverage_days: number | null;
  buy_quantity: number;
  unit_cost: number | null;
  line_cost: number | null;
  confidence: string;
}

export interface PurchaseList {
  market_id: string;
  market_name: string;
  cycle_days: number;
  generated_at: string;
  items: PurchaseItem[];
  totals: { items: number; urgent: number; units: number; estimated_cost: number; missing_cost: number };
}

export interface Explanation {
  text: string;
  source: "llm" | "template";
  checked: { value: string; fact: string }[];
  rejected: { text: string; problems: string[] } | null;
  facts: Record<string, string | number | null>;
  llm_enabled: boolean;
  elapsed_ms: number;
}

export interface ModelScore {
  key: "lgbm" | "ma4" | "naive" | "snaive";
  name: string;
  mae: number;
  mape: number;
  wape: number;
  bias: number;
  n: number;
}

export interface Evaluation {
  status: "ready" | "running" | "error" | "idle";
  error?: string | null;
  running_for_s?: number;
  generated_at?: string;
  elapsed_s?: number;
  dataset?: { name: string; stores: number; items: number; series: number; weeks: number; first_week: string; last_week: string };
  protocol?: {
    test_weeks: number;
    refit_every: number;
    folds: number;
    horizon: string;
    train_rows_last_fold: number;
    test_rows: number;
    features: number;
    rounds: number;
  };
  models?: ModelScore[];
  winner?: string;
  improvement_vs_ma4_pct?: number;
  win_rate_vs_ma4_pct?: number;
  folds?: { fold: number; start: string; weeks: number; lgbm_wape: number; ma4_wape: number }[];
  weekly_total?: { week: string; actual: number; lgbm: number; ma4: number }[];
  by_size?: { size_bucket: number; label: string; lgbm_wape: number; ma4_wape: number }[];
  samples?: { label: string; lgbm_wape: number; ma4_wape: number; points: { week: string; actual: number; lgbm: number | null; ma4: number | null }[] }[];
  feature_importance?: { feature: string; label: string; pct: number }[];
  production_model?: { ready: boolean; kind: string; overall_mean: number | null };
}
