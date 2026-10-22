"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  FileUp,
  Loader2,
  MessageSquareText,
  PackageCheck,
  ShieldCheck,
  Package,
  Pencil,
  RefreshCw,
  ShoppingCart,
  Sparkles,
  Store,
  Undo2,
  type LucideIcon,
} from "lucide-react";
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmtDateTime, fmtNum } from "@/lib/format";
import type { Explanation, LearningPanel as LearningPanelData, WeekProfile } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const TRIGGER_ICON: Record<string, LucideIcon> = {
  product_created: Sparkles,
  sale: ShoppingCart,
  sale_cancelled: Undo2,
  stock_adjust: Package,
  product_updated: Pencil,
  market_updated: Store,
  recalc: RefreshCw,
  import: FileUp,
  purchase: PackageCheck,
};

export function LearningPanelDialog({
  productId,
  open,
  onOpenChange,
}: {
  productId: string | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useI18n();
  const [data, setData] = useState<LearningPanelData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && productId) {
      setLoading(true);
      api
        .learning(productId)
        .then(setData)
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [open, productId]);

  const confidenceVariant = data?.confidence === "alta" ? "success" : data?.confidence === "media" ? "warning" : "destructive";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-ponto-ink" /> {t("aiPanel.title")}
          </DialogTitle>
          {data && (
            <p className="text-sm text-muted-foreground">
              {data.product_name}
              {data.category_name ? ` · ${data.category_name}` : ""}
            </p>
          )}
        </DialogHeader>

        {loading || !data ? (
          <div className="flex h-40 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-5">
            {productId && <ExplanationCard productId={productId} />}

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label={t("market.learnedRate")} value={`${fmtNum(data.final_rate)}${t("market.perDay")}`} highlight />
              <Metric label={t("aiPanel.nSales")} value={String(data.n_sales)} />
              <Metric label={t("aiPanel.confidence")} value="" badge={data.confidence} variant={confidenceVariant} />
              <Metric label={t("aiPanel.window")} value={data.window_start && data.window_end ? `${fmtDateTime(data.window_start).slice(0, 10)} → ${fmtDateTime(data.window_end).slice(0, 10)}` : "—"} small />
            </div>

            {data.profile && <WeekProfileCard profile={data.profile} />}

            <div>
              <p className="mb-2 text-sm font-bold">{t("aiPanel.blend")}</p>
              <div className="space-y-3 rounded-2xl border bg-muted/40 p-4">
                <BlendRow
                  label={t("aiPanel.yourData")}
                  pct={data.data_share_pct}
                  color="bg-emerald-500"
                  detail={`${fmtNum(data.observed_rate)}/d`}
                />
                <BlendRow
                  label={t("aiPanel.dataset")}
                  pct={data.dataset_share_pct}
                  color="bg-primary"
                  detail={`${fmtNum(data.prior_rate)}/d`}
                />
                <p className="rounded-xl bg-card p-3 text-center font-mono text-xs">{data.formula}</p>
              </div>
            </div>

            {data.evolution.length > 1 && (
              <div>
                <p className="mb-2 text-sm font-bold">{t("aiPanel.evolution")}</p>
                <div className="h-44 rounded-2xl border bg-card p-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.evolution.map((e, i) => ({ ...e, idx: i + 1 }))}>
                      <XAxis dataKey="idx" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                      <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={45} />
                      <ReTooltip
                        contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--popover))" }}
                      />
                      <Line type="monotone" dataKey="final_rate" name="final" stroke="hsl(var(--ponto))" strokeWidth={2.5} dot={false} />
                      <Line type="monotone" dataKey="observed_rate" name="obs" stroke="hsl(var(--chart-1))" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                      <Line type="monotone" dataKey="prior_rate" name="prior" stroke="hsl(150 10% 60%)" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            <div>
              <p className="mb-2 text-sm font-bold">{t("aiPanel.currentValues")}</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric label={t("aiPanel.minStock")} value={fmtNum(data.min_stock)} />
                <Metric label={t("aiPanel.maxStock")} value={fmtNum(data.max_stock)} />
                <Metric label={t("aiPanel.recommended")} value={fmtNum(data.recommended_quantity)} highlight />
                <Metric
                  label={t("aiPanel.safety")}
                  value={
                    data.logs[0] ? fmtNum(JSON.parse(data.logs[0].details).seguranca ?? "0") : "—"
                  }
                />
              </div>
            </div>

            <Separator />
            <div>
              <p className="mb-2 text-sm font-bold">{t("aiPanel.history")}</p>
              <div className="rounded-2xl border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[130px]">{t("aiPanel.reason")}</TableHead>
                      <TableHead>Prior</TableHead>
                      <TableHead>Obs.</TableHead>
                      <TableHead>α</TableHead>
                      <TableHead>Final</TableHead>
                      <TableHead>n</TableHead>
                      <TableHead className="w-[140px]">{t("common.stock")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.logs.map((log) => {
                      const d = JSON.parse(log.details || "{}");
                      return (
                        <TableRow key={log.id}>
                          <TableCell>
                            <span className="flex items-center gap-1.5 text-xs font-semibold">
                              {(() => {
                                const TriggerIcon = TRIGGER_ICON[log.trigger];
                                return TriggerIcon ? (
                                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-ponto-soft text-ponto-ink">
                                    <TriggerIcon className="h-3.5 w-3.5" />
                                  </span>
                                ) : (
                                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-muted">•</span>
                                );
                              })()}
                              <span className="flex flex-col">
                                <span>{d.motivo || log.trigger}</span>
                                <span className="block text-[10px] font-normal text-muted-foreground">
                                  {fmtDateTime(log.created_at)}
                                </span>
                              </span>
                            </span>
                          </TableCell>
                          <TableCell className="text-xs">{log.prior_rate.toFixed(3)}</TableCell>
                          <TableCell className="text-xs">{log.observed_rate.toFixed(3)}</TableCell>
                          <TableCell className="text-xs">{log.alpha.toFixed(2)}</TableCell>
                          <TableCell className="text-xs font-bold text-primary">{log.final_rate.toFixed(3)}</TableCell>
                          <TableCell className="text-xs">{log.n_sales}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            min {fmtNum(log.min_stock)} · rec {fmtNum(log.recommended_quantity)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ExplanationCard({ productId }: { productId: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(true);
  const [showChecks, setShowChecks] = useState(false);

  const load = (refresh = false) => {
    setLoading(true);
    api
      .explanation(productId, refresh)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]);

  return (
    <div className="rounded-2xl border-2 border-primary/20 bg-primary/5 p-4">
      <div className="mb-2 flex items-center gap-2">
        <MessageSquareText className="h-4 w-4 text-primary" />
        <p className="text-sm font-bold">{t("explain.title")}</p>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-7 px-2 text-xs"
          onClick={() => load(true)}
          disabled={loading}
          title={t("explain.regenerate")}
        >
          <RefreshCw className={loading ? "animate-spin" : ""} />
        </Button>
      </div>
      {loading && !data ? (
        <div className="space-y-2">
          <div className="h-3 w-full animate-pulse rounded bg-primary/15" />
          <div className="h-3 w-11/12 animate-pulse rounded bg-primary/15" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-primary/15" />
          <p className="pt-1 text-xs text-muted-foreground">{t("explain.loading")}</p>
        </div>
      ) : data ? (
        <>
          <p className={`text-[15px] leading-relaxed ${loading ? "opacity-50" : ""}`}>{data.text}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant="success" className="gap-1">
              <ShieldCheck className="h-3 w-3" />
              {t("explain.verified").replace("{n}", String(data.checked.length))}
            </Badge>
            <Badge variant={data.source === "llm" ? "ai" : "secondary"}>
              {data.source === "llm" ? t("explain.byLlm") : t("explain.byTemplate")}
            </Badge>
            <button className="text-xs font-semibold text-primary hover:underline" onClick={() => setShowChecks((v) => !v)}>
              {showChecks ? t("explain.hideChecks") : t("explain.showChecks")}
            </button>
          </div>
          {showChecks && (
            <div className="mt-3 space-y-2 rounded-xl bg-card p-3 text-xs">
              <p className="text-muted-foreground">{t("explain.howChecked")}</p>
              <div className="flex flex-wrap gap-1.5">
                {data.checked.map((c, i) => (
                  <span key={i} className="rounded-lg bg-muted px-2 py-0.5 font-mono">
                    {c.value} = {c.fact}
                  </span>
                ))}
              </div>
              {data.rejected && (
                <div className="rounded-lg border border-amber-300/60 bg-amber-50 p-2 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
                  <p className="font-semibold">{t("explain.rejected")}</p>
                  <p className="mt-1">{data.rejected.problems.join("; ")}</p>
                  <p className="mt-1 italic opacity-80">“{data.rejected.text}”</p>
                </div>
              )}
              {!data.llm_enabled && <p className="text-muted-foreground">{t("explain.noLlm")}</p>}
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">{t("explain.error")}</p>
      )}
    </div>
  );
}

function WeekProfileCard({ profile }: { profile: WeekProfile }) {
  const { t } = useI18n();
  const signed = (v: number) => `${v > 0 ? "+" : ""}${Math.round(v)}%`;
  const sourceText =
    profile.source === "produto"
      ? t("profile.sourceProduct").replace("{n}", String(profile.days_observed))
      : profile.source === "loja"
        ? t("profile.sourceStore")
        : t("profile.sourceDataset");
  return (
    <div className="rounded-2xl border bg-card p-4">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <p className="text-sm font-bold">{t("profile.title")}</p>
        <Badge variant={profile.source === "padrao" ? "secondary" : "ai"}>{sourceText}</Badge>
      </div>
      {profile.source !== "padrao" && profile.peak_pct >= 10 && (
        <p className="mb-2 text-sm">
          {t("profile.peak")
            .replace("{day}", profile.peak_phrase)
            .replace("{pct}", String(profile.peak_pct))}
        </p>
      )}
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={profile.next_days}>
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
            <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={35} />
            <ReTooltip
              formatter={(v: number) => [fmtNum(Math.round(v * 10) / 10), t("profile.forecast")]}
              contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--popover))" }}
            />
            <Bar dataKey="qty" radius={[6, 6, 0, 0]}>
              {profile.next_days.map((d, i) => (
                <Cell key={i} fill={d.weekday === profile.peak_weekday ? "hsl(var(--ponto))" : "hsl(var(--primary))"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 grid grid-cols-7 gap-1 text-center">
        {profile.labels.map((l, i) => (
          <div key={l} className={`rounded-lg py-1 ${i === profile.peak_weekday ? "bg-ponto-soft" : "bg-muted/50"}`}>
            <p className="text-[10px] font-semibold uppercase text-muted-foreground">{l}</p>
            <p className="font-mono text-xs font-bold">{signed((profile.index[i] - 1) * 100)}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        {t("profile.minRule")
          .replace("{d}", fmtNum(Math.round(profile.reorder_days * 10) / 10))
          .replace("{q}", fmtNum(Math.round(profile.reorder_demand * 10) / 10))}{" "}
        {profile.safety_method === "erro" && profile.sigma_daily !== null
          ? t("profile.safetyError")
              .replace("{s}", fmtNum(Math.round(profile.sigma_daily * 10) / 10))
              .replace("{p}", String(profile.service_level_pct))
          : t("profile.safetyRule")}
      </p>
    </div>
  );
}

function Metric({
  label,
  value,
  highlight,
  badge,
  variant,
  small,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  badge?: string;
  variant?: "success" | "warning" | "destructive";
  small?: boolean;
}) {
  return (
    <div className={`rounded-2xl border bg-card p-3 ${highlight ? "ring-2 ring-primary/40" : ""}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      {badge ? (
        <Badge variant={variant} className="mt-1">
          {badge === "alta" ? "Alta" : badge === "media" ? "Média" : "Baixa"}
        </Badge>
      ) : (
        <p className={`mt-1 font-black ${small ? "text-xs" : "text-lg"}`}>{value}</p>
      )}
    </div>
  );
}

function BlendRow({ label, pct, color, detail }: { label: string; pct: number; color: string; detail: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs font-bold">
        <span>
          {label} <span className="text-muted-foreground">({detail})</span>
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function LearningButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <Button variant="ghost" size="sm" className="h-8 gap-1 text-ponto-ink" onClick={onClick} title={t("aiPanel.title")}>
      {children}
    </Button>
  );
}