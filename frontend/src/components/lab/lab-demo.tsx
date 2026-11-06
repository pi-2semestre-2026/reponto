"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Beer,
  Brain,
  Croissant,
  FastForward,
  FlaskConical,
  Loader2,
  Milk,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  Sparkles,
  Zap,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as ReTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { fmtMoney, fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { labApi, type LabProduct, type LabSnapshot, type LabStore } from "@/lib/simulator-api";
import { cn } from "@/lib/utils";

const SPEEDS = [
  { key: "normal", ms: 700, days: 1 },
  { key: "fast", ms: 250, days: 1 },
  { key: "week", ms: 600, days: 7 },
];
const ICONS: Record<string, typeof Beer> = { cerveja: Beer, pao: Croissant, leite: Milk };
const C_REAL = "hsl(var(--foreground))";
const C_AI = "hsl(var(--primary))";
const C_NOAI = "hsl(var(--ponto))";
const C_TRUE = "hsl(var(--muted-foreground))";

const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${fmtNum(Math.round(v * 10 ** d) / 10 ** d)}%`);
const signed = (v: number) => `${v > 0 ? "+" : ""}${v}%`;

export function LabDemo() {
  const { t } = useI18n();
  const [sid, setSid] = useState<string | null>(null);
  const [snap, setSnap] = useState<LabSnapshot | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(0);
  const [starting, setStarting] = useState(false);
  const busy = useRef(false);

  const start = async () => {
    setStarting(true);
    try {
      if (sid) labApi.remove(sid).catch(() => {});
      const res = await labApi.create();
      setSid(res.sid);
      setSnap(res.snapshot);
      setPlaying(true);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const tick = useCallback(
    async (days: number) => {
      if (!sid || busy.current) return;
      busy.current = true;
      try {
        const res = await labApi.step(sid, days);
        setSnap(res.snapshot);
        if (res.snapshot.done) setPlaying(false);
      } catch (e) {
        setPlaying(false);
        toast.error((e as Error).message);
      } finally {
        busy.current = false;
      }
    },
    [sid]
  );

  useEffect(() => {
    if (!playing || !sid) return;
    const s = SPEEDS[speed];
    const timer = setInterval(() => tick(s.days), s.ms);
    return () => clearInterval(timer);
  }, [playing, sid, speed, tick]);

  useEffect(() => {
    return () => {
      if (sid) labApi.remove(sid).catch(() => {});
    };
  }, [sid]);

  const shift = async (kind: string) => {
    if (!sid) return;
    try {
      const res = await labApi.shift(sid, kind);
      setSnap(res.snapshot);
      toast.success(res.snapshot.shifts[res.snapshot.shifts.length - 1]?.label ?? "");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="animate-fade-in-up flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="flex items-center gap-2 font-display text-3xl font-bold tracking-tight">
            <FlaskConical className="h-7 w-7 text-primary" /> {t("lab.title")}
          </h1>
          <p className="mt-1 text-muted-foreground">{t("lab.subtitle")}</p>
        </div>
        <Button variant="press" size="lg" onClick={start} disabled={starting}>
          {starting ? <Loader2 className="animate-spin" /> : snap ? <RotateCcw /> : <Play />}
          {snap ? t("lab.restart") : t("lab.start")}
        </Button>
      </div>

      {!snap ? (
        <IntroCard />
      ) : (
        <>
          <ControlBar
            snap={snap}
            playing={playing}
            speed={speed}
            onToggle={() => setPlaying((p) => !p)}
            onSpeed={setSpeed}
            onStep={() => tick(7)}
            onShift={shift}
          />
          <Scoreboard ai={snap.stores.ai} noai={snap.stores.noai} />
          {snap.products.map((p) => (
            <ProductPanel key={p.key} p={p} day={snap.day_index} shifts={snap.shifts.filter((s) => s.product === p.key)} />
          ))}
          <LearningCurve snap={snap} />
        </>
      )}
    </div>
  );
}

function IntroCard() {
  const { t } = useI18n();
  const items = [
    { icon: Beer, title: t("lab.intro.beer.title"), text: t("lab.intro.beer.text") },
    { icon: Croissant, title: t("lab.intro.bread.title"), text: t("lab.intro.bread.text") },
    { icon: Milk, title: t("lab.intro.milk.title"), text: t("lab.intro.milk.text") },
  ];
  return (
    <Card className="animate-fade-in-up">
      <CardContent className="space-y-5 p-6">
        <div className="grid gap-4 md:grid-cols-3">
          {items.map((it) => (
            <div key={it.title} className="rounded-2xl border bg-muted/30 p-4">
              <it.icon className="mb-2 h-6 w-6 text-primary" />
              <p className="font-display font-bold">{it.title}</p>
              <p className="text-sm text-muted-foreground">{it.text}</p>
            </div>
          ))}
        </div>
        <div className="grid gap-3 text-sm md:grid-cols-2">
          <p className="rounded-xl bg-primary/10 p-3">
            <Brain className="mr-1 inline h-4 w-4 text-primary" /> <b>{t("lab.intro.ai.title")}</b> {t("lab.intro.ai.text")}
          </p>
          <p className="rounded-xl bg-ponto-soft p-3">
            <b>{t("lab.intro.noai.title")}</b> {t("lab.intro.noai.text")}
          </p>
        </div>
        <p className="text-xs text-muted-foreground">{t("lab.intro.same")}</p>
      </CardContent>
    </Card>
  );
}

function ControlBar({
  snap,
  playing,
  speed,
  onToggle,
  onSpeed,
  onStep,
  onShift,
}: {
  snap: LabSnapshot;
  playing: boolean;
  speed: number;
  onToggle: () => void;
  onSpeed: (i: number) => void;
  onStep: () => void;
  onShift: (kind: string) => void;
}) {
  const { t } = useI18n();
  const week = Math.floor(snap.day_index / 7) + (snap.done ? 0 : 1);
  const date = new Date(snap.date + "T12:00:00");
  return (
    <Card className="sticky top-16 z-30 border-primary/30 bg-background/95 backdrop-blur">
      <CardContent className="flex flex-wrap items-center gap-4 p-4">
        <div className="min-w-[220px] flex-1">
          <div className="mb-1 flex items-baseline justify-between font-mono text-sm">
            <span className="font-bold">
              {t("lab.day")} {snap.day_index} / {snap.total_days} · {t("lab.week")} {week}
            </span>
            <span className="text-muted-foreground">
              {snap.done ? t("lab.done") : `${snap.weekday} ${date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`}
            </span>
          </div>
          <Progress value={(snap.day_index / snap.total_days) * 100} className="h-3" />
        </div>
        <div className="flex items-center gap-1">
          <Button size="sm" variant={playing ? "outline" : "press"} onClick={onToggle} disabled={snap.done}>
            {playing ? <Pause /> : <Play />} {playing ? t("lab.pause") : t("lab.play")}
          </Button>
          <Button size="sm" variant="ghost" onClick={onStep} disabled={snap.done || playing} title={t("lab.stepWeek")}>
            <SkipForward />
          </Button>
          {SPEEDS.map((s, i) => (
            <button
              key={s.key}
              onClick={() => onSpeed(i)}
              className={cn(
                "rounded-lg px-2 py-1 font-mono text-xs font-semibold",
                i === speed ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              )}
            >
              {i === 2 ? <FastForward className="inline h-3 w-3" /> : null} {t(`lab.speed.${s.key}`)}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1 text-xs font-semibold text-muted-foreground">
            <Zap className="h-3.5 w-3.5 text-ponto" /> {t("lab.changeReality")}
          </span>
          {snap.available_shifts.map((s) => (
            <Button key={s.kind} size="sm" variant="outline" onClick={() => onShift(s.kind)} disabled={snap.done}>
              {t(`lab.shift.${s.kind}`)}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function Scoreboard({ ai, noai }: { ai: LabStore; noai: LabStore }) {
  const { t } = useI18n();
  const rows: { label: string; a: string; b: string; better: boolean }[] = [
    { label: t("lab.kpi.fill"), a: pct(ai.fill_pct), b: pct(noai.fill_pct), better: (ai.fill_pct ?? 0) >= (noai.fill_pct ?? 0) },
    { label: t("lab.kpi.stockoutDays"), a: fmtNum(ai.stockout_days), b: fmtNum(noai.stockout_days), better: ai.stockout_days <= noai.stockout_days },
    { label: t("lab.kpi.lost"), a: fmtMoney(ai.lost_r), b: fmtMoney(noai.lost_r), better: ai.lost_r <= noai.lost_r },
    { label: t("lab.kpi.waste"), a: fmtMoney(ai.waste_r), b: fmtMoney(noai.waste_r), better: ai.waste_r <= noai.waste_r },
    { label: t("lab.kpi.profit"), a: fmtMoney(ai.revenue - ai.cost), b: fmtMoney(noai.revenue - noai.cost), better: ai.revenue - ai.cost >= noai.revenue - noai.cost },
  ];
  return (
    <Card className="animate-fade-in-up">
      <CardContent className="p-0">
        <div className="grid grid-cols-[1.4fr_1fr_1fr] border-b text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <div className="px-4 py-2">{t("lab.kpi.title")}</div>
          <div className="flex items-center gap-1 px-4 py-2 text-primary">
            <Sparkles className="h-3.5 w-3.5" /> {t("lab.store.ai")}
          </div>
          <div className="px-4 py-2 text-ponto-ink">{t("lab.store.noai")}</div>
        </div>
        {rows.map((r) => (
          <div key={r.label} className="grid grid-cols-[1.4fr_1fr_1fr] border-b last:border-0">
            <div className="px-4 py-2 text-sm">{r.label}</div>
            <div className={cn("px-4 py-2 font-mono text-sm", r.better && "font-bold text-primary")}>{r.a}</div>
            <div className="px-4 py-2 font-mono text-sm">{r.b}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ProductPanel({ p, day, shifts }: { p: LabProduct; day: number; shifts: LabSnapshot["shifts"] }) {
  const { t } = useI18n();
  const Icon = ICONS[p.key] ?? Beer;
  const pattern = p.labels.map((l, i) => ({
    label: l,
    real: Math.round((p.true_index[i] - 1) * 100),
    ia: Math.round((p.learned_index[i] - 1) * 100),
  }));
  const learnedPeak = pattern.reduce((a, b) => (b.ia > a.ia ? b : a));
  const learnedLow = pattern.reduce((a, b) => (b.ia < a.ia ? b : a));
  const history = p.history.map((h) => ({
    ...h,
    tick: `${h.label} ${h.date.slice(8, 10)}/${h.date.slice(5, 7)}`,
    falta_ia: h.ai_stockout ? h.ai_sold : null,
  }));
  return (
    <Card className="animate-fade-in-up">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Icon className="h-5 w-5 text-primary" /> {p.name}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              {t("lab.cycle").replace("{n}", String(p.cycle_days))}
              {p.perishable ? ` · ${t("lab.perishable")}` : ""}
            </Badge>
            {p.source === "modelo" ? (
              <Badge variant="ai">{t("lab.phase.model").replace("{d}", String(p.switched_day ?? day))}</Badge>
            ) : (
              <Badge variant="info">{t("lab.phase.rule")}</Badge>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          <b>{t("lab.reality")}</b> {p.story}
        </p>
      </CardHeader>
      <CardContent className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <p className="mb-1 text-sm font-bold">{t("lab.patternTitle")}</p>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pattern}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 10 }} width={38} unit="%" />
                <ReTooltip formatter={(v: number, n: string) => [signed(v), n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="hsl(var(--border))" />
                <Bar dataKey="real" name={t("lab.series.truth")} fill={C_TRUE} fillOpacity={0.45} radius={[4, 4, 0, 0]} />
                <Bar dataKey="ia" name={t("lab.series.learned")} fill={C_AI} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-muted-foreground">
            {t("lab.patternSays")
              .replace("{peak}", learnedPeak.label)
              .replace("{pp}", signed(learnedPeak.ia))
              .replace("{low}", learnedLow.label)
              .replace("{lp}", signed(learnedLow.ia))}{" "}
            {t("lab.patternError").replace("{e}", pct(p.pattern_error_pp))}
          </p>
        </div>
        <div>
          <p className="mb-1 text-sm font-bold">{t("lab.dailyTitle")}</p>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={history}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval={Math.max(0, Math.floor(history.length / 8))} />
                <YAxis tick={{ fontSize: 10 }} width={38} />
                <ReTooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {shifts.map((s) => {
                  const h = history.find((x) => x.day === s.day);
                  return h ? <ReferenceLine key={s.day} x={h.tick} stroke={C_NOAI} strokeDasharray="4 3" /> : null;
                })}
                {p.switched_day != null &&
                  (() => {
                    const h = history.find((x) => x.day === p.switched_day);
                    return h ? <ReferenceLine x={h.tick} stroke={C_AI} strokeDasharray="2 2" label={{ value: t("lab.modelOn"), fontSize: 10, fill: C_AI, position: "insideTopLeft" }} /> : null;
                  })()}
                <Bar dataKey="demand" name={t("lab.series.demand")} fill={C_REAL} fillOpacity={0.15} />
                <Line dataKey="ai_forecast" name={t("lab.series.ai")} stroke={C_AI} strokeWidth={2.5} dot={false} />
                <Line dataKey="noai_forecast" name={t("lab.series.noai")} stroke={C_NOAI} strokeWidth={2} strokeDasharray="5 4" dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Chip label={t("lab.chip.errAi")} value={pct(p.wape_ai_28)} good />
            <Chip label={t("lab.chip.errNoai")} value={pct(p.wape_noai_28)} />
            <Chip label={t("lab.chip.stockouts")} value={`${p.stockouts_ai} × ${p.stockouts_noai}`} />
            <Chip label={t("lab.chip.buy")} value={fmtNum(Math.round(p.recommended))} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Chip({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded-xl border bg-muted/30 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("font-mono text-sm font-bold", good && "text-primary")}>{value}</p>
    </div>
  );
}

function LearningCurve({ snap }: { snap: LabSnapshot }) {
  const { t } = useI18n();
  const byDay = new Map<number, Record<string, number>>();
  for (const p of snap.products) {
    for (const e of p.pattern_error_series) {
      const row = byDay.get(e.day) ?? { day: e.day + 1 };
      row[p.key] = e.error_pp;
      byDay.set(e.day, row);
    }
  }
  const data = Array.from(byDay.values());
  const colors: Record<string, string> = { cerveja: C_AI, pao: C_NOAI, leite: "hsl(var(--chart-4))" };
  return (
    <Card className="animate-fade-in-up">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t("lab.curveTitle")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("lab.curveSub")}</p>
      </CardHeader>
      <CardContent>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} width={38} unit="pp" />
              <ReTooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {snap.shifts.map((s) => (
                <ReferenceLine key={s.day} x={s.day + 1} stroke={C_NOAI} strokeDasharray="4 3" />
              ))}
              {snap.products.map((p) => (
                <Line key={p.key} dataKey={p.key} name={p.name} stroke={colors[p.key]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
