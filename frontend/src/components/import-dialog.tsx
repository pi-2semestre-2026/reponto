"use client";

import { useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  Upload,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { burstConfetti } from "@/lib/confetti";
import { fmtDate, fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ImportPreview, ImportResult } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = "pick" | "reading" | "preview" | "importing" | "done";

const SAMPLES = [
  { href: "/exemplos/produtos_erp_exemplo.csv", key: "import.sampleCatalog" },
  { href: "/exemplos/vendas_pdv_exemplo.csv", key: "import.sampleSales" },
];

export function ImportDialog({
  marketId,
  open,
  onOpenChange,
  onDone,
}: {
  marketId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<Step>("pick");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragging, setDragging] = useState(false);

  const reset = () => {
    setStep("pick");
    setFile(null);
    setPreview(null);
    setResult(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const close = (v: boolean) => {
    if (!v) {
      if (step === "done") onDone();
      reset();
    }
    onOpenChange(v);
  };

  const read = async (f: File) => {
    setFile(f);
    setStep("reading");
    try {
      setPreview(await api.importPreview(marketId, f));
      setStep("preview");
    } catch (e) {
      toast.error((e as Error).message);
      reset();
    }
  };

  const runImport = async () => {
    if (!file) return;
    setStep("importing");
    try {
      const r = await api.importFile(marketId, file);
      setResult(r);
      setStep("done");
      burstConfetti();
    } catch (e) {
      toast.error((e as Error).message);
      setStep("preview");
    }
  };

  const isSales = preview?.kind === "sales";

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" /> {t("import.title")}
          </DialogTitle>
          <DialogDescription>{t("import.subtitle")}</DialogDescription>
        </DialogHeader>

        {(step === "pick" || step === "reading") && (
          <div className="space-y-4">
            <button
              type="button"
              disabled={step === "reading"}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files?.[0];
                if (f) read(f);
              }}
              className={cn(
                "flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors",
                dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/40"
              )}
            >
              {step === "reading" ? (
                <Loader2 className="h-10 w-10 animate-spin text-primary" />
              ) : (
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Upload className="h-7 w-7" />
                </span>
              )}
              <span className="font-display text-base font-bold">
                {step === "reading" ? t("import.reading") : t("import.drop")}
              </span>
              <span className="max-w-md text-sm text-muted-foreground">{t("import.formats")}</span>
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) read(f);
              }}
            />
            <div className="rounded-2xl bg-muted/50 p-4 text-sm">
              <p className="mb-2 font-semibold">{t("import.howTitle")}</p>
              <ul className="space-y-1 text-muted-foreground">
                <li>• {t("import.how1")}</li>
                <li>• {t("import.how2")}</li>
                <li>• {t("import.how3")}</li>
              </ul>
              <div className="mt-3 flex flex-wrap gap-2">
                {SAMPLES.map((s) => (
                  <Button key={s.href} variant="outline" size="sm" asChild>
                    <a href={s.href} download>
                      <Download /> {t(s.key)}
                    </a>
                  </Button>
                ))}
              </div>
            </div>
          </div>
        )}

        {preview && (step === "preview" || step === "importing") && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="ai">{isSales ? t("import.kindSales") : t("import.kindCatalog")}</Badge>
              <Badge variant="secondary">
                {fmtNum(preview.valid_rows)} {t("import.rows")}
              </Badge>
              <Badge variant="secondary">
                {fmtNum(preview.products)} {t("import.products")}
              </Badge>
              {preview.date_from && preview.date_to && (
                <Badge variant="secondary">
                  {fmtDate(preview.date_from + "T12:00:00")} → {fmtDate(preview.date_to + "T12:00:00")}
                </Badge>
              )}
              <span className="ml-auto truncate font-mono text-[11px] text-muted-foreground">
                {preview.filename} · {preview.encoding} · {preview.delimiter}
              </span>
            </div>

            <div>
              <p className="mb-2 text-sm font-bold">{t("import.mapping")}</p>
              <div className="flex flex-wrap gap-2">
                {preview.columns.map((c, i) => (
                  <span
                    key={i}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs",
                      c.field ? "border-primary/30 bg-primary/5" : "border-dashed text-muted-foreground"
                    )}
                  >
                    <span className="font-mono">{c.header}</span>
                    <ArrowRight className="h-3 w-3" />
                    <span className="font-semibold">{c.label ?? t("import.ignored")}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto rounded-2xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {isSales && <TableHead>{t("import.col.date")}</TableHead>}
                    <TableHead>{t("import.col.product")}</TableHead>
                    {isSales ? (
                      <>
                        <TableHead className="text-right">{t("import.col.qty")}</TableHead>
                        <TableHead className="text-right">{t("import.col.price")}</TableHead>
                        <TableHead>{t("import.col.receipt")}</TableHead>
                      </>
                    ) : (
                      <>
                        <TableHead className="text-right">{t("import.col.price")}</TableHead>
                        <TableHead className="text-right">{t("import.col.cost")}</TableHead>
                        <TableHead className="text-right">{t("import.col.stock")}</TableHead>
                      </>
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.sample.slice(0, 6).map((r) => (
                    <TableRow key={r.line}>
                      {isSales && <TableCell className="text-xs">{r.date ? fmtDate(r.date + "T12:00:00") : "—"}</TableCell>}
                      <TableCell>
                        <p className="text-sm font-semibold">{r.product}</p>
                        {r.sku && <p className="font-mono text-[10px] text-muted-foreground">{r.sku}</p>}
                      </TableCell>
                      {isSales ? (
                        <>
                          <TableCell className="text-right font-mono text-xs">{r.quantity ? fmtNum(r.quantity) : "—"}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{r.unit_price ? fmtMoney(r.unit_price) : "—"}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{r.receipt ?? "—"}</TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell className="text-right font-mono text-xs">{r.unit_price ? fmtMoney(r.unit_price) : "—"}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{r.cost ? fmtMoney(r.cost) : "—"}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{r.stock ? fmtNum(r.stock) : "—"}</TableCell>
                        </>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {(preview.warnings.length > 0 || preview.errors.length > 0) && (
              <div className="space-y-1 rounded-2xl border border-amber-300/50 bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
                {preview.warnings.map((w, i) => (
                  <p key={i} className="flex items-start gap-1.5">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {w}
                  </p>
                ))}
                {preview.errors.slice(0, 5).map((e, i) => (
                  <p key={`e${i}`} className="font-mono">
                    {t("import.line")} {e.line}: {e.message}
                  </p>
                ))}
              </div>
            )}

            <p className="text-xs text-muted-foreground">{isSales ? t("import.salesRule") : t("import.catalogRule")}</p>

            <DialogFooter className="gap-2 sm:gap-2">
              <Button variant="ghost" onClick={reset} disabled={step === "importing"}>
                <RotateCcw /> {t("import.another")}
              </Button>
              <Button variant="press" onClick={runImport} disabled={step === "importing"}>
                {step === "importing" ? <Loader2 className="animate-spin" /> : <Upload />}
                {t("import.confirm").replace("{n}", fmtNum(preview.valid_rows))}
              </Button>
            </DialogFooter>
          </div>
        )}

        {step === "done" && result && (
          <div className="space-y-5 py-2 text-center">
            <CheckCircle2 className="mx-auto h-14 w-14 animate-check-pop text-primary" />
            <div>
              <p className="font-display text-xl font-bold">{t("import.doneTitle")}</p>
              <p className="text-sm text-muted-foreground">{t("import.doneSub")}</p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label={t("import.stat.rows")} value={fmtNum(result.rows_imported)} />
              <Stat label={t("import.stat.created")} value={fmtNum(result.products_created)} />
              <Stat label={t("import.stat.updated")} value={fmtNum(result.products_updated)} />
              <Stat label={t("import.stat.sales")} value={fmtNum(result.sales_created)} />
            </div>
            {result.rows_skipped > 0 && (
              <p className="text-xs text-amber-700">
                {result.rows_skipped} {t("import.skipped")}
              </p>
            )}
            <Button variant="press" size="lg" onClick={() => close(false)}>
              {t("import.finish")}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-card p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold">{value}</p>
    </div>
  );
}
