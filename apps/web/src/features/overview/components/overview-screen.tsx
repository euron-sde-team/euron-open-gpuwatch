"use client";

import {
  ActivityIcon,
  BellRingIcon,
  CoinsIcon,
  CpuIcon,
  LightbulbIcon,
  MoonIcon,
  PlusIcon,
  ServerIcon,
  TrendingDownIcon,
  type LucideIcon,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";

import { CHART, seriesColor } from "@/components/charts/chart-tooltip";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useFleetSeries } from "@/features/fleet/api";
import { InsightCard } from "@/features/insights/components/insight-card";
import type { GlossaryKey } from "@/lib/glossary";
import { cn } from "@/lib/cn";
import { formatHours, formatNusd, formatPercent, formatRatio, metric } from "@/lib/format";

import { useOverview } from "../api";

const TimeSeriesChart = dynamic(() => import("@/components/charts/time-series"), {
  ssr: false,
  loading: () => <Skeleton className="h-[330px] w-full" />,
});

function Stat({
  label,
  value,
  sub,
  icon: Icon,
  tone = "primary",
  hint,
  href,
}: {
  label: string;
  value: React.ReactNode;
  sub: React.ReactNode;
  icon: LucideIcon;
  tone?: "primary" | "savings" | "warning" | "danger";
  hint?: GlossaryKey;
  href?: string;
}) {
  const body = (
    <>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "flex size-7 items-center justify-center rounded-lg",
            { primary: "bg-primary-soft text-primary", savings: "bg-savings-soft text-savings", warning: "bg-warning-soft text-warning", danger: "bg-danger-soft text-danger" }[tone],
          )}
        >
          <Icon className="size-3.5" />
        </span>
        <span className="min-w-0 text-[12.5px] leading-tight font-medium sm:truncate text-muted-foreground">{label}</span>
        {hint && <Hint term={hint} />}
      </div>
      <div className="truncate text-[24px] leading-none font-semibold tracking-[-0.02em] text-foreground tabular">{value}</div>
      <div className="text-[11.5px] sm:truncate text-muted-foreground">{sub}</div>
    </>
  );
  const cls = "surface flex min-w-0 flex-col gap-3 p-4";
  return href ? (
    <Link href={href} className={cn(cls, "transition-shadow hover:shadow-[var(--elev-3)] focus-visible:outline-2 focus-visible:outline-ring")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function FleetChart() {
  const q = useFleetSeries("24h");
  if (q.isPending) return <Skeleton className="h-[330px] w-full" />;
  if (q.isError) return <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data.points.length) return <p className="py-16 text-center text-[13px] text-muted-foreground">No readings in the last 24 hours yet.</p>;
  const pct = (v: number) => formatPercent(v, 0);
  return (
    <TimeSeriesChart
      ariaLabel="Fleet utilization and memory over the last 24 hours"
      rows={q.data.points as unknown as Record<string, unknown>[]}
      height={330}
      leftFormat={pct}
      leftDomain={[0, 100]}
      rightFormat={(v) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10_000 ? 0 : 1)}kW` : `${Math.round(v)}W`)}
      series={[
        { key: "util_avg", label: "Average utilization", color: CHART.util, kind: "area", format: pct },
        { key: "mem_pct_avg", label: "Average memory used", color: CHART.mem, format: pct },
        { key: "power_w", label: "Total power", color: CHART.power, axis: "right", dashed: true, format: (v) => metric.watts(v) },
      ]}
    />
  );
}

export function OverviewScreen() {
  const q = useOverview();
  const o = q.data;
  const header = <PageHeader title="Overview" description="What your GPUs cost, how much of it bought nothing, and what to look at first." />;

  if (q.isError && !o) {
    return (
      <>
        {header}
        <Surface>
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </Surface>
      </>
    );
  }
  if (o && o.hosts_total === 0) {
    return (
      <>
        {header}
        <Surface>
          <EmptyState
            icon={ServerIcon}
            title="Add your first GPU host"
            description="Install the GPUWatch agent on a machine with NVIDIA GPUs. Within seconds you see every GPU live; within the hour, where the money goes and what is idle. Nothing leaves your network."
            action={
              <Button nativeButton={false} render={<Link href="/hosts?add=1" />}>
                <PlusIcon />
                Add a host
              </Button>
            }
          />
        </Surface>
      </>
    );
  }

  const idleShare = o && o.spend_7d_nusd ? o.idle_7d_nusd / o.spend_7d_nusd : null;
  return (
    <>
      {header}
      <div className="space-y-4">
        {o && !o.rates_set && (
          <div className="flex flex-col gap-3 rounded-2xl bg-primary-soft px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[13px] text-foreground">
              <span className="font-semibold">Costs need a rate.</span> GPUWatch ships no prices: set what your GPUs cost per hour to see spend, idle cost
              and savings.
            </p>
            <Button size="sm" nativeButton={false} render={<Link href="/costs?tab=rates" />}>
              <CoinsIcon />
              Set rates
            </Button>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {!o ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[118px] rounded-2xl" />)
          ) : (
            <>
              <Stat
                label="Spend, last 7 days"
                icon={CoinsIcon}
                value={formatNusd(o.spend_7d_nusd)}
                sub={`${formatNusd(o.spend_month_nusd)} this month${o.unpriced_gpu_hours_7d ? `, ${formatHours(o.unpriced_gpu_hours_7d)} unpriced` : ""}`}
                href="/costs"
              />
              <Stat
                label="Paid for idle time"
                icon={MoonIcon}
                tone="warning"
                hint="idleCost"
                value={formatNusd(o.idle_7d_nusd)}
                sub={idleShare != null ? `${formatRatio(idleShare, 0)} of 7-day spend` : "Set rates to see it"}
                href="/costs"
              />
              <Stat
                label="Waste found, per month"
                icon={TrendingDownIcon}
                tone="warning"
                hint="waste"
                value={formatNusd(o.est_monthly_waste_nusd)}
                sub={`${o.insights_open} open finding${o.insights_open === 1 ? "" : "s"}`}
                href="/insights"
              />
              <Stat
                label="GPUs reporting"
                icon={CpuIcon}
                tone={o.gpus_lost || o.hosts_online < o.hosts_total ? "danger" : "savings"}
                value={`${o.gpus_reporting} of ${o.gpus_total}`}
                sub={
                  o.gpus_lost
                    ? `${o.gpus_lost} lost, ${o.hosts_online} of ${o.hosts_total} hosts online`
                    : `${o.hosts_online} of ${o.hosts_total} hosts online${o.util_now_avg != null ? `, ${formatPercent(o.util_now_avg, 0)} busy now` : ""}`
                }
                href="/live"
              />
            </>
          )}
        </div>
        {o && o.alerts_firing > 0 && (
          <Link
            href="/alerts"
            className="flex items-center gap-3 rounded-2xl bg-danger-soft px-4 py-3 text-[13px] text-foreground transition-[filter] hover:brightness-95 focus-visible:outline-2 focus-visible:outline-ring dark:hover:brightness-125"
          >
            <BellRingIcon className="size-4 text-danger" />
            <span>
              <span className="font-semibold">{o.alerts_firing} alert{o.alerts_firing === 1 ? "" : "s"} firing.</span> Open Alerts to see what and where.
            </span>
          </Link>
        )}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Surface className="flex flex-col">
            <SurfaceHeader
              title="Fleet, last 24 hours"
              description="Average utilization and memory across reporting GPUs, and their total power"
              action={
                <Button variant="subtle" size="xs" nativeButton={false} render={<Link href="/live" />}>
                  <ActivityIcon />
                  Live
                </Button>
              }
            />
            <div className="px-5 pb-5">
              <FleetChart />
            </div>
          </Surface>
          <Surface>
            <SurfaceHeader
              title="Who used the GPUs"
              titleExtra={<Hint term="attribution" />}
              description="Cost by workload, last 7 days"
              action={
                <Button variant="subtle" size="xs" nativeButton={false} render={<Link href="/costs" />}>
                  Costs
                </Button>
              }
            />
            {!o ? (
              <Skeleton className="mx-5 mb-5 h-48" />
            ) : !o.top_workloads.length ? (
              <p className="px-5 pb-5 text-[13px] text-muted-foreground">
                {o.rates_set ? "No priced GPU time in the last 7 days yet." : "Workload costs appear once a rate is set."}
              </p>
            ) : (
              <ul className="space-y-3 px-5 pb-5">
                {o.top_workloads.map((w, i) => (
                  <li key={w.key}>
                    <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
                      <span className="truncate font-medium">{w.label}</span>
                      <span className="shrink-0 font-semibold tabular">{formatNusd(w.nusd)}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted" aria-hidden>
                      <div className="h-full rounded-full" style={{ width: `${100 * w.share}%`, background: w.key === "__idle__" ? CHART.idle : seriesColor(i) }} />
                    </div>
                    <div className="mt-1 text-[11.5px] text-muted-foreground">
                      {formatHours(w.gpu_hours)} GPU time{w.idle_nusd > 0 && w.key !== "__idle__" ? `, ${formatNusd(w.idle_nusd)} held idle` : ""}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Surface>
        </div>
        <section aria-label="Top findings" className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-[14px] font-semibold">
              <LightbulbIcon className="size-4 text-primary" />
              What to look at first
            </h2>
            <Button variant="subtle" size="xs" nativeButton={false} render={<Link href="/insights" />}>
              All insights
            </Button>
          </div>
          {!o ? (
            <div className="grid gap-3 lg:grid-cols-2">
              <Skeleton className="h-40 rounded-2xl" />
              <Skeleton className="h-40 rounded-2xl" />
            </div>
          ) : !o.top_insights.length ? (
            <Surface>
              <p className="px-5 py-6 text-[13px] text-muted-foreground">No open findings. GPUWatch keeps checking every GPU for idle spend, throttling and memory pressure.</p>
            </Surface>
          ) : (
            <div className="grid items-start gap-3 lg:grid-cols-2">
              {o.top_insights.slice(0, 4).map((i) => (
                <InsightCard key={i.id} insight={i} />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
