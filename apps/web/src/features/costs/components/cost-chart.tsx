"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART, ChartTooltipCard } from "@/components/charts/chart-tooltip";
import type { CostSeries } from "@/lib/api/types";
import { formatCompact, formatNusd } from "@/lib/format";

type Point = CostSeries["points"][number];

const dayFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const hourFmt = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
const fullFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

function tick(iso: string, interval: CostSeries["interval"]): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return interval === "day" ? dayFmt.format(d) : hourFmt.format(d);
}

function title(iso: string, interval: CostSeries["interval"]): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return interval === "day" ? dayFmt.format(d) : fullFmt.format(d);
}

/** Stacked cost per bucket, one bar segment per series key. */
export default function CostChart({ series, colors }: { series: CostSeries; colors: Map<string, string> }) {
  const last = series.keys[series.keys.length - 1];
  return (
    <div className="h-[280px] w-full" role="img" aria-label="Estimated cost over time, stacked by group">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={series.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke={CHART.grid} />
          <XAxis
            dataKey="bucket"
            tickFormatter={(v: string) => tick(v, series.interval)}
            tick={{ fill: CHART.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            minTickGap={24}
          />
          <YAxis
            tickFormatter={(v: number) => (v === 0 ? "$0" : `$${formatCompact(v / 1e9)}`)}
            tick={{ fill: CHART.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={52}
          />
          <Tooltip
            cursor={{ fill: "var(--muted)", opacity: 0.6 }}
            content={({ active, payload }) => {
              const point = payload?.[0]?.payload as Point | undefined;
              if (!active || !point) return null;
              const rows = series.keys
                .map((k) => ({ key: k, value: point.values[k] ?? 0 }))
                .filter((r) => r.value > 0)
                .sort((a, b) => b.value - a.value)
                .map((r) => ({ label: series.labels[r.key] ?? r.key, value: formatNusd(r.value), color: colors.get(r.key) ?? CHART.idle }));
              const total = series.keys.reduce((sum, k) => sum + (point.values[k] ?? 0), 0);
              return (
                <ChartTooltipCard
                  title={title(point.bucket, series.interval)}
                  rows={rows.length ? rows : [{ label: "No priced GPU time", value: "$0.00", color: CHART.idle }]}
                  footer={
                    <span className="flex justify-between gap-5">
                      Total (estimate)
                      <span className="font-semibold text-foreground tabular">{formatNusd(total)}</span>
                    </span>
                  }
                />
              );
            }}
          />
          {series.keys.map((k) => (
            <Bar
              key={k}
              name={series.labels[k] ?? k}
              dataKey={(p: Point) => p.values[k] ?? 0}
              stackId="cost"
              fill={colors.get(k) ?? CHART.idle}
              radius={k === last ? [3, 3, 0, 0] : 0}
              maxBarSize={36}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
