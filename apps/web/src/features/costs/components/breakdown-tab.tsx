"use client";

import { BarChart3Icon, ClockIcon, CoinsIcon, MoonIcon, PauseCircleIcon, TriangleAlertIcon } from "lucide-react";
import dynamic from "next/dynamic";
import * as React from "react";

import { ChartLegend } from "@/components/charts/chart-tooltip";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CostSummary, GroupBy } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatNusd } from "@/lib/format";

import { useCosts, useCostSeries, useRates } from "../api";
import { colorMap, formatGpuHours, groupLabel, IDLE_KEY, ShareBar, StatTile, type CostRange } from "./costs-shared";

const CostChart = dynamic(() => import("./cost-chart"), {
  ssr: false,
  loading: () => <Skeleton className="h-[280px] w-full" />,
});

function share(part: number, total: number): string {
  if (!total) return "0% of total";
  const pct = (100 * part) / total;
  return `${pct > 0 && pct < 0.1 ? "<0.1" : pct.toFixed(1).replace(/\.0$/, "")}% of total`;
}

function Kpis({ data }: { data: CostSummary }) {
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4">
      <StatTile label="Total cost" icon={CoinsIcon} hint="rate" value={formatNusd(data.total_nusd)} sub="Estimate from your rates, selected period" />
      <StatTile
        label="Idle with nothing running"
        icon={MoonIcon}
        hint="idleCost"
        accent="warning"
        value={formatNusd(data.idle_nusd)}
        sub={share(data.idle_nusd, data.total_nusd)}
      />
      <StatTile
        label="Held idle by workloads"
        icon={PauseCircleIcon}
        hint="heldIdle"
        accent="warning"
        value={formatNusd(data.held_idle_nusd)}
        sub={share(data.held_idle_nusd, data.total_nusd)}
      />
      <StatTile
        label="GPU hours"
        icon={ClockIcon}
        accent="neutral"
        value={formatGpuHours(data.gpu_hours)}
        sub={data.unpriced_gpu_hours > 0 ? `Plus ${formatGpuHours(data.unpriced_gpu_hours)} h without a rate` : "All monitored hours are priced"}
      />
    </div>
  );
}

function KpiSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4" aria-busy aria-label="Loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="surface space-y-3 p-4">
          <Skeleton className="h-7 w-32" />
          <Skeleton className="h-7 w-24" />
          <Skeleton className="h-3.5 w-36" />
        </div>
      ))}
    </div>
  );
}

function SeriesPanel({ groupBy, range }: { groupBy: GroupBy; range: CostRange }) {
  const q = useCostSeries(groupBy, range);
  const colors = React.useMemo(() => colorMap(q.data?.keys ?? []), [q.data?.keys]);
  return (
    <Surface>
      <SurfaceHeader
        title="Cost over time"
        description={`Estimated spend per ${q.data?.interval === "day" ? "day" : "hour"}, stacked by ${groupLabel(groupBy).toLowerCase()}. The six largest are shown; the rest add up as Other.`}
      />
      <div className="px-3 pb-4 sm:px-5">
        {q.isPending ? (
          <Skeleton className="h-[280px] w-full" />
        ) : q.isError && !q.data ? (
          <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />
        ) : !q.data.keys.length ? (
          <EmptyState
            compact
            icon={BarChart3Icon}
            title="No priced GPU time in this period"
            description="Bars appear here as soon as a GPU with a rate reports samples. Try a longer range if the fleet was quiet."
          />
        ) : (
          <>
            <CostChart series={q.data} colors={colors} />
            <div className="mt-3 px-2 sm:px-0">
              <ChartLegend items={q.data.keys.map((k) => ({ label: q.data.labels[k] ?? k, color: colors.get(k) ?? "var(--chart-idle)" }))} />
            </div>
          </>
        )}
      </div>
    </Surface>
  );
}

