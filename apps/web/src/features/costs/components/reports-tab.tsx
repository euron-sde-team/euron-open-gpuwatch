"use client";

import { DownloadIcon, FileSpreadsheetIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Segmented } from "@/components/segmented";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import type { GroupBy } from "@/lib/api/types";
import { formatBytes, formatDateTime, formatNumber, formatNusd, formatRelative } from "@/lib/format";
import { rangeBounds } from "@/lib/range";

import { reportDownloadUrl, useCreateReport, useReports } from "../api";
import { GROUP_OPTIONS, groupLabel, RANGE_OPTIONS, type CostRange } from "./costs-shared";

function ExportForm({ defaultGroup, defaultRange }: { defaultGroup: GroupBy; defaultRange: CostRange }) {
  const create = useCreateReport();
  const [groupBy, setGroupBy] = React.useState<GroupBy>(defaultGroup);
  const [range, setRange] = React.useState<CostRange>(defaultRange);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate(
      { group_by: groupBy, ...rangeBounds(range), note: note.trim() || null },
      {
        onSuccess: (r) => {
          toast.success(`Report ready: ${formatNumber(r.rows)} rows, ${formatNusd(r.total_nusd)} in total.`);
          setNote("");
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <form onSubmit={submit} noValidate className="px-5 pb-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[11rem_auto_1fr_auto] lg:items-end">
        <Field label="Group by" htmlFor="report-group">
          <SimpleSelect id="report-group" value={groupBy} onValueChange={(v) => v && setGroupBy(v as GroupBy)} options={GROUP_OPTIONS} />
        </Field>
        <Field label="Period">
          <Segmented ariaLabel="Report period" value={range} onChange={setRange} options={RANGE_OPTIONS} className="lg:w-44" />
        </Field>
        <Field label="Note" htmlFor="report-note" className="sm:col-span-2 lg:col-span-1">
          <Input id="report-note" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Optional, for example October chargeback" />
        </Field>
        <Button type="submit" disabled={create.isPending} className="sm:col-span-2 sm:justify-self-start lg:col-span-1">
          <FileSpreadsheetIcon />
          {create.isPending ? "Exporting..." : "Export CSV"}
        </Button>
      </div>
      {error && <FieldError className="mt-3">{error}</FieldError>}
    </form>
  );
}

export function ReportsTab({ canWrite, defaultGroup, defaultRange }: { canWrite: boolean; defaultGroup: GroupBy; defaultRange: CostRange }) {
  const q = useReports();

  return (
    <div className="space-y-5">
      {canWrite ? (
        <Surface>
          <SurfaceHeader
            title="Export a cost report"
            description="A CSV of estimated cost, idle cost and GPU hours per group for the chosen period, ready for a spreadsheet or a chargeback."
          />
          <ExportForm defaultGroup={defaultGroup} defaultRange={defaultRange} />
        </Surface>
      ) : null}
      <Surface className="overflow-hidden">
        <SurfaceHeader title="Reports" description="Every export is kept, so anyone on the team can download it again." />
        {q.isPending ? (
          <TableSkeleton rows={4} cols={5} />
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} title="Could not load reports" onRetry={() => void q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState
            icon={FileSpreadsheetIcon}
            title="No reports yet"
            description={
              canWrite
                ? "Export a CSV above to share GPU costs by workload, team, host, GPU or model with finance or team leads."
                : "Reports are CSV exports of GPU cost by workload, team, host, GPU or model. Ask an admin to export one; it shows up here for you to download."
            }
            action={
              canWrite ? (
                <Button size="sm" variant="secondary" onClick={() => document.getElementById("report-note")?.focus()}>
                  <FileSpreadsheetIcon />
                  Export the first report
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>Group by</TableHead>
                <TableHead className="hidden lg:table-cell">Period</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Rows</TableHead>
                <TableHead className="hidden text-right md:table-cell">Total</TableHead>
                <TableHead className="hidden text-right md:table-cell">Size</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Download</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="max-w-[16rem]">
                    <div className="font-medium">{formatRelative(r.created_at)}</div>
                    <div className="truncate text-[12px] text-muted-foreground" title={r.note ?? r.filename}>
                      {r.note || r.filename}
                    </div>
                  </TableCell>
                  <TableCell>{groupLabel(r.group_by)}</TableCell>
                  <TableCell className="hidden whitespace-nowrap text-muted-foreground tabular lg:table-cell">
                    {formatDateTime(r.params.start)} to {formatDateTime(r.params.end)}
                  </TableCell>
                  <TableCell className="hidden text-right text-muted-foreground tabular sm:table-cell">{formatNumber(r.rows)}</TableCell>
                  <TableCell className="hidden text-right font-medium tabular md:table-cell">{formatNusd(r.total_nusd)}</TableCell>
                  <TableCell className="hidden text-right text-muted-foreground tabular md:table-cell">{formatBytes(r.bytes)}</TableCell>
                  <TableCell className="w-px text-right">
                    <a href={reportDownloadUrl(r.id)} download={r.filename} className={buttonVariants({ variant: "subtle", size: "xs" })}>
                      <DownloadIcon />
                      <span className="hidden sm:inline">Download</span>
                      <span className="sr-only sm:hidden">Download {r.filename}</span>
                    </a>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Surface>
    </div>
  );
}
