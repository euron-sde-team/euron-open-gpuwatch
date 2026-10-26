"use client";

import { CpuIcon, ThermometerIcon, ZapIcon } from "lucide-react";
import Link from "next/link";

import { Meter, MetricValue } from "@/components/metric-value";
import { GpuChip } from "@/components/status-chip";
import { Chip } from "@/components/ui/chip";
import type { Gpu, LiveSample } from "@/lib/api/types";
import { tempTone, throttleReasons } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatMemory, formatRate, formatRelative, metric } from "@/lib/format";

/** One GPU at a glance: status, utilization, memory, temperature, power, processes. */
export function GpuTile({ gpu, className }: { gpu: Gpu; className?: string }) {
  const live = (gpu.live ?? null) as LiveSample | null;
  const util = live?.util_gpu ?? null;
  const memTotal = live?.mem_total_mib ?? gpu.memory_total_mib ?? null;
  const reasons = throttleReasons(live?.util_gpu != null && live.util_gpu >= 50 ? live.throttle_reasons : null);
  const tone = tempTone(live?.temp_c);
  const quiet = gpu.status !== "ok";
  return (
    <Link
      href={`/gpus/${gpu.id}`}
      data-qa="gpu-tile"
      className={cn(
        "surface group flex min-w-0 flex-col gap-3 p-4 transition-shadow hover:shadow-[var(--elev-3)] focus-visible:outline-2 focus-visible:outline-ring",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-foreground">
            GPU {gpu.index} <span className="font-normal text-muted-foreground">{gpu.name.replace(/^NVIDIA /, "")}</span>
          </div>
          <div className="truncate text-[11.5px] text-muted-foreground">{gpu.host_name}</div>
        </div>
        <GpuChip value={gpu.status} />
      </div>

      {quiet && !live ? (
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">
          {gpu.status === "lost"
            ? "Stopped appearing in its host's reports."
            : gpu.status === "retired"
              ? "Taken out of service."
              : `Last reading ${formatRelative(gpu.last_seen_at)}.`}
        </p>
      ) : (
        <>
          <div>
            <div className="mb-1.5 flex items-baseline justify-between">
              <span className="text-[11.5px] font-medium text-muted-foreground">Utilization</span>
              <span className="text-[22px] leading-none font-semibold tracking-[-0.02em]">
                <MetricValue value={util} format={(v) => metric.pct(v)} className={util == null ? "text-[13px] font-normal" : undefined} />
              </span>
            </div>
            <Meter value={util} label="GPU utilization" />
          </div>
          <div>
            <div className="mb-1.5 flex items-baseline justify-between text-[11.5px]">
              <span className="font-medium text-muted-foreground">Memory</span>
              <span className="text-foreground tabular">
                <MetricValue value={live?.mem_used_mib} format={formatMemory} />
                {memTotal != null && <span className="text-muted-foreground"> / {formatMemory(memTotal)}</span>}
              </span>
            </div>
            <Meter value={live?.mem_used_mib} max={memTotal ?? undefined} tone="mem" label="Memory used" />
          </div>
          <div className="grid grid-cols-3 gap-2 text-[12px]">
            <span className={cn("flex items-center gap-1", tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-muted-foreground")}>
              <ThermometerIcon className="size-3.5 shrink-0" />
              <MetricValue value={live?.temp_c} format={(v) => metric.temp(v)} className="truncate" />
            </span>
            <span className="flex items-center gap-1 text-muted-foreground">
              <ZapIcon className="size-3.5 shrink-0" />
              <MetricValue value={live?.power_w} format={(v) => metric.watts(v)} className="truncate" />
            </span>
            <span className="flex items-center gap-1 text-muted-foreground">
              <CpuIcon className="size-3.5 shrink-0" />
              {live?.procs == null ? <MetricValue value={null} format={String} className="truncate" /> : `${live.procs} proc${live.procs === 1 ? "" : "s"}`}
            </span>
          </div>
        </>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-0.5 text-[11px] text-muted-foreground">
        {reasons.map((r) => (
          <Chip key={r} tone={r === "Thermal" ? "danger" : "warning"}>
            {r}
          </Chip>
        ))}
        <span className="ml-auto tabular">{formatRate(gpu.nusd_per_hour)}</span>
      </div>
    </Link>
  );
}
