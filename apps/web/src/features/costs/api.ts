"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { GroupBy, RateIn, RateUpdate, ReportIn, WorkloadRuleIn } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { rangeBounds, type Range } from "@/lib/range";

export function useCosts(groupBy: GroupBy, range: Range) {
  return useQuery({
    queryKey: qk.costs(groupBy, range),
    queryFn: () => unwrap(api.GET("/api/v1/costs", { params: { query: { group_by: groupBy, ...rangeBounds(range) } } })),
    staleTime: STALE.analytics,
    refetchInterval: 60_000,
  });
}

export function useCostSeries(groupBy: GroupBy, range: Range) {
  return useQuery({
    queryKey: qk.costSeries(groupBy, range),
    queryFn: () =>
      unwrap(api.GET("/api/v1/costs/series", { params: { query: { group_by: groupBy, ...rangeBounds(range) } } })),
    staleTime: STALE.analytics,
    refetchInterval: 60_000,
  });
}

export function useRates() {
  return useQuery({ queryKey: qk.rates, queryFn: () => unwrap(api.GET("/api/v1/rates")), staleTime: STALE.config });
}

export function useWorkloadRules() {
  return useQuery({
    queryKey: qk.workloadRules,
    queryFn: () => unwrap(api.GET("/api/v1/workload-rules")),
    staleTime: STALE.config,
  });
}

export function useReports() {
  return useQuery({ queryKey: qk.reports, queryFn: () => unwrap(api.GET("/api/v1/reports")), staleTime: STALE.config });
}

function useInvalidateCosts() {
  const client = useQueryClient();
  return () => {
    for (const key of [qk.costsAll, qk.rates, qk.workloadRules, qk.reports, qk.gpus, qk.live, qk.overview, qk.insightsAll]) {
      void client.invalidateQueries({ queryKey: key });
    }
  };
}

export function useCreateRate() {
  const done = useInvalidateCosts();
  return useMutation({ mutationFn: (body: RateIn) => unwrap(api.POST("/api/v1/rates", { body })), onSuccess: done });
}

export function useUpdateRate() {
  const done = useInvalidateCosts();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RateUpdate }) =>
      unwrap(api.PATCH("/api/v1/rates/{rate_id}", { params: { path: { rate_id: id } }, body })),
    onSuccess: done,
  });
}

export function useDeleteRate() {
  const done = useInvalidateCosts();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/rates/{rate_id}", { params: { path: { rate_id: id } } })),
    onSuccess: done,
  });
}

export function useSaveWorkloadRule() {
  const done = useInvalidateCosts();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: WorkloadRuleIn }) =>
      id
        ? unwrap(api.PUT("/api/v1/workload-rules/{rule_id}", { params: { path: { rule_id: id } }, body }))
        : unwrap(api.POST("/api/v1/workload-rules", { body })),
    onSuccess: done,
  });
}

export function useDeleteWorkloadRule() {
  const done = useInvalidateCosts();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/workload-rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: done,
  });
}

export function useApplyWorkloadRules() {
  const done = useInvalidateCosts();
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/workload-rules/apply")), onSuccess: done });
}

export function useCreateReport() {
  const done = useInvalidateCosts();
  return useMutation({ mutationFn: (body: ReportIn) => unwrap(api.POST("/api/v1/reports", { body })), onSuccess: done });
}

/** The report CSV is served with a content-disposition header: a plain link downloads it. */
export function reportDownloadUrl(id: string): string {
  return `/api/v1/reports/${id}/download`;
}
