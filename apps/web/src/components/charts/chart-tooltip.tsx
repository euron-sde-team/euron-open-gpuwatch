"use client";

import * as React from "react";

export interface TooltipRow {
  label: string;
  value: string;
  color: string;
}

/** Shared tooltip card for every chart: title, then one row per series. */
export function ChartTooltipCard({ title, rows, footer }: { title: string; rows: TooltipRow[]; footer?: React.ReactNode }) {
  return (
    <div className="min-w-44 rounded-xl bg-popover px-3 py-2.5 text-xs text-popover-foreground shadow-[var(--elev-4)] ring-1 ring-black/5 dark:ring-white/8">
      <div className="mb-1.5 font-medium text-muted-foreground">{title}</div>
      <div className="space-y-1">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-5">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="size-2 rounded-[3px]" style={{ background: r.color }} aria-hidden />
              {r.label}
            </span>
            <span className="font-semibold text-foreground tabular">{r.value}</span>
          </div>
        ))}
      </div>
      {footer && <div className="mt-1.5 pt-1.5 text-muted-foreground">{footer}</div>}
    </div>
  );
}

export function ChartLegend({ items }: { items: { label: string; color: string; value?: string }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: i.color }} aria-hidden />
          {i.label}
          {i.value && <span className="font-semibold text-foreground tabular">{i.value}</span>}
        </li>
      ))}
    </ul>
  );
}

export const CHART = {
  util: "var(--chart-util)",
  mem: "var(--chart-mem)",
  power: "var(--chart-power)",
  temp: "var(--chart-temp)",
  idle: "var(--chart-idle)",
  grid: "var(--chart-grid)",
  axis: "var(--chart-axis)",
} as const;

/** Categorical colors for workloads, teams, hosts (cycled past six). */
export const SERIES = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"] as const;

export function seriesColor(i: number): string {
  return SERIES[i % SERIES.length] ?? SERIES[0];
}
