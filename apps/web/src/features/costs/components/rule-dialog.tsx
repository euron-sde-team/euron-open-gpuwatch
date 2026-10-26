"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";
import type { WorkloadRule, WorkloadRuleIn } from "@/lib/api/types";

import { useSaveWorkloadRule } from "../api";

const HOST_LABEL = /^[A-Za-z0-9_.-]+=.{0,100}$/;

/** The body the API expects for a rule, from an existing one (used to toggle enabled). */
export function ruleBody(r: WorkloadRule, patch: Partial<WorkloadRuleIn> = {}): WorkloadRuleIn {
  return {
    priority: r.priority,
    workload: r.workload,
    team: r.team,
    process_pattern: r.process_pattern,
    container_prefix: r.container_prefix,
    username: r.username,
    host_label: r.host_label,
    enabled: r.enabled,
    ...patch,
  };
}

/** Field-level checks that mirror the API, so most mistakes never leave the form. */
export function validateRule(v: {
  priority: string;
  workload: string;
  processPattern: string;
  containerPrefix: string;
  username: string;
  hostLabel: string;
}): Record<string, string> {
  const errs: Record<string, string> = {};
  const p = Number(v.priority);
  if (!v.priority.trim() || !Number.isInteger(p) || p < 0 || p > 10_000) errs.priority = "Whole number from 0 to 10,000.";
  if (!v.workload.trim()) errs.workload = 'Name the workload, for example "llm-serving".';
  if (v.processPattern) {
    try {
      new RegExp(v.processPattern);
    } catch {
      errs.processPattern = "Not a valid regular expression.";
    }
  }
  if (v.hostLabel.trim() && !HOST_LABEL.test(v.hostLabel.trim())) errs.hostLabel = "Use key=value, for example team=research.";
  if (!v.processPattern.trim() && !v.containerPrefix.trim() && !v.username.trim() && !v.hostLabel.trim()) {
    errs.conditions = "Add at least one condition: a process pattern, container prefix, user or host label.";
  }
  return errs;
}

export function RuleDialog({
  open,
  onOpenChange,
  editing = null,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editing?: WorkloadRule | null;
}) {
  const save = useSaveWorkloadRule();
  const [priority, setPriority] = React.useState("100");
  const [workload, setWorkload] = React.useState("");
  const [team, setTeam] = React.useState("");
  const [processPattern, setProcessPattern] = React.useState("");
  const [containerPrefix, setContainerPrefix] = React.useState("");
  const [username, setUsername] = React.useState("");
  const [hostLabel, setHostLabel] = React.useState("");
  const [enabled, setEnabled] = React.useState(true);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setPriority(String(editing?.priority ?? 100));
      setWorkload(editing?.workload ?? "");
      setTeam(editing?.team ?? "");
      setProcessPattern(editing?.process_pattern ?? "");
      setContainerPrefix(editing?.container_prefix ?? "");
      setUsername(editing?.username ?? "");
      setHostLabel(editing?.host_label ?? "");
      setEnabled(editing?.enabled ?? true);
      setErrors({});
      setServerError(null);
    }
  }, [open, editing]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validateRule({ priority, workload, processPattern, containerPrefix, username, hostLabel });
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    const body: WorkloadRuleIn = {
      priority: Number(priority),
      workload: workload.trim(),
      team: team.trim() || null,
      process_pattern: processPattern || null,
      container_prefix: containerPrefix.trim() || null,
      username: username.trim() || null,
      host_label: hostLabel.trim() || null,
      enabled,
    };
    save.mutate(
      { id: editing?.id, body },
      {
        onSuccess: () => {
          toast.success(editing ? `Rule for "${body.workload}" saved.` : `Rule added. New samples are attributed to "${body.workload}" from now on.`);
          onOpenChange(false);
        },
        onError: (err) => setServerError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !save.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? `Edit rule for "${editing.workload}"` : "New workload rule"}</DialogTitle>
          <DialogDescription>
            Processes that match every condition you set are attributed to this workload and team. Lower priority numbers are checked first.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-[1fr_1fr_6.5rem]">
              <Field label="Workload" htmlFor="rule-workload" error={errors.workload}>
                <Input id="rule-workload" value={workload} maxLength={80} onChange={(e) => setWorkload(e.target.value)} placeholder="llm-serving" />
              </Field>
              <Field label="Team" htmlFor="rule-team" hint="Optional">
                <Input id="rule-team" value={team} maxLength={80} onChange={(e) => setTeam(e.target.value)} placeholder="research" />
              </Field>
              <Field label="Priority" htmlFor="rule-priority" error={errors.priority}>
                <Input id="rule-priority" inputMode="numeric" className="tabular" value={priority} onChange={(e) => setPriority(e.target.value)} />
              </Field>
            </div>
            <div className="space-y-3 rounded-xl bg-muted/60 p-4">
              <p className="text-[12.5px] font-medium text-muted-foreground">Conditions (all that are set must match)</p>
              <Field label="Process name pattern" htmlFor="rule-process" error={errors.processPattern} hint="A regular expression, for example ^vllm|python.*serve">
                <Input
                  id="rule-process"
                  className="font-mono text-[13px]"
                  value={processPattern}
                  maxLength={200}
                  onChange={(e) => setProcessPattern(e.target.value)}
                  placeholder="^vllm"
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Container id prefix" htmlFor="rule-container">
                  <Input
                    id="rule-container"
                    className="font-mono text-[13px]"
                    value={containerPrefix}
                    maxLength={64}
                    onChange={(e) => setContainerPrefix(e.target.value)}
                    placeholder="3f2a9c"
                  />
                </Field>
                <Field label="User" htmlFor="rule-user">
                  <Input id="rule-user" value={username} maxLength={64} onChange={(e) => setUsername(e.target.value)} placeholder="svc-inference" />
                </Field>
              </div>
              <Field label="Host label" htmlFor="rule-label" error={errors.hostLabel} hint="key=value, matched against the host's labels">
                <Input
                  id="rule-label"
                  className="font-mono text-[13px]"
                  value={hostLabel}
                  maxLength={120}
                  onChange={(e) => setHostLabel(e.target.value)}
                  placeholder="pool=inference"
                />
              </Field>
              {errors.conditions && <FieldError>{errors.conditions}</FieldError>}
            </div>
            <label htmlFor="rule-enabled" className="flex items-center justify-between gap-3 text-[13px]">
              <span>
                <span className="font-medium">Enabled</span>
                <span className="block text-xs text-muted-foreground">A disabled rule is kept but never matches.</span>
              </span>
              <Switch id="rule-enabled" checked={enabled} onCheckedChange={setEnabled} />
            </label>
            {serverError && <FieldError>{serverError}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {editing ? (save.isPending ? "Saving..." : "Save rule") : save.isPending ? "Adding..." : "Add rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
