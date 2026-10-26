"use client";

import * as React from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { useGpus, useHosts } from "@/features/fleet/api";
import { errorMessage } from "@/lib/api/errors";
import type { Rate, RateIn } from "@/lib/api/types";

import { useCreateRate, useUpdateRate } from "../api";

type Scope = RateIn["scope"];

const OTHER = "__other__";

const SCOPE_OPTIONS: { value: Scope; label: string; description: string }[] = [
  { value: "model", label: "Model", description: "Every GPU with this model name" },
  { value: "host", label: "Host", description: "Every GPU on one host" },
  { value: "gpu", label: "GPU", description: "One GPU" },
];

/** "2.49" -> null when valid, else the reason. Up to 6 decimals, above 0. */
export function validateUsd(value: string): string | null {
  const v = value.trim();
  if (!v) return "Enter what one GPU hour costs, in US dollars.";
  if (!/^\d+(\.\d{1,6})?$/.test(v)) return "Use a plain number with up to 6 decimals, for example 2.49.";
  const n = Number(v);
  if (!(n > 0)) return "The rate must be above 0.";
  if (n > 100_000) return "That is above the 100,000 USD per hour limit.";
  return null;
}

export function scopeLabel(scope: string): string {
  return SCOPE_OPTIONS.find((o) => o.value === scope)?.label ?? scope;
}

export function rateTarget(r: Rate): string {
  return r.gpu_model ?? r.host_name ?? r.gpu_label ?? "Unknown";
}

