"use client";

import { PencilIcon, PlusIcon, ShieldAlertIcon, Trash2Icon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { SeverityChip } from "@/components/status-chip";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGpus, useHosts } from "@/features/fleet/api";
import { errorMessage } from "@/lib/api/errors";
import type { AlertRule } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { useAlertRules, useChannels, useDeleteAlertRule, useSaveAlertRule } from "../api";

import { ruleToInput } from "./alert-utils";

function useScopeLabel() {
  const hosts = useHosts();
  const gpus = useGpus();
  return React.useCallback(
    (r: AlertRule): string => {
      if (r.scope_gpu_id) {
        const g = gpus.data?.find((x) => x.id === r.scope_gpu_id);
        return g ? `GPU ${g.index} on ${g.host_name}` : "One GPU";
      }
      if (r.scope_host_id) {
        const h = hosts.data?.find((x) => x.id === r.scope_host_id);
        return h ? `Host ${h.name || h.hostname}` : "One host";
      }
      if (r.scope_label) return `Label ${r.scope_label}`;
      return r.kind === "agent_offline" ? "All hosts" : "All GPUs";
    },
    [hosts.data, gpus.data],
  );
}

export function RulesPanel({
  canWrite,
  onCreate,
  onEdit,
}: {
  canWrite: boolean;
  onCreate: () => void;
  onEdit: (r: AlertRule) => void;
}) {
  const q = useAlertRules();
  const channels = useChannels();
  const save = useSaveAlertRule();
  const del = useDeleteAlertRule();
  const scopeLabel = useScopeLabel();
  const [target, setTarget] = React.useState<AlertRule | null>(null);
  const [toggling, setToggling] = React.useState<string | null>(null);

  const channelName = React.useMemo(() => new Map((channels.data ?? []).map((c) => [c.id, c.name])), [channels.data]);

  function toggle(r: AlertRule, on: boolean) {
    setToggling(r.id);
    save.mutate(
      { id: r.id, body: { ...ruleToInput(r), enabled: on } },
      {
        onSuccess: () => toast.success(on ? `"${r.name}" is watching again.` : `"${r.name}" is paused.`),
        onError: (e) => toast.error(errorMessage(e)),
        onSettled: () => setToggling(null),
      },
    );
  }

  return (
    <Surface className="overflow-hidden">
      <SurfaceHeader title="Rules" description="Each rule is checked every minute against every GPU and host in its scope" />
      {q.isPending ? (
        <TableSkeleton rows={5} cols={5} />
      ) : q.isError && !q.data ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : !q.data?.length ? (
        <EmptyState
          icon={ShieldAlertIcon}
          title="No alert rules"
          description="Rules decide when GPUWatch raises an alert: a reading past a limit, an agent going quiet, or a GPU dropping off its host."
          action={
            canWrite ? (
              <Button size="sm" onClick={onCreate}>
                <PlusIcon />
                Add a rule
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rule</TableHead>
              <TableHead className="hidden sm:table-cell">Severity</TableHead>
              <TableHead className="hidden lg:table-cell">Scope</TableHead>
              <TableHead className="hidden md:table-cell">Channels</TableHead>
              <TableHead>Firing</TableHead>
              <TableHead className="text-right">Enabled</TableHead>
              {canWrite && (
                <TableHead className="text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {q.data.map((r) => {
              const names = r.channel_ids.map((id) => channelName.get(id)).filter((n): n is string => !!n);
              return (
                <TableRow key={r.id} className={cn(!r.enabled && "opacity-60")}>
                  <TableCell className="min-w-52">
                    <div className="font-medium">{r.name}</div>
                    <div className="text-[12.5px] text-muted-foreground">{r.description}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 sm:hidden">
                      <SeverityChip value={r.severity} />
                    </div>
                    <div className="mt-1 text-[12px] text-muted-foreground lg:hidden">{scopeLabel(r)}</div>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <SeverityChip value={r.severity} />
                  </TableCell>
                  <TableCell className="hidden whitespace-nowrap text-muted-foreground lg:table-cell">{scopeLabel(r)}</TableCell>
                  <TableCell className="hidden max-w-56 md:table-cell">
                    {names.length ? (
                      <span className="text-muted-foreground">{names.join(", ")}</span>
                    ) : (
                      <span className="text-faint">Dashboard only</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {r.firing > 0 ? (
                      <Chip tone="danger" dot>
                        <span className="tabular">{r.firing}</span>
                      </Chip>
                    ) : (
                      <span className="text-faint tabular">0</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {canWrite ? (
                      <Switch
                        checked={r.enabled}
                        disabled={toggling === r.id}
                        aria-label={r.enabled ? `Pause ${r.name}` : `Enable ${r.name}`}
                        onCheckedChange={(on) => toggle(r, on)}
                      />
                    ) : (
                      <Chip tone={r.enabled ? "success" : "neutral"} dot>
                        {r.enabled ? "On" : "Off"}
                      </Chip>
                    )}
                  </TableCell>
                  {canWrite && (
                    <TableCell className="w-px text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="subtle" size="icon-sm" aria-label={`Edit ${r.name}`} onClick={() => onEdit(r)}>
                          <PencilIcon />
                        </Button>
                        <Button variant="subtle" size="icon-sm" aria-label={`Delete ${r.name}`} onClick={() => setTarget(r)}>
                          <Trash2Icon />
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Delete "${target?.name ?? ""}"?`}
        description="The rule stops watching immediately and its event history is deleted with it. Pause it instead if you may want it back."
        confirmLabel="Delete rule"
        pending={del.isPending}
        onConfirm={() =>
          target &&
          del.mutate(target.id, {
            onSuccess: () => {
              toast.success("Rule deleted.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </Surface>
  );
}
