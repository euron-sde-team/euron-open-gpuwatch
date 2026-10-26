"use client";

import * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { InsightSettings } from "@/lib/api/types";

import { useInsightSettings, useSaveInsightSettings } from "../api";

type Key = keyof InsightSettings;

const FIELDS: { key: Key; label: string; unit: string; hint: string; group: string }[] = [
  { key: "idle_util_pct", label: "Idle below", unit: "%", hint: "A minute counts as idle under this average utilization.", group: "Idle rule" },
  { key: "idle_min_minutes", label: "For at least", unit: "min", hint: "Only runs of idle minutes this long are reported.", group: "Idle rule" },
  { key: "idle_min_share", label: "Report when idle over", unit: "0 to 1", hint: "Share of monitored time in idle runs before a GPU is reported.", group: "Idle rule" },
  { key: "held_mem_pct", label: "Held when memory over", unit: "%", hint: "Or when any process is on the GPU: a model is loaded.", group: "Idle rule" },
  { key: "window_days", label: "Look back", unit: "days", hint: "Spend findings use this window; health findings use one day.", group: "Spend" },
  { key: "underused_util_pct", label: "Underused below", unit: "%", hint: "Average utilization while work runs.", group: "Spend" },
  { key: "underused_min_hours", label: "Underused for", unit: "h", hint: "Busy hours needed before it is reported.", group: "Spend" },
  { key: "oversized_peak_pct", label: "Oversized when peak below", unit: "%", hint: "Peak memory as a share of the card, over a day of data.", group: "Spend" },
  { key: "throttle_pct", label: "Throttled over", unit: "%", hint: "Share of busy time running below full clocks.", group: "Health" },
  { key: "mem_pressure_pct", label: "Memory pressure over", unit: "%", hint: "Memory used, as a share of the card.", group: "Health" },
  { key: "mem_pressure_minutes", label: "Memory pressure for", unit: "min", hint: "Minutes in the last day.", group: "Health" },
  { key: "kv_cache_full", label: "KV cache full at", unit: "0 to 1", hint: "With requests waiting: the server cannot admit more.", group: "Inference" },
  { key: "queue_minutes", label: "Queueing for", unit: "min", hint: "Minutes in the last day.", group: "Inference" },
  { key: "overprovisioned_util_pct", label: "Overprovisioned below", unit: "%", hint: "Average GPU utilization of a serving endpoint.", group: "Inference" },
];

/** The idle rule and thresholds the insights engine uses, editable by admins. */
export function InsightSettingsCard() {
  const q = useInsightSettings();
  const save = useSaveInsightSettings();
  const { canWrite } = usePermissions();
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (q.data) setDraft(Object.fromEntries(Object.entries(q.data).map(([k, v]) => [k, String(v)])));
  }, [q.data]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!q.data) return;
    const body = { ...q.data } as Record<string, number>;
    for (const f of FIELDS) {
      const n = Number(draft[f.key]);
      if (!Number.isFinite(n)) {
        setError(`${f.label}: enter a number.`);
        return;
      }
      body[f.key] = n;
    }
    setError(null);
    save.mutate(body as unknown as InsightSettings, {
      onSuccess: () => toast.success("Insight rules saved. Findings update on the next evaluation."),
      onError: (err) => setError(errorMessage(err)),
    });
  }

  const groups = [...new Set(FIELDS.map((f) => f.group))];
  return (
    <Surface id="insight-rules">
      <SurfaceHeader title="Insight rules" description="What counts as idle, underused, throttled or queueing. Applies to every GPU." />
      <div className="px-5 pb-5">
        {q.isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
        ) : (
          <form onSubmit={submit} className="space-y-5" noValidate>
            {groups.map((g) => (
              <fieldset key={g} className="space-y-3">
                <legend className="mb-2 text-[11px] font-semibold tracking-[0.06em] text-faint uppercase">{g}</legend>
                <div className="grid gap-3 sm:grid-cols-2">
                  {FIELDS.filter((f) => f.group === g).map((f) => (
                    <Field key={f.key} label={f.label} htmlFor={`is-${f.key}`} hint={f.hint}>
                      <div className="relative">
                        <Input
                          id={`is-${f.key}`}
                          inputMode="decimal"
                          className="pr-14 tabular"
                          value={draft[f.key] ?? ""}
                          disabled={!canWrite}
                          onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                        />
                        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-faint">{f.unit}</span>
                      </div>
                    </Field>
                  ))}
                </div>
              </fieldset>
            ))}
            {error && <FieldError>{error}</FieldError>}
            {canWrite ? (
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? "Saving..." : "Save rules"}
              </Button>
            ) : (
              <p className="text-[12.5px] text-muted-foreground">Admins and owners can change these rules.</p>
            )}
          </form>
        )}
      </div>
    </Surface>
  );
}
