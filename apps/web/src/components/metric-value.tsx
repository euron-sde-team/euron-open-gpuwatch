"use client";

import * as React from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { NOT_AVAILABLE } from "@/lib/format";
import { GLOSSARY } from "@/lib/glossary";

/**
 * A metric reading. ``null`` means the driver did not report it on this GPU, which is
 * shown as a muted "Not available" with an explanation, never as 0.
 */
export function MetricValue({
  value,
  format,
  className,
  reason,
}: {
  value: number | null | undefined;
  format: (v: number) => string;
  className?: string;
  /** Why the value is missing, when it is not the driver (no rate set, no traffic). */
  reason?: React.ReactNode;
}) {
  if (value == null) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <span
              tabIndex={0}
              data-qa="not-available"
              className={cn("cursor-help text-faint underline decoration-dotted underline-offset-4 focus-visible:outline-2 focus-visible:outline-ring", className)}
            />
          }
        >
          {NOT_AVAILABLE}
        </TooltipTrigger>
        <TooltipContent>{reason ?? GLOSSARY.notAvailable}</TooltipContent>
      </Tooltip>
    );
  }
  return <span className={cn("tabular", className)}>{format(value)}</span>;
}

/** A labelled reading for spec lists: "Temperature  64°C". */
export function MetricRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-[13px]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium text-foreground">{children}</dd>
    </div>
  );
}

/** A thin horizontal meter (utilization, memory). Null renders an empty, dashed track. */
export function Meter({
  value,
  max = 100,
  tone = "util",
  className,
  label,
}: {
  value: number | null | undefined;
  max?: number;
  tone?: "util" | "mem" | "power" | "temp";
  className?: string;
  label: string;
}) {
  const pct = value == null || !max ? null : Math.max(0, Math.min(100, (100 * value) / max));
  const color = { util: "bg-chart-util", mem: "bg-chart-mem", power: "bg-chart-power", temp: "bg-chart-temp" }[tone];
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct == null ? undefined : Math.round(pct)}
      aria-valuetext={pct == null ? NOT_AVAILABLE : `${Math.round(pct)}%`}
      className={cn("relative h-1.5 overflow-hidden rounded-full", pct == null ? "bg-[repeating-linear-gradient(90deg,var(--muted)_0_4px,transparent_4px_8px)]" : "bg-muted", className)}
    >
      {pct != null && <div className={cn("absolute inset-y-0 left-0 rounded-full transition-[width] duration-500", color)} style={{ width: `${pct}%` }} />}
    </div>
  );
}
