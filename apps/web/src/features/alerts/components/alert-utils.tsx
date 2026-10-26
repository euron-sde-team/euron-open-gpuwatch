"use client";

import * as React from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AlertRule, AlertRuleIn } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";

export const ALERT_TABS = ["events", "rules", "channels", "deliveries"] as const;
export type AlertTab = (typeof ALERT_TABS)[number];

export function isAlertTab(v: unknown): v is AlertTab {
  return typeof v === "string" && (ALERT_TABS as readonly string[]).includes(v);
}

export type Metric = NonNullable<AlertRuleIn["metric"]>;
export type RuleKind = NonNullable<AlertRuleIn["kind"]>;
export type SeverityValue = NonNullable<AlertRuleIn["severity"]>;

export const METRICS: { value: Metric; label: string; unit: string }[] = [
  { value: "util_gpu", label: "GPU utilization", unit: "%" },
  { value: "util_mem", label: "Memory bandwidth", unit: "%" },
  { value: "mem_used_pct", label: "Memory used %", unit: "%" },
  { value: "temp_c", label: "Temperature", unit: "°C" },
  { value: "power_w", label: "Power W", unit: "W" },
  { value: "power_pct", label: "Power % of limit", unit: "%" },
  { value: "fan_pct", label: "Fan %", unit: "%" },
];

export function metricUnit(metric: string | null | undefined): string {
  return METRICS.find((m) => m.value === metric)?.unit ?? "";
}

export const SEVERITIES: { value: SeverityValue; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "warning", label: "Warning" },
  { value: "info", label: "Info" },
];

export const SEVERITY_ORDER: SeverityValue[] = ["critical", "warning", "info"];

/** "45s", "12m", "3h 20m", "2d 4h". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

export function secondsBetween(from: string, to: string | Date): number {
  const end = typeof to === "string" ? new Date(to).getTime() : to.getTime();
  return (end - new Date(from).getTime()) / 1000;
}

/** A relative time ("5m ago") with the exact date and time on hover or focus. */
export function TimeAgo({ iso, className, empty = "Never" }: { iso: string | null | undefined; className?: string; empty?: string }) {
  if (!iso) return <span className={cn("text-faint", className)}>{empty}</span>;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <time
            dateTime={iso}
            tabIndex={0}
            className={cn("cursor-default rounded-sm tabular focus-visible:outline-2 focus-visible:outline-ring", className)}
          />
        }
      >
        {formatRelative(iso)}
      </TooltipTrigger>
      <TooltipContent>{formatDateTime(iso)}</TooltipContent>
    </Tooltip>
  );
}

/** The full write body of an existing rule, for in-place toggles. */
export function ruleToInput(rule: AlertRule): AlertRuleIn {
  return {
    name: rule.name,
    kind: rule.kind,
    metric: rule.kind === "threshold" ? (rule.metric as Metric | null) : null,
    operator: rule.kind === "threshold" ? (rule.operator as "gt" | "lt" | null) : null,
    threshold: rule.kind === "threshold" ? rule.threshold : null,
    duration_s: rule.duration_s,
    scope_host_id: rule.scope_host_id,
    scope_gpu_id: rule.scope_gpu_id,
    scope_label: rule.scope_label,
    severity: rule.severity,
    channel_ids: rule.channel_ids,
    notify_resolved: rule.notify_resolved,
    enabled: rule.enabled,
  };
}

/** Re-renders every `ms` so relative times and "Firing for" stay current. */
export function useNow(ms = 30_000): Date {
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
