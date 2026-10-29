import type { Product } from "./types";

export type ProductSortKey = "name" | "category" | "price" | "cost" | "stock" | "coverage" | "status" | "learned_rate";
export type ProductSort = {key: ProductSortKey; direction: "asc" | "desc"} | null;

export function nextProductSort(current: ProductSort, key: ProductSortKey): ProductSort {
  if (current?.key !== key) return {key, direction: "asc"};
  return current.direction === "asc" ? {key, direction: "desc"} : null;
}

export function productStockStatus(p: Product) {
  return p.status === "processing" ? "processing" : Number(p.stock) <= 0 ? "out" : Number(p.stock) <= Number(p.min_stock) ? "low" : "ok";
}

export function sortMarketProducts(products: Product[], sort: ProductSort, locale = "pt") {
  if (!sort) return products;
  const collator = new Intl.Collator(locale === "pt" ? "pt-BR" : "en", {sensitivity: "base", numeric: true});
  const statuses = locale === "pt" ? {processing: "IA", out: "ESGOTADO", low: "BAIXO", ok: "OK"} : {processing: "IA", out: "OUT OF STOCK", low: "LOW", ok: "OK"};
  const value = (p: Product): string | number | null => {
    switch (sort.key) {
      case "name": return p.name;
      case "category": return p.status === "processing" ? null : p.category_name;
      case "status": return statuses[productStockStatus(p)];
      case "coverage": return p.status === "processing" || p.learned_rate <= 0 ? null : Number(p.stock) / p.learned_rate;
      case "learned_rate": return p.status === "processing" ? null : p.learned_rate;
      default: return Number(p[sort.key]);
    }
  };
  return products.map((product, index) => ({product, index})).sort((a, b) => {
    const x = value(a.product), y = value(b.product);
    // Missing/processing values stay last in either direction.
    if (x === null || y === null) return x === y ? a.index - b.index : x === null ? 1 : -1;
    const comparison = typeof x === "number" && typeof y === "number" ? x - y : collator.compare(String(x), String(y));
    return comparison ? comparison * (sort.direction === "asc" ? 1 : -1) : a.index - b.index;
  }).map(row => row.product);
}
