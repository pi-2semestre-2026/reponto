export type DashboardPreset = "today" | "7d" | "30d" | "month" | "custom";

// Match the backend's market calendar, rather than the browser's UTC date.
export function dashboardRange(preset: DashboardPreset, customFrom = "", customTo = "", now = new Date()) {
  if (preset === "custom") return customFrom && customTo ? {from: customFrom, to: customTo} : null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) => parts.find(p => p.type === type)!.value;
  const today = `${part("year")}-${part("month")}-${part("day")}`;
  if (preset === "today") return {from: today, to: today};
  if (preset === "month") return {from: today.slice(0, 8) + "01", to: today};
  // Arithmetic on calendar dates in UTC avoids DST shifts in day durations.
  const start = new Date(today + "T00:00:00Z");
  start.setUTCDate(start.getUTCDate() - (preset === "7d" ? 6 : 29));
  return {from: start.toISOString().slice(0, 10), to: today};
}
