"use client";

import { InboxIcon, PlusIcon, SendIcon } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Notification } from "@/lib/api/types";
import { formatTime } from "@/lib/format";

import { useChannels, useNotifications } from "../api";

import { TimeAgo } from "./alert-utils";

const TRANSITION: Record<string, { label: string; tone: "danger" | "success" | "info" | "neutral" }> = {
  fired: { label: "Fired", tone: "danger" },
  resolved: { label: "Resolved", tone: "success" },
  test: { label: "Test", tone: "info" },
};

function Status({ n }: { n: Notification }) {
  if (n.delivered_at) {
    return (
      <Chip tone="success" dot>
        Delivered
      </Chip>
    );
  }
  if (n.failed_at) {
    return (
      <Chip tone="danger" dot>
        Failed
      </Chip>
    );
  }
  if (n.attempts === 0) {
    return (
      <Chip tone="neutral" dot>
        Queued
      </Chip>
    );
  }
  return (
    <Chip tone="warning" dot>
      Retrying at {formatTime(n.next_attempt_at)}
    </Chip>
  );
}

export function DeliveriesPanel({ onAddChannel }: { onAddChannel: () => void }) {
  const q = useNotifications();
  const hasChannels = Boolean(useChannels().data?.length);
  return (
    <Surface className="overflow-hidden">
      <SurfaceHeader
        title="Deliveries"
        description="Every notification GPUWatch sent or is still trying to send. Failures retry with backoff, up to 8 attempts."
      />
      {q.isPending ? (
        <TableSkeleton rows={6} cols={5} />
      ) : q.isError && !q.data ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : !q.data?.length ? (
        <EmptyState
          icon={InboxIcon}
          title="Nothing delivered yet"
          description={`Each time a rule fires or resolves, its channels get a message and the attempt shows here with its status. ${hasChannels ? "Send a test from a channel to see one." : "Add a channel and send a test to see one."}`}
          action={
            hasChannels ? (
              <Button size="sm" variant="secondary" onClick={onAddChannel}>
                <SendIcon />
                Send a test
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
              <TableHead>Channel</TableHead>
              <TableHead>Transition</TableHead>
              <TableHead className="hidden sm:table-cell text-right">Attempts</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden md:table-cell">Last error</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {q.data.map((n) => {
              const t = TRANSITION[n.transition] ?? { label: n.transition, tone: "neutral" as const };
              return (
                <TableRow key={n.id}>
                  <TableCell className="min-w-36">
                    <div className="font-medium">{n.channel_name}</div>
                    <div className="text-[12px] text-muted-foreground">
                      <TimeAgo iso={n.created_at} />
                    </div>
                  </TableCell>
                  <TableCell>
                    <Chip tone={t.tone}>{t.label}</Chip>
                  </TableCell>
                  <TableCell className="hidden text-right tabular sm:table-cell">{n.attempts}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    <Status n={n} />
                    {n.last_error && <p className="mt-1 max-w-64 truncate text-[12px] text-danger md:hidden" title={n.last_error}>{n.last_error}</p>}
                  </TableCell>
                  <TableCell className="hidden max-w-80 md:table-cell">
                    {n.last_error ? (
                      <span className="line-clamp-2 text-[12.5px] break-words text-danger" title={n.last_error}>
                        {n.last_error}
                      </span>
                    ) : (
                      <span className="text-faint">None</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Surface>
  );
}
