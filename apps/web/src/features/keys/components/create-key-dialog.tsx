"use client";

import { CheckCircle2Icon, TriangleAlertIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { CodeBlock } from "@/components/code-block";
import { CopyButton } from "@/components/copy-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import type { ApiKey, ApiKeyCreated } from "@/lib/api/types";

import { useCreateKey, useUpdateKey } from "../api";

export function KeyRevealed({ created }: { created: ApiKeyCreated }) {
  const [origin, setOrigin] = React.useState("");
  React.useEffect(() => setOrigin(window.location.origin), []);
  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-xl bg-warning-soft px-4 py-3 text-[13px]">
        <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-warning" />
        <p className="text-foreground">
          Copy this key now. It is shown <strong>once</strong>; GPUWatch stores only a peppered hash and cannot show it again.
        </p>
      </div>
      <div className="flex items-center gap-2 rounded-xl bg-muted p-1.5 pl-3.5">
        <code className="min-w-0 flex-1 truncate font-mono text-[12.5px] select-all" data-testid="new-key">
          {created.key}
        </code>
        <CopyButton value={created.key} label="Copy key" variant="default" />
      </div>
      <CodeBlock
        samples={[
          { id: "curl", label: "curl", code: `curl -H "Authorization: Bearer ${created.key}" \\\n  ${origin}/api/v1/gpus` },
          {
            id: "prometheus",
            label: "Python",
            code: `import httpx\n\ngpus = httpx.get(\n    "${origin}/api/v1/gpus",\n    headers={"Authorization": "Bearer ${created.key}"},\n).json()\nfor g in gpus:\n    print(g["name"], g["status"], (g["live"] or {}).get("util_gpu"))`,
          },
        ]}
      />
    </div>
  );
}

/** "2026-12-31" -> the end of that day in UTC, so a key works through its last day. */
export function expiryFromDate(value: string): string | null {
  if (!value) return null;
  const d = new Date(`${value}T23:59:59Z`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** Creates a key, or edits one when `editing` is set (the secret is never shown again). */
export function CreateKeyDialog({
  open,
  onOpenChange,
  editing = null,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editing?: ApiKey | null;
}) {
  const create = useCreateKey();
  const update = useUpdateKey();
  const pending = create.isPending || update.isPending;
  const [name, setName] = React.useState("");
  const [rpm, setRpm] = React.useState("");
  const [expires, setExpires] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<ApiKeyCreated | null>(null);

  React.useEffect(() => {
    if (open) {
      setName(editing?.name ?? "");
      setRpm(editing?.rpm_limit ? String(editing.rpm_limit) : "");
      setExpires(editing?.expires_at ? editing.expires_at.slice(0, 10) : "");
      setErrors({});
      setServerError(null);
      setCreated(null);
    }
  }, [open, editing]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name it after what uses it, for example "grafana".';
    const n = rpm.trim() ? Number(rpm) : null;
    if (n != null && (!Number.isInteger(n) || n < 1)) errs.rpm = "Whole number above 0, or empty for the service default.";
    const expiresAt = expiryFromDate(expires);
    if (expires && (!expiresAt || new Date(expiresAt) <= new Date())) errs.expires = "Pick a date from today on, or leave it empty for no expiry.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    const body = {
      name: name.trim(),
      rpm_limit: n,
      expires_at: expiresAt,
    };
    if (editing) {
      update.mutate(
        { id: editing.id, body },
        {
          onSuccess: () => {
            toast.success(`Key "${body.name}" updated.`);
            onOpenChange(false);
          },
          onError: (err) => setServerError(errorMessage(err)),
        },
      );
      return;
    }
    create.mutate(body, {
      onSuccess: (k) => {
        setCreated(k);
        toast.success("API key created.");
      },
      onError: (err) => setServerError(errorMessage(err)),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className={created ? "max-w-2xl" : "max-w-lg"}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {created && <CheckCircle2Icon className="size-5 text-savings" />}
            {created ? `Key "${created.name}" is ready` : editing ? `Edit "${editing.name}"` : "New API key"}
          </DialogTitle>
          <DialogDescription>
            {created
              ? "Use it as a Bearer token for read-only access. Revoke it any time from API keys."
              : editing
                ? "Changes apply to the next request made with this key. The key itself stays the same."
                : "A read-only key for automation: scripts, Grafana or a cron job can read GPUs, costs and alerts. Keys never change anything."}
          </DialogDescription>
        </DialogHeader>
        {created ? (
          <>
            <DialogBody>
              <KeyRevealed created={created} />
            </DialogBody>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>I have copied the key</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
            <DialogBody className="space-y-4">
              <Field label="Name" htmlFor="key-name" error={errors.name}>
                <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="grafana" />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Requests per minute" htmlFor="key-rpm" error={errors.rpm} hint="Over it, calls get 429">
                  <Input id="key-rpm" inputMode="numeric" className="tabular" placeholder="Service default" value={rpm} onChange={(e) => setRpm(e.target.value)} />
                </Field>
                <Field label="Expires" htmlFor="key-expires" error={errors.expires} hint="Empty: never">
                  <Input id="key-expires" type="date" className="tabular" value={expires} onChange={(e) => setExpires(e.target.value)} />
                </Field>
              </div>
              {serverError && <FieldError>{serverError}</FieldError>}
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={pending}>
                {editing ? (pending ? "Saving..." : "Save changes") : pending ? "Creating..." : "Create key"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
