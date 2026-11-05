"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Brain, ClipboardList, LineChart, ShoppingBasket } from "lucide-react";
import { Wordmark } from "@/components/logo";
import { PontoDot } from "@/components/ponto-dot";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n";
import { getToken } from "@/lib/token";

// Exemplos ilustrativos da lista de compras (mesmas situações e cores de /markets/[id]/compras).
// Clicar no cartão alterna entre eles.
const STATUS_VARIANT = { esgotado: "destructive", comprar: "warning", atencao: "info" } as const;
const SAMPLE_LISTS = [
  {
    cycle: "landing.card.cycle",
    cost: "R$ 183,80",
    items: [
      { key: "banana", status: "esgotado", qty: "10", unit: "kg" },
      { key: "pao", status: "comprar", qty: "60", unit: "un" },
      { key: "leite", status: "comprar", qty: "12", unit: "un" },
      { key: "cafe", status: "atencao", qty: "4", unit: "un" },
    ],
  },
  {
    cycle: "landing.card.cycleBiweekly",
    cost: "R$ 199,60",
    items: [
      { key: "arroz", status: "esgotado", qty: "4", unit: "un" },
      { key: "feijao", status: "comprar", qty: "8", unit: "un" },
      { key: "oleo", status: "atencao", qty: "6", unit: "un" },
      { key: "detergente", status: "comprar", qty: "10", unit: "un" },
    ],
  },
  {
    cycle: "landing.card.cycleDaily",
    cost: "R$ 157,50",
    items: [
      { key: "pao", status: "esgotado", qty: "80", unit: "un" },
      { key: "ovo", status: "comprar", qty: "6", unit: "dz" },
      { key: "tomate", status: "atencao", qty: "5", unit: "kg" },
      { key: "iogurte", status: "comprar", qty: "12", unit: "un" },
    ],
  },
] as const;

const TICKER_KEYS = ["landing.t1", "landing.t2", "landing.t3", "landing.t4", "landing.t5", "landing.t6", "landing.t7", "landing.t8"];

