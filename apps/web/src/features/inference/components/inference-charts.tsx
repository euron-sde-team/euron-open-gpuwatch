"use client";

import { InfoIcon } from "lucide-react";
import * as React from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { CHART, ChartLegend, ChartTooltipCard, seriesColor } from "@/components/charts/chart-tooltip";
import type { InferencePoint } from "@/lib/api/types";
import { formatDateTime, formatPercent, formatSeconds, formatTime } from "@/lib/format";
import type { Range } from "@/lib/range";

import { formatRate } from "./inference-format";

interface Row {
  t: number;
  rps: number | null;
  tps: number | null;
  ttft50: number | null;
  ttft95: number | null;
  e2e95: number | null;
  waiting: number | null;
  running: number | null;
  kv: number | null;
}

interface SeriesDef {
  key: keyof Omit<Row, "t">;
  label: string;
  color: string;
  dashed?: boolean;
}

const HEIGHT = 200;

const shortDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

function tickFormatter(range: Range) {
  return (t: number) => (range === "7d" ? shortDate.format(new Date(t)) : formatTime(new Date(t).toISOString()));
}

function makeTooltip(series: SeriesDef[], format: (v: number) => string) {
  function ChartTip({ active, payload, label }: TooltipContentProps) {
    if (!active || !payload?.length) return null;
    const rows = series
      .filter((s) => payload.some((p) => p.dataKey === s.key))
      .map((s) => {
        const v = payload.find((p) => p.dataKey === s.key)?.value;
        return { label: s.label, color: s.color, value: typeof v === "number" ? format(v) : "No data" };
      });
    return <ChartTooltipCard title={formatDateTime(new Date(Number(label)).toISOString())} rows={rows} />;
  }
  return ChartTip;
}

function ChartPanel({ title, legend, note, children }: { title: string; legend: SeriesDef[]; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <figure className="min-w-0 rounded-xl bg-muted/40 p-4">
      <figcaption className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <span className="text-[13px] font-semibold text-foreground">{title}</span>
        <ChartLegend items={legend.map((s) => ({ label: s.label, color: s.color }))} />
      </figcaption>
      {children}
      {note && (
        <p className="mt-2 flex items-start gap-1.5 text-[12px] leading-snug text-muted-foreground">
          <InfoIcon className="mt-px size-3.5 shrink-0" />
          {note}
        </p>
      )}
    </figure>
  );
}

function Lines({ data, series, range, format, yFormat }: { data: Row[]; series: SeriesDef[]; range: Range; format: (v: number) => string; yFormat: (v: number) => string }) {
  const Tip = React.useMemo(() => makeTooltip(series, format), [series, format]);
  return (
    <ResponsiveContainer width="100%" height={HEIGHT}>
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={CHART.grid} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tickFormatter={tickFormatter(range)}
          stroke={CHART.axis}
          tick={{ fontSize: 11, fill: CHART.axis }}
          tickLine={false}
          axisLine={false}
          minTickGap={36}
        />
        <YAxis width={48} tickFormatter={yFormat} stroke={CHART.axis} tick={{ fontSize: 11, fill: CHART.axis }} tickLine={false} axisLine={false} />
        <Tooltip content={Tip} cursor={{ stroke: CHART.axis, strokeDasharray: "3 3" }} />
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            name={s.label}
            type="monotone"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "4 3" : undefined}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function Areas({ data, series, range }: { data: Row[]; series: SeriesDef[]; range: Range }) {
  const Tip = React.useMemo(() => makeTooltip(series, formatRate), [series]);
  return (
    <ResponsiveContainer width="100%" height={HEIGHT}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={CHART.grid} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tickFormatter={tickFormatter(range)}
          tick={{ fontSize: 11, fill: CHART.axis }}
          tickLine={false}
          axisLine={false}
          minTickGap={36}
        />
        <YAxis width={48} tickFormatter={formatRate} tick={{ fontSize: 11, fill: CHART.axis }} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip content={Tip} cursor={{ stroke: CHART.axis, strokeDasharray: "3 3" }} />
        {series.map((s) => (
          <Area
            key={s.key}
            dataKey={s.key}
            name={s.label}
            type="monotone"
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.16}
            strokeWidth={2}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

const THROUGHPUT: SeriesDef[] = [
  { key: "rps", label: "Requests/s", color: seriesColor(0) },
  { key: "tps", label: "Tokens/s", color: seriesColor(1) },
];
const LATENCY_ALL: SeriesDef[] = [
  { key: "ttft50", label: "TTFT p50", color: seriesColor(0) },
  { key: "ttft95", label: "TTFT p95", color: seriesColor(0), dashed: true },
  { key: "e2e95", label: "End to end p95", color: seriesColor(2) },
];
const LATENCY_E2E: SeriesDef[] = [{ key: "e2e95", label: "End to end p95", color: seriesColor(2) }];
const QUEUE: SeriesDef[] = [
  { key: "running", label: "Running", color: CHART.util },
  { key: "waiting", label: "Waiting", color: CHART.power },
];
const KV: SeriesDef[] = [{ key: "kv", label: "KV cache used", color: CHART.mem }];

const pct = (v: number) => formatPercent(v, 0);

/** Requests and token throughput, latency, queue and KV cache for one endpoint's window. */
export default function InferenceCharts({ points, range }: { points: InferencePoint[]; range: Range }) {
  const data = React.useMemo<Row[]>(
    () =>
      points.map((p) => ({
        t: new Date(p.ts).getTime(),
        rps: p.requests_per_s,
        tps: p.generation_tokens_per_s,
        ttft50: p.ttft_p50_s,
        ttft95: p.ttft_p95_s,
        e2e95: p.e2e_p95_s,
        waiting: p.waiting,
        running: p.running,
        kv: p.kv_cache == null ? null : p.kv_cache * 100,
      })),
    [points],
  );
  const hasTtft = data.some((r) => r.ttft50 != null || r.ttft95 != null);
  const hasKv = data.some((r) => r.kv != null);
  const hasQueue = data.some((r) => r.waiting != null || r.running != null);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartPanel title="Throughput" legend={THROUGHPUT}>
        <Lines data={data} series={THROUGHPUT} range={range} format={formatRate} yFormat={formatRate} />
      </ChartPanel>
      <ChartPanel
        title="Latency"
        legend={hasTtft ? LATENCY_ALL : LATENCY_E2E}
        note={hasTtft ? undefined : "This server does not expose time to first token (TGI has no TTFT histogram), so only end to end latency is drawn."}
      >
        <Lines data={data} series={hasTtft ? LATENCY_ALL : LATENCY_E2E} range={range} format={formatSeconds} yFormat={formatSeconds} />
      </ChartPanel>
      <ChartPanel title="Queue" legend={QUEUE} note={hasQueue ? undefined : "This server does not report running and waiting requests."}>
        <Areas data={data} series={QUEUE} range={range} />
      </ChartPanel>
      <ChartPanel
        title="KV cache"
        legend={KV}
        note={hasKv ? undefined : "This server does not expose KV cache usage (TGI has no KV cache gauge)."}
      >
        <Lines data={data} series={KV} range={range} format={pct} yFormat={pct} />
      </ChartPanel>
    </div>
  );
}
