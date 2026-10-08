"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Minus, Plus, ShoppingCart, ShoppingBasket, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Product } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  marketId: string;
  products: Product[];
  onDone: () => void;
}

export function SaleCartDialog({ open, onOpenChange, marketId, products, onDone }: Props) {
  const { t } = useI18n();
  const [cart, setCart] = useState<Record<string, number>>({});
  const [finishing, setFinishing] = useState(false);
  const [retro, setRetro] = useState(false);
  const [retroDate, setRetroDate] = useState("");

  useEffect(() => {
    if (open) {
      setCart({});
      setRetro(false);
      setRetroDate("");
    }
  }, [open]);

  const ready = products.filter((p) => p.status === "ready");

  const addToCart = (p: Product) => {
    setCart((c) => ({ ...c, [p.id]: (c[p.id] || 0) + 1 }));
  };
  const changeQty = (p: Product, delta: number) => {
    setCart((c) => {
      const next = Math.max(0, (c[p.id] || 0) + delta);
      if (next > parseFloat(p.stock)) {
        toast.error(
          `${t("common.error")}: ${p.name} — ${t("common.stock")} ${fmtNum(p.stock)}`
        );
        return { ...c, [p.id]: parseFloat(p.stock) };
      }
      const copy = { ...c };
      if (next === 0) delete copy[p.id];
      else copy[p.id] = next;
      return copy;
    });
  };
  const setQty = (p: Product, raw: string) => {
    const v = parseFloat(raw) || 0;
    const max = parseFloat(p.stock);
    if (v > max) {
      toast.error(`Estoque insuficiente para ${p.name}: ${fmtNum(p.stock)} disponível`);
      setCart((c) => ({ ...c, [p.id]: max }));
      return;
    }
    setCart((c) => {
      const copy = { ...c };
      if (v <= 0) delete copy[p.id];
      else copy[p.id] = v;
      return copy;
    });
  };

  const cartItems = useMemo(
    () => ready.filter((p) => cart[p.id] > 0),
    [ready, cart]
  );
  const total = cartItems.reduce((s, p) => s + parseFloat(p.price) * cart[p.id], 0);

  const finish = async () => {
    if (cartItems.length === 0) return;
    setFinishing(true);
    try {
      await api.createSale({
        market_id: marketId,
        items: cartItems.map((p) => ({ product_id: p.id, quantity: cart[p.id] })),
        sold_at: retro && retroDate ? new Date(retroDate + "T12:00:00Z").toISOString() : undefined,
      });
      toast.success(t("sale.success"));
      onOpenChange(false);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setFinishing(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShoppingBasket className="h-5 w-5 text-primary" /> {t("sale.title")}
          </DialogTitle>
          <DialogDescription>{t("sale.desc")}</DialogDescription>
        </DialogHeader>

        <div className="grid max-h-[55vh] gap-5 overflow-y-auto pr-1 md:grid-cols-2">
          <div className="space-y-2">
            <p className="text-sm font-bold text-muted-foreground">{t("market.products")}</p>
            {ready.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">{t("sale.empty")}</p>}
            {ready.map((p) => (
              <div key={p.id} className="flex items-center gap-3 rounded-xl border bg-card p-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold">{p.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {fmtMoney(p.price)} · {t("common.stock")}: {fmtNum(p.stock)}
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => addToCart(p)} disabled={parseFloat(p.stock) <= 0}>
                  <Plus className="h-4 w-4" /> {t("sale.add")}
                </Button>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <p className="flex items-center gap-1.5 text-sm font-bold text-muted-foreground">
              <ShoppingCart className="h-4 w-4" /> {t("sale.cart")}
            </p>
            {cartItems.length === 0 && (
              <p className="py-6 text-center text-sm text-muted-foreground">{t("sale.cartEmpty")}</p>
            )}
            {cartItems.map((p) => (
              <div key={p.id} className="flex items-center gap-2 rounded-xl border bg-accent/30 p-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold">{p.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {fmtMoney(p.price)} × {fmtNum(String(cart[p.id]))} ={" "}
                    <span className="font-bold text-foreground">{fmtMoney(String(parseFloat(p.price) * cart[p.id]))}</span>
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => changeQty(p, -1)}>
                    <Minus className="h-3.5 w-3.5" />
                  </Button>
                  <Input
                    className="h-7 w-16 px-2 text-center"
                    value={cart[p.id]}
                    onChange={(e) => setQty(p, e.target.value)}
                    type="number"
                    min={0}
                    max={parseFloat(p.stock)}
                  />
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => changeQty(p, 1)}>
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => setQty(p, "0")}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <Separator />
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Switch checked={retro} onCheckedChange={setRetro} id="retro" />
            <div>
              <Label htmlFor="retro" className="text-sm">
                {t("sale.retro")}
              </Label>
              <p className="text-xs text-muted-foreground">{t("sale.retroDesc")}</p>
            </div>
            {retro && <Input type="date" className="h-9 w-40" value={retroDate} onChange={(e) => setRetroDate(e.target.value)} max={new Date().toISOString().slice(0, 10)} />}
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">{t("sale.total")}</p>
            <p className={cn("font-display text-2xl font-bold text-primary")}>{fmtMoney(String(total))}</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant="press" onClick={finish} disabled={cartItems.length === 0 || finishing}>
            {finishing ? <Loader2 className="animate-spin" /> : <Badge variant="default" className="rounded-md px-1.5 text-[10px]">{cartItems.length}</Badge>}
            {t("sale.finish")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}