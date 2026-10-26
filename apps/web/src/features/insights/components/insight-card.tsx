"use client";

import {
  ArchiveIcon,
  ChevronDownIcon,
  CircleCheckIcon,
  CoinsIcon,
  CpuIcon,
  FlameIcon,
  GaugeIcon,
  type LucideIcon,
  MemoryStickIcon,
  MoonIcon,
  RotateCcwIcon,
  ServerCrashIcon,
  TimerIcon,
  TrendingDownIcon,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { InsightStatusChip, SeverityChip } from "@/components/status-chip";
import { Button } from "@/components/ui/button";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { Insight } from "@/lib/api/types";
import { insightKindLabel } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatDateTime, formatHours, formatMemory, formatNusd, formatRatio, formatRelative } from "@/lib/format";

import { useInsightAction } from "../api";

const ICON: Record<string, LucideIcon> = {
  idle_loaded: MoonIcon,
  idle_empty: ArchiveIcon,
  underused: TrendingDownIcon,
  oversized_vram: MemoryStickIcon,
  throttled: FlameIcon,
  memory_pressure: GaugeIcon,
  gpu_errors: ServerCrashIcon,
  inference_queueing: TimerIcon,
  inference_overprovisioned: CpuIcon,
};

interface Period {
  start: string;
  end: string;
  hours: number;
}