function BreakdownTable({ data, groupBy, colors }: { data: CostSummary; groupBy: GroupBy; colors: Map<string, string> }) {
  if (!data.rows.length) {
    return (
      <EmptyState
        compact
        icon={BarChart3Icon}
        title="Nothing to break down yet"
        description={`Each ${groupLabel(groupBy).toLowerCase()} gets a row once priced GPU time is recorded in this period. Pick a longer range, or check that agents are reporting.`}
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{groupLabel(groupBy)}</TableHead>
          <TableHead className="text-right">Cost</TableHead>
          <TableHead className="hidden md:table-cell">
            <span className="inline-flex items-center gap-1">
              Idle share <Hint term="heldIdle" />
            </span>
          </TableHead>
          <TableHead className="hidden text-right sm:table-cell">GPU hours</TableHead>
          <TableHead>
            <span className="sm:hidden">Share</span>
            <span className="hidden sm:inline">Share of total</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.rows.map((r) => {
          const idle = r.key === IDLE_KEY;
          return (
            <TableRow key={r.key}>
              <TableCell className="max-w-[14rem]">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="size-2 shrink-0 rounded-[3px] bg-faint"
                    style={{ background: idle ? "var(--chart-idle)" : (colors.get(r.key) ?? colors.get("__other__")) }}
                  />
                  <span className={cn("truncate font-medium", idle && "text-muted-foreground")}>{r.label}</span>
                </div>
              </TableCell>
              <TableCell className="text-right font-medium tabular">{formatNusd(r.nusd)}</TableCell>
              <TableCell className="hidden md:table-cell">
                <ShareBar value={r.nusd ? r.idle_nusd / r.nusd : 0} color="var(--chart-idle)" label={`Idle share of ${r.label}`} />
              </TableCell>
              <TableCell className="hidden text-right text-muted-foreground tabular sm:table-cell">{formatGpuHours(r.gpu_hours)}</TableCell>
              <TableCell>
                <ShareBar value={r.share} color={idle ? "var(--chart-idle)" : undefined} label={`${r.label} share of total cost`} />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function BreakdownTab({ groupBy, range, onSetRate }: { groupBy: GroupBy; range: CostRange; onSetRate: () => void }) {
  const q = useCosts(groupBy, range);
  const rates = useRates();
  const series = useCostSeries(groupBy, range);
  const colors = React.useMemo(() => colorMap(series.data?.keys ?? []), [series.data?.keys]);

  if (q.isPending || rates.isPending) {
    return (
      <div className="space-y-5">
        <KpiSkeleton />
        <Surface className="p-5">
          <Skeleton className="h-[280px] w-full" />
        </Surface>
        <Surface className="overflow-hidden pt-3">
          <TableSkeleton rows={5} cols={5} />
        </Surface>
      </div>
    );
  }
  if (q.isError && !q.data) {
    return (
      <Surface>
        <ErrorState error={q.error} title="Could not load costs" onRetry={() => void q.refetch()} />
      </Surface>
    );
  }
  const data = q.data;

  if (rates.data && rates.data.length === 0 && data.total_nusd === 0) {
    return (
      <Surface>
        <EmptyState
          icon={CoinsIcon}
          title="Costs appear once a GPU has an hourly rate"
          description="GPUWatch ships no prices, because what an hour costs depends on your cloud contract or hardware. Set a rate for a GPU model, a host or a single GPU, and every monitored hour is priced from then on."
          action={
            <Button size="sm" onClick={onSetRate}>
              <CoinsIcon />
              Set a rate
            </Button>
          }
        />
      </Surface>
    );
  }

  return (
    <div className="space-y-5">
      <Kpis data={data} />
      {data.unpriced_gpu_hours > 0 && (
        <div className="flex flex-col gap-3 rounded-xl bg-warning-soft px-4 py-3 text-[13px] sm:flex-row sm:items-center sm:justify-between">
          <p className="flex gap-3 text-foreground">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-warning" />
            <span>
              <strong className="tabular">{formatGpuHours(data.unpriced_gpu_hours)}</strong> GPU hours have no rate, so they are not in these totals.
            </span>
          </p>
          <Button size="xs" variant="secondary" className="self-start sm:self-auto" onClick={onSetRate}>
            Set a rate
          </Button>
        </div>
      )}
      <SeriesPanel groupBy={groupBy} range={range} />
      <Surface className="overflow-hidden">
        <SurfaceHeader
          title={`By ${groupLabel(groupBy).toLowerCase()}`}
          titleExtra={groupBy === "workload" || groupBy === "team" ? <Hint term="attribution" /> : undefined}
          description="Largest first. Idle share is the part of a row's cost spent while the GPU was held but not working."
        />
        <BreakdownTable data={data} groupBy={groupBy} colors={colors} />
      </Surface>
    </div>
  );
}
