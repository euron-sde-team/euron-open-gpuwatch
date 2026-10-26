"use client";

import * as React from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { NOT_AVAILABLE } from "@/lib/format";

import { CHART, ChartLegend, ChartTooltipCard } from "./chart-tooltip";

export interface Series {
  key: string;
  label: string;
  color: string;
  kind?: "line" | "area";
  axis?: "left" | "right";
  format: (v: number) => string;
  dashed?: boolean;
}

const axisProps = {
  stroke: CHART.axis,
  tick: { fill: CHART.axis, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

const timeFmt = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
const dayFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const longFmt = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

/**
 * Lines and areas over time. Missing readings stay gaps (never drawn as zero), and the
 * tooltip says "Not available" for them.
 */
export default function TimeSeriesChart({
  rows,
  series,
  height = 220,
  leftFormat,
  rightFormat,
  leftDomain,
  rightDomain,
  ariaLabel,
  legend = true,
}: {
  rows: Record<string, unknown>[];
  series: Series[];
  height?: number;
  leftFormat?: (v: number) => string;
  rightFormat?: (v: number) => string;
  leftDomain?: [number | "auto", number | "auto"];
  rightDomain?: [number | "auto", number | "auto"];
  ariaLabel: string;
  legend?: boolean;
}) {
  const span = rows.length > 1 ? new Date(String(rows[rows.length - 1]?.ts)).getTime() - new Date(String(rows[0]?.ts)).getTime() : 0;
  const tick = (t: string) => (span > 2 * 86_400_000 ? dayFmt : timeFmt).format(new Date(t));
  const hasRight = series.some((s) => s.axis === "right");
  const ids = React.useId().replace(/:/g, "");
  return (
    <div className="flex w-full flex-col gap-2">
      {legend && <ChartLegend items={series.map((s) => ({ label: s.label, color: s.color }))} />}
      <div className="w-full" style={{ height }} role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 6, right: hasRight ? 0 : 6, bottom: 0, left: 0 }}>
            <defs>
              {series
                .filter((s) => s.kind === "area")
                .map((s) => (
                  <linearGradient key={s.key} id={`${ids}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
                  </linearGradient>
                ))}
            </defs>
            <CartesianGrid vertical={false} stroke={CHART.grid} />
            <XAxis dataKey="ts" tickFormatter={tick} {...axisProps} minTickGap={36} />
            <YAxis yAxisId="left" tickFormatter={leftFormat} width={58} domain={leftDomain} {...axisProps} />
            {hasRight && <YAxis yAxisId="right" orientation="right" tickFormatter={rightFormat} width={58} domain={rightDomain} {...axisProps} />}
            <Tooltip
              cursor={{ stroke: CHART.axis, strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as Record<string, unknown> | undefined;
                if (!active || !row) return null;
                return (
                  <ChartTooltipCard
                    title={longFmt.format(new Date(String(row.ts)))}
                    rows={series.map((s) => {
                      const v = row[s.key];
                      return { label: s.label, color: s.color, value: typeof v === "number" ? s.format(v) : NOT_AVAILABLE };
                    })}
                  />
                );
              }}
            />
            {series.map((s) =>
              s.kind === "area" ? (
                <Area
                  key={s.key}
                  yAxisId={s.axis ?? "left"}
                  type="monotone"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={2}
                  fill={`url(#${ids}-${s.key})`}
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3.5, strokeWidth: 2, stroke: "var(--card)" }}
                />
              ) : (
                <Line
                  key={s.key}
                  yAxisId={s.axis ?? "left"}
                  type="monotone"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={2}
                  strokeDasharray={s.dashed ? "4 3" : undefined}
                  connectNulls={false}
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3.5, strokeWidth: 2, stroke: "var(--card)" }}
                />
              ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
