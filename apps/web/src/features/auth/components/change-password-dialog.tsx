"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";

import { useChangePassword } from "../api";

export const MIN_PASSWORD = 10;

export function passwordProblem(current: string, next: string, confirm: string): string | null {
  if (!current) return "Enter your current password.";
  if (next.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters for the new password.`;
  if (next === current) return "The new password must differ from the current one.";
  if (next !== confirm) return "The two new passwords do not match.";
  return null;
}

export function ChangePasswordForm({ onDone, footer }: { onDone?: () => void; footer?: "dialog" | "inline" }) {
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [problem, setProblem] = React.useState<string | null>(null);
  const change = useChangePassword();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const p = passwordProblem(current, next, confirm);
    setProblem(p);
    if (p) return;
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          toast.success("Password changed. Other sessions were signed out.");
          setCurrent("");
          setNext("");
          setConfirm("");
          onDone?.();
        },
        onError: (err) => setProblem(errorMessage(err)),
      },
    );
  }

  const fields = (
    <div className="space-y-4">
      <Field label="Current password" htmlFor="pw-current">
        <Input id="pw-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <Field label="New password" htmlFor="pw-new" hint={`At least ${MIN_PASSWORD} characters.`}>
        <Input id="pw-new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <Field label="Confirm new password" htmlFor="pw-confirm" error={problem ?? undefined}>
        <Input id="pw-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
    </div>
  );

  if (footer === "inline") {
    return (
      <form onSubmit={submit} className="max-w-md space-y-4">
        {fields}
        <Button type="submit" disabled={change.isPending}>
          {change.isPending ? "Saving..." : "Change password"}
        </Button>
      </form>
    );
  }
  return (
    <form onSubmit={submit} className="flex min-h-0 flex-col">
      <DialogBody>{fields}</DialogBody>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={change.isPending}>
          {change.isPending ? "Saving..." : "Change password"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ChangePasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change password</DialogTitle>
          <DialogDescription>You stay signed in here; other sessions are signed out.</DialogDescription>
        </DialogHeader>
        <ChangePasswordForm onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
