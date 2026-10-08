"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  BarChart3,
  Coins,
  Inbox,
  Loader2,
  Plus,
  Receipt,
  ShoppingBasket,
  Store,
  Trophy,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { PontoDot } from "@/components/ponto-dot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Analytics } from "@/lib/types";
import { cn } from "@/lib/utils";

const CHART_COLORS = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
  "hsl(155 12% 55%)",
  "hsl(27 60% 62%)",
  "hsl(150 10% 70%)",
];

type Preset = "today" | "7d" | "30d" | "month" | "custom";

function AnimatedNumber({ value, format }: { value: number; format: (v: number) => string }) {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const from = prev.current;
    prev.current = value;
    if (reduced || from === value) {
      setDisplay(value);
      return;
    }
    const duration = 900;
    const start = performance.now();
    let raf: number;
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (value - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);

  return <>{format(display)}</>;
}

export default function DashboardPage() {
  const { t } = useI18n();
  const [preset, setPreset] = useState<Preset>("30d");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  const range = useMemo(() => {
    const today = new Date();
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    if (preset === "today") return { from: iso(today), to: iso(today) };
    if (preset === "7d") {
      const from = new Date(today.getTime() - 6 * 86400000);
      return { from: iso(from), to: iso(today) };
    }
    if (preset === "30d") {
      const from = new Date(today.getTime() - 29 * 86400000);
      return { from: iso(from), to: iso(today) };
    }
    if (preset === "month") {
      const from = new Date(today.getFullYear(), today.getMonth(), 1);
      return { from: iso(from), to: iso(today) };
    }
    if (customFrom && customTo) return { from: customFrom, to: customTo };
    return null;
  }, [preset, customFrom, customTo]);

  const load = useCallback(() => {
    if (!range) return;
    setLoading(true);
    api
      .analytics({ date_from: range.from, date_to: range.to })
      .then(setData)
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [range]);

  useEffect(load, [load]);

  const pct = (v: number | null, positive = true) => {
    if (v === null) return null;
    const good = positive ? v >= 0 : v <= 0;
    return (
      <span className={cn("flex items-center gap-0.5 text-xs font-bold", good ? "text-primary" : "text-destructive")}>
        {v >= 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
        {Math.abs(v)}% <span className="font-medium text-muted-foreground">{t("dash.vsPrev")}</span>
      </span>
    );
  };

  return (
    <div className="min-h-screen">
      <Header active="/dashboard" />
      <main className="container space-y-6 py-8">
        <div className="animate-fade-in-up flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight">{t("dash.title")}</h1>
            <p className="mt-1 text-muted-foreground">{t("dash.subtitle")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                ["today", t("common.today")],
                ["7d", t("common.7d")],
                ["30d", t("common.30d")],
                ["month", t("common.month")],
                ["custom", t("common.custom")],
              ] as [Preset, string][]
            ).map(([key, label]) => (
              <Button
                key={key}
                size="sm"
                variant={preset === key ? "press" : "outline"}
                onClick={() => setPreset(key)}
              >
                {label}
              </Button>
            ))}
            {preset === "custom" && (
              <div className="flex items-center gap-2">
                <Input type="date" className="h-9 w-36" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
                <span className="text-sm text-muted-foreground">→</span>
                <Input type="date" className="h-9 w-36" value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
              </div>
            )}
          </div>
        </div>

        {loading && !data ? (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Skeleton className="h-72" />
              <Skeleton className="h-72" />
            </div>
          </div>
        ) : data ? (
          <>
            <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard icon={Coins} label={t("dash.revenue")} value={parseFloat(data.stats.revenue)} format={fmtMoney} sub={pct(data.revenue_change_pct)} />
              <StatCard icon={Receipt} label={t("dash.sales")} value={data.stats.sales_count} format={fmtNum} sub={pct(data.sales_change_pct)} />
              <StatCard icon={BarChart3} label={t("dash.ticket")} value={parseFloat(data.stats.avg_ticket)} format={fmtMoney} />
              <StatCard icon={ShoppingBasket} label={t("dash.items")} value={parseFloat(data.stats.items_sold)} format={fmtNum} />
            </div>

            <div className="grid gap-4 lg:grid-cols-5">
              <Card className="animate-fade-in-up lg:col-span-3">
                <CardHeader>
                  <CardTitle className="text-base">{t("dash.dailyRevenue")}</CardTitle>
                </CardHeader>
                <CardContent className="h-64">
                  {data.daily_series.length === 0 ? (
                    <Empty />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.daily_series.map((d) => ({ ...d, revenue: parseFloat(d.revenue) }))}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                        <XAxis
                          dataKey="date"
                          tickFormatter={(v) => String(v).slice(5)}
                          tick={{ fontSize: 11 }}
                          stroke="hsl(var(--muted-foreground))"
                        />
                        <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={50} />
                        <ReTooltip
                          formatter={(v: number) => fmtMoney(v)}
                          contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))" }}
                        />
                        <Bar dataKey="revenue" fill="hsl(var(--chart-1))" radius={[6, 6, 0, 0]} maxBarSize={40} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              <Card className="animate-fade-in-up lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-base">{t("dash.byCategory")}</CardTitle>
                </CardHeader>
                <CardContent className="h-64">
                  {data.revenue_by_category.length === 0 ? (
                    <Empty />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={data.revenue_by_category.map((c) => ({ name: c.category_name, value: parseFloat(c.revenue) }))}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={55}
                          outerRadius={90}
                          paddingAngle={3}
                          strokeWidth={0}
                        >
                          {data.revenue_by_category.map((_, i) => (
                            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                          ))}
                        </Pie>
                        <ReTooltip
                          formatter={(v: number) => fmtMoney(v)}
                          contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))" }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="animate-fade-in-up">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Trophy className="h-4 w-4 text-ponto-ink" /> {t("dash.topProducts")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2.5">
                  {data.top_products.length === 0 && <Empty />}
                  {data.top_products.map((p, i) => (
                    <div key={i} className="flex items-center gap-3 rounded-xl bg-muted/50 p-2.5">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary font-display text-xs font-bold text-primary-foreground">
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-bold">{p.product_name}</p>
                        <p className="text-xs text-muted-foreground">{fmtNum(p.quantity)} un · {p.category_name ?? "—"}</p>
                      </div>
                      <span className="font-mono text-sm font-semibold text-primary">{fmtMoney(p.revenue)}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="animate-fade-in-up">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <AlertTriangle className="h-4 w-4 text-amber-500" /> {t("dash.lowStock")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2.5">
                  {data.low_stock_alerts.length === 0 && (
                    <p className="flex flex-col items-center gap-2 py-6 text-center text-sm text-muted-foreground">
                      <BadgeCheck className="h-8 w-8 text-primary" />
                      {t("dash.noAlerts")}
                    </p>
                  )}
                  {data.low_stock_alerts.map((a) => (
                    <Link
                      key={a.product_id}
                      href={`/markets/${a.market_id}`}
                      className="flex items-center gap-3 rounded-xl bg-muted/50 p-2.5 hover:bg-muted"
                    >
                      <Badge variant={a.status === "esgotado" ? "destructive" : "warning"}>
                        {a.status === "esgotado" ? t("market.stockStatus.out") : t("market.stockStatus.low")}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-bold">{a.product_name}</p>
                        <p className="truncate text-xs text-muted-foreground">{a.market_name}</p>
                      </div>
                      <span className="font-mono text-sm font-semibold">
                        {fmtNum(a.stock)} <span className="text-xs font-normal text-muted-foreground">/ min {fmtNum(a.min_stock)}</span>
                      </span>
                    </Link>
                  ))}
                </CardContent>
              </Card>

              <Card className="animate-fade-in-up">
                <CardHeader className="flex-row items-center justify-between space-y-0">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Store className="h-4 w-4 text-primary" /> {t("dash.markets")}
                  </CardTitle>
                  <Button variant="ghost" size="sm" asChild>
                    <Link href="/markets/new">
                      <Plus className="h-4 w-4" />
                    </Link>
                  </Button>
                </CardHeader>
                <CardContent className="space-y-2.5">
                  {data.markets_overview.length === 0 && (
                    <p className="py-6 text-center text-sm text-muted-foreground">{t("dash.noMarkets")}</p>
                  )}
                  {data.markets_overview.map((m) => (
                    <Link
                      key={m.market_id}
                      href={`/markets/${m.market_id}`}
                      className="block rounded-xl bg-muted/50 p-3 hover:bg-muted"
                    >
                      <div className="flex items-center justify-between">
                        <p className="font-bold">{m.name}</p>
                        {m.processing_count > 0 && (
                          <Badge variant="ai" className="gap-1.5">
                            <PontoDot className="h-2 w-2" />
                            {m.processing_count} {t("dash.processing")}
                          </Badge>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span>
                          {m.products_count} {t("dash.products")}
                        </span>
                        <span>
                          {t("dash.stockValue")}: <span className="font-mono">{fmtMoney(m.stock_value)}</span>
                        </span>
                        <span>≈{m.customers_per_day} {t("markets.customersDay")}</span>
                        {m.low_stock_count > 0 && (
                          <span className="flex items-center gap-1 font-bold text-amber-600">
                            <AlertTriangle className="h-3 w-3" /> {m.low_stock_count}
                          </span>
                        )}
                      </div>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  format,
  sub,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  format: (v: number) => string;
  sub?: React.ReactNode;
}) {
  return (
    <Card className="hover-lift">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-muted-foreground">{label}</p>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Icon className="h-5 w-5" />
          </span>
        </div>
        <p className="mt-2 font-display text-2xl font-bold tracking-tight tabular-nums">
          <AnimatedNumber value={value} format={format} />
        </p>
        <div className="mt-1 min-h-5">{sub}</div>
      </CardContent>
    </Card>
  );
}

function Empty() {
  const { t } = useI18n();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
      <Inbox className="h-8 w-8 opacity-40" />
      {t("common.noData")}
    </div>
  );
}