"use client";

import * as React from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError, FieldHint, Label } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useGpus, useHosts } from "@/features/fleet/api";
import { errorMessage } from "@/lib/api/errors";
import type { AlertRule, AlertRuleIn } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { useChannels, useSaveAlertRule } from "../api";

import { METRICS, metricUnit, SEVERITIES, type Metric, type RuleKind, type SeverityValue } from "./alert-utils";

type Scope = "all" | "host" | "gpu" | "label";

const DURATION_PRESETS = [
  { value: 0, label: "At once" },
  { value: 60, label: "1 min" },
  { value: 300, label: "5 min" },
  { value: 900, label: "15 min" },
];

const KIND_HELP: Record<RuleKind, string> = {
  threshold: "Fires when a GPU reading stays past a limit for the duration you set.",
  agent_offline: "Fires when a host's agent stops reporting, for example the machine or the network went down.",
  gpu_lost: "Fires when a GPU disappears from a host that still reports (fell off the bus, driver reset).",
};

const LABEL_RE = /^[A-Za-z0-9_.-]+=.{0,100}$/;

function scopeOf(rule: AlertRule | null): Scope {
  if (!rule) return "all";
  if (rule.scope_gpu_id) return "gpu";
  if (rule.scope_host_id) return "host";
  if (rule.scope_label) return "label";
  return "all";
}

