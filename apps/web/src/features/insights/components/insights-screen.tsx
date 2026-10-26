"use client";

import { CoinsIcon, LightbulbIcon, RefreshCwIcon, SlidersHorizontalIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { InsightStatus } from "@/lib/api/types";
import { formatNusd } from "@/lib/format";

import { useEvaluateInsights, useInsights } from "../api";
import { InsightCard } from "./insight-card";

const TABS: { value: InsightStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "dismissed", label: "Dismissed" },
  { value: "resolved", label: "Resolved" },
];

const EMPTY: Record<InsightStatus, { title: string; description: string }> = {
  open: {
    title: "Nothing needs attention",
    description:
      "GPUWatch checks every GPU every few minutes for idle spend, oversized cards, throttling, memory pressure, hardware errors and inference queueing. New findings appear here with their evidence and a monthly cost estimate.",
  },
  acknowledged: { title: "Nothing acknowledged", description: "Acknowledge a finding to mark it as being handled. It keeps being re-checked and resolves by itself." },
  dismissed: { title: "Nothing dismissed", description: "Dismissed findings stay hidden until the condition clears and comes back." },
  resolved: { title: "Nothing resolved yet", description: "Findings whose condition cleared show up here, so you can see what changed." },
};

export function InsightsScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("status");
  const status: InsightStatus = TABS.some((t) => t.value === raw) ? (raw as InsightStatus) : "open";
  const q = useInsights(status);
  const evaluate = useEvaluateInsights();
  const { canWrite } = usePermissions();
  const items = q.data ?? [];
  const monthly = items.reduce((a, i) => a + (i.est_monthly_nusd ?? 0), 0);

  return (
    <>
      <PageHeader
        title="Insights"
        description="Why your GPUs are expensive or slow, ranked by what they cost. Every finding shows its evidence and what to do; GPUWatch never changes anything itself."
        actions={
          <>
            <Button variant="secondary" size="sm" nativeButton={false} render={<Link href="/settings#insight-rules" />}>
              <SlidersHorizontalIcon />
              Rules
            </Button>
            {canWrite && (
              <Button
                variant="secondary"
                size="sm"
                disabled={evaluate.isPending}
                onClick={() =>
                  evaluate.mutate(undefined, {
                    onSuccess: (r) => toast.success(`Checked every GPU: ${r.message}.`),
                    onError: (err) => toast.error(errorMessage(err)),
                  })
                }
              >
                <RefreshCwIcon className={evaluate.isPending ? "animate-spin" : undefined} />
                Check now
              </Button>
            )}
          </>
        }
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Segmented<InsightStatus>
          ariaLabel="Status"
          value={status}
          onChange={(v) => router.replace(v === "open" ? pathname : `${pathname}?status=${v}`, { scroll: false })}
          options={TABS}
          className="sm:w-[480px]"
        />
        {status === "open" && monthly > 0 && (
          <div className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
            <CoinsIcon className="size-3.5 text-warning" />
            Open findings cost about <span className="font-semibold text-foreground tabular">{formatNusd(monthly)}</span> a month
            <Hint term="waste" />
          </div>
        )}
      </div>
      {q.isPending ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-2xl" />
          ))}
        </div>
      ) : q.isError ? (
        <Surface>
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </Surface>
      ) : !items.length ? (
        <Surface>
          <EmptyState
            icon={LightbulbIcon}
            title={EMPTY[status].title}
            description={EMPTY[status].description}
            action={
              <Button variant="secondary" size="sm" nativeButton={false} render={<Link href="/live" />}>
                See the GPUs
              </Button>
            }
          />
        </Surface>
      ) : (
        <div className="grid items-start gap-3 lg:grid-cols-2">
          {items.map((i) => (
            <InsightCard key={i.id} insight={i} />
          ))}
        </div>
      )}
    </>
  );
}
