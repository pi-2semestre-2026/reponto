"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, BadgeCheck, ClipboardCopy, ClipboardList, Loader2, PackageCheck } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { burstConfetti } from "@/lib/confetti";
import { fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { getToken } from "@/lib/token";
import type { PurchaseItem, PurchaseList } from "@/lib/types";

const STATUS_VARIANT = { esgotado: "destructive", comprar: "warning", atencao: "info" } as const;

export default function PurchaseListPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useI18n();
  const marketId = params.id;

  const [data, setData] = useState<PurchaseList | null>(null);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api.purchaseList(marketId);
      setData(d);
      setQty(Object.fromEntries(d.items.map((i) => [i.product_id, String(i.buy_quantity)])));
      setSelected(Object.fromEntries(d.items.map((i) => [i.product_id, i.status !== "atencao"])));
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [marketId]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    load();
  }, [load, router]);

  const chosen = useMemo(
    () => (data?.items ?? []).filter((i) => selected[i.product_id] && parseFloat(qty[i.product_id] || "0") > 0),
    [data, selected, qty]
  );
  const chosenCost = chosen.reduce((sum, i) => sum + (i.unit_cost ?? 0) * parseFloat(qty[i.product_id] || "0"), 0);

  const copyForSupplier = async () => {
    if (!data || chosen.length === 0) return;
    const lines = chosen.map((i) => `• ${i.name}${i.sku ? ` (${i.sku})` : ""}: ${fmtNum(qty[i.product_id])} ${i.unit}`);
    const text = `${t("purchase.supplierHeader").replace("{market}", data.market_name)}\n\n${lines.join("\n")}\n\n${t("purchase.supplierFooter")}`;
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("purchase.copied"));
    } catch {
      toast.error(t("common.error"));
    }
  };

  const receive = async () => {
    if (chosen.length === 0) return;
    setSaving(true);
    try {
      const r = await api.receivePurchase(
        marketId,
        chosen.map((i) => ({ product_id: i.product_id, quantity: parseFloat(qty[i.product_id]) }))
      );
      toast.success(t("purchase.received").replace("{n}", String(r.received)));
      burstConfetti();
      setTimeout(load, 1200);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header active="/markets" />
      <main className="container space-y-6 py-8">
        <div className="animate-fade-in-up flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <Button variant="ghost" size="icon" onClick={() => router.push(`/markets/${marketId}`)}>
              <ArrowLeft />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 font-display text-3xl font-bold tracking-tight">
                <ClipboardList className="h-7 w-7 text-primary" /> {t("purchase.title")}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {data ? `${data.market_name} · ${t("purchase.cycle").replace("{d}", String(data.cycle_days))}` : "…"}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={copyForSupplier} disabled={chosen.length === 0}>
              <ClipboardCopy /> {t("purchase.copy")}
            </Button>
            <Button variant="press" size="lg" onClick={receive} disabled={chosen.length === 0 || saving}>
              {saving ? <Loader2 className="animate-spin" /> : <PackageCheck />} {t("purchase.receive")}
            </Button>
          </div>
        </div>

        {data === null ? (
          <div className="space-y-4">
            <Skeleton className="h-24" />
            <Skeleton className="h-72" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Kpi label={t("purchase.kpi.items")} value={fmtNum(data.totals.items)} />
              <Kpi label={t("purchase.kpi.urgent")} value={fmtNum(data.totals.urgent)} tone={data.totals.urgent > 0 ? "danger" : undefined} />
              <Kpi label={t("purchase.kpi.selected")} value={fmtNum(chosen.length)} />
              <Kpi
                label={t("purchase.kpi.cost")}
                value={fmtMoney(chosenCost)}
                hint={data.totals.missing_cost > 0 ? t("purchase.missingCost").replace("{n}", String(data.totals.missing_cost)) : undefined}
              />
            </div>

            <Card className="animate-fade-in-up">
              <CardContent className="p-0">
                {data.items.length === 0 ? (
                  <div className="flex flex-col items-center gap-3 py-16 text-center">
                    <BadgeCheck className="h-12 w-12 text-primary" />
                    <p className="font-display text-lg font-bold">{t("purchase.empty")}</p>
                    <p className="text-sm text-muted-foreground">{t("purchase.emptySub")}</p>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-10" />
                        <TableHead>{t("common.name")}</TableHead>
                        <TableHead>{t("purchase.col.status")}</TableHead>
                        <TableHead className="text-right">{t("common.stock")}</TableHead>
                        <TableHead className="text-right">{t("market.coverage")}</TableHead>
                        <TableHead className="text-right">{t("purchase.col.rate")}</TableHead>
                        <TableHead className="w-32 text-right">{t("purchase.col.buy")}</TableHead>
                        <TableHead className="text-right">{t("purchase.col.cost")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((i) => (
                        <Row
                          key={i.product_id}
                          item={i}
                          checked={!!selected[i.product_id]}
                          onCheck={(v) => setSelected((s) => ({ ...s, [i.product_id]: v }))}
                          qty={qty[i.product_id] ?? ""}
                          onQty={(v) => setQty((q) => ({ ...q, [i.product_id]: v }))}
                          t={t}
                        />
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
            <p className="text-xs text-muted-foreground">{t("purchase.rule")}</p>
          </>
        )}
      </main>
    </div>
  );
}

function Row({
  item,
  checked,
  onCheck,
  qty,
  onQty,
  t,
}: {
  item: PurchaseItem;
  checked: boolean;
  onCheck: (v: boolean) => void;
  qty: string;
  onQty: (v: string) => void;
  t: (k: string) => string;
}) {
  const q = parseFloat(qty || "0");
  return (
    <TableRow className={checked ? "" : "opacity-55"}>
      <TableCell>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
          className="h-4 w-4 accent-[hsl(var(--primary))]"
        />
      </TableCell>
      <TableCell>
        <p className="font-bold">{item.name}</p>
        <p className="text-xs text-muted-foreground">
          {item.category_name ?? "—"}
          {item.sku ? ` · ${item.sku}` : ""}
        </p>
      </TableCell>
      <TableCell>
        <Badge variant={STATUS_VARIANT[item.status]}>{t(`purchase.status.${item.status}`)}</Badge>
      </TableCell>
      <TableCell className="text-right font-mono text-sm">
        {fmtNum(item.stock)} <span className="text-xs text-muted-foreground">/ min {fmtNum(Math.round(item.min_stock))}</span>
      </TableCell>
      <TableCell className="text-right font-mono text-sm">
        {item.coverage_days === null ? "—" : `${fmtNum(item.coverage_days)} ${t("market.days")}`}
      </TableCell>
      <TableCell className="text-right font-mono text-sm">
        {fmtNum(Math.round(item.daily_rate * 10) / 10)}
        <span className="text-xs text-muted-foreground">{t("market.perDay")}</span>
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-1.5">
          <Input
            type="number"
            min={0}
            step={item.unit === "kg" ? "0.5" : "1"}
            value={qty}
            onChange={(e) => onQty(e.target.value)}
            className="h-9 w-20 text-right font-mono"
          />
          <span className="w-10 text-left text-xs text-muted-foreground">{item.unit}</span>
        </div>
      </TableCell>
      <TableCell className="text-right font-mono text-sm">{item.unit_cost ? fmtMoney(item.unit_cost * q) : "—"}</TableCell>
    </TableRow>
  );
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "danger" }) {
  return (
    <div className="animate-fade-in-up rounded-2xl border bg-card p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`mt-1 font-display text-2xl font-bold ${tone === "danger" ? "text-destructive" : ""}`}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
