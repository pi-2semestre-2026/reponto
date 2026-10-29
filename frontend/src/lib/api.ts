import type {
  Analytics,
  Category,
  Evaluation,
  Explanation,
  ImportPreview,
  ImportResult,
  LearningPanel,
  Market,
  Product,
  PurchaseList,
  Sale,
  SalePage,
  User,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("reponto_token");
}

export function setToken(t: string | null) {
  if (t) localStorage.setItem("reponto_token", t);
  else localStorage.removeItem("reponto_token");
}

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, string | undefined>): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  const url = new URL(API_URL + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, v);
    }
  }

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    cache: "no-store",
  });

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    if (res.status === 401 && typeof window !== "undefined") {
      setToken(null);
      window.location.href = "/login";
    }
    const message = typeof detail === "string" ? detail
      : detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string" ? detail.message
      : `Erro ${res.status}`;
    throw new ApiError(res.status, message, detail);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | undefined>) => request<T>("GET", path, undefined, params),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),

  register: (name: string, email: string, password: string) =>
    api.post<{ access_token: string }>("/auth/register", { name, email, password }),
  login: (email: string, password: string) =>
    api.post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => api.get<User>("/auth/me"),

  markets: () => api.get<Market[]>("/markets"),
  createMarket: (body: Omit<Market, "id" | "created_at">) => api.post<Market>("/markets", body),
  updateMarket: (id: string, body: Omit<Market, "id" | "created_at">) => api.patch<Market>(`/markets/${id}`, body),
  deleteMarket: (id: string) => api.delete<void>(`/markets/${id}`),

  products: (marketId: string) => api.get<Product[]>(`/markets/${marketId}/products`),
  createProduct: (marketId: string, body: ProductRegistration) =>
    api.post<Product & {stock_added: boolean}>(`/markets/${marketId}/products`, body),
  updateProduct: (id: string, body: { name?: string; price?: number; cost?: number; unit?: string }) =>
    api.patch<Product>(`/products/${id}`, body),
  deleteProduct: (id: string) => api.delete<void>(`/products/${id}`),
  adjustStock: (id: string, delta: number, reason: string) =>
    api.post<Product>(`/products/${id}/stock`, { delta, reason }),
  learning: (id: string) => api.get<LearningPanel>(`/products/${id}/learning`),
  explanation: (id: string, refresh = false) =>
    api.get<Explanation>(`/products/${id}/explanation`, { refresh: refresh ? "true" : undefined }),

  importPreview: (marketId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<ImportPreview>(`/markets/${marketId}/import/preview`, fd);
  },
  importFile: (marketId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<ImportResult>(`/markets/${marketId}/import`, fd);
  },

  purchaseList: (marketId: string) => api.get<PurchaseList>(`/markets/${marketId}/purchase-list`),
  receivePurchase: (marketId: string, items: { product_id: string; quantity: number }[], note?: string) =>
    api.post<{ received: number; units: number }>(`/markets/${marketId}/purchases`, { items, note: note ?? "" }),

  evaluation: () => api.get<Evaluation>("/ml/evaluation"),

  salesPage: (params: { market_id?: string; date_from?: string; date_to?: string; page: number; page_size: number }) => api.get<SalePage>("/sales/history", {...params, page: String(params.page), page_size: String(params.page_size)}),
  sales: (params?: { market_id?: string; date_from?: string; date_to?: string }) => api.get<Sale[]>("/sales", params),
  getSale: (id: string) => api.get<Sale>(`/sales/${id}`),
  createSale: (body: { market_id: string; items: { product_id: string; quantity: number }[]; sold_at?: string }) =>
    api.post<Sale>("/sales", body),
  cancelSale: (id: string) => api.post<Sale>(`/sales/${id}/cancel`),

  categories: () => api.get<Category[]>("/categories"),
  createCategory: (body: { name: string; description: string; keywords?: string }) =>
    api.post<Category>("/categories", body),
  updateCategory: (id: string, body: { name: string; description: string; keywords?: string }) =>
    api.patch<Category>(`/categories/${id}`, body),
  deleteCategory: (id: string) => api.delete<void>(`/categories/${id}`),

  analytics: (params: { date_from: string; date_to: string; market_id?: string }) =>
    api.get<Analytics>("/analytics", params),
};

export { API_URL, ApiError };

export type ProductRegistration = {
  name: string; price: number; cost?: number; stock: number; unit: string;
  duplicate_action?: "auto" | "add_stock" | "create_new";
  existing_product_id?: string;
};
export type DuplicateProductDetails = {
  code: "duplicate_product";
  existing_product: Pick<Product, "id" | "name" | "price" | "cost" | "unit">;
};
