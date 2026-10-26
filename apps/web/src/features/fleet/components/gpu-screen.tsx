"use client";

import { ArchiveIcon, ArrowLeftIcon, LightbulbIcon, RotateCcwIcon, SparklesIcon } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { seriesColor, CHART } from "@/components/charts/chart-tooltip";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { MetricRow, MetricValue } from "@/components/metric-value";
import { Segmented } from "@/components/segmented";
import { GpuChip, SimBadge } from "@/components/status-chip";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { InsightCard } from "@/features/insights/components/insight-card";
import { errorMessage } from "@/lib/api/errors";
import type { Gpu, LiveSample, MetricPoint } from "@/lib/api/types";
import { throttleReasons } from "@/lib/chips";
import { formatDateTime, formatHours, formatMemory, formatNusd, formatPercent, formatRate, formatRatio, formatRelative, metric } from "@/lib/format";
import { RANGE_LABEL, RANGES, type Range } from "@/lib/range";

import { useExplanation, useGpu, useGpuMetrics, useGpuProcesses, useRetireGpu } from "../api";

const TimeSeriesChart = dynamic(() => import("@/components/charts/time-series"), {
  ssr: false,
  loading: () => <Skeleton className="h-[220px] w-full" />,
});

function Explanation({ id }: { id: string }) {
  const q = useExplanation(id);
  if (q.isPending) return <Skeleton className="h-36 rounded-2xl" />;
  if (q.isError) return <Surface><ErrorState compact error={q.error} onRetry={() => void q.refetch()} /></Surface>;
  const e = q.data;
  const cost = e.cost_nusd ?? 0;
  const parts =
    e.cost_nusd != null && cost > 0
      ? [
          { label: "Working", value: cost - (e.idle_nusd ?? 0) - (e.held_idle_nusd ?? 0), color: CHART.util },
          { label: "Held idle", value: e.held_idle_nusd ?? 0, color: CHART.power },
          { label: "Nothing running", value: e.idle_nusd ?? 0, color: CHART.idle },
        ]
      : [];
  return (
    <Surface className="overflow-hidden">
      <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-1.5 text-[11.5px] font-semibold tracking-[0.06em] text-primary uppercase">
            <SparklesIcon className="size-3.5" />
            Why this GPU costs what it does
          </div>
          <h2 className="text-[18px] leading-snug font-semibold tracking-[-0.015em] text-foreground">{e.headline}</h2>
          <div className="max-w-3xl space-y-1 text-[13.5px] leading-relaxed text-muted-foreground">
            {e.sentences.map((s) => (
              <p key={s}>{s}</p>
            ))}
          </div>
        </div>
        {parts.length > 0 && (
          <div className="w-full shrink-0 lg:w-72">
            <div className="flex items-baseline justify-between">
              <span className="text-[12px] text-muted-foreground">Last {e.window_days} days</span>
              <span className="text-[20px] font-semibold tabular">{formatNusd(cost)}</span>
            </div>
            <div className="mt-2 flex h-2.5 overflow-hidden rounded-full bg-muted" aria-hidden>
              {parts.map((p) => (
                <div key={p.label} style={{ width: `${(100 * p.value) / cost}%`, background: p.color }} />
              ))}
            </div>
            <ul className="mt-2.5 space-y-1 text-[12px]">
              {parts.map((p) => (
                <li key={p.label} className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="size-2 rounded-[3px]" style={{ background: p.color }} aria-hidden />
                    {p.label}
                  </span>
                  <span className="font-medium tabular">
                    {formatNusd(p.value)} <span className="text-faint">{formatRatio(p.value / cost, 0)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Surface>
  );
}

function Charts({ id, range }: { id: string; range: Range }) {
  const q = useGpuMetrics(id, range);
  if (q.isPending) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-72 rounded-2xl" />
        ))}
      </div>
    );
  }
  if (q.isError) return <Surface><ErrorState error={q.error} onRetry={() => void q.refetch()} /></Surface>;
  const rows = q.data.points.map((p: MetricPoint) => ({
    ...p,
    mem_pct: p.mem_used_mib != null && p.mem_total_mib ? (100 * p.mem_used_mib) / p.mem_total_mib : null,
    throttle_power_pct: p.throttle_power != null ? 100 * p.throttle_power : null,
    throttle_thermal_pct: p.throttle_thermal != null ? 100 * p.throttle_thermal : null,
  }));
  if (!rows.length) {
    return (
      <Surface>
        <p className="px-5 py-10 text-center text-[13px] text-muted-foreground">No readings in this range. Pick a longer range, or check that the host is reporting.</p>
      </Surface>
    );
  }
  const avail = new Set(q.data.available);
  const resLabel = { raw: "every sample", "1m": "per minute", "1h": "per hour" }[q.data.resolution];
  const pct = (v: number) => formatPercent(v, 0);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Surface>
        <SurfaceHeader title="Utilization" titleExtra={<Hint term="utilization" />} description={`GPU and memory bandwidth, ${resLabel}`} />
        <div className="px-5 pb-5">
          <TimeSeriesChart
            ariaLabel="GPU utilization over time"
            rows={rows}
            leftFormat={pct}
            leftDomain={[0, 100]}
            series={[
              { key: "util", label: "GPU", color: CHART.util, kind: "area", format: pct },
              ...(avail.has("util_mem") ? [{ key: "util_mem", label: "Memory bandwidth", color: CHART.mem, format: pct }] : []),
            ]}
          />
        </div>
      </Surface>
      <Surface>
        <SurfaceHeader title="Memory" description="Used, against the card's total" />
        <div className="px-5 pb-5">
          <TimeSeriesChart
            ariaLabel="Memory used over time"
            rows={rows}
            leftFormat={(v) => (v === 0 ? "0" : `${Math.round(v / 1024)} GiB`)}
            leftDomain={[0, "auto"]}
            series={[
              { key: "mem_used_mib", label: "Used", color: CHART.mem, kind: "area", format: formatMemory },
              { key: "mem_total_mib", label: "Total", color: CHART.axis, dashed: true, format: formatMemory },
            ]}
          />
        </div>
      </Surface>
      <Surface>
        <SurfaceHeader title="Temperature and power" description={avail.has("power_w") ? "Power on the right axis" : "This GPU does not report power"} />
        <div className="px-5 pb-5">
          <TimeSeriesChart
            ariaLabel="Temperature and power over time"
            rows={rows}
            leftFormat={(v) => `${Math.round(v)}°`}
            rightFormat={(v) => `${Math.round(v)} W`}
            series={[
              { key: "temp_c", label: "Temperature", color: CHART.temp, format: (v) => metric.temp(v) },
              { key: "power_w", label: "Power", color: CHART.power, axis: "right", format: (v) => metric.watts(v) },
            ]}
          />
        </div>
      </Surface>
      <Surface>
        <SurfaceHeader
          title="Clocks and throttling"
          titleExtra={<Hint term="throttle" />}
          description={avail.has("throttle_power") ? "Share of busy time slowed down, on the right axis" : "This GPU reports no throttle reasons"}
        />
        <div className="px-5 pb-5">
          <TimeSeriesChart
            ariaLabel="SM clock and throttling over time"
            rows={rows}
            leftFormat={(v) => `${Math.round(v)}`}
            rightFormat={pct}
            rightDomain={[0, 100]}
            series={[
              { key: "sm_clock_mhz", label: "SM clock (MHz)", color: CHART.util, format: (v) => metric.mhz(v) },
              ...(avail.has("throttle_power")
                ? [
                    { key: "throttle_power_pct", label: "Power cap", color: CHART.power, axis: "right" as const, kind: "area" as const, format: pct },
                    { key: "throttle_thermal_pct", label: "Thermal", color: CHART.temp, axis: "right" as const, kind: "area" as const, format: pct },
                  ]
                : []),
            ]}
          />
        </div>
      </Surface>
    </div>
  );
}

