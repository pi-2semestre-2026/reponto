"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Brain,
  Loader2,
  MapPin,
  Package,
  Pencil,
  Plus,
  Settings,
  ShoppingBasket,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { LearningPanelDialog } from "@/components/learning-panel";
import { PontoDot } from "@/components/ponto-dot";
import { SaleCartDialog } from "@/components/sale-cart";
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
import { Label } from "@/components/ui/label";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Market, Product } from "@/lib/types";

const UNITS = ["unidade", "kg", "g", "L", "ml", "pacote", "caixa", "dz"];

export default function MarketPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useI18n();
  const marketId = params.id;

  const [market, setMarket] = useState<Market | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [saleOpen, setSaleOpen] = useState(false);
  const [learningId, setLearningId] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [adjustProduct, setAdjustProduct] = useState<Product | null>(null);
  const [deleteProduct, setDeleteProduct] = useState<Product | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const hadProcessing = useRef(false);

  const load = useCallback(async () => {
    try {
      const [m, ps] = await Promise.all([api.markets(), api.products(marketId)]);
      const me = m.find((x) => x.id === marketId) ?? null;
      setMarket(me);
      setProducts(ps);
      const processing = ps.some((p) => p.status === "processing");
      if (processing) hadProcessing.current = true;
      else if (hadProcessing.current) {
        hadProcessing.current = false;
        toast.success(t("toast.aiDone"));
      }
      return processing;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    }
  }, [marketId, t]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      const stillProcessing = await load();
      if (!active) return;
      timer = setTimeout(poll, stillProcessing ? 2000 : 15000);
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [load]);

  if (market === null && products === null) {
    return (
      <div className="min-h-screen">
        <Header active="/markets" />
        <main className="container space-y-4 py-10">
          <Skeleton className="h-28" />
          <Skeleton className="h-72" />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header active="/markets" />
      <main className="container space-y-6 py-8">
        <div className="animate-fade-in-up flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <Button variant="ghost" size="icon" onClick={() => router.push("/markets")}>
              <ArrowLeft />
            </Button>
            <div>
              <h1 className="font-display text-3xl font-bold tracking-tight">{market?.name}</h1>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                {market?.location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-4 w-4" /> {market.location}
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <Users className="h-4 w-4" /> ≈{market?.customers_per_day} {t("markets.customersDay")}
                </span>
                <span className="flex items-center gap-1">
                  <Package className="h-4 w-4" /> {market?.replenishment_cycle_days} {t("wizard.daysUnit")}
                </span>
                <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setSettingsOpen(true)}>
                  <Settings className="h-4 w-4" /> {t("market.settings")}
                </Button>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setNewOpen(true)}>
              <Plus /> {t("market.newProduct")}
            </Button>
            <Button variant="press" size="lg" onClick={() => setSaleOpen(true)}>
              <ShoppingBasket /> {t("market.newSale")}
            </Button>
          </div>
        </div>

        <Card className="animate-fade-in-up">
          <CardContent className="p-0">
            {products === null ? (
              <div className="space-y-3 p-6">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : products.length === 0 ? (
              <div className="flex flex-col items-center gap-4 py-16 text-center">
                <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Package className="h-8 w-8" strokeWidth={2.25} />
                </span>
                <p className="font-display text-lg font-bold">{t("market.noProducts")}</p>
                <Button variant="press" onClick={() => setNewOpen(true)}>
                  <Plus /> {t("market.newProduct")}
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.name")}</TableHead>
                    <TableHead>{t("nav.categories")}</TableHead>
                    <TableHead>{t("common.price")}</TableHead>
                    <TableHead>{t("common.stock")}</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>{t("market.learnedRate")}</TableHead>
                    <TableHead className="text-right">{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {products.map((p) => (
                    <ProductRow
                      key={p.id}
                      p={p}
                      onEdit={() => setEditProduct(p)}
                      onAdjust={() => setAdjustProduct(p)}
                      onDelete={() => setDeleteProduct(p)}
                      onLearning={() => setLearningId(p.id)}
                      t={t}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      <SaleCartDialog
        open={saleOpen}
        onOpenChange={setSaleOpen}
        marketId={marketId}
        products={products ?? []}
        onDone={load}
      />
      <LearningPanelDialog productId={learningId} open={!!learningId} onOpenChange={(v) => !v && setLearningId(null)} />
      <ProductDialog
        open={newOpen || !!editProduct}
        onOpenChange={(v) => {
          if (!v) {
            setNewOpen(false);
            setEditProduct(null);
          }
        }}
        marketId={marketId}
        product={editProduct}
        onSaved={load}
      />
      <AdjustDialog product={adjustProduct} onOpenChange={(v) => !v && setAdjustProduct(null)} onSaved={load} />
      <DeleteDialog
        open={!!deleteProduct}
        onOpenChange={(v) => {
          if (!v) setDeleteProduct(null);
        }}
        title={t("product.delete.confirm")}
        desc={t("product.delete.desc")}
        onConfirm={async () => {
          if (!deleteProduct) return;
          await api.deleteProduct(deleteProduct.id);
          toast.success(t("toast.deleted"));
          setDeleteProduct(null);
          load();
        }}
      />
      {market && (
        <MarketSettingsDialog
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          market={market}
          onSaved={load}
        />
      )}
    </div>
  );
}

function ProductRow({
  p,
  onEdit,
  onAdjust,
  onDelete,
  onLearning,
  t,
}: {
  p: Product;
  onEdit: () => void;
  onAdjust: () => void;
  onDelete: () => void;
  onLearning: () => void;
  t: (k: string) => string;
}) {
  const stock = parseFloat(p.stock);
  const min = parseFloat(p.min_stock);
  const status =
    p.status === "processing"
      ? "processing"
      : stock <= 0
        ? "out"
        : stock <= min
          ? "low"
          : "ok";

  const confVariant = p.confidence === "alta" ? "success" : p.confidence === "media" ? "warning" : "info";

  return (
    <TableRow className="group">
      <TableCell>
        <p className="font-bold">{p.name}</p>
        <p className="text-xs text-muted-foreground">{p.unit}</p>
      </TableCell>
      <TableCell>
        {p.status === "processing" ? (
          <Badge variant="ai" className="gap-1.5">
            <PontoDot className="h-2 w-2" /> {t("market.aiProcessing")}
          </Badge>
        ) : (
          <Badge variant="secondary">{p.category_name ?? "—"}</Badge>
        )}
      </TableCell>
      <TableCell className="font-semibold">{fmtMoney(p.price)}</TableCell>
      <TableCell>
        <span className={status === "out" ? "font-bold text-destructive" : status === "low" ? "font-bold text-amber-600" : ""}>
          {fmtNum(p.stock)}
        </span>
      </TableCell>
      <TableCell>
        {status === "processing" && (
          <Badge variant="ai" className="gap-1.5">
            <PontoDot className="h-2 w-2" /> IA
          </Badge>
        )}
        {status === "out" && <Badge variant="destructive">{t("market.stockStatus.out")}</Badge>}
        {status === "low" && <Badge variant="warning">{t("market.stockStatus.low")}</Badge>}
        {status === "ok" && <Badge variant="success">{t("market.stockStatus.ok")}</Badge>}
      </TableCell>
      <TableCell>
        {p.status === "processing" ? (
          <span className="text-xs text-muted-foreground">…</span>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <button onClick={onLearning} className="flex items-center gap-1.5 hover:opacity-80">
                <span className="font-bold">{fmtNum(p.learned_rate)}</span>
                <span className="text-xs text-muted-foreground">{t("market.perDay")}</span>
                <Badge variant={confVariant} className="px-1.5 py-0 text-[10px]">
                  {t(`market.confidence.${p.confidence}`)}
                </Badge>
              </button>
            </TooltipTrigger>
            <TooltipContent>{t("aiPanel.title")}</TooltipContent>
          </Tooltip>
        )}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-0.5 opacity-60 transition-opacity group-hover:opacity-100">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-ponto-ink" onClick={onLearning}>
            <Brain className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onAdjust} title={t("product.adjust.title")}>
            <Package className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onEdit}>
            <Pencil className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

function ProductDialog({
  open,
  onOpenChange,
  marketId,
  product,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  marketId: string;
  product: Product | null;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [stock, setStock] = useState("");
  const [unit, setUnit] = useState("unidade");
  const [saving, setSaving] = useState(false);
  const isEdit = !!product;

  useEffect(() => {
    if (open) {
      setName(product?.name ?? "");
      setPrice(product ? product.price : "");
      setStock(product ? product.stock : "");
      setUnit(product?.unit ?? "unidade");
    }
  }, [open, product]);

  const save = async () => {
    setSaving(true);
    try {
      if (isEdit && product) {
        await api.updateProduct(product.id, { name, price: parseFloat(price), unit });
        toast.success(t("toast.updated"));
      } else {
        await api.createProduct(marketId, { name, price: parseFloat(price), stock: parseFloat(stock), unit });
        toast.success(t("toast.productCreated"));
      }
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t("product.edit.title") : t("product.dialog.title")}</DialogTitle>
          {!isEdit && <DialogDescription>{t("product.dialog.desc")}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t("product.dialog.name")}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("product.dialog.namePh")} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>{t("product.dialog.price")}</Label>
              <Input type="number" step="0.01" min={0} value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
            {!isEdit && (
              <div className="space-y-2">
                <Label>{t("product.dialog.stock")}</Label>
                <Input type="number" step="0.001" min={0} value={stock} onChange={(e) => setStock(e.target.value)} />
              </div>
            )}
            <div className={isEdit ? "col-span-1" : ""}>
              <Label>{t("product.dialog.unit")}</Label>
              <Select value={unit} onValueChange={setUnit}>
                <SelectTrigger className="mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {UNITS.map((u) => (
                    <SelectItem key={u} value={u}>
                      {u}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {!isEdit && (
            <p className="flex items-start gap-2.5 rounded-xl bg-ponto-soft px-4 py-3 text-xs font-medium text-ponto-ink">
              <Sparkles className="mt-0.5 h-4 w-4 shrink-0" />
              {t("product.dialog.aiNote")}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant="press" onClick={save} disabled={saving || !name.trim() || !price}>
            {saving && <Loader2 className="animate-spin" />}
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AdjustDialog({
  product,
  onOpenChange,
  onSaved,
}: {
  product: Product | null;
  onOpenChange: (v: boolean) => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (product) {
      setDelta("");
      setReason("");
    }
  }, [product]);

  const save = async () => {
    if (!product) return;
    setSaving(true);
    try {
      await api.adjustStock(product.id, parseFloat(delta), reason);
      toast.success(t("toast.updated"));
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!product} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("product.adjust.title")}</DialogTitle>
          {product && <DialogDescription>{product.name}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t("product.adjust.delta")}</Label>
            <Input type="number" step="0.001" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="+10 ou -5" />
          </div>
          <div className="space-y-2">
            <Label>{t("product.adjust.reason")}</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("product.adjust.ph")} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant="press" onClick={save} disabled={saving || !delta || parseFloat(delta) === 0}>
            {saving && <Loader2 className="animate-spin" />}
            {t("common.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({
  open,
  onOpenChange,
  title,
  desc,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  desc: string;
  onConfirm: () => Promise<void>;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{desc}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
          >
            {busy && <Loader2 className="animate-spin" />}
            {t("common.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MarketSettingsDialog({
  open,
  onOpenChange,
  market,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  market: Market;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(market.name);
  const [location, setLocation] = useState(market.location);
  const [customers, setCustomers] = useState(String(market.customers_per_day));
  const [cycle, setCycle] = useState(market.cycle_unit);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setName(market.name);
      setLocation(market.location);
      setCustomers(String(market.customers_per_day));
      setCycle(market.cycle_unit);
    }
  }, [open, market]);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateMarket(market.id, {
        name,
        location,
        customers_per_day: parseInt(customers, 10),
        cycle_unit: cycle,
        replenishment_cycle_days: 7,
      });
      toast.success(t("toast.updated"));
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setSaving(true);
    try {
      await api.deleteMarket(market.id);
      toast.success(t("toast.deleted"));
      onOpenChange(false);
      window.location.href = "/markets";
    } catch (e) {
      toast.error((e as Error).message);
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("market.settings")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t("common.name")}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>{t("market.location")}</Label>
            <Input value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>{t("markets.customersDay")}</Label>
              <Input type="number" min={1} value={customers} onChange={(e) => setCustomers(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>{t("wizard.cycle.q")}</Label>
              <Select value={cycle} onValueChange={setCycle}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="diario">{t("wizard.customers.daily")}</SelectItem>
                  <SelectItem value="semanal">{t("wizard.customers.weekly")}</SelectItem>
                  <SelectItem value="quinzenal">{t("wizard.customers.biweekly")}</SelectItem>
                  <SelectItem value="mensal">{t("wizard.customers.monthly")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter className="sm:justify-between">
          <Button variant="destructive" onClick={remove}>
            <Trash2 /> {t("market.delete")}
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="press" onClick={save} disabled={saving}>
              {saving && <Loader2 className="animate-spin" />}
              {t("common.save")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}