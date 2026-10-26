"use client";

import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Hint } from "@/components/hint";
import { CHART, seriesColor } from "@/components/charts/chart-tooltip";
import type { GroupBy } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";
import type { Range } from "@/lib/range";

export const IDLE_KEY = "__idle__";

export const GROUP_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: "workload", label: "Workload" },
  { value: "team", label: "Team" },
  { value: "host", label: "Host" },
  { value: "gpu", label: "GPU" },
  { value: "model", label: "Model" },
];

export const COST_RANGES = ["24h", "7d", "30d"] as const satisfies readonly Range[];
export type CostRange = (typeof COST_RANGES)[number];

export const RANGE_OPTIONS: { value: CostRange; label: string }[] = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
];

export function isGroupBy(v: unknown): v is GroupBy {
  return typeof v === "string" && GROUP_OPTIONS.some((o) => o.value === v);
}

export function isCostRange(v: unknown): v is CostRange {
  return typeof v === "string" && (COST_RANGES as readonly string[]).includes(v);
}

export function groupLabel(v: string): string {
  return GROUP_OPTIONS.find((o) => o.value === v)?.label ?? v;
}

/** GPU hours as a plain figure: "0.4", "12.5", "1,204". */
export function formatGpuHours(h: number): string {
  if (!Number.isFinite(h)) return "n/a";
  if (h >= 100) return formatNumber(h);
  return h.toFixed(1).replace(/\.0$/, "");
}

/** One color per series key: the idle bucket is always grey, the rest cycle the palette. */
export function colorMap(keys: readonly string[]): Map<string, string> {
  const out = new Map<string, string>();
  let i = 0;
  for (const k of keys) {
    if (k === IDLE_KEY) out.set(k, CHART.idle);
    else out.set(k, seriesColor(i++));
  }
  return out;
}

/** A thin horizontal bar for a 0..1 share, with the percent next to it. */
export function ShareBar({ value, color, label, className }: { value: number; color?: string; label: string; className?: string }) {
  const pct = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0)) * 100;
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        className="relative h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-muted sm:w-20"
      >
        <div className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-11 text-right text-muted-foreground tabular">{pct < 0.1 && pct > 0 ? "<0.1%" : `${pct.toFixed(1).replace(/\.0$/, "")}%`}</span>
    </div>
  );
}

/** A headline figure in the KpiTile style, with a plain sub-line instead of a period delta. */
export function StatTile({
  label,
  value,
  sub,
  icon: Icon,
  hint,
  accent = "primary",
}: {
  label: string;
  value: React.ReactNode;
  sub: React.ReactNode;
  icon: LucideIcon;
  hint?: GlossaryKey;
  accent?: "primary" | "savings" | "warning" | "neutral";
}) {
  const iconTone = {
    primary: "bg-primary-soft text-primary",
    savings: "bg-savings-soft text-savings",
    warning: "bg-warning-soft text-warning",
    neutral: "bg-neutral-soft text-muted-foreground",
  }[accent];
  return (
    <div className="surface flex min-w-0 flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg", iconTone)}>
          <Icon className="size-3.5" />
        </span>
        <span className="min-w-0 text-[12.5px] leading-tight font-medium text-muted-foreground sm:truncate">{label}</span>
        {hint && <Hint term={hint} />}
      </div>
      <div>
        <div className="truncate text-[24px] leading-none font-semibold tracking-[-0.02em] text-foreground tabular">{value}</div>
        <div className="mt-2 truncate text-[11.5px] text-muted-foreground">{sub}</div>
      </div>
    </div>
  );
}
