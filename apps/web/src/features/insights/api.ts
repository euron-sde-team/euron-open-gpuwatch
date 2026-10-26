"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { InsightSettings, InsightStatus } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useInsights(status?: InsightStatus) {
  return useQuery({
    queryKey: qk.insights(status),
    queryFn: () => unwrap(api.GET("/api/v1/insights", { params: { query: status ? { status: [status] } : {} } })),
    staleTime: STALE.analytics,
    refetchInterval: 60_000,
  });
}

export function useInsightSettings() {
  return useQuery({
    queryKey: qk.insightSettings,
    queryFn: () => unwrap(api.GET("/api/v1/settings/insights")),
    staleTime: STALE.config,
  });
}

function useInvalidateInsights() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: qk.insightsAll });
    void client.invalidateQueries({ queryKey: qk.overview });
    void client.invalidateQueries({ queryKey: ["gpus"] });
  };
}

export function useInsightAction() {
  const done = useInvalidateInsights();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "acknowledge" | "dismiss" | "reopen" }) =>
      unwrap(api.POST("/api/v1/insights/{insight_id}/actions", { params: { path: { insight_id: id } }, body: { action } })),
    onSuccess: done,
  });
}

export function useEvaluateInsights() {
  const done = useInvalidateInsights();
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/insights/evaluate")), onSuccess: done });
}

export function useSaveInsightSettings() {
  const client = useQueryClient();
  const done = useInvalidateInsights();
  return useMutation({
    mutationFn: (body: InsightSettings) => unwrap(api.PUT("/api/v1/settings/insights", { body })),
    onSuccess: (data) => {
      client.setQueryData(qk.insightSettings, data);
      done();
    },
  });
}
