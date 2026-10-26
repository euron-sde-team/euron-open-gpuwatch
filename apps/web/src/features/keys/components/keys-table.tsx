"use client";

import { BanIcon, KeyRoundIcon, PencilIcon, PlusIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import type { ApiKey } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatCompact, formatDate, formatRelative } from "@/lib/format";

import { useKeys, useRevokeKey } from "../api";

export function keyStatus(k: Pick<ApiKey, "revoked_at" | "expires_at">, now = new Date()): "active" | "revoked" | "expired" {
  if (k.revoked_at) return "revoked";
  if (k.expires_at && new Date(k.expires_at) <= now) return "expired";
  return "active";
}

export function KeysTable({
  includeRevoked,
  canWrite,
  onCreate,
  onEdit,
}: {
  includeRevoked: boolean;
  canWrite: boolean;
  onCreate: () => void;
  onEdit: (k: ApiKey) => void;
}) {
  const q = useKeys(includeRevoked);
  const revoke = useRevokeKey();
  const [target, setTarget] = React.useState<ApiKey | null>(null);

  if (q.isPending) return <div className="pt-3"><TableSkeleton rows={5} cols={5} /></div>;
  if (q.isError && !q.data) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data?.length)
    return (
      <EmptyState
        icon={KeyRoundIcon}
        title="No API keys yet"
        description="A gwk_ key gives scripts and dashboards read-only access to the REST API: GPUs, history, costs, insights and alerts. Each key has its own rate limit and can expire."
        action={
          canWrite ? (
            <Button size="sm" onClick={onCreate}>
              <PlusIcon />
              Create a key
            </Button>
          ) : undefined
        }
      />
    );

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Key</TableHead>
            <TableHead className="hidden md:table-cell">Expires</TableHead>
            <TableHead className="hidden lg:table-cell">Rate limit</TableHead>
            <TableHead className="hidden sm:table-cell">Last used</TableHead>
            <TableHead>Status</TableHead>
            {canWrite && <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {q.data.map((k) => {
            const status = keyStatus(k);
            return (
              <TableRow key={k.id} className={cn(status !== "active" && "opacity-60")}>
                <TableCell>
                  <div className="font-medium">{k.name}</div>
                  <div className="font-mono text-[11.5px] text-muted-foreground">{k.display}</div>
                </TableCell>
                <TableCell className="hidden text-muted-foreground md:table-cell">
                  {k.expires_at ? formatDate(k.expires_at) : <span className="text-faint">Never</span>}
                </TableCell>
                <TableCell className="hidden text-muted-foreground tabular lg:table-cell">
                  {k.rpm_limit ? `${formatCompact(k.rpm_limit)} / min` : "Service default"}
                </TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">{formatRelative(k.last_used_at)}</TableCell>
                <TableCell>
                  <Chip tone={status === "active" ? "success" : status === "revoked" ? "danger" : "neutral"} dot>
                    {status === "active" ? "Active" : status === "revoked" ? "Revoked" : "Expired"}
                  </Chip>
                </TableCell>
                {canWrite && (
                  <TableCell className="w-px text-right">
                    {status === "active" && (
                      <div className="flex justify-end gap-1">
                      <Button variant="subtle" size="icon-sm" aria-label={`Edit ${k.name}`} onClick={() => onEdit(k)}>
                        <PencilIcon />
                      </Button>
                      <Button variant="destructive-soft" size="xs" aria-label={`Revoke ${k.name}`} onClick={() => setTarget(k)}>
                        <BanIcon className="sm:hidden" />
                        <span className="hidden sm:inline">Revoke</span>
                      </Button>
                      </div>
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Revoke "${target?.name ?? ""}"?`}
        description={
          <>
            Requests using <span className="font-mono">{target?.display}</span> start failing with 401 immediately. This cannot be undone; create a
            new key to restore access.
          </>
        }
        confirmLabel="Revoke key"
        pending={revoke.isPending}
        onConfirm={() =>
          target &&
          revoke.mutate(target.id, {
            onSuccess: () => {
              toast.success("Key revoked.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
