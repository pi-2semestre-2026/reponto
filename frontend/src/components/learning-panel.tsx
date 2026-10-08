"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  Loader2,
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
import type { LearningPanel as LearningPanelData } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
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
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label={t("market.learnedRate")} value={`${fmtNum(data.final_rate)}${t("market.perDay")}`} highlight />
              <Metric label={t("aiPanel.nSales")} value={String(data.n_sales)} />
              <Metric label={t("aiPanel.confidence")} value="" badge={data.confidence} variant={confidenceVariant} />
              <Metric label={t("aiPanel.window")} value={data.window_start && data.window_end ? `${fmtDateTime(data.window_start).slice(0, 10)} → ${fmtDateTime(data.window_end).slice(0, 10)}` : "—"} small />
            </div>

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
      <Progress value={pct} className="h-3 [&>div]:bg-transparent">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </Progress>
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