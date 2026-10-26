"use client";

import * as React from "react";

import { Hint } from "@/components/hint";
import { MetricValue } from "@/components/metric-value";
import type { InferenceStats } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatNusd, formatPercent, formatRatio, formatSeconds } from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";

import { formatRate } from "./inference-format";

const COST_REASON = "Needs an hourly rate for the GPUs this server runs on, and some traffic in the window. Set rates under Costs.";

interface StatDef {
  label: string;
  hint?: GlossaryKey;
  render: (s: InferenceStats) => React.ReactNode;
}

const STATS: StatDef[] = [
  { label: "Requests/s", render: (s) => <MetricValue value={s.requests_per_s} format={formatRate} /> },
  { label: "Generated tokens/s", render: (s) => <MetricValue value={s.generation_tokens_per_s} format={formatRate} /> },
  { label: "TTFT p50", hint: "ttft", render: (s) => <MetricValue value={s.ttft_p50_s} format={formatSeconds} /> },
  { label: "TTFT p95", hint: "ttft", render: (s) => <MetricValue value={s.ttft_p95_s} format={formatSeconds} /> },
  { label: "Inter-token p50", render: (s) => <MetricValue value={s.itl_p50_s} format={formatSeconds} /> },
  { label: "End to end p95", render: (s) => <MetricValue value={s.e2e_p95_s} format={formatSeconds} /> },
  { label: "Queue (waiting)", render: (s) => <MetricValue value={s.waiting_avg} format={formatRate} /> },
  { label: "KV cache", render: (s) => <MetricValue value={s.kv_cache_avg} format={(v) => formatRatio(v, 0)} /> },
  { label: "GPU utilization", render: (s) => <MetricValue value={s.gpu_util_avg} format={(v) => formatPercent(v, 0)} /> },
  { label: "Cost per 1M tokens", hint: "costPerMillion", render: (s) => <MetricValue value={s.nusd_per_million_tokens} format={formatNusd} reason={COST_REASON} /> },
  { label: "Cost per request", render: (s) => <MetricValue value={s.nusd_per_request} format={formatNusd} reason={COST_REASON} /> },
];

/** The serving stats of one window, as a label and value grid. */
export function StatGrid({ stats, className, dense = false }: { stats: InferenceStats; className?: string; dense?: boolean }) {
  return (
    <dl className={cn("grid grid-cols-2 gap-x-4", dense ? "gap-y-2.5" : "gap-y-3.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6", className)}>
      {STATS.map((d) => (
        <div key={d.label} className="min-w-0">
          <dt className="flex items-center gap-1 text-[11.5px] leading-tight text-muted-foreground">
            <span className="truncate">{d.label}</span>
            {d.hint && <Hint term={d.hint} />}
          </dt>
          <dd className={cn("mt-0.5 font-semibold text-foreground", dense ? "text-[14px]" : "text-[16px] tracking-[-0.01em]")}>{d.render(stats)}</dd>
        </div>
      ))}
    </dl>
  );
}