/** Adds a rate, or edits the price and note of one when `editing` is set. */
export function RateDialog({ open, onOpenChange, editing = null }: { open: boolean; onOpenChange: (o: boolean) => void; editing?: Rate | null }) {
  const create = useCreateRate();
  const update = useUpdateRate();
  const pending = create.isPending || update.isPending;
  const gpus = useGpus();
  const hosts = useHosts();

  const [scope, setScope] = React.useState<Scope>("model");
  const [modelChoice, setModelChoice] = React.useState("");
  const [modelText, setModelText] = React.useState("");
  const [hostId, setHostId] = React.useState("");
  const [gpuId, setGpuId] = React.useState("");
  const [usd, setUsd] = React.useState("");
  const [note, setNote] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setScope("model");
      setModelChoice("");
      setModelText("");
      setHostId("");
      setGpuId("");
      setUsd(editing ? String(editing.usd_per_hour) : "");
      setNote(editing?.note ?? "");
      setErrors({});
      setServerError(null);
    }
  }, [open, editing]);

  const activeGpus = React.useMemo(() => (gpus.data ?? []).filter((g) => g.status !== "retired"), [gpus.data]);
  const modelNames = React.useMemo(() => [...new Set(activeGpus.map((g) => g.name))].sort(), [activeGpus]);
  const modelOptions = React.useMemo(
    () => [...modelNames.map((n) => ({ value: n, label: n })), { value: OTHER, label: "Another model (type its name)" }],
    [modelNames],
  );
  const freeText = modelChoice === OTHER || modelNames.length === 0;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const usdError = validateUsd(usd);
    if (usdError) errs.usd = usdError;
    const model = (freeText ? modelText : modelChoice).trim();
    if (!editing) {
      if (scope === "model" && !model) errs.target = "Pick the GPU model this rate applies to, or type its name as the driver reports it.";
      if (scope === "host" && !hostId) errs.target = "Pick the host this rate applies to.";
      if (scope === "gpu" && !gpuId) errs.target = "Pick the GPU this rate applies to.";
    }
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    const noteValue = note.trim() || null;

    if (editing) {
      update.mutate(
        { id: editing.id, body: { usd_per_hour: usd.trim(), note: noteValue } },
        {
          onSuccess: () => {
            toast.success(`Rate for ${rateTarget(editing)} updated. Costs are recalculated from your rates.`);
            onOpenChange(false);
          },
          onError: (err) => setServerError(errorMessage(err)),
        },
      );
      return;
    }
    const body: RateIn = {
      scope,
      gpu_model: scope === "model" ? model : null,
      host_id: scope === "host" ? hostId : null,
      gpu_id: scope === "gpu" ? gpuId : null,
      usd_per_hour: usd.trim(),
      note: noteValue,
    };
    create.mutate(body, {
      onSuccess: (r) => {
        toast.success(`Rate set for ${rateTarget(r)}: it covers ${r.gpus_covered} GPU${r.gpus_covered === 1 ? "" : "s"}.`);
        onOpenChange(false);
      },
      onError: (err) => setServerError(errorMessage(err)),
    });
  }

  const optionsFailed = gpus.isError || hosts.isError;

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? `Edit rate for ${rateTarget(editing)}` : "Add a rate"}</DialogTitle>
          <DialogDescription>
            {editing
              ? "A new price applies to every hour in the cost views, past and future, since costs are computed from the current rates."
              : "What one GPU hour costs you. The most specific rate wins: a GPU's own, then its host's, then its model's."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            {!editing && (
              <>
                <Field label="Applies to" hint={SCOPE_OPTIONS.find((o) => o.value === scope)?.description}>
                  <Segmented
                    ariaLabel="Rate scope"
                    value={scope}
                    onChange={(v) => {
                      setScope(v);
                      setErrors({});
                    }}
                    options={SCOPE_OPTIONS}
                  />
                </Field>
                {scope === "model" && modelNames.length > 0 && (
                  <Field label="GPU model" htmlFor="rate-model" error={freeText ? undefined : errors.target}>
                    <SimpleSelect id="rate-model" value={modelChoice} onValueChange={setModelChoice} placeholder="Pick a model" options={modelOptions} />
                  </Field>
                )}
                {scope === "model" && freeText && (
                  <Field
                    label={modelNames.length ? "Model name" : "GPU model"}
                    htmlFor="rate-model-text"
                    error={errors.target}
                    hint="Exactly as the driver reports it, for example NVIDIA H100 80GB HBM3."
                    className={modelNames.length ? "-mt-1" : undefined}
                  >
                    <Input id="rate-model-text" value={modelText} maxLength={120} onChange={(e) => setModelText(e.target.value)} placeholder="NVIDIA A100-SXM4-80GB" />
                  </Field>
                )}
                {scope === "host" && (
                  <Field label="Host" htmlFor="rate-host" error={errors.target}>
                    <SimpleSelect
                      id="rate-host"
                      value={hostId}
                      onValueChange={setHostId}
                      placeholder={hosts.isPending ? "Loading hosts..." : hosts.data?.length ? "Pick a host" : "No hosts enrolled yet"}
                      options={(hosts.data ?? []).filter((h) => h.status !== "revoked").map((h) => ({ value: h.id, label: h.name }))}
                    />
                  </Field>
                )}
                {scope === "gpu" && (
                  <Field label="GPU" htmlFor="rate-gpu" error={errors.target}>
                    <SimpleSelect
                      id="rate-gpu"
                      value={gpuId}
                      onValueChange={setGpuId}
                      placeholder={gpus.isPending ? "Loading GPUs..." : activeGpus.length ? "Pick a GPU" : "No GPUs reporting yet"}
                      options={activeGpus.map((g) => ({ value: g.id, label: `${g.host_name} GPU ${g.index} (${g.name})` }))}
                    />
                  </Field>
                )}
                {optionsFailed && (
                  <p className="text-[12.5px] text-muted-foreground">
                    Could not load the host or GPU list.{" "}
                    <button
                      type="button"
                      className="font-medium text-primary underline-offset-4 hover:underline"
                      onClick={() => {
                        void gpus.refetch();
                        void hosts.refetch();
                      }}
                    >
                      Retry
                    </button>
                  </p>
                )}
              </>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="USD per hour" htmlFor="rate-usd" error={errors.usd} hint="Per GPU, up to 6 decimals">
                <div className="relative">
                  <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-muted-foreground">$</span>
                  <Input
                    id="rate-usd"
                    inputMode="decimal"
                    className="pl-6 tabular"
                    placeholder="2.49"
                    value={usd}
                    aria-invalid={errors.usd ? true : undefined}
                    onChange={(e) => setUsd(e.target.value)}
                  />
                </div>
              </Field>
              <Field label="Note" htmlFor="rate-note" hint="Optional, for example the contract">
                <Input id="rate-note" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder="1-year reserved, us-east" />
              </Field>
            </div>
            {serverError && <FieldError>{serverError}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {editing ? (pending ? "Saving..." : "Save rate") : pending ? "Adding..." : "Add rate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
