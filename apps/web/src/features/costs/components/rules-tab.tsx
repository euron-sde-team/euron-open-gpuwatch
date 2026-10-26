"use client";

import { HistoryIcon, PencilIcon, PlusIcon, Trash2Icon, WorkflowIcon } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import type { WorkloadRule } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { useApplyWorkloadRules, useDeleteWorkloadRule, useSaveWorkloadRule, useWorkloadRules } from "../api";
import { RuleDialog, ruleBody } from "./rule-dialog";

function shorten(v: string, n = 12): string {
  return v.length > n ? `${v.slice(0, n)}...` : v;
}

function Conditions({ r }: { r: WorkloadRule }) {
  const items = [
    r.process_pattern && { key: "p", text: `process ~ /${r.process_pattern}/`, title: r.process_pattern },
    r.container_prefix && { key: "c", text: `container ${shorten(r.container_prefix)}`, title: r.container_prefix },
    r.username && { key: "u", text: `user ${r.username}`, title: r.username },
    r.host_label && { key: "l", text: `label ${r.host_label}`, title: r.host_label },
  ].filter((x): x is { key: string; text: string; title: string } => !!x);
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((i) => (
        <Chip key={i.key} tone="neutral" title={i.title} className="max-w-[16rem] font-mono font-medium">
          <span className="truncate">{i.text}</span>
        </Chip>
      ))}
    </div>
  );
}

export function RulesTab({ canWrite }: { canWrite: boolean }) {
  const q = useWorkloadRules();
  const save = useSaveWorkloadRule();
  const remove = useDeleteWorkloadRule();
  const apply = useApplyWorkloadRules();
  const [open, setOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<WorkloadRule | null>(null);
  const [target, setTarget] = React.useState<WorkloadRule | null>(null);
  const [confirmApply, setConfirmApply] = React.useState(false);
  const [toggling, setToggling] = React.useState<string | null>(null);

  const add = () => {
    setEditing(null);
    setOpen(true);
  };

  function toggle(r: WorkloadRule, on: boolean) {
    setToggling(r.id);
    save.mutate(
      { id: r.id, body: ruleBody(r, { enabled: on }) },
      {
        onSuccess: () => toast.success(on ? `Rule for "${r.workload}" enabled.` : `Rule for "${r.workload}" disabled.`),
        onError: (e) => toast.error(errorMessage(e)),
        onSettled: () => setToggling(null),
      },
    );
  }

  let body: React.ReactNode;
  if (q.isPending) body = <TableSkeleton rows={4} cols={5} />;
  else if (q.isError && !q.data) body = <ErrorState error={q.error} title="Could not load workload rules" onRetry={() => void q.refetch()} />;
  else if (!q.data?.length)
    body = (
      <EmptyState
        icon={WorkflowIcon}
        title="No workload rules yet"
        description="Without rules, GPU time is attributed to each process's name. Add a rule to group processes by name pattern, container, user or host label into a workload and a team, so costs read by who used them."
        action={
          canWrite ? (
            <Button size="sm" onClick={add}>
              <PlusIcon />
              Add a rule
            </Button>
          ) : (
            <span className="text-[12.5px] text-muted-foreground">Ask an admin to add one.</span>
          )
        }
      />
    );
  else
    body = (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-px">Priority</TableHead>
            <TableHead>Workload</TableHead>
            <TableHead className="hidden md:table-cell">Matches</TableHead>
            <TableHead>Status</TableHead>
            {canWrite && (
              <TableHead className="text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {q.data.map((r) => (
            <TableRow key={r.id} className={cn(!r.enabled && "opacity-60")}>
              <TableCell className="text-muted-foreground tabular">{r.priority}</TableCell>
              <TableCell className="max-w-[14rem]">
                <div className="truncate font-medium">{r.workload}</div>
                <div className="truncate text-[12px] text-muted-foreground">{r.team ? `Team ${r.team}` : "No team"}</div>
                <div className="mt-1.5 md:hidden">
                  <Conditions r={r} />
                </div>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                <Conditions r={r} />
              </TableCell>
              <TableCell>
                {canWrite ? (
                  <label className="inline-flex items-center gap-2 text-[12.5px] text-muted-foreground">
                    <span className="hidden sm:inline">{r.enabled ? "Enabled" : "Disabled"}</span>
                    <Switch
                      checked={r.enabled}
                      disabled={toggling === r.id}
                      aria-label={r.enabled ? `Disable rule for ${r.workload}` : `Enable rule for ${r.workload}`}
                      onCheckedChange={(on) => toggle(r, on)}
                    />
                  </label>
                ) : (
                  <Chip tone={r.enabled ? "success" : "neutral"} dot>
                    {r.enabled ? "Enabled" : "Disabled"}
                  </Chip>
                )}
              </TableCell>
              {canWrite && (
                <TableCell className="w-px text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="subtle"
                      size="icon-sm"
                      aria-label={`Edit rule for ${r.workload}`}
                      onClick={() => {
                        setEditing(r);
                        setOpen(true);
                      }}
                    >
                      <PencilIcon />
                    </Button>
                    <Button variant="subtle" size="icon-sm" aria-label={`Delete rule for ${r.workload}`} onClick={() => setTarget(r)}>
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
          title="Workload rules"
          titleExtra={<Hint text="Rules run in priority order and the first match wins. Processes no rule matches are attributed to their process name, and time with nothing running counts as idle." />}
          description="Name the workloads and teams behind GPU time. Unmatched processes are attributed to their process name."
          action={
            canWrite && (
              <>
                {!!q.data?.length && (
                  <Button size="sm" variant="secondary" onClick={() => setConfirmApply(true)}>
                    <HistoryIcon />
                    <span className="hidden sm:inline">Apply to recent history</span>
                    <span className="sm:hidden">Apply</span>
                  </Button>
                )}
                {!!q.data?.length && (
                  <Button size="sm" onClick={add}>
                    <PlusIcon />
                    Add rule
                  </Button>
                )}
              </>
            )
          }
        />
        <div className="flex items-center gap-1.5 px-5 pb-2 text-xs text-muted-foreground">
          How time is split between processes <Hint term="attribution" />
        </div>
        {body}
      </Surface>
      {!canWrite && <p className="mt-3 text-xs text-muted-foreground">Only admins and owners can change workload rules.</p>}
      <RuleDialog open={open} onOpenChange={setOpen} editing={editing} />
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Delete the rule for "${target?.workload ?? ""}"?`}
        description="New samples it matched fall through to the next rule, or to their process name. Hours already attributed keep their workload until you apply the rules to recent history."
        confirmLabel="Delete rule"
        pending={remove.isPending}
        onConfirm={() =>
          target &&
          remove.mutate(target.id, {
            onSuccess: () => {
              toast.success("Rule deleted.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
      <ConfirmDialog
        open={confirmApply}
        onOpenChange={setConfirmApply}
        destructive={false}
        title="Re-attribute recent history?"
        description="Every hour that still has raw samples is attributed again with the current rules, so workload and team costs change for that period. Older hours, already rolled up, keep their attribution."
        confirmLabel="Apply rules"
        pending={apply.isPending}
        onConfirm={() =>
          apply.mutate(undefined, {
            onSuccess: (ack) => {
              toast.success(ack.message || "Rules applied. Costs update within a minute.");
              setConfirmApply(false);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
