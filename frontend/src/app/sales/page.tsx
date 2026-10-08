"use client";

import { useCallback, useEffect, useState } from "react";
import { Ban, Eye, Loader2, ReceiptText, X } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Market, Sale } from "@/lib/types";

export default function SalesPage() {
  const { t } = useI18n();
  const [sales, setSales] = useState<Sale[] | null>(null);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [marketId, setMarketId] = useState<string>("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [detail, setDetail] = useState<Sale | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Sale | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(() => {
    api
      .sales({ market_id: marketId || undefined, date_from: from || undefined, date_to: to || undefined })
      .then(setSales)
      .catch((e) => toast.error(e.message));
  }, [marketId, from, to]);

  useEffect(() => {
    api.markets().then(setMarkets).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const cancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api.cancelSale(cancelTarget.id);
      toast.success(t("toast.saleCancelled"));
      setCancelTarget(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header active="/sales" />
      <main className="container space-y-6 py-8">
        <div className="animate-fade-in-up">
          <h1 className="font-display text-3xl font-bold tracking-tight">{t("sales.title")}</h1>
          <p className="mt-1 text-muted-foreground">{t("sales.subtitle")}</p>
        </div>

        <div className="animate-fade-in flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <p className="text-xs font-bold text-muted-foreground">{t("sales.market")}</p>
            <Select value={marketId || "all"} onValueChange={(v) => setMarketId(v === "all" ? "" : v)}>
              <SelectTrigger className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("sales.allMarkets")}</SelectItem>
                {markets.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold text-muted-foreground">{t("sales.from")}</p>
            <Input type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="space-y-1">
            <p className="text-xs font-bold text-muted-foreground">{t("sales.to")}</p>
            <Input type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          <Button
            variant="outline"
            onClick={() => {
              setMarketId("");
              setFrom("");
              setTo("");
            }}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <Card className="animate-fade-in-up">
          <CardContent className="p-0">
            {sales === null ? (
              <div className="space-y-3 p-6">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : sales.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-16 text-center">
                <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <ReceiptText className="h-8 w-8" strokeWidth={2.25} />
                </span>
                <p className="text-muted-foreground">{t("common.noData")}</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    <TableHead>{t("sales.market")}</TableHead>
                    <TableHead>{t("sales.items")}</TableHead>
                    <TableHead>{t("sale.total")}</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sales.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="text-sm">{fmtDateTime(s.sold_at)}</TableCell>
                      <TableCell className="text-sm font-semibold">
                        {markets.find((m) => m.id === s.market_id)?.name ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {s.items.length} {t("sales.items")}
                        <span className="ml-1 text-muted-foreground">
                          ({fmtNum(s.items.reduce((acc, i) => acc + parseFloat(i.quantity), 0))} un)
                        </span>
                      </TableCell>
                      <TableCell className="font-mono font-semibold text-primary">{fmtMoney(s.total)}</TableCell>
                      <TableCell>
                        {s.status === "completed" ? (
                          <Badge variant="success">{t("sales.completed")}</Badge>
                        ) : (
                          <Badge variant="destructive">{t("sales.cancelled")}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDetail(s)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                          {s.status === "completed" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive"
                              onClick={() => setCancelTarget(s)}
                            >
                              <Ban className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sales.details")}</DialogTitle>
            {detail && <DialogDescription>{fmtDateTime(detail.sold_at)}</DialogDescription>}
          </DialogHeader>
          {detail && (
            <div className="space-y-2">
              {detail.items.map((i) => (
                <div key={i.id} className="flex items-center justify-between rounded-xl bg-muted/50 p-3 text-sm">
                  <div>
                    <p className="font-bold">{i.product_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {fmtNum(i.quantity)} × {fmtMoney(i.unit_price)}
                    </p>
                  </div>
                  <span className="font-bold">{fmtMoney(i.subtotal)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t pt-3">
                <span className="font-bold">{t("sale.total")}</span>
                <span className="font-display text-xl font-bold text-primary">{fmtMoney(detail.total)}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!cancelTarget} onOpenChange={(v) => !v && setCancelTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("sales.cancelConfirm")}</DialogTitle>
            <DialogDescription>{t("sales.cancelDesc")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" onClick={cancel} disabled={cancelling}>
              {cancelling && <Loader2 className="animate-spin" />}
              {t("sales.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}