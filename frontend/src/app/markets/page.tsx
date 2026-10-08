"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, MapPin, Plus, Store, Users } from "lucide-react";
import { toast } from "sonner";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Market } from "@/lib/types";

const CYCLE_LABEL: Record<string, Record<string, string>> = {
  pt: { diario: "reposição diária", semanal: "reposição semanal", quinzenal: "reposição quinzenal", mensal: "reposição mensal" },
  en: { diario: "daily restock", semanal: "weekly restock", quinzenal: "biweekly restock", mensal: "monthly restock" },
};

export default function MarketsPage() {
  const router = useRouter();
  const { t, locale } = useI18n();
  const [markets, setMarkets] = useState<Market[] | null>(null);

  useEffect(() => {
    api
      .markets()
      .then(setMarkets)
      .catch((e) => toast.error(e.message));
  }, []);

  return (
    <div className="min-h-screen">
      <Header active="/markets" />
      <main className="container py-10">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4 animate-fade-in-up">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight">{t("markets.title")}</h1>
            <p className="mt-1 text-muted-foreground">{t("markets.subtitle")}</p>
          </div>
          <Button variant="press" size="lg" onClick={() => router.push("/markets/new")}>
            <Plus /> {t("markets.new")}
          </Button>
        </div>

        {markets === null ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-44" />
            ))}
          </div>
        ) : markets.length === 0 ? (
          <Card className="mx-auto max-w-md text-center animate-fade-in-up">
            <CardHeader>
              <span className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Store className="h-7 w-7" strokeWidth={2.25} />
              </span>
              <CardTitle>{t("dash.noMarkets")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Button variant="press" size="lg" onClick={() => router.push("/markets/new")}>
                <Plus /> {t("markets.new")}
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="stagger grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {markets.map((m) => (
              <Card key={m.id} className="hover-lift cursor-pointer" onClick={() => router.push(`/markets/${m.id}`)}>
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-primary">
                      <Store className="h-6 w-6" />
                    </span>
                    <CardTitle className="text-lg">{m.name}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  {m.location && (
                    <p className="flex items-center gap-2">
                      <MapPin className="h-4 w-4 shrink-0" /> {m.location}
                    </p>
                  )}
                  <p className="flex items-center gap-2">
                    <Users className="h-4 w-4 shrink-0" /> ≈{m.customers_per_day} {t("markets.customersDay")}
                  </p>
                </CardContent>
                <CardFooter className="justify-between">
                  <Badge variant="secondary">{CYCLE_LABEL[locale][m.cycle_unit] ?? m.cycle_unit}</Badge>
                  <span className="flex items-center gap-1 text-sm font-bold text-primary">
                    {t("common.actions") === "Actions" ? "Open" : "Abrir"} <ArrowRight className="h-4 w-4" />
                  </span>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}