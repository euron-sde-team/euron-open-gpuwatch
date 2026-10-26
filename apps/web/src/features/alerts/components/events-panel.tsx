"use client";

import { BellRingIcon, CheckCircle2Icon, PlusIcon } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { SeverityChip } from "@/components/status-chip";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AlertEvent } from "@/lib/api/types";
import { severityChip } from "@/lib/chips";
import { cn } from "@/lib/cn";

import { useAlertEvents, useChannels } from "../api";

import { formatDuration, secondsBetween, SEVERITY_ORDER, TimeAgo, useNow } from "./alert-utils";

function Target({ e }: { e: AlertEvent }) {
  if (e.gpu_id) {
    return (
      <Link
        href={`/gpus/${e.gpu_id}`}
        className="rounded-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
      >
        {e.gpu_label ?? "GPU"}
      </Link>
    );
  }
  if (e.host_name) return <span>{e.host_name}</span>;
  return <span className="text-faint">Fleet</span>;
}

function FiringSummary({ events, loading }: { events: AlertEvent[]; loading: boolean }) {
  const firing = events.filter((e) => !e.resolved_at);
  return (
    <Surface className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4">
      {loading ? (
        <Skeleton className="h-5 w-56" />
      ) : firing.length ? (
        <>
          <div className="flex items-center gap-2 text-[14px] font-semibold text-foreground">
            <span className="flex size-7 items-center justify-center rounded-lg bg-danger-soft text-danger">
              <BellRingIcon className="size-3.5" />
            </span>
            <span>
              <span className="tabular">{firing.length}</span> firing now
            </span>
          </div>
          <ul className="flex flex-wrap items-center gap-2" aria-label="Firing by severity">
            {SEVERITY_ORDER.map((s) => {
              const n = firing.filter((e) => e.severity === s).length;
              if (!n) return null;
              const spec = severityChip(s);
              return (
                <li key={s}>
                  <Chip tone={spec.tone} dot>
                    <span className="tabular">{n}</span> {spec.label.toLowerCase()}
                  </Chip>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <div className="flex items-center gap-2 text-[14px] font-semibold text-foreground">
          <span className="flex size-7 items-center justify-center rounded-lg bg-savings-soft text-savings">
            <CheckCircle2Icon className="size-3.5" />
          </span>
          Nothing is firing
          <span className="text-[12.5px] font-normal text-muted-foreground">Every rule is quiet across the fleet.</span>
        </div>
      )}
    </Surface>
  );
}

export function EventsPanel({ onAddChannel, onOpenRules }: { onAddChannel: () => void; onOpenRules: () => void }) {
  const q = useAlertEvents(false);
  const channels = useChannels();
  const channelCount = channels.data?.length ?? 0;
  const now = useNow();
  const events = q.data ?? [];

  return (
    <>
      <FiringSummary events={events} loading={q.isPending} />
      <Surface className="overflow-hidden">
        <SurfaceHeader title="Alert events" description="Firing first, then the most recent resolved ones" />
        {q.isPending ? (
          <TableSkeleton rows={5} cols={5} />
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !events.length ? (
          <EmptyState
            icon={BellRingIcon}
            title="No alerts have fired"
            description={
              channelCount
                ? `Your rules watch every host and GPU. The next alert reaches your ${channelCount === 1 ? "channel" : `${channelCount} channels`} by email or webhook.`
                : "The built-in rules (agent offline, GPU lost, too hot, memory almost full) already watch every host and GPU. Add a channel so the next alert reaches you by email or webhook."
            }
            action={
              channelCount ? (
                <Button size="sm" variant="secondary" onClick={onOpenRules}>
                  Review rules
                </Button>
              ) : (
                <Button size="sm" onClick={onAddChannel}>
                  <PlusIcon />
                  Add a channel
                </Button>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alert</TableHead>
                <TableHead className="hidden md:table-cell">Target</TableHead>
                <TableHead className="hidden sm:table-cell">Started</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead className="hidden lg:table-cell text-right">Notifications</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => {
                const firing = !e.resolved_at;
                return (
                  <TableRow key={e.id} className={cn(!firing && "text-muted-foreground")}>
                    <TableCell className="min-w-56 max-w-[28rem]">
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityChip value={e.severity} />
                        <span className={cn("font-medium", firing ? "text-foreground" : "text-muted-foreground")}>{e.rule_name}</span>
                      </div>
                      <p className="mt-1 text-[12.5px] leading-snug text-muted-foreground">{e.message}</p>
                      <div className="mt-1 text-[12px] md:hidden">
                        <Target e={e} />
                      </div>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <Target e={e} />
                    </TableCell>
                    <TableCell className="hidden whitespace-nowrap sm:table-cell">
                      <TimeAgo iso={e.started_at} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {firing ? (
                        <Chip tone="danger" dot>
                          Firing for {formatDuration(secondsBetween(e.started_at, now))}
                        </Chip>
                      ) : (
                        <span className="tabular">{formatDuration(secondsBetween(e.started_at, e.resolved_at ?? now))}</span>
                      )}
                    </TableCell>
                    <TableCell className="hidden text-right whitespace-nowrap lg:table-cell">
                      <span className="inline-flex items-center gap-2">
                        <span className="tabular">{e.notifications}</span>
                        {e.notifications_failed > 0 && (
                          <Chip tone="warning">
                            <span className="tabular">{e.notifications_failed}</span> failed
                          </Chip>
                        )}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Surface>
    </>
  );
}
