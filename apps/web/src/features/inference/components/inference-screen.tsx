"use client";

import { CpuIcon, ServerIcon, SparklesIcon, XIcon } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import type { InferenceEndpoint } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import type { Range } from "@/lib/range";

import { useInferenceEndpoints, useInferenceSeries } from "../api";

import { endpointKindLabel } from "./inference-format";
import { StatGrid } from "./inference-stats";

const InferenceCharts = dynamic(() => import("./inference-charts"), {
  ssr: false,
  loading: () => (
    <div className="grid gap-4 lg:grid-cols-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-[260px] w-full rounded-xl" />
      ))}
    </div>
  ),
});

const DETAIL_RANGES: { value: Range; label: string }[] = [
  { value: "1h", label: "1h" },
  { value: "6h", label: "6h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
];

const EXAMPLE = "GPUWATCH_INFERENCE=llama-chat=vllm,http://localhost:8000/metrics,0";

function EndpointCard({ ep, selected, onSelect }: { ep: InferenceEndpoint; selected: boolean; onSelect: () => void }) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        "surface flex min-w-0 cursor-pointer flex-col gap-4 p-4 transition-shadow hover:shadow-[var(--elev-3)]",
        selected && "bg-primary-soft/40 ring-2 ring-primary/50 dark:bg-primary-soft/10",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              aria-pressed={selected}
              aria-label={`${ep.name}: ${selected ? "hide details" : "show details"}`}
              onClick={(e) => {
                e.stopPropagation();
                onSelect();
              }}
              className="truncate rounded-sm text-left text-[15px] font-semibold tracking-[-0.01em] text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              {ep.name}
            </button>
            <Chip tone="primary">{endpointKindLabel(ep.kind)}</Chip>
          </div>
          <div className="mt-0.5 truncate font-mono text-[12px] text-muted-foreground" title={ep.model ?? undefined}>
            {ep.model ?? "Model not reported"}
          </div>
        </div>
        <Chip tone={ep.up ? "success" : "danger"} dot title={ep.last_seen_at ? `Last scraped ${formatRelative(ep.last_seen_at)}` : "Never scraped"}>
          {ep.up ? "Up" : "Down"}
        </Chip>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <ServerIcon className="size-3.5" />
          {ep.host_name}
        </span>
        <span className="inline-flex min-w-0 items-center gap-1">
          <CpuIcon className="size-3.5 shrink-0" />
          <span className="truncate">{ep.gpu_labels.length ? ep.gpu_labels.join(", ") : "No GPU bound"}</span>
        </span>
      </div>
      <div className="rounded-xl bg-muted/50 p-3">
        <div className="mb-2 text-[11px] font-semibold tracking-[0.04em] text-subtle uppercase">Last 24h</div>
        <StatGrid stats={ep.stats_24h} dense />
      </div>
    </div>
  );
}

function CardsSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy aria-label="Loading">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="surface space-y-4 p-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3.5 w-56" />
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 8 }).map((__, j) => (
              <Skeleton key={j} className="h-8" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EndpointDetail({ ep, onClose }: { ep: InferenceEndpoint; onClose: () => void }) {
  const [range, setRange] = React.useState<Range>("24h");
  const q = useInferenceSeries(ep.id, range);
  return (
    <Surface id="endpoint-detail" aria-label={`${ep.name} details`} className="mt-6 scroll-mt-20">
      <SurfaceHeader
        title={ep.name}
        titleExtra={<Chip tone="primary">{endpointKindLabel(ep.kind)}</Chip>}
        description={`${ep.model ?? "Model not reported"} on ${ep.host_name}`}
        action={
          <>
            <Segmented ariaLabel="Time range" value={range} onChange={setRange} options={DETAIL_RANGES} className="w-48" />
            <Button variant="subtle" size="icon-sm" aria-label="Close details" onClick={onClose}>
              <XIcon />
            </Button>
          </>
        }
      />
      <div className="space-y-5 px-5 pb-5">
        {q.isPending ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[260px] w-full rounded-xl" />
              ))}
            </div>
          </>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
        ) : q.data ? (
          <>
            <StatGrid stats={q.data.summary} />
            {q.data.points.length ? (
              <InferenceCharts points={q.data.points} range={range} />
            ) : (
              <EmptyState
                compact
                icon={SparklesIcon}
                title="No samples in this window"
                description="The agent has not reported this endpoint in the selected range. Pick a longer range, or check that the server's /metrics is reachable from the agent."
                action={
                  range !== "7d" ? (
                    <Button size="sm" variant="secondary" onClick={() => setRange("7d")}>
                      Show 7 days
                    </Button>
                  ) : undefined
                }
              />
            )}
          </>
        ) : null}
      </div>
    </Surface>
  );
}

export function InferenceScreen() {
  const q = useInferenceEndpoints();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selectedId = params.get("endpoint");
  const selected = q.data?.find((e) => e.id === selectedId) ?? null;

  const select = React.useCallback(
    (id: string | null) => {
      const sp = new URLSearchParams(params.toString());
      if (id) sp.set("endpoint", id);
      else sp.delete("endpoint");
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  React.useEffect(() => {
    if (selected) document.getElementById("endpoint-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selected]);

  return (
    <>
      <PageHeader
        title="Inference"
        description="Serving metrics from vLLM and TGI next to the GPUs they run on, with cost per million tokens."
      />
      {q.isPending ? (
        <CardsSkeleton />
      ) : q.isError && !q.data ? (
        <Surface>
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </Surface>
      ) : !q.data?.length ? (
        <Surface>
          <EmptyState
            icon={SparklesIcon}
            title="No inference endpoints yet"
            description={
              <>
                The agent scrapes a vLLM or TGI server&apos;s /metrics when started with GPUWATCH_INFERENCE (name=kind,url,gpu indexes), for example{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12px] break-all text-foreground">{EXAMPLE}</code>. Throughput, latency and
                cost per token then appear here next to the GPUs serving them.
              </>
            }
            action={
              <Button size="sm" nativeButton={false} render={<Link href="/hosts" />}>
                <ServerIcon />
                Add a host
              </Button>
            }
          />
        </Surface>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {q.data.map((ep) => (
              <EndpointCard key={ep.id} ep={ep} selected={ep.id === selected?.id} onSelect={() => select(ep.id === selected?.id ? null : ep.id)} />
            ))}
          </div>
          {selected ? (
            <EndpointDetail key={selected.id} ep={selected} onClose={() => select(null)} />
          ) : (
            <p className="mt-4 text-[12.5px] text-muted-foreground">Select an endpoint to chart its throughput, latency, queue and KV cache over time.</p>
          )}
        </>
      )}
    </>
  );
}
