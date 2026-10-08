"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Coins,
  Flame,
  Gamepad2,
  Pause,
  PartyPopper,
  Play,
  Plus,
  Rocket,
  ShoppingBag,
  Store,
  Timer,
  TrendingDown,
  TrendingUp,
  Truck,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import { fmtMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import {
  simApi,
  type SimDayReport,
  type SimProduct,
  type SimScenario,
  type SimSnapshot,
} from "@/lib/simulator-api";
import { cn } from "@/lib/utils";
import { ReportPanel } from "./report";

const CAT_COLORS: Record<string, string> = {
  "Hortifrúti": "#57A644",
  "Padaria": "#C98B3D",
  "Bebidas": "#3E8DA8",
  "Laticínios e Ovos": "#9575B5",
  "Carnes e Aves": "#C05656",
  "Mercearia": "#8B6F47",
  "Congelados e Frios": "#5FA8A0",
  "Limpeza": "#E2B33C",
  "Higiene e Beleza": "#D67BA8",
  "Pet e Bebê": "#7B8794",
};

const SPEEDS = [
  { days: 1, ms: 850 },
  { days: 7, ms: 950 },
  { days: 30, ms: 1200 },
];

const EVENT_ICONS: Record<string, typeof Flame> = {
  heat: Flame,
  party: PartyPopper,
  down: TrendingDown,
  up: TrendingUp,
};

interface ToastItem {
  id: string;
  kind: string;
  emojiKind: string;
  text: string;
}

export function SimulatorGame() {
  const { t } = useI18n();
  const [phase, setPhase] = useState<"setup" | "playing" | "done">("setup");
  const [scenarios, setScenarios] = useState<SimScenario[]>([]);
  const [scenario, setScenario] = useState("bairro");
  const [days, setDays] = useState(365);
  const [cycle, setCycle] = useState(7);
  const [seed, setSeed] = useState("");

  const [sid, setSid] = useState<string | null>(null);
  const [snap, setSnap] = useState<SimSnapshot | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(1);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const busy = useRef(false);

  useEffect(() => {
    simApi
      .scenarios()
      .then(setScenarios)
      .catch((e) => toast.error(e.message));
  }, []);

  const addToast = useCallback(
    (report: SimDayReport) => {
      for (const ev of report.events) {
        const item: ToastItem = {
          id: `${ev.kind}-${ev.starts_on}-${Math.random().toString(36).slice(2, 7)}`,
          kind: ev.kind,
          emojiKind: ev.emoji_kind,
          text: t(`sim.event.${ev.kind}`),
        };
        setToasts((list) => [...list.slice(-3), item]);
        setTimeout(() => setToasts((list) => list.filter((x) => x.id !== item.id)), 5200);
      }
    },
    [t]
  );

  const applyStep = useCallback(
    (res: { reports: SimDayReport[]; snapshot: SimSnapshot }) => {
      setSnap(res.snapshot);
      for (const r of res.reports) addToast(r);
      if (res.snapshot.done) {
        setPlaying(false);
        setPhase("done");
      }
    },
    [addToast]
  );

  const tick = useCallback(
    async (daysToStep: number) => {
      if (!sid || busy.current) return;
      busy.current = true;
      try {
        const res = await simApi.step(sid, daysToStep);
        applyStep(res);
      } catch (e) {
        setPlaying(false);
        toast.error((e as Error).message);
      } finally {
        busy.current = false;
      }
    },
    [sid, applyStep]
  );

  useEffect(() => {
    if (phase !== "playing" || !playing || !sid) return;
    const speed = SPEEDS[speedIdx];
    const timer = setInterval(() => tick(speed.days), speed.ms);
    return () => clearInterval(timer);
  }, [phase, playing, sid, speedIdx, tick]);

  const start = async () => {
    try {
      const res = await simApi.createSession({
        scenario,
        days,
        cycle_days: cycle,
        seed: seed ? parseInt(seed, 10) : null,
      });
      setSid(res.sid);
      setSnap(res.snapshot);
      setPhase("playing");
      setPlaying(true);
      setToasts([]);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const finish = async () => {
    if (!sid || busy.current) return;
    setPlaying(false);
    busy.current = true;
    try {
      while (true) {
        const res = await simApi.step(sid, 30);
        setSnap(res.snapshot);
        if (res.snapshot.done) {
          setPhase("done");
          break;
        }
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      busy.current = false;
    }
  };

  const exit = async () => {
    setPlaying(false);
    if (sid) simApi.deleteSession(sid).catch(() => {});
    setSid(null);
    setSnap(null);
    setPhase("setup");
  };

  if (phase === "done" && sid) {
    return (
      <div className="container py-10">
        <ReportPanel sid={sid} onNewGame={exit} />
      </div>
    );
  }

  if (phase === "playing" && snap) {
    return (
      <div className="container max-w-6xl py-8">
        <EventToasts toasts={toasts} />
        <GameHud snap={snap} />
        <ControlsRow
          playing={playing}
          speedIdx={speedIdx}
          onToggle={() => setPlaying((p) => !p)}
          onSpeed={setSpeedIdx}
          onStep={() => tick(1)}
          onFinish={finish}
          onExit={exit}
        />
        <ShelfGrid snap={snap} />
      </div>
    );
  }

  return (
    <SetupScreen
      scenarios={scenarios}
      scenario={scenario}
      days={days}
      cycle={cycle}
      seed={seed}
      onScenario={setScenario}
      onDays={setDays}
      onCycle={setCycle}
      onSeed={setSeed}
      onStart={start}
    />
  );
}


function SetupScreen({
  scenarios,
  scenario,
  days,
  cycle,
  seed,
  onScenario,
  onDays,
  onCycle,
  onSeed,
  onStart,
}: {
  scenarios: SimScenario[];
  scenario: string;
  days: number;
  cycle: number;
  seed: string;
  onScenario: (v: string) => void;
  onDays: (v: number) => void;
  onCycle: (v: number) => void;
  onSeed: (v: string) => void;
  onStart: () => void;
}) {
  const { t } = useI18n();
  const dayOptions = [
    { v: 90, label: "3m" },
    { v: 180, label: "6m" },
    { v: 365, label: "1 ano" },
    { v: 730, label: "2 anos" },
  ];
  const cycleOptions = [
    { v: 3, label: "3 dias" },
    { v: 7, label: "1 semana" },
    { v: 14, label: "2 semanas" },
  ];

  return (
    <div className="container max-w-3xl py-12">
      <div className="animate-fade-in-up mb-10 text-center">
        <span className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Gamepad2 className="h-8 w-8" strokeWidth={2.25} />
        </span>
        <h1 className="font-display text-4xl font-bold tracking-tight">{t("sim.title")}</h1>
        <p className="mx-auto mt-3 max-w-xl text-muted-foreground">{t("sim.subtitle")}</p>
      </div>

      <div className="stagger space-y-8">
        <section>
          <p className="mb-3 font-display text-sm font-bold uppercase tracking-wide text-muted-foreground">
            {t("sim.setup.scenario")}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            {scenarios.map((s) => (
              <button
                key={s.key}
                onClick={() => onScenario(s.key)}
                className={cn(
                  "press-3d rounded-lg border-2 bg-card p-5 text-left transition-all",
                  scenario === s.key ? "border-primary" : "border-input hover:border-primary/50"
                )}
              >
                <Store className={cn("mb-3 h-6 w-6", scenario === s.key ? "text-primary" : "text-muted-foreground")} />
                <p className="font-display font-bold">{s.name}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{s.description}</p>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  ≈{s.customers_per_day} {t("sim.setup.customers")} · {s.products} {t("sim.setup.products")}
                </p>
              </button>
            ))}
          </div>
        </section>

        <section>
          <p className="mb-3 font-display text-sm font-bold uppercase tracking-wide text-muted-foreground">
            {t("sim.setup.days")}
          </p>
          <div className="flex flex-wrap gap-2">
            {dayOptions.map((d) => (
              <Chip key={d.v} active={days === d.v} onClick={() => onDays(d.v)}>
                {d.label}
              </Chip>
            ))}
          </div>
        </section>

        <section>
          <p className="mb-3 font-display text-sm font-bold uppercase tracking-wide text-muted-foreground">
            {t("sim.setup.cycle")}
          </p>
          <div className="flex flex-wrap gap-2">
            {cycleOptions.map((c) => (
              <Chip key={c.v} active={cycle === c.v} onClick={() => onCycle(c.v)}>
                {c.label}
              </Chip>
            ))}
          </div>
        </section>

        <section className="max-w-xs">
          <p className="mb-3 font-display text-sm font-bold uppercase tracking-wide text-muted-foreground">
            {t("sim.setup.seed")}
          </p>
          <Input
            type="number"
            value={seed}
            onChange={(e) => onSeed(e.target.value)}
            placeholder={t("sim.setup.seedPh")}
          />
        </section>

        <div className="flex justify-center pt-2">
          <Button variant="press" size="xl" onClick={onStart}>
            <Gamepad2 /> {t("sim.start")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full border-2 px-5 py-2 font-display text-sm font-semibold transition-all",
        active ? "border-primary bg-primary text-primary-foreground" : "border-input bg-card hover:border-primary/50"
      )}
    >
      {children}
    </button>
  );
}


function useCountUp(value: number) {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);
  useEffect(() => {
    const from = prev.current;
    prev.current = value;
    if (from === value) {
      setDisplay(value);
      return;
    }
    const start = performance.now();
    let raf: number;
    const tickFn = (now: number) => {
      const p = Math.min((now - start) / 500, 1);
      setDisplay(from + (value - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tickFn);
    };
    raf = requestAnimationFrame(tickFn);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return display;
}

function GameHud({ snap }: { snap: SimSnapshot }) {
  const { t } = useI18n();
  const date = new Date(snap.date + "T12:00:00");
  const dayLabel = date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
  const year = date.getFullYear();
  const revenue = useCountUp(snap.cash.revenue);
  const progress = (snap.day_index / snap.total_days) * 100;
  const wape = snap.summary.wape_pct;
  const wapeColor = wape == null ? "text-muted-foreground" : wape <= 20 ? "text-primary" : wape <= 35 ? "text-amber-600" : "text-destructive";

  return (
    <Card className="mb-4 overflow-hidden">
      <CardContent className="p-5">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
          <div className="animate-check-pop" key={snap.day_index}>
            <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              {t("sim.day")} {snap.day_index} · {snap.total_days}
            </p>
            <p className="font-display text-4xl font-bold leading-none tracking-tight">
              {dayLabel}
              <span className="ml-2 text-xl text-muted-foreground">{year}</span>
            </p>
          </div>

          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              {t("sim.revenue")}
            </p>
            <p className="font-display text-2xl font-bold tabular-nums">{fmtMoney(revenue)}</p>
          </div>

          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              {t("sim.profit")}
            </p>
            <p className={cn("font-display text-2xl font-bold tabular-nums", snap.cash.profit < 0 && "text-destructive")}>
              {fmtMoney(snap.cash.profit)}
            </p>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <HudChip label={t("sim.wape")} value={fmtPct(wape)} className={wapeColor} />
            <HudChip label={t("sim.service")} value={fmtPct(snap.summary.service_pct)} />
            <HudChip label={t("sim.bias")} value={fmtPct(snap.summary.bias_pct)} />
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Progress value={progress} className="h-2" />
          <span className="font-mono text-xs text-muted-foreground">{Math.round(progress)}%</span>
        </div>
      </CardContent>
    </Card>
  );
}

function HudChip({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="rounded-xl border bg-card px-3.5 py-1.5 text-center">
      <p className="text-[9px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("font-mono text-sm font-bold", className)}>{value}</p>
    </div>
  );
}

function ControlsRow({
  playing,
  speedIdx,
  onToggle,
  onSpeed,
  onStep,
  onFinish,
  onExit,
}: {
  playing: boolean;
  speedIdx: number;
  onToggle: () => void;
  onSpeed: (i: number) => void;
  onStep: () => void;
  onFinish: () => void;
  onExit: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <Button variant="press" onClick={onToggle} size="lg">
        {playing ? <Pause /> : <Play />} {playing ? t("sim.pause") : t("sim.play")}
      </Button>
      <div className="flex overflow-hidden rounded-xl border-2">
        {SPEEDS.map((s, i) => (
          <button
            key={s.days}
            onClick={() => onSpeed(i)}
            className={cn(
              "flex items-center gap-1.5 px-3.5 py-2.5 font-display text-sm font-semibold transition-colors",
              i === speedIdx ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:bg-accent"
            )}
          >
            <Timer className="h-3.5 w-3.5" /> {t(`sim.speed${s.days}`)}
          </button>
        ))}
      </div>
      <Button variant="outline" onClick={onStep}>
        <Plus /> {t("sim.step1")}
      </Button>
      <Button variant="ponto" onClick={onFinish}>
        <Rocket /> {t("sim.finish")}
      </Button>
      <Button variant="ghost" onClick={onExit} className="ml-auto text-muted-foreground">
        <X /> {t("sim.exit")}
      </Button>
    </div>
  );
}


function ShelfGrid({ snap }: { snap: SimSnapshot }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
      {snap.products.map((p) => (
        <ProductCard key={p.key} p={p} day={snap.day_index} soldLabel={t("sim.sold")} lostLabel={t("sim.lost")} />
      ))}
    </div>
  );
}

function ProductCard({ p, day, soldLabel, lostLabel }: { p: SimProduct; day: number; soldLabel: string; lostLabel: string }) {
  const { t } = useI18n();
  const catColor = CAT_COLORS[p.category] ?? "#8B9491";
  const pct = p.max_stock > 0 ? Math.min(100, (p.stock / p.max_stock) * 100) : 0;
  const barColor = p.stock <= 0 ? "bg-destructive" : p.stock <= p.min_stock ? "bg-amber-500" : pct < 40 ? "bg-amber-400" : "bg-primary";

  return (
    <Card className="overflow-hidden transition-all duration-300">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-display text-sm font-bold">{p.name}</p>
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: catColor }} />
              {p.category}
            </p>
          </div>
          <span className="shrink-0 font-mono text-xs font-semibold text-muted-foreground">{p.final_rate.toFixed(1)}/d</span>
        </div>

        <div className="mt-3">
          <div className="mb-1 flex justify-between font-mono text-[10px] text-muted-foreground">
            <span>
              {t("sim.stock")} <b className="text-foreground">{Math.round(p.stock)}</b> / {Math.round(p.max_stock)}
            </span>
            <span>{Math.round(pct)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className={cn("h-full rounded-full transition-all duration-500", barColor)} style={{ width: `${pct}%` }} />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5" key={day}>
          {p.today_sold > 0 && (
            <span className="animate-check-pop flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">
              <ShoppingBag className="h-3 w-3" /> +{p.today_sold} {soldLabel}
            </span>
          )}
          {p.today_lost > 0 && (
            <span className="animate-check-pop flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 font-mono text-[10px] font-bold text-destructive">
              −{p.today_lost} {lostLabel}
            </span>
          )}
          {p.restocked > 0 && (
            <span className="animate-check-pop flex items-center gap-1 rounded-full bg-ponto-soft px-2 py-0.5 font-mono text-[10px] font-bold text-ponto-ink">
              <Truck className="h-3 w-3" /> +{p.restocked}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}


function EventToasts({ toasts }: { toasts: ToastItem[] }) {
  return (
    <div className="pointer-events-none fixed right-5 top-20 z-50 flex w-72 flex-col gap-2">
      {toasts.map((toastItem) => {
        const Icon = EVENT_ICONS[toastItem.emojiKind] ?? TrendingUp;
        return (
          <div
            key={toastItem.id}
            className="animate-fade-in-up flex items-start gap-3 rounded-xl border-2 border-ponto/40 bg-card p-3.5 shadow-[0_12px_32px_-12px_hsl(var(--foreground)/0.3)]"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ponto-soft text-ponto-ink">
              <Icon className="h-5 w-5" />
            </span>
            <p className="text-sm font-semibold leading-snug">{toastItem.text}</p>
          </div>
        );
      })}
    </div>
  );
}


function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v}%`;
}
