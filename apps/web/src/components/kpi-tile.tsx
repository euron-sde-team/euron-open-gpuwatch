"use client";

import { ArrowDownRightIcon, ArrowUpRightIcon, MinusIcon, type LucideIcon } from "lucide-react";
import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { computeDelta, formatDelta } from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";

import { Hint } from "./hint";

/**
 * Headline number with its change versus the previous period. `goodWhen` says which
 * direction is good news, so a rise in utilization reads green and a rise in idle
 * cost reads amber.
 */
export function KpiTile({
  label,
  value,
  current,
  previous,
  goodWhen = "up",
  icon: Icon,
  hint,
  comparison,
  accent,
  loading = false,
}: {
  label: string;
  value: React.ReactNode;
  current?: number;
  previous?: number;
  goodWhen?: "up" | "down" | "neutral";
  icon: LucideIcon;
  hint?: GlossaryKey;
  comparison: string;
  accent?: "primary" | "savings" | "warning";
  loading?: boolean;
}) {
  const delta = computeDelta(current, previous);
  const good =
    !delta || delta.direction === "flat" || goodWhen === "neutral"
      ? "neutral"
      : (delta.direction === "up") === (goodWhen === "up")
        ? "good"
        : "bad";
  const DeltaIcon = !delta || delta.direction === "flat" ? MinusIcon : delta.direction === "up" ? ArrowUpRightIcon : ArrowDownRightIcon;
  const iconTone = {
    primary: "bg-primary-soft text-primary",
    savings: "bg-savings-soft text-savings",
    warning: "bg-warning-soft text-warning",
  }[accent ?? "primary"];

  return (
    <div className="surface flex min-w-0 flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <span className={cn("flex size-7 items-center justify-center rounded-lg", iconTone)}>
          <Icon className="size-3.5" />
        </span>
        <span className="min-w-0 text-[12.5px] leading-tight font-medium text-muted-foreground sm:truncate">{label}</span>
        {hint && <Hint term={hint} />}
      </div>
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-7 w-24" />
          <Skeleton className="h-3.5 w-32" />
        </div>
      ) : (
        <div>
          <div className="truncate text-[24px] leading-none font-semibold tracking-[-0.02em] text-foreground tabular">{value}</div>
          <div className="mt-2 flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
            {delta ? (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 rounded-full px-1.5 py-px font-semibold tabular",
                  good === "good" && "bg-savings-soft text-savings",
                  good === "bad" && "bg-warning-soft text-warning",
                  good === "neutral" && "bg-neutral-soft text-muted-foreground",
                )}
              >
                <DeltaIcon className="size-3" />
                {formatDelta(delta)}
              </span>
            ) : (
              <span className="rounded-full bg-neutral-soft px-1.5 py-px font-medium">New</span>
            )}
            <span className="hidden truncate sm:inline">{comparison}</span>
          </div>
        </div>
      )}
    </div>
  );
}
