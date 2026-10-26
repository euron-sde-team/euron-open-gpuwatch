"use client";

import { ShieldCheckIcon, Undo2Icon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError, FieldHint, Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";
import type { Channel, ChannelIn } from "@/lib/api/types";

import { useSaveChannel } from "../api";

type Kind = ChannelIn["kind"];

const EMAIL_RE = /^\S+@\S+\.\S+$/;

export function parseEmails(raw: string): string[] {
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ChannelDialog({
  open,
  onOpenChange,
  editing,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editing: Channel | null;
}) {
  const save = useSaveChannel();
  const [name, setName] = React.useState("");
  const [kind, setKind] = React.useState<Kind>("email");
  const [emails, setEmails] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [secret, setSecret] = React.useState("");
  const [removeSecret, setRemoveSecret] = React.useState(false);
  const [enabled, setEnabled] = React.useState(true);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? "");
    setKind(editing?.kind ?? "email");
    setEmails(editing?.emails.join(", ") ?? "");
    setUrl(editing?.url ?? "");
    setSecret("");
    setRemoveSecret(false);
    setEnabled(editing?.enabled ?? true);
    setErrors({});
    setServerError(null);
  }, [open, editing]);

  const hasSecret = !!editing && editing.kind === "webhook" && editing.signed;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name it after who it reaches, for example "On-call email".';
    const list = parseEmails(emails);
    if (kind === "email") {
      if (!list.length) errs.emails = "Enter at least one address.";
      else if (list.length > 20) errs.emails = "Up to 20 addresses per channel.";
      else {
        const bad = list.find((a) => !EMAIL_RE.test(a));
        if (bad) errs.emails = `"${bad}" is not a valid email address.`;
      }
    }
    if (kind === "webhook" && !/^https?:\/\/\S+$/i.test(url.trim())) errs.url = "Use a full http:// or https:// URL.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);

    const body: ChannelIn = { name: name.trim(), kind, enabled };
    if (kind === "email") body.emails = list;
    else {
      body.url = url.trim();
      // Omitted keeps the current secret; an empty string removes it.
      if (secret.trim()) body.secret = secret.trim();
      else if (removeSecret) body.secret = "";
    }
    save.mutate(
      { id: editing?.id, body },
      {
        onSuccess: () => {
          toast.success(editing ? `Channel "${body.name}" updated.` : `Channel "${body.name}" added. Send a test to check it.`);
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
          <DialogTitle>{editing ? `Edit "${editing.name}"` : "New channel"}</DialogTitle>
          <DialogDescription>Where alerts go. A rule notifies each of its channels when it fires and when it resolves.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-5">
            <Field label="Name" htmlFor="ch-name" error={errors.name}>
              <Input id="ch-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="On-call email" />
            </Field>
            <div className="space-y-1.5">
              <Label>Kind</Label>
              <Segmented
                ariaLabel="Channel kind"
                value={kind}
                onChange={setKind}
                options={[
                  { value: "email", label: "Email" },
                  { value: "webhook", label: "Webhook" },
                ]}
              />
            </div>
            {kind === "email" ? (
              <Field label="Addresses" htmlFor="ch-emails" error={errors.emails} hint="Comma separated, up to 20.">
                <Input id="ch-emails" value={emails} onChange={(e) => setEmails(e.target.value)} placeholder="oncall@example.com, ml-infra@example.com" />
              </Field>
            ) : (
              <>
                <Field label="URL" htmlFor="ch-url" error={errors.url} hint="GPUWatch POSTs a JSON body here. Link-local and cloud metadata addresses are refused.">
                  <Input id="ch-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.example.com/gpuwatch" className="font-mono text-[13px]" />
                </Field>
                <div className="space-y-1.5">
                  <Label htmlFor="ch-secret" className="justify-between">
                    <span>Signing secret</span>
                    {hasSecret && !removeSecret && (
                      <Button type="button" variant="link" size="xs" className="text-danger" onClick={() => {
                        setRemoveSecret(true);
                        setSecret("");
                      }}>
                        Remove secret
                      </Button>
                    )}
                  </Label>
                  {removeSecret ? (
                    <div className="flex items-center justify-between gap-3 rounded-lg bg-warning-soft px-3 py-2 text-[12.5px] text-foreground">
                      <span>The secret is removed when you save. Deliveries will be unsigned.</span>
                      <Button type="button" variant="subtle" size="xs" onClick={() => setRemoveSecret(false)}>
                        <Undo2Icon />
                        Keep it
                      </Button>
                    </div>
                  ) : (
                    <>
                      <Input
                        id="ch-secret"
                        type="password"
                        autoComplete="new-password"
                        value={secret}
                        maxLength={200}
                        onChange={(e) => setSecret(e.target.value)}
                        placeholder={hasSecret ? "Leave empty to keep the current secret" : "Optional"}
                      />
                      <FieldHint className="flex items-center gap-1.5">
                        {hasSecret && <ShieldCheckIcon className="size-3.5 text-savings" />}
                        {hasSecret
                          ? "This webhook is signed. Type a new secret to rotate it."
                          : "With a secret, every delivery carries an HMAC signature your receiver can verify."}
                      </FieldHint>
                    </>
                  )}
                </div>
              </>
            )}
            <label className="flex items-center justify-between gap-4 text-[13px]">
              <span>
                <span className="font-medium text-foreground">Enabled</span>
                <span className="block text-xs text-muted-foreground">A disabled channel receives nothing, not even tests.</span>
              </span>
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </label>
            {serverError && <FieldError>{serverError}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {editing ? (save.isPending ? "Saving..." : "Save changes") : save.isPending ? "Adding..." : "Add channel"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
