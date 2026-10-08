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
  unit: string;
  price: string;
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
  unit_price: string;
  subtotal: string;
}

export interface Sale {
  id: string;
  market_id: string;
  total: string;
  status: "completed" | "cancelled";
  sold_at: string;
  created_at: string;
  cancelled_at: string | null;
  items: SaleItem[];
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