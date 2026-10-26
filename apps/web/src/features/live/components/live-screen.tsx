"use client";

import { ActivityIcon, PlusIcon, SearchIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { SimBadge } from "@/components/status-chip";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Gpu, LiveSample } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatPercent } from "@/lib/format";

import { useLiveGpus, type StreamState } from "../api";
import { GpuTile } from "./gpu-tile";

type Filter = "all" | "busy" | "idle" | "problem";

function busy(g: Gpu): boolean {
  const live = g.live as LiveSample | null;
  return g.status === "ok" && (live?.util_gpu ?? 0) >= 5;
}

export function StreamBadge({ state }: { state: StreamState }) {
  const label = state === "live" ? "Live" : state === "polling" ? "Refreshing every 5 s" : "Connecting";
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-[12px] font-medium text-muted-foreground" data-qa="stream-state">
      <span className="relative flex size-2">
        {state === "live" && <span className="absolute inline-flex size-full animate-ping rounded-full bg-savings opacity-40" />}
        <span className={cn("relative inline-flex size-2 rounded-full", state === "live" ? "bg-savings" : state === "polling" ? "bg-warning" : "bg-faint")} />
      </span>
      {label}
    </span>
  );
}

export function LiveScreen() {
  const { query, stream } = useLiveGpus();
  const [filter, setFilter] = React.useState<Filter>("all");
  const [search, setSearch] = React.useState("");
  const gpus = query.data ?? [];

  const visible = gpus.filter((g) => {
    if (filter === "busy" && !busy(g)) return false;
    if (filter === "idle" && (busy(g) || g.status !== "ok")) return false;
    if (filter === "problem" && g.status === "ok") return false;
    const q = search.trim().toLowerCase();
    return !q || `${g.host_name} ${g.name} gpu ${g.index}`.toLowerCase().includes(q);
  });
  const byHost = new Map<string, Gpu[]>();
  for (const g of visible) byHost.set(g.host_id, [...(byHost.get(g.host_id) ?? []), g]);

  const reporting = gpus.filter((g) => g.status === "ok");
  const avg = reporting.length
    ? reporting.reduce((a, g) => a + ((g.live as LiveSample | null)?.util_gpu ?? 0), 0) / reporting.length
    : null;

  const header = (
    <PageHeader
      title="Live"
      description="Every GPU right now. Tiles update as soon as an agent reports, every few seconds."
      actions={<StreamBadge state={stream} />}
    />
  );

  if (query.isPending) {
    return (
      <>
        {header}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-2xl" />
          ))}
        </div>
      </>
    );
  }
  if (query.isError && !query.data) {
    return (
      <>
        {header}
        <Surface>
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        </Surface>
      </>
    );
  }
  if (!gpus.length) {
    return (
      <>
        {header}
        <Surface>
          <EmptyState
            icon={ActivityIcon}
            title="No GPUs reporting yet"
            description="Install the agent on a machine with NVIDIA GPUs. It finds every GPU through the driver and its readings appear here within seconds."
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

  return (
    <>
      {header}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-[13px] text-muted-foreground">
          <span className="font-semibold text-foreground tabular">{reporting.length}</span> of {gpus.length} GPUs reporting
          {avg != null && (
            <>
              , average utilization <span className="font-semibold text-foreground tabular">{formatPercent(avg, 0)}</span>
            </>
          )}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-faint" />
            <Input aria-label="Search GPUs" placeholder="Host or model" className="pl-8 sm:w-52" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Segmented<Filter>
            ariaLabel="Filter GPUs"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "busy", label: "Busy" },
              { value: "idle", label: "Idle" },
              { value: "problem", label: "Problems" },
            ]}
          />
        </div>
      </div>
      {byHost.size === 0 ? (
        <Surface>
          <EmptyState
            compact
            icon={SearchIcon}
            title="No GPUs match"
            description="Nothing matches this filter right now. Clear it to see every GPU."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setFilter("all");
                  setSearch("");
                }}
              >
                Clear filters
              </Button>
            }
          />
        </Surface>
      ) : (
        <div className="space-y-6">
          {[...byHost.values()].map((list) => (
            <section key={list[0]?.host_id} aria-label={list[0]?.host_name}>
              <div className="mb-2.5 flex items-center gap-2">
                <h2 className="text-[13px] font-semibold text-foreground">{list[0]?.host_name}</h2>
                {list[0]?.host_simulated && <SimBadge />}
                <span className="text-[12px] text-muted-foreground">{list.length} GPU{list.length === 1 ? "" : "s"}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {list.map((g) => (
                  <GpuTile key={g.id} gpu={g} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
