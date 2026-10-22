"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical, Info, Loader2, ShieldCheck, Trophy } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { getToken } from "@/lib/token";
import type { Evaluation } from "@/lib/types";
import { cn } from "@/lib/utils";

const C_ACTUAL = "hsl(var(--muted-foreground))";
const C_LGBM = "hsl(var(--primary))";
const C_MA4 = "hsl(var(--ponto))";
const TOOLTIP_STYLE = { borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--popover))", fontSize: 12 };

const pct = (v: number | undefined | null, digits = 1) =>
  v === undefined || v === null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: digits })}%`;
const shortDate = (iso: string) => {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
};

export default function ModelPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [data, setData] = useState<Evaluation | null>(null);
  const [sample, setSample] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    let active = true;
    const poll = async () => {
      try {
        const d = await api.evaluation();
        if (!active) return;
        setData(d);
        if (d.status === "running" || d.status === "idle") timer = setTimeout(poll, 5000);
      } catch {
        timer = setTimeout(poll, 8000);
      }
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [router]);

  const ready = data?.status === "ready" && data.models;
  const lg = data?.models?.find((m) => m.key === "lgbm");
  const ma = data?.models?.find((m) => m.key === "ma4");

  return (
    <div className="min-h-screen">
      <Header active="/modelo" />
      <main className="container space-y-6 py-8">
        <div className="animate-fade-in-up">
          <h1 className="flex items-center gap-2 font-display text-3xl font-bold tracking-tight">
            <FlaskConical className="h-7 w-7 text-primary" /> {t("model.title")}
          </h1>
          <p className="mt-1 max-w-3xl text-muted-foreground">{t("model.subtitle")}</p>
        </div>

        {!data && (
          <div className="space-y-4">
            <Skeleton className="h-32" />
            <Skeleton className="h-80" />
          </div>
        )}

        {data && !ready && (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
              {data.status === "error" ? (
                <>
                  <p className="font-display text-lg font-bold">{t("model.error")}</p>
                  <p className="font-mono text-xs text-muted-foreground">{data.error}</p>
                </>
              ) : (
                <>
                  <Loader2 className="h-10 w-10 animate-spin text-primary" />
                  <p className="font-display text-lg font-bold">{t("model.running")}</p>
                  <p className="max-w-md text-sm text-muted-foreground">
                    {t("model.runningSub")} {data.running_for_s ? `(${data.running_for_s}s)` : ""}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {ready && lg && ma && (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <Card className="animate-fade-in-up md:col-span-1">
                <CardContent className="space-y-1 p-6">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <Trophy className="h-4 w-4 text-primary" /> {t("model.kpi.reduction")}
                  </p>
                  <p className="font-display text-5xl font-bold text-primary">−{pct(data.improvement_vs_ma4_pct, 0)}</p>
                  <p className="text-sm text-muted-foreground">{t("model.kpi.reductionSub")}</p>
                </CardContent>
              </Card>
              <Card className="animate-fade-in-up">
                <CardContent className="space-y-3 p-6">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("model.kpi.wape")}</p>
                  <WapeBar label={lg.name} value={lg.wape} max={Math.max(lg.wape, ma.wape)} color="bg-primary" />
                  <WapeBar label={ma.name} value={ma.wape} max={Math.max(lg.wape, ma.wape)} color="bg-ponto" />
                  <p className="text-xs text-muted-foreground">{t("model.kpi.wapeSub")}</p>
                </CardContent>
              </Card>
              <Card className="animate-fade-in-up">
                <CardContent className="space-y-1 p-6">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("model.kpi.wins")}</p>
                  <p className="font-display text-5xl font-bold">{pct(data.win_rate_vs_ma4_pct)}</p>
                  <p className="text-sm text-muted-foreground">
                    {t("model.kpi.winsSub").replace("{n}", fmtNum(data.dataset?.series ?? 0))}
                  </p>
                </CardContent>
              </Card>
            </div>

            <Card className="animate-fade-in-up">
              <CardHeader>
                <CardTitle className="text-base">{t("model.table.title")}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("model.table.model")}</TableHead>
                      <TableHead className="text-right">MAE</TableHead>
                      <TableHead className="text-right">MAPE</TableHead>
                      <TableHead className="text-right">WAPE</TableHead>
                      <TableHead className="text-right">{t("model.table.bias")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...data.models!].sort((a, b) => a.wape - b.wape).map((m) => (
                      <TableRow key={m.key} className={cn(m.key === "lgbm" && "bg-primary/5")}>
                        <TableCell className="font-semibold">
                          {m.name}
                          {m.key === "lgbm" && (
                            <Badge variant="success" className="ml-2">
                              {t("model.table.best")}
                            </Badge>
                          )}
                          {m.key === "ma4" && (
                            <Badge variant="secondary" className="ml-2">
                              {t("model.table.spreadsheet")}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono">{fmtNum(m.mae)}</TableCell>
                        <TableCell className="text-right font-mono">{pct(m.mape, 2)}</TableCell>
                        <TableCell className="text-right font-mono font-bold">{pct(m.wape, 2)}</TableCell>
                        <TableCell className="text-right font-mono">
                          {m.bias > 0 ? "+" : ""}
                          {pct(m.bias, 2)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <p className="px-6 py-3 text-xs text-muted-foreground">{t("model.table.legend")}</p>
              </CardContent>
            </Card>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="animate-fade-in-up">
                <CardHeader>
                  <CardTitle className="text-base">{t("model.chart.total")}</CardTitle>
                </CardHeader>
                <CardContent className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.weekly_total}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="week" tickFormatter={shortDate} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                      <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={55} tickFormatter={(v) => fmtNum(v)} />
                      <ReTooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => shortDate(String(v))} formatter={(v: number) => fmtNum(v)} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Line dataKey="actual" name={t("model.series.actual")} stroke={C_ACTUAL} strokeWidth={2} dot={false} />
                      <Line dataKey="lgbm" name="LightGBM" stroke={C_LGBM} strokeWidth={2.5} dot={false} />
                      <Line dataKey="ma4" name={t("model.series.ma4")} stroke={C_MA4} strokeWidth={2} strokeDasharray="5 4" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card className="animate-fade-in-up">
                <CardHeader>
                  <CardTitle className="text-base">{t("model.chart.folds")}</CardTitle>
                </CardHeader>
                <CardContent className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.folds?.map((f) => ({ ...f, label: shortDate(f.start) }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                      <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={40} unit="%" />
                      <ReTooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => pct(v, 2)} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="lgbm_wape" name="LightGBM" fill={C_LGBM} radius={[6, 6, 0, 0]} />
                      <Bar dataKey="ma4_wape" name={t("model.series.ma4")} fill={C_MA4} radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>

            {data.samples && data.samples.length > 0 && (
              <Card className="animate-fade-in-up">
                <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
                  <CardTitle className="text-base">{t("model.chart.sample")}</CardTitle>
                  <div className="flex flex-wrap gap-1.5">
                    {data.samples.map((s, i) => (
                      <button
                        key={s.label}
                        onClick={() => setSample(i)}
                        className={cn(
                          "rounded-lg px-3 py-1 text-xs font-semibold transition-colors",
                          i === sample ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-muted/70"
                        )}
                      >
                        {s.label.split(" · ")[0]}
                      </button>
                    ))}
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="mb-2 text-xs text-muted-foreground">
                    {data.samples[sample].label} · WAPE LightGBM {pct(data.samples[sample].lgbm_wape)} vs.{" "}
                    {t("model.series.ma4").toLowerCase()} {pct(data.samples[sample].ma4_wape)}
                  </p>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={data.samples[sample].points}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="week" tickFormatter={shortDate} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                        <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={45} />
                        <ReTooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => shortDate(String(v))} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line dataKey="actual" name={t("model.series.actual")} stroke={C_ACTUAL} strokeWidth={2} dot={{ r: 2 }} />
                        <Line dataKey="lgbm" name="LightGBM" stroke={C_LGBM} strokeWidth={2.5} dot={false} connectNulls={false} />
                        <Line dataKey="ma4" name={t("model.series.ma4")} stroke={C_MA4} strokeWidth={2} strokeDasharray="5 4" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{t("model.chart.sampleNote")}</p>
                </CardContent>
              </Card>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="animate-fade-in-up">
                <CardHeader>
                  <CardTitle className="text-base">{t("model.importance")}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2.5">
                  {data.feature_importance?.filter((f) => f.pct >= 0.1).map((f) => (
                    <div key={f.feature}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="font-semibold">{f.label}</span>
                        <span className="font-mono">{pct(f.pct)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.max(1, f.pct)}%` }} />
                      </div>
                    </div>
                  ))}
                  <p className="pt-1 text-xs text-muted-foreground">{t("model.importanceNote")}</p>
                </CardContent>
              </Card>

              <Card className="animate-fade-in-up">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ShieldCheck className="h-4 w-4 text-primary" /> {t("model.method")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <Fact label={t("model.m.data")} value={`${data.dataset?.name}`} />
                  <Fact
                    label={t("model.m.series")}
                    value={`${fmtNum(data.dataset?.series ?? 0)} (${data.dataset?.stores} ${t("model.m.stores")} × ${data.dataset?.items} ${t("model.m.items")}), ${fmtNum(data.dataset?.weeks ?? 0)} ${t("model.m.weeks")}`}
                  />
                  <Fact
                    label={t("model.m.protocol")}
                    value={t("model.m.protocolValue")
                      .replace("{w}", String(data.protocol?.test_weeks))
                      .replace("{r}", String(data.protocol?.refit_every))
                      .replace("{f}", String(data.protocol?.folds))}
                  />
                  <Fact label={t("model.m.horizon")} value={data.protocol?.horizon ?? ""} />
                  <Fact label={t("model.m.leakage")} value={t("model.m.leakageValue")} />
                  <Fact
                    label={t("model.m.production")}
                    value={data.production_model?.ready ? data.production_model.kind : t("model.m.productionOff")}
                  />
                  <div className="mt-3 flex gap-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
                    <Info className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>{t("model.limits")}</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function WapeBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-semibold">{label}</span>
        <span className="font-mono font-bold">{pct(value, 2)}</span>
      </div>
      <div className="h-3 rounded-full bg-muted">
        <div className={`h-3 rounded-full ${color}`} style={{ width: `${(value / max) * 100}%` }} />
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <span className="w-32 shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}
