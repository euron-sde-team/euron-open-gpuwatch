"use client";

import { ScrollTextIcon, SearchIcon } from "lucide-react";
import * as React from "react";

import { AdminOnly } from "@/components/admin-only";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import type { AuditEntry } from "@/lib/api/types";
import { formatDateTime, formatRelative } from "@/lib/format";

import { useAuditLog } from "../api";

function actionTone(action: string): "danger" | "success" | "info" | "primary" | "neutral" {
  if (/(deleted|revoked|purged|disabled)/.test(action)) return "danger";
  if (/created/.test(action)) return "success";
  if (/(updated|changed|published)/.test(action)) return "info";
  if (/^auth\./.test(action)) return "neutral";
  return "primary";
}

function detailsText(d: AuditEntry["details"]): string {
  const entries = Object.entries(d ?? {});
  if (!entries.length) return "";
  return entries
    .map(([k, v]) => `${k}: ${typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

export function AuditScreen() {
  const [input, setInput] = React.useState("");
  const [action, setAction] = React.useState("");
  React.useEffect(() => {
    const t = setTimeout(() => setAction(input.trim()), 350);
    return () => clearTimeout(t);
  }, [input]);
  const { user, canWrite } = usePermissions();
  const q = useAuditLog(action || undefined, canWrite);
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every configuration change and sign-in, append-only: who did what, to which object, from where."
      />
      {user && !canWrite ? (
        <AdminOnly what="The audit log" />
      ) : (
      <>
      <div className="mb-3 relative w-full sm:w-72">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Filter by action, e.g. rate.created" aria-label="Filter by action" className="pl-9" />
      </div>
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={10} cols={4} />
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !rows.length ? (
          <EmptyState
            icon={ScrollTextIcon}
            title={action ? "No entries for this action" : "Nothing audited yet"}
            description={action ? "Action names look like rate.created or host.revoked. Clear the filter to see everything." : "Enrolments and changes to hosts, rates, rules, alerts, channels, keys and users are recorded here as they happen."}
            action={action ? <Button variant="secondary" size="sm" onClick={() => setInput("")}>Clear filter</Button> : undefined}
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead className="hidden md:table-cell">Actor</TableHead>
                  <TableHead className="hidden lg:table-cell">Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap">
                      <div className="tabular">{formatDateTime(e.at)}</div>
                      <div className="text-[11px] text-subtle">{formatRelative(e.at)}</div>
                    </TableCell>
                    <TableCell>
                      <Chip tone={actionTone(e.action)} className="font-mono">
                        {e.action}
                      </Chip>
                      {e.target_type && <div className="mt-1 text-[11.5px] text-subtle">{e.target_type}</div>}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <div className="truncate">{e.actor_email ?? "System"}</div>
                      {e.ip && <div className="font-mono text-[11px] text-subtle">{e.ip}</div>}
                    </TableCell>
                    <TableCell className="hidden max-w-[420px] lg:table-cell">
                      <div className="truncate text-[12px] text-muted-foreground" title={detailsText(e.details)}>
                        {detailsText(e.details) || <span className="text-faint">No details</span>}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between px-5 py-3 text-xs text-muted-foreground">
              <span>{rows.length} entries</span>
              {q.hasNextPage ? (
                <Button variant="secondary" size="sm" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage}>
                  {q.isFetchingNextPage ? "Loading..." : "Load older"}
                </Button>
              ) : (
                <span>Beginning of the log</span>
              )}
            </div>
          </>
        )}
      </Surface>
      </>
      )}
    </>
  );
}