export default function LandingPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [listIdx, setListIdx] = useState(0);
  const sample = SAMPLE_LISTS[listIdx];
  const nextList = () => setListIdx((i) => (i + 1) % SAMPLE_LISTS.length);

  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);

  const features = [
    { icon: Brain, title: t("landing.f1.title"), desc: t("landing.f1.desc") },
    { icon: LineChart, title: t("landing.f2.title"), desc: t("landing.f2.desc") },
    { icon: ShoppingBasket, title: t("landing.f3.title"), desc: t("landing.f3.desc") },
  ];

  return (
    <main className="relative flex min-h-screen flex-col overflow-x-clip">
      <header className="relative z-10">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
          <Wordmark markClassName="h-8 w-8" className="[&>span:last-child]:text-2xl" />
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="lg" asChild>
              <Link href="/login">{t("login.submit")}</Link>
            </Button>
            <Button variant="press" size="lg" asChild>
              <Link href="/register">{t("register.submit")}</Link>
            </Button>
          </div>
        </div>
      </header>

      <section className="relative">
        <div className="bg-dots pointer-events-none absolute inset-0 [mask-image:radial-gradient(60%_60%_at_70%_40%,black,transparent)]" />
        <div className="relative mx-auto grid w-full max-w-6xl items-center gap-14 px-6 pb-20 pt-10 lg:grid-cols-[1.05fr_0.95fr] lg:pb-28 lg:pt-16">
          <div className="animate-fade-in-up">
            <span className="mb-6 inline-flex items-center gap-2.5 rounded-full border bg-card px-4 py-1.5 text-sm font-semibold text-muted-foreground">
              <PontoDot />
              {t("landing.badge")}
            </span>
            <h1 className="font-display text-5xl font-bold leading-[1.04] tracking-tight sm:text-6xl lg:text-7xl">
              {t("landing.hero.title1")}{" "}
              <span className="relative inline-flex items-baseline text-primary">
                {t("landing.hero.title2")}
                <PontoDot className="absolute -right-5 top-1 h-3.5 w-3.5" />
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
              {t("landing.hero.subtitle")}
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Button variant="press" size="xl" onClick={() => router.push("/register")}>
                {t("landing.cta")} <ArrowRight />
              </Button>
              <Button variant="outline" size="xl" onClick={() => router.push("/login")}>
                {t("landing.cta2")}
              </Button>
            </div>
            <p className="mt-5 font-mono text-xs text-muted-foreground">{t("landing.hero.note")}</p>
          </div>

          <div className="relative mx-auto w-full max-w-sm animate-fade-in-up [animation-delay:150ms] lg:max-w-none">
            <div className="absolute -right-6 top-10 h-40 w-40 rounded-full bg-ponto/15 blur-2xl" />
            <div className="absolute -left-4 bottom-6 h-44 w-44 rounded-full bg-primary/15 blur-2xl" />

            <div className="animate-float relative">
              <div className="absolute inset-0 -z-10 rotate-6 rounded-lg border bg-card" />
              <button
                type="button"
                onClick={nextList}
                aria-label={t("landing.card.hint")}
                className="receipt-edge relative block w-full rotate-1 cursor-pointer rounded-lg border-2 border-dashed border-border bg-card p-6 text-left shadow-[0_24px_48px_-24px_hsl(var(--foreground)/0.25)] transition-transform duration-200 hover:-rotate-0 hover:scale-[1.02] active:scale-[0.99]"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <ClipboardList className="h-5 w-5 text-primary" />
                    <span className="font-display text-lg font-bold">{t("purchase.title")}</span>
                  </div>
                  <Badge variant="secondary">{t(sample.cycle)}</Badge>
                </div>

                <div className="my-4 border-t border-dashed" />

                <ul key={listIdx} className="stagger space-y-3">
                  {sample.items.map((item) => (
                    <li key={item.key} className="flex items-center gap-3">
                      <span className="min-w-0 flex-1 truncate text-sm font-semibold">{t(`landing.list.${item.key}`)}</span>
                      <Badge variant={STATUS_VARIANT[item.status]} className="shrink-0 px-2 py-0 text-[10px]">
                        {t(`purchase.status.${item.status}`)}
                      </Badge>
                      <span className="w-16 shrink-0 text-right font-mono text-sm font-semibold">
                        {item.qty} <span className="text-xs font-normal text-muted-foreground">{item.unit}</span>
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="my-4 border-t border-dashed" />

                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                    {t("purchase.kpi.cost")}
                  </span>
                  <span key={listIdx} className="animate-check-pop font-display text-2xl font-bold">
                    {sample.cost}
                  </span>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <span className="font-mono text-[11px] text-muted-foreground">{t("landing.card.hint")}</span>
                  <span className="flex gap-1.5">
                    {SAMPLE_LISTS.map((_, i) => (
                      <span
                        key={i}
                        className={`h-1.5 w-1.5 rounded-full ${i === listIdx ? "bg-ponto" : "bg-muted-foreground/30"}`}
                      />
                    ))}
                  </span>
                </div>
              </button>

              <span className="absolute -right-3 -top-4 rotate-6 rounded-full bg-sun px-3.5 py-1.5 font-display text-xs font-bold uppercase tracking-wide text-[hsl(35_80%_18%)] shadow-md">
                {t("landing.card.sticker")}
              </span>
            </div>
          </div>
        </div>
      </section>

      <div className="relative border-y-2 border-[hsl(var(--primary-deep))] bg-primary py-3.5">
        <div className="flex w-max animate-marquee gap-10 hover:[animation-play-state:paused]">
          {[...TICKER_KEYS, ...TICKER_KEYS].map((key, i) => (
            <span key={i} className="flex items-center gap-10 whitespace-nowrap font-mono text-sm text-primary-foreground/95">
              {t(key)}
              <span className="h-2 w-2 rounded-full bg-ponto" />
            </span>
          ))}
        </div>
      </div>

      <section className="mx-auto w-full max-w-6xl px-6 py-20 lg:py-24">
        <div className="stagger grid gap-5 sm:grid-cols-3">
          {features.map((f, i) => (
            <div
              key={i}
              className="hover-lift group relative rounded-lg border bg-card p-7 shadow-[0_1px_2px_hsl(var(--foreground)/0.05)]"
            >
              <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <f.icon className="h-6 w-6" strokeWidth={2.25} />
              </span>
              <h3 className="font-display text-lg font-bold">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.desc}</p>
              <span className="absolute right-5 top-5 h-2 w-2 rounded-full bg-ponto/40 transition-colors group-hover:bg-ponto" />
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-20">
        <div className="relative overflow-hidden rounded-2xl bg-primary px-8 py-14 text-center sm:px-14">
          <div
            className="pointer-events-none absolute inset-0"
            style={{ backgroundImage: "radial-gradient(hsl(0 0% 100% / 0.10) 1.5px, transparent 1.5px)", backgroundSize: "24px 24px" }}
          />
          <div className="relative">
            <h2 className="font-display text-3xl font-bold tracking-tight text-primary-foreground sm:text-5xl">
              {t("landing.ctaBand.title")}
            </h2>
            <p className="mx-auto mt-4 max-w-lg text-primary-foreground/80">{t("landing.ctaBand.sub")}</p>
            <Button variant="ponto" size="xl" className="mt-8" onClick={() => router.push("/register")}>
              {t("landing.cta")} <ArrowRight />
            </Button>
          </div>
        </div>
      </section>

      <footer className="border-t py-8">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-4 px-6 sm:flex-row">
          <Wordmark />
          <p className="text-sm text-muted-foreground">{t("landing.footer.tag")}</p>
          <p className="font-mono text-xs text-muted-foreground">© 2026 REPONTO</p>
        </div>
      </footer>
    </main>
  );
}