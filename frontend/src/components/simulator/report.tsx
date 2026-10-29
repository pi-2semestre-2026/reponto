"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Bot,
  Coins,
  Gamepad2,
  Loader2,
  Scale,
  TrendingUp,
} from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { burstConfetti } from "@/lib/confetti";
import { fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { simApi, type SimCoach, type SimReport } from "@/lib/simulator-api";

const VERDICT_STYLE: Record<string, { color: string; bg: string; Icon: typeof BadgeCheck }> = {
  acertivo: { color: "text-primary", bg: "bg-primary/10", Icon: BadgeCheck },
  parcial: { color: "text-amber-600", bg: "bg-amber-500/10", Icon: Scale },
  fora: { color: "text-destructive", bg: "bg-destructive/10", Icon: AlertTriangle },
  sem_dados: { color: "text-muted-foreground", bg: "bg-muted", Icon: Scale },
};

export function ReportPanel({ sid, onNewGame }: { sid: string; onNewGame: () => void }) {
  const { t } = useI18n();
  const [data, setData] = useState<{ report: SimReport; coach: SimCoach } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    simApi
      .report(sid)
      .then((d) => {
        if (!active) return;
        setData(d);
        if (d.report.verdict.level === "acertivo") burstConfetti();
      })
      .catch(() => {})
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [sid]);

  if (loading || !data) {
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col items-center gap-4 py-20">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="font-display text-lg font-bold">{t("sim.report.coachLoading")}</p>
        <div className="grid w-full gap-4 sm:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  const { report, coach } = data;
  const v = report.verdict;
  const style = VERDICT_STYLE[v.level] ?? VERDICT_STYLE.sem_dados;
  const verdictText = t(`sim.report.${v.level}`);
  const coachIsLLM = coach.source === "llm";

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <div className="animate-fade-in-up">
        <h2 className="font-display text-3xl font-bold tracking-tight">{t("sim.report.title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {report.config.scenario} · {report.config.days} {t("sim.day").toLowerCase()}s ·{" "}
          {t("sim.setup.cycle")}: {report.config.cycle_days}d · seed {report.config.seed}
        </p>
      </div>

      <Card className={`animate-fade-in-up border-2 ${v.level === "acertivo" ? "border-primary/40" : ""}`}>
        <CardContent className="flex flex-wrap items-center gap-5 p-6">
          <span className={`flex h-16 w-16 items-center justify-center rounded-2xl ${style.bg} ${style.color}`}>
            <style.Icon className="h-9 w-9" strokeWidth={2.25} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
              {t("sim.report.verdictTitle")}
            </p>
            <p className={`font-display text-2xl font-bold ${style.color}`}>{verdictText}</p>
            {v.direction && (
              <Badge variant={v.direction === "superestima" ? "warning" : "info"} className="mt-2">
                {t(`sim.report.${v.direction}`)}
              </Badge>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3 text-center sm:gap-6">
            <Metric label={t("sim.report.wapeWeek")} value={fmtPct(report.summary.rate_wape_pct ?? report.summary.wape_clean_pct)} />
            <Metric label={t("sim.report.bias")} value={fmtPct(report.summary.bias_clean_pct ?? report.summary.bias_pct)} />
            <Metric label={t("sim.service")} value={fmtPct(report.summary.service_pct)} />
          </div>
        </CardContent>
      </Card>

      <Card className="animate-fade-in-up [animation-delay:100ms]">
        <CardContent className="p-6">
          <p className="mb-4 flex items-center gap-2 font-display text-lg font-bold">
            <Gamepad2 className="h-5 w-5 text-ponto-ink" /> {t("sim.report.coach")}
            <Badge variant="ai" className="ml-auto gap-1.5">
              <Bot className="h-3.5 w-3.5" />
              {coachIsLLM ? t("sim.report.coachLLM") : t("sim.report.coachLocal")}
            </Badge>
          </p>
          <p className="font-display text-lg font-semibold">{coach.headline}</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
                {t("sim.report.observations")}
              </p>
              <ul className="space-y-1.5 text-sm">
                {coach.observations.map((o, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    {o}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">
                {t("sim.report.recommendations")}
              </p>
              <ul className="space-y-1.5 text-sm">
                {coach.recommendations.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ponto" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="animate-fade-in-up [animation-delay:150ms]">
          <CardContent className="p-5">
            <p className="mb-3 text-sm font-bold">{t("sim.report.chartCompare")}</p>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={report.daily_compare}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" width={40} />
                  <ReTooltip contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    type="monotone"
                    dataKey="actual"
                    name={t("sim.report.chartActual")}
                    stroke="hsl(var(--chart-1))"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="predicted"
                    name={t("sim.report.chartPredicted")}
                    stroke="hsl(var(--chart-2))"
                    strokeWidth={2}
                    strokeDasharray="5 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="animate-fade-in-up [animation-delay:200ms]">
          <CardContent className="p-5">
            <p className="mb-3 text-sm font-bold">{t("sim.report.chartCash")}</p>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={report.daily_cash}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" width={52} />
                  <ReTooltip
                    formatter={(v: number) => fmtMoney(v)}
                    contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))" }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="revenue" name={t("sim.revenue")} fill="hsl(var(--chart-1))" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="lost_r" name={t("sim.lostR")} fill="hsl(var(--chart-2))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="animate-fade-in-up [animation-delay:250ms]">
        <CardContent className="p-0">
          <p className="px-6 pt-5 text-sm font-bold">{t("sim.report.percat")}</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Categoria</TableHead>
                <TableHead>{t("sim.report.wapeWeek")}</TableHead>
                <TableHead>{t("sim.report.bias")}</TableHead>
                <TableHead>{t("sim.report.stockoutPct")}</TableHead>
                <TableHead className="text-right">{t("sim.report.samples")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.per_category.map((c) => (
                <TableRow key={c.category}>
                  <TableCell className="font-bold">{c.category}</TableCell>
                  <TableCell>
                    <WapeCell pct={c.rate_wape_pct ?? c.wape_clean_pct ?? c.wape_pct} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">{fmtPct(c.bias_pct)}</TableCell>
                  <TableCell className="font-mono text-xs">{fmtPct(c.stockout_pct)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{c.samples}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-4 pb-4">
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="flex items-center gap-1.5">
            <Coins className="h-4 w-4 text-primary" /> {t("sim.revenue")}:{" "}
            <b className="font-mono">{fmtMoney(report.totals.revenue)}</b>
          </span>
          <span className="flex items-center gap-1.5">
            <TrendingUp className="h-4 w-4 text-primary" /> {t("sim.profit")}:{" "}
            <b className="font-mono">{fmtMoney(report.totals.profit)}</b>
          </span>
          <span>
            {t("sim.lostR")}: <b className="font-mono">{fmtMoney(report.totals.lost_r)}</b>
          </span>
          <span>
            {t("dash.items")}: <b className="font-mono">{fmtNum(report.totals.demand_units)}</b>
          </span>
        </div>
        <Button variant="press" size="lg" onClick={onNewGame}>
          <Gamepad2 /> {t("sim.report.newGame")}
        </Button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-muted/60 px-4 py-2.5">
      <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-mono text-lg font-semibold">{value}</p>
    </div>
  );
}

function WapeCell({ pct }: { pct: number | null }) {
  const color = pct == null ? "text-muted-foreground" : pct <= 20 ? "text-primary" : pct <= 35 ? "text-amber-600" : "text-destructive";
  return <span className={`font-mono text-xs font-bold ${color}`}>{fmtPct(pct)}</span>;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v > 0 && !v.toString().startsWith("-") ? "+" : ""}${v}%`;
}