function Processes({ id }: { id: string }) {
  const q = useGpuProcesses(id);
  return (
    <Surface>
      <SurfaceHeader title="Processes and workloads" titleExtra={<Hint term="attribution" />} description="On the GPU now, and who used it over the last day" />
      {q.isPending ? (
        <Skeleton className="mx-5 mb-5 h-32" />
      ) : q.isError ? (
        <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />
      ) : (
        <div className="grid gap-6 px-5 pb-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="min-w-0">
            {!q.data.listed ? (
              <p className="text-[13px] text-muted-foreground">
                The driver does not list processes here. <Hint term="unattributed" />
              </p>
            ) : !q.data.current.length ? (
              <p className="text-[13px] text-muted-foreground">Nothing is running on this GPU right now.</p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Process</TableHead>
                      <TableHead>Workload</TableHead>
                      <TableHead className="text-right">Memory</TableHead>
                      <TableHead className="text-right">SM share</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {q.data.current.map((p) => (
                      <TableRow key={p.pid}>
                        <TableCell>
                          <div className="font-medium">{p.name}</div>
                          <div className="text-[11.5px] text-muted-foreground tabular">
                            pid {p.pid}
                            {p.username && `, ${p.username}`}
                            {p.container_id && `, container ${p.container_id}`}
                          </div>
                        </TableCell>
                        <TableCell>
                          <span className="font-medium">{p.workload}</span>
                          {p.team && <span className="block text-[11.5px] text-muted-foreground">{p.team}</span>}
                        </TableCell>
                        <TableCell className="text-right">
                          <MetricValue value={p.mem_used_mib} format={formatMemory} />
                        </TableCell>
                        <TableCell className="text-right">
                          <MetricValue value={p.sm_util} format={(v) => formatPercent(v, 0)} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
          <div>
            <div className="mb-2 text-[12px] font-medium text-muted-foreground">Last {q.data.window_hours} hours</div>
            {!q.data.workloads.length ? (
              <p className="text-[13px] text-muted-foreground">No attributed time yet. It appears after the first rollup, within a few minutes.</p>
            ) : (
              <ul className="space-y-2.5">
                {q.data.workloads.map((w, i) => (
                  <li key={w.workload}>
                    <div className="mb-1 flex items-baseline justify-between gap-2 text-[12.5px]">
                      <span className="truncate font-medium">{w.label}</span>
                      <span className="shrink-0 text-muted-foreground tabular">
                        {formatHours(w.gpu_hours)} <span className="text-faint">{formatRatio(w.share, 0)}</span>
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted" aria-hidden>
                      <div className="h-full rounded-full" style={{ width: `${100 * w.share}%`, background: w.workload ? seriesColor(i) : CHART.idle }} />
                    </div>
                    {w.idle_hours > 0 && w.workload !== "" && <div className="mt-0.5 text-[11px] text-warning">{formatHours(w.idle_hours)} held idle</div>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Surface>
  );
}

function Specs({ gpu }: { gpu: Gpu }) {
  const live = gpu.live as LiveSample | null;
  return (
    <Surface>
      <SurfaceHeader title="This GPU" description={live ? `Last reading ${formatRelative(live.ts)}` : `Last seen ${formatRelative(gpu.last_seen_at)}`} />
      <dl className="divide-y divide-hairline px-5 pb-4">
        <MetricRow label="Utilization"><MetricValue value={live?.util_gpu} format={(v) => metric.pct(v)} /></MetricRow>
        <MetricRow label="Memory"><MetricValue value={live?.mem_used_mib} format={formatMemory} /> of {formatMemory(gpu.memory_total_mib)}</MetricRow>
        <MetricRow label="Temperature"><MetricValue value={live?.temp_c} format={(v) => metric.temp(v)} /></MetricRow>
        <MetricRow label="Power"><MetricValue value={live?.power_w} format={(v) => metric.watts(v)} /> of {metric.watts(gpu.power_limit_w)}</MetricRow>
        <MetricRow label="Fan"><MetricValue value={live?.fan_pct} format={(v) => metric.pct(v)} /></MetricRow>
        <MetricRow label="SM clock"><MetricValue value={live?.sm_clock_mhz} format={(v) => metric.mhz(v)} /></MetricRow>
        <MetricRow label="PCIe in / out">
          <MetricValue value={live?.pcie_rx_kbps} format={(v) => metric.kbps(v)} /> / <MetricValue value={live?.pcie_tx_kbps} format={(v) => metric.kbps(v)} />
        </MetricRow>
        <MetricRow label="Uncorrected ECC errors"><MetricValue value={live?.ecc_uncorrected} format={(v) => metric.count(v)} /></MetricRow>
        <MetricRow label="Throttling now">{throttleReasons(live?.throttle_reasons).join(", ") || (live?.throttle_reasons == null ? <MetricValue value={null} format={String} /> : "None")}</MetricRow>
        <MetricRow label="Rate">{formatRate(gpu.nusd_per_hour)}{gpu.rate_scope && <span className="ml-1 text-faint">({gpu.rate_scope})</span>}</MetricRow>
        <MetricRow label="UUID"><span className="font-mono text-[11.5px] break-all">{gpu.uuid}</span></MetricRow>
        {gpu.pci_bus_id && <MetricRow label="PCI bus"><span className="font-mono text-[11.5px]">{gpu.pci_bus_id}</span></MetricRow>}
        {gpu.mig_mode != null && <MetricRow label="MIG">{gpu.mig_mode ? "Enabled" : "Disabled"}</MetricRow>}
        <MetricRow label="First seen">{formatDateTime(gpu.first_seen_at)}</MetricRow>
      </dl>
    </Surface>
  );
}

export function GpuScreen({ id }: { id: string }) {
  const gpu = useGpu(id);
  const explain = useExplanation(id);
  const [range, setRange] = React.useState<Range>("24h");
  const retire = useRetireGpu();
  const { canWrite } = usePermissions();

  if (gpu.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-36 rounded-2xl" />
        <Skeleton className="h-72 rounded-2xl" />
      </div>
    );
  }
  if (gpu.isError) {
    return (
      <Surface>
        <ErrorState error={gpu.error} title="Could not load this GPU" onRetry={() => void gpu.refetch()} />
      </Surface>
    );
  }
  const g = gpu.data;
  const findings = explain.data?.findings ?? [];

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <Link href="/live" className="mb-2 inline-flex items-center gap-1 text-[12.5px] text-muted-foreground hover:text-foreground">
            <ArrowLeftIcon className="size-3.5" />
            Live
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[22px] leading-tight font-semibold tracking-[-0.02em] text-foreground">
              GPU {g.index} <span className="font-normal text-muted-foreground">on {g.host_name}</span>
            </h1>
            <GpuChip value={g.status} />
            {g.host_simulated && <SimBadge />}
          </div>
          <p className="mt-1 text-[13px] text-muted-foreground">
            {g.name}, {formatMemory(g.memory_total_mib)}, {formatRate(g.nusd_per_hour)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canWrite && (g.status === "lost" || g.status === "retired") && (
            <Button
              variant="secondary"
              size="sm"
              disabled={retire.isPending}
              onClick={() =>
                retire.mutate(
                  { id: g.id, retired: g.status !== "retired" },
                  {
                    onSuccess: () => toast.success(g.status === "retired" ? "GPU restored." : "GPU retired."),
                    onError: (err) => toast.error(errorMessage(err)),
                  },
                )
              }
            >
              {g.status === "retired" ? <RotateCcwIcon /> : <ArchiveIcon />}
              {g.status === "retired" ? "Restore" : "Retire"}
            </Button>
          )}
          <Segmented<Range>
            ariaLabel="Range"
            value={range}
            onChange={setRange}
            options={RANGES.map((r) => ({ value: r, label: RANGE_LABEL[r] }))}
            className="w-64"
          />
        </div>
      </div>
      <div className="space-y-4">
        <Explanation id={id} />
        <Charts id={id} range={range} />
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <Processes id={id} />
            <section aria-label="Findings for this GPU" className="space-y-3">
              <div className="flex items-center gap-2">
                <LightbulbIcon className="size-4 text-primary" />
                <h2 className="text-[14px] font-semibold">Findings</h2>
                {findings.length > 0 && <Chip tone="primary">{findings.length}</Chip>}
              </div>
              {findings.length ? (
                findings.map((f) => <InsightCard key={f.id} insight={f} />)
              ) : (
                <Surface>
                  <p className="px-5 py-6 text-[13px] text-muted-foreground">No open findings for this GPU. It is checked every few minutes.</p>
                </Surface>
              )}
            </section>
          </div>
          <Specs gpu={g} />
        </div>
      </div>
    </>
  );
}
