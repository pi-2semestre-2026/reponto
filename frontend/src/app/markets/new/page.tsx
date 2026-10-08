"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import confetti from "canvas-confetti";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  CalendarRange,
  Building2,
  Footprints,
  Loader2,
  MapPin,
  Moon,
  PartyPopper,
  RefreshCw,
  ShoppingCart,
  Store,
  Sunrise,
  Warehouse,
} from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { OptionCard } from "@/components/option-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { burstConfetti } from "@/lib/confetti";
import { useI18n } from "@/lib/i18n";

const STEPS = 5;

export default function MarketWizardPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [customers, setCustomers] = useState<number | null>(null);
  const [customCustomers, setCustomCustomers] = useState("");
  const [location, setLocation] = useState("");
  const [cycle, setCycle] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const progress = useMemo(() => ((step + 1) / STEPS) * 100, [step]);

  const customerOptions = [30, 100, 300, 1000];
  const cycleOptions = [
    { unit: "diario", label: t("wizard.customers.daily"), icon: <Sunrise className="h-6 w-6" strokeWidth={2.25} /> },
    { unit: "semanal", label: t("wizard.customers.weekly"), icon: <CalendarDays className="h-6 w-6" strokeWidth={2.25} /> },
    { unit: "quinzenal", label: t("wizard.customers.biweekly"), icon: <CalendarRange className="h-6 w-6" strokeWidth={2.25} /> },
    { unit: "mensal", label: t("wizard.customers.monthly"), icon: <Moon className="h-6 w-6" strokeWidth={2.25} /> },
  ];

  const create = async () => {
    setCreating(true);
    try {
      const market = await api.createMarket({
        name,
        location,
        customers_per_day: customers ?? parseInt(customCustomers || "100", 10),
        cycle_unit: cycle ?? "semanal",
        replenishment_cycle_days: 7,
      });
      burstConfetti();
      toast.success(t("toast.marketCreated"));
      setTimeout(() => router.push(`/markets/${market.id}`), 1200);
    } catch (err) {
      toast.error((err as Error).message);
      setCreating(false);
    }
  };

  const canAdvance = () => {
    if (step === 0) return name.trim().length >= 2;
    if (step === 1) return customers !== null || (customCustomers && parseInt(customCustomers, 10) > 0);
    if (step === 2) return true;
    if (step === 3) return cycle !== null;
    return true;
  };

  const next = () => {
    if (!canAdvance()) return;
    setStep((s) => Math.min(s + 1, STEPS - 1));
  };
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const selectedCycle = cycleOptions.find((c) => c.unit === cycle);

  return (
    <div className="min-h-screen">
      <Header active="/markets" />
      <main className="container flex min-h-[calc(100vh-4rem)] max-w-3xl flex-col justify-center py-10">
        <div className="mb-8 animate-fade-in">
          <div className="mb-2 flex items-center justify-between font-mono text-sm font-semibold text-muted-foreground">
            <span>
              {t("wizard.step")} {step + 1} {t("common.of")} {STEPS}
            </span>
            <span className="text-primary">{Math.round(progress)}%</span>
          </div>
          <Progress value={progress} striped className="h-5" />
        </div>

        <div key={step} className="animate-fade-in-up">
          {step === 0 && (
            <div className="flex flex-col items-center gap-8 text-center">
              <div>
                <StepIcon icon={<Store className="h-8 w-8" strokeWidth={2.25} />} />
                <h1 className="mt-4 font-display text-3xl font-bold tracking-tight">{t("wizard.name.q")}</h1>
                <p className="mt-2 text-muted-foreground">{t("wizard.name.hint")}</p>
              </div>
              <Input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("wizard.name.ph")}
                className="h-16 max-w-md text-center font-display text-2xl font-bold"
                onKeyDown={(e) => e.key === "Enter" && next()}
              />
            </div>
          )}

          {step === 1 && (
            <div className="flex flex-col items-center gap-8 text-center">
              <div>
                <StepIcon icon={<Footprints className="h-8 w-8" strokeWidth={2.25} />} />
                <h1 className="mt-4 font-display text-3xl font-bold tracking-tight">{t("wizard.customers.q")}</h1>
                <p className="mt-2 text-muted-foreground">{t("wizard.customers.hint")}</p>
              </div>
              <div className="grid w-full gap-3 sm:grid-cols-2">
                {customerOptions.map((c) => (
                  <OptionCard
                    key={c}
                    selected={customers === c}
                    onClick={() => {
                      setCustomers(c);
                      setCustomCustomers("");
                      setTimeout(next, 350);
                    }}
                    title={c === 1000 ? "1000+" : `≈${c}`}
                    subtitle={t("wizard.customersUnit")}
                    icon={
                      c <= 100 ? (
                        <ShoppingCart className="h-6 w-6" strokeWidth={2.25} />
                      ) : c <= 300 ? (
                        <Building2 className="h-6 w-6" strokeWidth={2.25} />
                      ) : (
                        <Warehouse className="h-6 w-6" strokeWidth={2.25} />
                      )
                    }
                  />
                ))}
              </div>
              <div className="flex w-full max-w-md items-center gap-3">
                <span className="whitespace-nowrap font-display text-sm font-semibold text-muted-foreground">
                  {t("wizard.customers.custom")}:
                </span>
                <Input
                  type="number"
                  min={1}
                  value={customCustomers}
                  onChange={(e) => {
                    setCustomCustomers(e.target.value);
                    setCustomers(null);
                  }}
                  placeholder={t("wizard.customers.ph")}
                />
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="flex flex-col items-center gap-8 text-center">
              <div>
                <StepIcon icon={<MapPin className="h-8 w-8" strokeWidth={2.25} />} />
                <h1 className="mt-4 font-display text-3xl font-bold tracking-tight">{t("wizard.location.q")}</h1>
                <p className="mt-2 text-muted-foreground">{t("wizard.location.hint")}</p>
              </div>
              <Input
                autoFocus
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder={t("wizard.location.ph")}
                className="h-14 max-w-lg text-lg"
                onKeyDown={(e) => e.key === "Enter" && next()}
              />
            </div>
          )}

          {step === 3 && (
            <div className="flex flex-col items-center gap-8 text-center">
              <div>
                <StepIcon icon={<RefreshCw className="h-8 w-8" strokeWidth={2.25} />} />
                <h1 className="mt-4 font-display text-3xl font-bold tracking-tight">{t("wizard.cycle.q")}</h1>
              </div>
              <div className="grid w-full gap-3 sm:grid-cols-2">
                {cycleOptions.map((c) => (
                  <OptionCard
                    key={c.unit}
                    selected={cycle === c.unit}
                    onClick={() => {
                      setCycle(c.unit);
                      setTimeout(next, 350);
                    }}
                    title={c.label}
                    icon={c.icon}
                  />
                ))}
              </div>
            </div>
          )}

          {step === 4 && (
            <Card className="mx-auto max-w-lg">
              <CardContent className="flex flex-col items-center gap-5 p-8 text-center">
                <span className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                  <PartyPopper className="h-8 w-8 text-primary" strokeWidth={2.25} />
                </span>
                <h1 className="font-display text-3xl font-bold tracking-tight">{t("wizard.review.q")}</h1>
                <p className="text-muted-foreground">{t("wizard.review.hint")}</p>
                <div className="w-full space-y-3 rounded-2xl bg-muted/60 p-5 text-left text-sm">
                  <Row icon={<Store className="h-4 w-4" />} value={name || "—"} />
                  <Separator />
                  <Row
                    icon={<Footprints className="h-4 w-4" />}
                    value={`${customers ?? customCustomers ?? "—"} ${t("wizard.customersUnit")}`}
                  />
                  <Separator />
                  <Row icon={<MapPin className="h-4 w-4" />} value={location || "—"} />
                  <Separator />
                  <Row icon={<RefreshCw className="h-4 w-4" />} value={selectedCycle?.label ?? "—"} />
                </div>
                <Button variant="press" size="xl" className="w-full" onClick={create} disabled={creating}>
                  {creating ? <Loader2 className="animate-spin" /> : null}
                  {t("wizard.finish")}
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        {step < 4 && (
          <div className="mt-10 flex items-center justify-between">
            <Button variant="ghost" onClick={back} disabled={step === 0}>
              <ArrowLeft /> {t("common.back")}
            </Button>
            <Button variant="press" onClick={next} disabled={!canAdvance()} size="lg">
              {t("common.confirm")} <ArrowRight />
            </Button>
          </div>
        )}
      </main>
    </div>
  );
}

function StepIcon({ icon }: { icon: React.ReactNode }) {
  return (
    <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
      {icon}
    </span>
  );
}

function Row({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex items-center gap-2 font-semibold text-muted-foreground">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">{icon}</span>
      </span>
      <span className="text-right font-bold">{value}</span>
    </div>
  );
}