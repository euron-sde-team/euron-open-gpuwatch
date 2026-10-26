"use client";

import { PencilIcon, UserPlusIcon, UsersIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AdminOnly } from "@/components/admin-only";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { MIN_PASSWORD } from "@/features/auth/components/change-password-dialog";
import { errorMessage } from "@/lib/api/errors";
import type { Role, User } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative, initials } from "@/lib/format";
import { ROLES, roleDescription, roleLabel } from "@/lib/roles";

import { useCreateUser, useUpdateUser, useUsers } from "../api";

const roleOptions = ROLES.map((r) => ({ value: r, label: roleLabel(r) }));

function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateUser();
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<Role>("viewer");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (open) {
      setName("");
      setEmail("");
      setRole("viewer");
      setPassword("");
      setError(null);
    }
  }, [open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Enter the person's name.");
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError("Enter a valid email address.");
    if (password.length < MIN_PASSWORD) return setError(`The initial password needs at least ${MIN_PASSWORD} characters.`);
    create.mutate(
      { name: name.trim(), email: email.trim(), role, password },
      {
        onSuccess: (u) => {
          toast.success(`${u.name} can now sign in. Share the initial password privately.`);
          onOpenChange(false);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a user</DialogTitle>
          <DialogDescription>Creates a dashboard account. They can change the initial password after signing in.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="u-name">
                <Input id="u-name" value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Email" htmlFor="u-email">
                <Input id="u-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </Field>
            </div>
            <Field label="Role" htmlFor="u-role" hint={roleDescription(role)}>
              <SimpleSelect id="u-role" value={role} onValueChange={(v) => setRole((v || "viewer") as Role)} options={roleOptions} />
            </Field>
            <Field label="Initial password" htmlFor="u-pw" hint={`At least ${MIN_PASSWORD} characters.`}>
              <Input id="u-pw" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Adding..." : "Add user"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RenameDialog({ user, onOpenChange }: { user: User | null; onOpenChange: (o: boolean) => void }) {
  const update = useUpdateUser();
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (user) {
      setName(user.name);
      setError(null);
    }
  }, [user]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    const value = name.trim();
    if (!value) return setError("Enter the name people see in the dashboard and the audit log.");
    update.mutate(
      { id: user.id, body: { name: value } },
      {
        onSuccess: () => {
          toast.success(`Renamed to ${value}.`);
          onOpenChange(false);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={user != null} onOpenChange={(o) => !update.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Rename {user?.name}</DialogTitle>
          <DialogDescription>The display name only; the email used to sign in stays the same.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody>
            <Field label="Name" htmlFor="rename-name" error={error ?? undefined}>
              <Input id="rename-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save name"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UsersScreen() {
  const { user: me, canWrite, canManageUsers } = usePermissions();
  const q = useUsers(canWrite);
  const update = useUpdateUser();
  const [open, setOpen] = React.useState(false);
  const [renaming, setRenaming] = React.useState<User | null>(null);

  function change(id: string, body: { role?: Role; disabled?: boolean }, msg: string) {
    update.mutate({ id, body }, { onSuccess: () => toast.success(msg), onError: (e) => toast.error(errorMessage(e)) });
  }

  return (
    <>
      <PageHeader
        title="Users"
        description="People who can sign in to this dashboard. Owners manage users; admins change configuration; viewers read."
        actions={
          canManageUsers && (
            <Button onClick={() => setOpen(true)}>
              <UserPlusIcon />
              Add user
            </Button>
          )
        }
      />
      {me && !canWrite ? (
        <AdminOnly what="The user list" />
      ) : (
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={4} cols={4} />
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState icon={UsersIcon} title="No users" description="Add the people who should see GPU costs and alerts, or manage hosts, rates and rules." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Role</TableHead>
                <TableHead className="hidden md:table-cell">Last sign-in</TableHead>
                <TableHead className="text-right">Access</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((u) => {
                const self = u.id === me?.id;
                return (
                  <TableRow key={u.id} className={cn(u.disabled && "opacity-55")}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11.5px] font-semibold text-primary">{initials(u.name)}</span>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 font-medium">
                            <span className="truncate">{u.name}</span>
                            {self && <Chip tone="primary">You</Chip>}
                            {canManageUsers && (
                              <Button variant="subtle" size="icon-xs" aria-label={`Rename ${u.name}`} onClick={() => setRenaming(u)}>
                                <PencilIcon />
                              </Button>
                            )}
                          </div>
                          <div className="truncate text-[12px] text-muted-foreground">{u.email}</div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      {canManageUsers && !self ? (
                        <SimpleSelect
                          aria-label={`Role for ${u.name}`}
                          size="sm"
                          className="w-28"
                          value={u.role}
                          options={roleOptions}
                          onValueChange={(v) => v && v !== u.role && change(u.id, { role: v as Role }, `${u.name} is now ${roleLabel(v)}.`)}
                        />
                      ) : (
                        <Chip tone={u.role === "owner" ? "primary" : u.role === "admin" ? "info" : "neutral"}>{roleLabel(u.role)}</Chip>
                      )}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground md:table-cell">{formatRelative(u.last_login_at)}</TableCell>
                    <TableCell className="text-right">
                      {canManageUsers && !self ? (
                        <label className="inline-flex items-center gap-2 text-[12.5px] text-muted-foreground">
                          {u.disabled ? "Disabled" : "Active"}
                          <Switch
                            checked={!u.disabled}
                            aria-label={u.disabled ? `Enable ${u.name}` : `Disable ${u.name}`}
                            onCheckedChange={(on) => change(u.id, { disabled: !on }, on ? `${u.name} can sign in again.` : `${u.name} was signed out and disabled.`)}
                          />
                        </label>
                      ) : (
                        <Chip tone={u.disabled ? "neutral" : "success"} dot>
                          {u.disabled ? "Disabled" : "Active"}
                        </Chip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Surface>
      )}
      {!canManageUsers && <p className="mt-3 text-xs text-muted-foreground">Only owners can add users or change roles.</p>}
      <InviteDialog open={open} onOpenChange={setOpen} />
      <RenameDialog user={renaming} onOpenChange={(o) => !o && setRenaming(null)} />
    </>
  );
}
