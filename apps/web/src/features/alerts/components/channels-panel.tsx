"use client";

import { ChevronRightIcon, MailIcon, PencilIcon, PlusIcon, SendIcon, ShieldCheckIcon, Trash2Icon, WebhookIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { errorMessage } from "@/lib/api/errors";
import type { Channel } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { useChannels, useDeleteChannel, useTestChannel } from "../api";

import { TimeAgo } from "./alert-utils";

function SigningHelp() {
  return (
    <details className="group mt-4 rounded-xl bg-muted/60 text-[13px] [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl px-4 py-3 font-medium text-foreground focus-visible:outline-2 focus-visible:outline-ring">
        <ChevronRightIcon className="size-4 text-muted-foreground transition-transform group-open:rotate-90" />
        How webhook signing works
      </summary>
      <div className="space-y-2.5 px-4 pb-4 pl-10 leading-relaxed text-muted-foreground">
        <p>
          Every webhook request carries <code className="rounded bg-card px-1 py-0.5 font-mono text-[12px] text-foreground">X-GPUWatch-Timestamp</code>, the
          Unix time it was sent. When the channel has a secret it also carries:
        </p>
        <pre className="overflow-x-auto rounded-lg bg-code-bg px-3.5 py-2.5 font-mono text-[12px] leading-[1.7] text-code-fg">
          {'X-GPUWatch-Signature: sha256=HMAC-SHA256(secret, "<timestamp>.<body>")'}
        </pre>
        <p>
          Recompute the HMAC over the timestamp, a full stop and the raw request body, compare it in constant time, and reject timestamps older than a few
          minutes so a captured request cannot be replayed.
        </p>
      </div>
    </details>
  );
}

function Target({ c }: { c: Channel }) {
  const text = c.kind === "email" ? c.emails.join(", ") : (c.url ?? "");
  return (
    <span className={cn("block truncate text-[12.5px] text-muted-foreground", c.kind === "webhook" && "font-mono text-[12px]")} title={text}>
      {text}
    </span>
  );
}

export function ChannelsPanel({
  canWrite,
  onCreate,
  onEdit,
}: {
  canWrite: boolean;
  onCreate: () => void;
  onEdit: (c: Channel) => void;
}) {
  const q = useChannels();
  const test = useTestChannel();
  const del = useDeleteChannel();
  const [testing, setTesting] = React.useState<string | null>(null);
  const [target, setTarget] = React.useState<Channel | null>(null);

  function sendTest(c: Channel) {
    setTesting(c.id);
    test.mutate(c.id, {
      onSuccess: () => toast.success(`Test queued for "${c.name}". It arrives within a few seconds; check Deliveries for the result.`),
      onError: (e) => toast.error(errorMessage(e)),
      onSettled: () => setTesting(null),
    });
  }

  return (
    <>
      <Surface className="overflow-hidden">
        <SurfaceHeader title="Channels" description="Email addresses and webhooks that rules notify" />
        {q.isPending ? (
          <TableSkeleton rows={3} cols={4} />
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState
            icon={SendIcon}
            title="No channels yet"
            description="Without a channel, alerts only show on this page. Add an email address or a webhook (Slack, PagerDuty, your own receiver) and attach it to rules."
            action={
              canWrite ? (
                <Button size="sm" onClick={onCreate}>
                  <PlusIcon />
                  Add a channel
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="pb-2">
            {q.data.map((c) => {
              const Icon = c.kind === "email" ? MailIcon : WebhookIcon;
              return (
                <li
                  key={c.id}
                  className={cn(
                    "flex flex-col gap-3 border-b border-hairline px-5 py-3.5 last:border-0 sm:flex-row sm:items-center",
                    !c.enabled && "opacity-60",
                  )}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                      <Icon className="size-4" />
                      <span className="sr-only">{c.kind === "email" ? "Email" : "Webhook"}</span>
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-medium">{c.name}</span>
                        {c.kind === "webhook" && c.signed && (
                          <Chip tone="success">
                            <ShieldCheckIcon />
                            Signed
                          </Chip>
                        )}
                        {!c.enabled && <Chip tone="neutral">Disabled</Chip>}
                      </div>
                      <Target c={c} />
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-muted-foreground">
                        <span>
                          Last delivery <TimeAgo iso={c.last_delivery_at} />
                        </span>
                      </div>
                      {c.last_error && <p className="mt-1 text-[12px] leading-snug break-words text-danger">{c.last_error}</p>}
                    </div>
                  </div>
                  {canWrite && (
                    <div className="flex shrink-0 items-center gap-1 pl-11 sm:pl-0">
                      <Button variant="secondary" size="xs" disabled={!c.enabled || testing === c.id} onClick={() => sendTest(c)} aria-label={`Send a test to ${c.name}`}>
                        <SendIcon />
                        {testing === c.id ? "Sending..." : "Send test"}
                      </Button>
                      <Button variant="subtle" size="icon-sm" aria-label={`Edit ${c.name}`} onClick={() => onEdit(c)}>
                        <PencilIcon />
                      </Button>
                      <Button variant="subtle" size="icon-sm" aria-label={`Delete ${c.name}`} onClick={() => setTarget(c)}>
                        <Trash2Icon />
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Surface>
      <SigningHelp />
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Delete "${target?.name ?? ""}"?`}
        description="Rules that notify this channel keep working but stop sending to it. Its delivery history is removed."
        confirmLabel="Delete channel"
        pending={del.isPending}
        onConfirm={() =>
          target &&
          del.mutate(target.id, {
            onSuccess: () => {
              toast.success("Channel deleted.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
