export function fmtMoney(v: string | number): string {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function fmtNum(v: string | number): string {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isInteger(n)) return n.toLocaleString("pt-BR");
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}

export function fmtDate(iso: string): string {
  // Calendar dates have no timezone; preserve their day instead of parsing as UTC.
  const calendar = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (calendar) return `${calendar[3]}/${calendar[2]}/${calendar[1]}`;
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const UNIT_NAMES: Record<string, [string, string, string, string]> = {
  unidade: ["unidade", "unidades", "unit", "units"],
  kg: ["quilograma", "quilogramas", "kilogram", "kilograms"],
  g: ["grama", "gramas", "gram", "grams"],
  litro: ["litro", "litros", "liter", "liters"],
  l: ["litro", "litros", "liter", "liters"],
  ml: ["mililitro", "mililitros", "milliliter", "milliliters"],
  pacote: ["pacote", "pacotes", "pack", "packs"],
  dz: ["dúzia", "dúzias", "dozen", "dozen"],
  caixa: ["caixa", "caixas", "box", "boxes"],
};

export function fmtQuantity(value: string | number, unit: string, locale = "pt") {
  const n = Number(value);
  const names = UNIT_NAMES[unit.toLowerCase()];
  const label = names ? names[(locale === "pt" ? 0 : 2) + (n === 1 ? 0 : 1)] : unit;
  return `${n.toLocaleString(locale === "pt" ? "pt-BR" : "en-US", {maximumFractionDigits: 3})} ${label}`;
}

// Sum only matching units, retaining the database's three decimal places.
export function saleQuantities(items: {quantity: string; unit: string}[], locale = "pt") {
  const totals = new Map<string, number>();
  for (const item of items) totals.set(item.unit, (totals.get(item.unit) ?? 0) + Math.round(Number(item.quantity) * 1000));
  return Array.from(totals, ([unit, total]) => fmtQuantity(total / 1000, unit, locale)).join(" · ");
}
