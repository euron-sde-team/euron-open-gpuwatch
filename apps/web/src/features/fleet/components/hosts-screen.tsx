"use client";

import { BanIcon, PencilIcon, PlusIcon, ServerIcon, TicketIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { GpuChip, HostChip, SimBadge } from "@/components/status-chip";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { EnrolmentToken, Host } from "@/lib/api/types";
import { formatDate, formatRelative } from "@/lib/format";

import { useEnrolmentTokens, useGpus, useHosts, useRevokeEnrolmentToken, useRevokeHost, useUpdateHost } from "../api";
import { AddHostDialog } from "./add-host-dialog";

function Labels({ labels }: { labels: Record<string, unknown> }) {
  const entries = Object.entries(labels);
  if (!entries.length) return <span className="text-faint">None</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => (
        <Chip key={k} tone="neutral">
          {k}={String(v)}
        </Chip>
      ))}
    </div>
  );
}

function EditHostDialog({ host, onOpenChange }: { host: Host | null; onOpenChange: (o: boolean) => void }) {
  const update = useUpdateHost();
  const [name, setName] = React.useState("");
  const [labels, setLabels] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (host) {
      setName(host.name === host.hostname ? "" : host.name);
      setLabels(Object.entries(host.labels).map(([k, v]) => `${k}=${String(v)}`).join(","));
      setError(null);
    }
  }, [host]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!host) return;
    const parsed: Record<string, string> = {};
    for (const part of labels.split(",").map((p) => p.trim()).filter(Boolean)) {
      const [k, ...v] = part.split("=");
      if (!k || !/^[A-Za-z0-9_.-]+$/.test(k.trim())) {
        setError("Labels are key=value pairs separated by commas.");
        return;
      }
      parsed[k.trim()] = v.join("=").trim();
    }
    update.mutate(
      { id: host.id, body: { display_name: name.trim() || null, labels: parsed } },
      {
        onSuccess: () => {
          toast.success("Host updated.");
          onOpenChange(false);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={!!host} onOpenChange={(o) => !update.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit {host?.name}</DialogTitle>
          <DialogDescription>A display name and labels. Rules, costs and filters can use labels.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Display name" htmlFor="host-name" hint={`Empty: the hostname (${host?.hostname ?? ""})`}>
              <Input id="host-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={host?.hostname} />
            </Field>
            <Field label="Labels" htmlFor="host-labels" hint="key=value, separated by commas">
              <Input id="host-labels" value={labels} onChange={(e) => setLabels(e.target.value)} placeholder="env=prod,team=ml" />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function HostGpus({ hostId }: { hostId: string }) {
  const gpus = useGpus();
  const list = (gpus.data ?? []).filter((g) => g.host_id === hostId && g.status !== "retired");
  if (!list.length) return <span className="text-faint">None yet</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {list.map((g) => (
        <Link
          key={g.id}
          href={`/gpus/${g.id}`}
          className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-[12px] hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          <span className="font-medium">GPU {g.index}</span>
          <span className="text-muted-foreground">{g.name.replace(/^NVIDIA /, "")}</span>
          {g.status !== "ok" && <GpuChip value={g.status} />}
        </Link>
      ))}
    </div>
  );
}

function TokensSection() {
  const { canWrite } = usePermissions();
  const tokens = useEnrolmentTokens(canWrite);
  const revoke = useRevokeEnrolmentToken();
  const [target, setTarget] = React.useState<EnrolmentToken | null>(null);
  if (!canWrite) return null;
  return (
    <Surface>
      <SurfaceHeader title="Enrolment tokens" description="Secrets agents exchange for their own host token. Revoking one stops new enrolments; enrolled hosts keep working." />
      {tokens.isPending ? (
        <TableSkeleton rows={2} cols={4} />
      ) : tokens.isError ? (
        <ErrorState compact error={tokens.error} onRetry={() => void tokens.refetch()} />
      ) : !tokens.data.length ? (
        <p className="px-5 pb-5 text-[13px] text-muted-foreground">No tokens yet. Add a host to create one.</p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Token</TableHead>
                <TableHead className="hidden md:table-cell">Labels</TableHead>
                <TableHead>Used</TableHead>
                <TableHead className="hidden sm:table-cell">Expires</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tokens.data.map((t) => (
                <TableRow key={t.id} className={t.usable ? undefined : "opacity-60"}>
                  <TableCell>
                    <div className="flex items-center gap-2 font-medium">
                      {t.name}
                      {t.simulated && <SimBadge />}
                    </div>
                    <div className="font-mono text-[11.5px] text-muted-foreground">{t.display}</div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <Labels labels={t.labels} />
                  </TableCell>
                  <TableCell className="tabular">
                    {t.uses}
                    {t.max_uses ? ` of ${t.max_uses}` : ""} {t.uses === 1 ? "host" : "hosts"}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">
                    {t.revoked_at ? <Chip tone="neutral">Revoked</Chip> : t.expires_at ? formatDate(t.expires_at) : "Never"}
                  </TableCell>
                  <TableCell className="w-px text-right">
                    {t.usable && (
                      <Button variant="subtle" size="icon-sm" aria-label={`Revoke ${t.name}`} onClick={() => setTarget(t)}>
                        <BanIcon />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Revoke "${target?.name}"?`}
        description="No new machine can enrol with it. Hosts already enrolled keep reporting."
        confirmLabel="Revoke token"
        pending={revoke.isPending}
        onConfirm={() =>
          target &&
          revoke.mutate(target.id, {
            onSuccess: () => {
              toast.success("Token revoked.");
              setTarget(null);
            },
            onError: (err) => toast.error(errorMessage(err)),
          })
        }
      />
    </Surface>
  );
}

export function HostsScreen() {
  const hosts = useHosts();
  const { canWrite } = usePermissions();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const adding = params.get("add") === "1";
  const setAdding = (open: boolean) => router.replace(open ? `${pathname}?add=1` : pathname, { scroll: false });
  const [editing, setEditing] = React.useState<Host | null>(null);
  const [revoking, setRevoking] = React.useState<Host | null>(null);
  const revoke = useRevokeHost();

  const addButton = canWrite ? (
    <Button onClick={() => setAdding(true)}>
      <PlusIcon />
      Add a host
    </Button>
  ) : null;

  return (
    <>
      <PageHeader
        title="Hosts"
        description="Machines running the GPUWatch agent. Each reports its GPUs, processes and inference servers every few seconds."
        actions={addButton}
      />
      <div className="space-y-4">
        <Surface>
          {hosts.isPending ? (
            <div className="pt-3">
              <TableSkeleton rows={4} cols={5} />
            </div>
          ) : hosts.isError ? (
            <ErrorState error={hosts.error} onRetry={() => void hosts.refetch()} />
          ) : !hosts.data.length ? (
            <EmptyState
              icon={ServerIcon}
              title="No hosts yet"
              description="Install the agent on a machine with NVIDIA GPUs. It reads the driver (NVML or an existing DCGM exporter) and sends readings here. It needs no inbound port."
              action={addButton ?? <p className="text-[12.5px] text-muted-foreground">Ask an admin to add a host.</p>}
            />
          ) : (
            <ul className="divide-y divide-hairline">
              {hosts.data.map((h) => (
                <li key={h.id} className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[14px] font-semibold text-foreground">{h.name}</span>
                      <HostChip value={h.status} />
                      {h.agent_status === "degraded" && h.status === "online" && <Chip tone="warning" dot>Degraded</Chip>}
                      {h.simulated && <SimBadge />}
                    </div>
                    {h.problems.length > 0 && (
                      <div className="flex gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[12.5px] text-foreground" role="status">
                        <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0 text-warning" />
                        <div className="space-y-0.5">
                          {h.problems.map((p, i) => (
                            <div key={i}>{String((p as { message?: string }).message ?? p)}</div>
                          ))}
                        </div>
                      </div>
                    )}
                    <HostGpus hostId={h.id} />
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
                      <span>
                        Last report <span className="text-foreground">{formatRelative(h.last_seen_at)}</span>
                      </span>
                      {h.driver_version && <span>Driver {h.driver_version}</span>}
                      {h.cuda_version && <span>CUDA {h.cuda_version}</span>}
                      {h.collector && <span className="capitalize">Collector {h.collector}</span>}
                      {h.agent_version && <span>Agent {h.agent_version}</span>}
                      {h.os && <span className="hidden md:inline">{h.os}</span>}
                    </div>
                    <Labels labels={h.labels} />
                  </div>
                  {canWrite && h.status !== "revoked" && (
                    <div className="flex shrink-0 gap-1">
                      <Button variant="subtle" size="sm" onClick={() => setEditing(h)}>
                        <PencilIcon />
                        Edit
                      </Button>
                      <Button variant="subtle" size="sm" onClick={() => setRevoking(h)}>
                        <BanIcon />
                        Revoke
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Surface>
        {hosts.data && hosts.data.length > 0 && canWrite && (
          <p className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
            <TicketIcon className="size-3.5 shrink-0" />
            <span>
              Enrol more machines with an existing token, or{" "}
              <button type="button" className="font-medium text-primary underline-offset-4 hover:underline" onClick={() => setAdding(true)}>
                create a new one
              </button>
              .
            </span>
          </p>
        )}
        <TokensSection />
      </div>
      <AddHostDialog open={adding} onOpenChange={setAdding} />
      <EditHostDialog host={editing} onOpenChange={(o) => !o && setEditing(null)} />
      <ConfirmDialog
        open={!!revoking}
        onOpenChange={(o) => !o && setRevoking(null)}
        title={`Revoke ${revoking?.name}?`}
        description="Its token stops working at once and its data is no longer accepted. History stays. To bring it back, enrol the machine again."
        confirmLabel="Revoke host"
        pending={revoke.isPending}
        onConfirm={() =>
          revoking &&
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              toast.success("Host revoked.");
              setRevoking(null);
            },
            onError: (err) => toast.error(errorMessage(err)),
          })
        }
      />
    </>
  );
}
