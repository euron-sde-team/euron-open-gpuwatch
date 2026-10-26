"use client";

import { CoinsIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import type { Rate } from "@/lib/api/types";
import { formatRate, formatRelative } from "@/lib/format";

import { useDeleteRate, useRates } from "../api";
import { RateDialog, rateTarget, scopeLabel } from "./rate-dialog";

const SCOPE_TONE = { model: "info", host: "primary", gpu: "savings" } as const;

function scopeTone(scope: string): "info" | "primary" | "savings" | "neutral" {
  return scope in SCOPE_TONE ? SCOPE_TONE[scope as keyof typeof SCOPE_TONE] : "neutral";
}

export function RatesTab({ canWrite }: { canWrite: boolean }) {
  const q = useRates();
  const remove = useDeleteRate();
  const [open, setOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Rate | null>(null);
  const [target, setTarget] = React.useState<Rate | null>(null);

  const add = () => {
    setEditing(null);
    setOpen(true);
  };

  let body: React.ReactNode;
  if (q.isPending) body = <TableSkeleton rows={4} cols={5} />;
  else if (q.isError && !q.data) body = <ErrorState error={q.error} title="Could not load rates" onRetry={() => void q.refetch()} />;
  else if (!q.data?.length)
    body = (
      <EmptyState
        icon={CoinsIcon}
        title="No rates yet"
        description="A rate is what one GPU hour costs you. GPUWatch ships no prices; set one per GPU model to price a whole fleet at once, then override single hosts or GPUs where the price differs."
        action={
          canWrite ? (
            <Button size="sm" onClick={add}>
              <PlusIcon />
              Add a rate
            </Button>
          ) : (
            <span className="text-[12.5px] text-muted-foreground">Ask an admin to set one.</span>
          )
        }
      />
    );
  else
    body = (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Applies to</TableHead>
            <TableHead className="text-right">Per hour</TableHead>
            <TableHead className="hidden text-right sm:table-cell">GPUs covered</TableHead>
            <TableHead className="hidden md:table-cell">Note</TableHead>
            <TableHead className="hidden lg:table-cell">Updated</TableHead>
            {canWrite && (
              <TableHead className="text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {q.data.map((r) => (
            <TableRow key={r.id}>
              <TableCell className="max-w-[18rem]">
                <div className="flex min-w-0 items-center gap-2">
                  <Chip tone={scopeTone(r.scope)}>{scopeLabel(r.scope)}</Chip>
                  <span className="truncate font-medium">{rateTarget(r)}</span>
                </div>
              </TableCell>
              <TableCell className="text-right font-medium tabular">{formatRate(r.nusd_per_hour)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground tabular sm:table-cell">
                {r.gpus_covered === 0 ? <span className="text-faint">None right now</span> : r.gpus_covered}
              </TableCell>
              <TableCell className="hidden max-w-[16rem] truncate text-muted-foreground md:table-cell">
                {r.note || <span className="text-faint">No note</span>}
              </TableCell>
              <TableCell className="hidden text-muted-foreground lg:table-cell">{formatRelative(r.updated_at)}</TableCell>
              {canWrite && (
                <TableCell className="w-px text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="subtle"
                      size="icon-sm"
                      aria-label={`Edit rate for ${rateTarget(r)}`}
                      onClick={() => {
                        setEditing(r);
                        setOpen(true);
                      }}
                    >
                      <PencilIcon />
                    </Button>
                    <Button variant="subtle" size="icon-sm" aria-label={`Delete rate for ${rateTarget(r)}`} onClick={() => setTarget(r)}>
                      <Trash2Icon />
                    </Button>
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );

  return (
    <>
      <Surface className="overflow-hidden">
        <SurfaceHeader
          title="Hourly rates"
          titleExtra={<Hint term="rate" />}
          description="The most specific rate wins: a GPU's own, then its host's, then its model's. GPUs with no rate are left out of the totals."
          action={
            canWrite && !!q.data?.length && (
              <Button size="sm" onClick={add}>
                <PlusIcon />
                Add rate
              </Button>
            )
          }
        />
        {body}
      </Surface>
      {!canWrite && <p className="mt-3 text-xs text-muted-foreground">Only admins and owners can change rates.</p>}
      <RateDialog open={open} onOpenChange={setOpen} editing={editing} />
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Delete the rate for ${target ? rateTarget(target) : ""}?`}
        description="GPUs it covered fall back to the next less specific rate, or drop out of the cost totals if there is none."
        confirmLabel="Delete rate"
        pending={remove.isPending}
        onConfirm={() =>
          target &&
          remove.mutate(target.id, {
            onSuccess: () => {
              toast.success("Rate deleted.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