export function RuleDialog({
  open,
  onOpenChange,
  editing,
  onAddChannel,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editing: AlertRule | null;
  onAddChannel: () => void;
}) {
  const save = useSaveAlertRule();
  const channels = useChannels();
  const hosts = useHosts();
  const gpus = useGpus();

  const [name, setName] = React.useState("");
  const [kind, setKind] = React.useState<RuleKind>("threshold");
  const [metric, setMetric] = React.useState<Metric>("temp_c");
  const [operator, setOperator] = React.useState<"gt" | "lt">("gt");
  const [threshold, setThreshold] = React.useState("");
  const [duration, setDuration] = React.useState("60");
  const [scope, setScope] = React.useState<Scope>("all");
  const [hostId, setHostId] = React.useState("");
  const [gpuId, setGpuId] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [severity, setSeverity] = React.useState<SeverityValue>("warning");
  const [channelIds, setChannelIds] = React.useState<string[]>([]);
  const [notifyResolved, setNotifyResolved] = React.useState(true);
  const [enabled, setEnabled] = React.useState(true);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? "");
    setKind(editing?.kind ?? "threshold");
    setMetric((editing?.metric as Metric | null) ?? "temp_c");
    setOperator(editing?.operator === "lt" ? "lt" : "gt");
    setThreshold(editing?.threshold != null ? String(editing.threshold) : "");
    setDuration(String(editing?.duration_s ?? 60));
    setScope(scopeOf(editing));
    setHostId(editing?.scope_host_id ?? "");
    setGpuId(editing?.scope_gpu_id ?? "");
    setLabel(editing?.scope_label ?? "");
    setSeverity(editing?.severity ?? "warning");
    setChannelIds(editing?.channel_ids ?? []);
    setNotifyResolved(editing?.notify_resolved ?? true);
    setEnabled(editing?.enabled ?? true);
    setErrors({});
    setServerError(null);
  }, [open, editing]);

  function toggleChannel(id: string, on: boolean) {
    setChannelIds((cur) => (on ? [...cur.filter((c) => c !== id), id] : cur.filter((c) => c !== id)));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name it after what it catches, for example "Training GPUs too hot".';
    const t = threshold.trim() === "" ? NaN : Number(threshold);
    if (kind === "threshold" && !Number.isFinite(t)) errs.threshold = "Enter the number the reading must cross.";
    const d = Number(duration);
    if (!Number.isInteger(d) || d < 0 || d > 86_400) errs.duration = "Whole seconds from 0 to 86400 (one day).";
    if (scope === "host" && !hostId) errs.scope = "Pick the host this rule watches.";
    if (scope === "gpu" && !gpuId) errs.scope = "Pick the GPU this rule watches.";
    if (scope === "label" && !LABEL_RE.test(label.trim())) errs.scope = 'Use key=value, for example "team=research".';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);

    const body: AlertRuleIn = {
      name: name.trim(),
      kind,
      metric: kind === "threshold" ? metric : null,
      operator: kind === "threshold" ? operator : null,
      threshold: kind === "threshold" ? t : null,
      duration_s: d,
      scope_host_id: scope === "host" ? hostId : null,
      scope_gpu_id: scope === "gpu" ? gpuId : null,
      scope_label: scope === "label" ? label.trim() : null,
      severity,
      channel_ids: channelIds,
      notify_resolved: notifyResolved,
      enabled,
    };
    save.mutate(
      { id: editing?.id, body },
      {
        onSuccess: () => {
          toast.success(editing ? `Rule "${body.name}" updated.` : `Rule "${body.name}" added. It is evaluated within a minute.`);
          onOpenChange(false);
        },
        onError: (err) => setServerError(errorMessage(err)),
      },
    );
  }

  const durationNum = Number(duration);
  const hostOptions = (hosts.data ?? []).map((h) => ({ value: h.id, label: h.name || h.hostname }));
  const gpuOptions = (gpus.data ?? []).map((g) => ({ value: g.id, label: `GPU ${g.index} on ${g.host_name} (${g.name})` }));

  return (
    <Dialog open={open} onOpenChange={(o) => !save.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{editing ? `Edit "${editing.name}"` : "New alert rule"}</DialogTitle>
          <DialogDescription>
            Rules are checked every minute. When one fires, its channels hear about it once, and again when it resolves.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-5">
            <Field label="Name" htmlFor="rule-name" error={errors.name}>
              <Input id="rule-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="Training GPUs too hot" />
            </Field>

            <div className="space-y-1.5">
              <Label>What it watches</Label>
              <Segmented
                ariaLabel="Rule kind"
                value={kind}
                onChange={setKind}
                options={[
                  { value: "threshold", label: "Threshold" },
                  { value: "agent_offline", label: "Agent offline" },
                  { value: "gpu_lost", label: "GPU lost" },
                ]}
              />
              <FieldHint>{KIND_HELP[kind]}</FieldHint>
            </div>

            {kind === "threshold" && (
              <div className="space-y-4 rounded-xl bg-muted/60 p-4">
                <div className="grid gap-3 sm:grid-cols-[1fr_auto_8rem]">
                  <Field label="Metric" htmlFor="rule-metric">
                    <SimpleSelect
                      id="rule-metric"
                      value={metric}
                      onValueChange={(v) => v && setMetric(v as Metric)}
                      options={METRICS.map((m) => ({ value: m.value, label: m.label }))}
                    />
                  </Field>
                  <Field label="Is" htmlFor="rule-op">
                    <SimpleSelect
                      id="rule-op"
                      className="sm:w-28"
                      value={operator}
                      onValueChange={(v) => v && setOperator(v === "lt" ? "lt" : "gt")}
                      options={[
                        { value: "gt", label: "Above" },
                        { value: "lt", label: "Below" },
                      ]}
                    />
                  </Field>
                  <Field label={`Threshold${metricUnit(metric) ? ` (${metricUnit(metric)})` : ""}`} htmlFor="rule-threshold" error={errors.threshold}>
                    <Input
                      id="rule-threshold"
                      inputMode="decimal"
                      className="tabular"
                      value={threshold}
                      onChange={(e) => setThreshold(e.target.value)}
                      placeholder={metric === "temp_c" ? "85" : "90"}
                    />
                  </Field>
                </div>
                <Field label="For at least" htmlFor="rule-duration" error={errors.duration} hint="Seconds the reading must stay past the threshold before the rule fires.">
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      id="rule-duration"
                      inputMode="numeric"
                      className="w-28 tabular"
                      value={duration}
                      onChange={(e) => setDuration(e.target.value)}
                      aria-describedby="rule-duration-presets"
                    />
                    <div id="rule-duration-presets" className="flex flex-wrap gap-1" role="group" aria-label="Duration presets">
                      {DURATION_PRESETS.map((p) => (
                        <Button
                          key={p.value}
                          type="button"
                          size="xs"
                          variant={durationNum === p.value ? "secondary" : "subtle"}
                          aria-pressed={durationNum === p.value}
                          className={cn(durationNum === p.value && "bg-primary-soft text-primary hover:bg-primary-soft")}
                          onClick={() => setDuration(String(p.value))}
                        >
                          {p.label}
                        </Button>
                      ))}
                    </div>
                  </div>
                </Field>
              </div>
            )}

            <div className="space-y-2">
              <Label>Scope</Label>
              <Segmented
                ariaLabel="Scope"
                value={scope}
                onChange={setScope}
                options={[
                  { value: "all", label: "All" },
                  { value: "host", label: "Host" },
                  { value: "gpu", label: "GPU" },
                  { value: "label", label: "Label" },
                ]}
              />
              {scope === "all" && <FieldHint>Every GPU and host, including ones enrolled later.</FieldHint>}
              {scope === "host" && (
                <SimpleSelect
                  aria-label="Host"
                  value={hostId}
                  onValueChange={setHostId}
                  placeholder={hosts.isPending ? "Loading hosts..." : hostOptions.length ? "Pick a host" : "No hosts enrolled yet"}
                  options={hostOptions}
                />
              )}
              {scope === "gpu" && (
                <SimpleSelect
                  aria-label="GPU"
                  value={gpuId}
                  onValueChange={setGpuId}
                  placeholder={gpus.isPending ? "Loading GPUs..." : gpuOptions.length ? "Pick a GPU" : "No GPUs reporting yet"}
                  options={gpuOptions}
                />
              )}
              {scope === "label" && (
                <>
                  <Input aria-label="Host label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="team=research" className="font-mono text-[13px]" />
                  <FieldHint>Matches hosts whose label has exactly this value.</FieldHint>
                </>
              )}
              {errors.scope && <FieldError>{errors.scope}</FieldError>}
              {(hosts.isError || gpus.isError) && (scope === "host" || scope === "gpu") && (
                <p className="text-[12.5px] text-muted-foreground">
                  Could not load the fleet.{" "}
                  <button
                    type="button"
                    className="font-medium text-primary underline-offset-4 hover:underline"
                    onClick={() => {
                      void hosts.refetch();
                      void gpus.refetch();
                    }}
                  >
                    Retry
                  </button>
                </p>
              )}
            </div>

            <Field label="Severity" htmlFor="rule-severity">
              <SimpleSelect id="rule-severity" value={severity} onValueChange={(v) => v && setSeverity(v as SeverityValue)} options={SEVERITIES} />
            </Field>

            <fieldset className="space-y-2">
              <legend className="mb-1.5 text-[13px] font-medium text-foreground">Notify</legend>
              {channels.isPending ? (
                <p className="text-[12.5px] text-muted-foreground">Loading channels...</p>
              ) : channels.isError ? (
                <p className="text-[12.5px] text-muted-foreground">
                  Could not load channels.{" "}
                  <button type="button" className="font-medium text-primary underline-offset-4 hover:underline" onClick={() => void channels.refetch()}>
                    Retry
                  </button>
                </p>
              ) : !channels.data?.length ? (
                <p className="rounded-xl bg-muted/60 px-4 py-3 text-[12.5px] text-muted-foreground">
                  No channels yet, so this rule only shows on the Events tab.{" "}
                  <button
                    type="button"
                    className="font-medium text-primary underline-offset-4 hover:underline"
                    onClick={() => {
                      onOpenChange(false);
                      onAddChannel();
                    }}
                  >
                    Add a channel
                  </button>
                </p>
              ) : (
                <ul className="grid gap-1 sm:grid-cols-2">
                  {channels.data.map((c) => {
                    const checked = channelIds.includes(c.id);
                    return (
                      <li key={c.id}>
                        <label
                          className={cn(
                            "flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors hover:bg-muted has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                            checked && "bg-primary-soft hover:bg-primary-soft",
                          )}
                        >
                          <input
                            type="checkbox"
                            className="size-4 accent-primary"
                            checked={checked}
                            onChange={(e) => toggleChannel(c.id, e.target.checked)}
                          />
                          <span className="min-w-0 flex-1 truncate font-medium">{c.name}</span>
                          <span className="text-[11.5px] text-muted-foreground">{c.kind === "email" ? "Email" : "Webhook"}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </fieldset>

            <div className="space-y-3">
              <label className="flex items-center justify-between gap-4 text-[13px]">
                <span>
                  <span className="font-medium text-foreground">Notify on resolve</span>
                  <span className="block text-xs text-muted-foreground">Send a second message when the condition clears.</span>
                </span>
                <Switch checked={notifyResolved} onCheckedChange={setNotifyResolved} />
              </label>
              <label className="flex items-center justify-between gap-4 text-[13px]">
                <span>
                  <span className="font-medium text-foreground">Enabled</span>
                  <span className="block text-xs text-muted-foreground">A disabled rule is kept but never evaluated.</span>
                </span>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </label>
            </div>

            {serverError && <FieldError>{serverError}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {editing ? (save.isPending ? "Saving..." : "Save changes") : save.isPending ? "Adding..." : "Add rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