/** The evidence behind a finding, in words and small tables. */
function Evidence({ insight }: { insight: Insight }) {
  const e = insight.evidence as Record<string, unknown>;
  const periods = (e.periods as Period[] | undefined) ?? [];
  const shares = e.shares as Record<string, number> | undefined;
  const candidate = e.candidate as { model: string; memory_total_mib: number; nusd_per_hour: number } | undefined;
  const rows: [string, string][] = [];
  if (typeof e.idle_hours === "number") rows.push(["Idle time", `${formatHours(e.idle_hours)} of ${formatHours(Number(e.monitored_hours ?? 0))} monitored`]);
  if (typeof e.cost_nusd === "number") rows.push(["Cost at your rate", formatNusd(e.cost_nusd)]);
  if (typeof e.busy_hours === "number") rows.push(["Busy time", formatHours(e.busy_hours)]);
  if (typeof e.avg_util === "number") rows.push(["Average utilization while busy", `${Math.round(e.avg_util)}%`]);
  if (typeof e.peak_mib === "number") rows.push(["Peak memory", `${formatMemory(e.peak_mib)} of ${formatMemory(Number(e.total_mib))}`]);
  if (typeof e.minutes === "number") rows.push(["Minutes affected", String(e.minutes)]);
  if (typeof e.ecc_new === "number") rows.push(["New uncorrected ECC errors", String(e.ecc_new)]);
  if (typeof e.xid_events === "number") rows.push(["XID events", String(e.xid_events)]);
  if (typeof e.nusd_per_million_tokens === "number") rows.push(["Cost per million tokens", formatNusd(e.nusd_per_million_tokens)]);
  if (candidate) rows.push(["Smaller card that fits", `${candidate.model} (${formatMemory(candidate.memory_total_mib)}, ${formatNusd(candidate.nusd_per_hour)}/h)`]);
  return (
    <div className="space-y-3 text-[12.5px]">
      {rows.length > 0 && (
        <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="text-right font-medium tabular">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {shares && (
        <div className="flex flex-wrap gap-3">
          {Object.entries(shares).map(([k, v]) => (
            <span key={k} className="rounded-md bg-muted px-2 py-1">
              {k === "hw" ? "Hardware slowdown" : k === "power" ? "Power cap" : "Thermal"}: <span className="font-semibold tabular">{formatRatio(v)}</span> of busy time
            </span>
          ))}
        </div>
      )}
      {periods.length > 0 && (
        <div>
          <div className="mb-1 text-muted-foreground">Longest idle periods</div>
          <ul className="space-y-0.5">
            {periods.slice(0, 5).map((p) => (
              <li key={p.start} className="flex justify-between gap-3 tabular">
                <span>
                  {formatDateTime(p.start)} to {formatDateTime(p.end)}
                </span>
                <span className="text-muted-foreground">{formatHours(p.hours)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-faint">
        Window {formatDateTime(insight.window_start)} to {formatDateTime(insight.window_end)}. First seen {formatRelative(insight.first_seen_at)}, last
        checked {formatRelative(insight.last_seen_at)}.
      </p>
    </div>
  );
}

export function InsightCard({ insight, compact = false }: { insight: Insight; compact?: boolean }) {
  const [open, setOpen] = React.useState(false);
  const act = useInsightAction();
  const { canWrite } = usePermissions();
  const Icon = ICON[insight.kind] ?? CircleCheckIcon;
  const subject = insight.gpu_label ?? insight.endpoint_name ?? insight.host_name;
  const subjectHref = insight.gpu_id ? `/gpus/${insight.gpu_id}` : insight.endpoint_id ? `/inference?endpoint=${insight.endpoint_id}` : "/hosts";
  const resolved = insight.status === "resolved";

  function run(action: "acknowledge" | "dismiss" | "reopen") {
    act.mutate(
      { id: insight.id, action },
      {
        onSuccess: () => toast.success({ acknowledge: "Acknowledged.", dismiss: "Dismissed.", reopen: "Reopened." }[action]),
        onError: (err) => toast.error(errorMessage(err)),
      },
    );
  }

  return (
    <article className={cn("surface flex flex-col gap-3 p-4", resolved && "opacity-75")} data-qa="insight-card">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-xl",
            insight.severity === "critical" ? "bg-danger-soft text-danger" : insight.severity === "warning" ? "bg-warning-soft text-warning" : "bg-info-soft text-info",
          )}
        >
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11.5px] font-medium text-muted-foreground">{insightKindLabel(insight.kind)}</span>
            <SeverityChip value={insight.severity} />
            {insight.status !== "open" && <InsightStatusChip value={insight.status} />}
          </div>
          <h3 className="mt-0.5 text-[14.5px] leading-snug font-semibold text-foreground">{insight.title}</h3>
          {subject && (
            <Link href={subjectHref} className="text-[12.5px] text-primary underline-offset-4 hover:underline">
              {subject}
            </Link>
          )}
        </div>
        {insight.est_monthly_nusd != null && insight.est_monthly_nusd > 0 && (
          <div className="shrink-0 text-right">
            <div className="flex items-center justify-end gap-1 text-[16px] font-semibold tracking-[-0.01em] text-foreground tabular">
              <CoinsIcon className="size-3.5 text-warning" />
              {formatNusd(insight.est_monthly_nusd)}
            </div>
            <div className="text-[11px] text-muted-foreground">est. per month</div>
          </div>
        )}
      </div>
      <p className="text-[13px] leading-relaxed text-muted-foreground">{insight.summary}</p>
      {!compact && (
        <div className="rounded-xl bg-muted/70 px-3.5 py-2.5 text-[13px] leading-relaxed">
          <span className="font-semibold text-foreground">What to do: </span>
          <span className="text-foreground/90">{insight.recommendation}</span>
        </div>
      )}
      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="subtle" size="xs" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            <ChevronDownIcon className={cn("transition-transform", open && "rotate-180")} />
            {open ? "Hide evidence" : "Show evidence"}
          </Button>
          {canWrite && !resolved && (
            <div className="ml-auto flex gap-1">
              {insight.status === "open" && (
                <Button variant="secondary" size="xs" disabled={act.isPending} onClick={() => run("acknowledge")}>
                  Acknowledge
                </Button>
              )}
              {insight.status !== "dismissed" ? (
                <Button variant="subtle" size="xs" disabled={act.isPending} onClick={() => run("dismiss")}>
                  Dismiss
                </Button>
              ) : (
                <Button variant="subtle" size="xs" disabled={act.isPending} onClick={() => run("reopen")}>
                  <RotateCcwIcon />
                  Reopen
                </Button>
              )}
            </div>
          )}
        </div>
      )}
      {open && !compact && <Evidence insight={insight} />}
    </article>
  );
}
