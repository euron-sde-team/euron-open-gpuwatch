"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { EnrolmentTokenIn, HostUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { rangeBounds, type Range } from "@/lib/range";

export function useHosts() {
  return useQuery({
    queryKey: qk.hosts,
    queryFn: () => unwrap(api.GET("/api/v1/hosts")),
    staleTime: STALE.live,
    refetchInterval: 15_000,
  });
}

export function useGpus() {
  return useQuery({
    queryKey: qk.gpus,
    queryFn: () => unwrap(api.GET("/api/v1/gpus", { params: { query: { include_retired: true } } })),
    staleTime: STALE.live,
    refetchInterval: 15_000,
  });
}

export function useGpu(id: string) {
  return useQuery({
    queryKey: qk.gpu(id),
    queryFn: () => unwrap(api.GET("/api/v1/gpus/{gpu_id}", { params: { path: { gpu_id: id } } })),
    staleTime: STALE.live,
    refetchInterval: 10_000,
  });
}

export function useGpuMetrics(id: string, range: Range) {
  return useQuery({
    queryKey: qk.gpuMetrics(id, range),
    queryFn: () => {
      const { start, end } = rangeBounds(range);
      return unwrap(api.GET("/api/v1/gpus/{gpu_id}/metrics", { params: { path: { gpu_id: id }, query: { start, end } } }));
    },
    staleTime: STALE.live,
    refetchInterval: range === "1h" ? 15_000 : 60_000,
  });
}

export function useGpuProcesses(id: string) {
  return useQuery({
    queryKey: qk.gpuProcesses(id),
    queryFn: () => unwrap(api.GET("/api/v1/gpus/{gpu_id}/processes", { params: { path: { gpu_id: id } } })),
    staleTime: STALE.live,
    refetchInterval: 15_000,
  });
}

export function useExplanation(id: string) {
  return useQuery({
    queryKey: qk.explain(id),
    queryFn: () => unwrap(api.GET("/api/v1/gpus/{gpu_id}/explain", { params: { path: { gpu_id: id } } })),
    staleTime: STALE.analytics,
    refetchInterval: 60_000,
  });
}

export function useFleetSeries(range: Range) {
  return useQuery({
    queryKey: qk.fleetSeries(range),
    queryFn: () => unwrap(api.GET("/api/v1/fleet/series", { params: { query: rangeBounds(range) } })),
    staleTime: STALE.analytics,
    refetchInterval: 60_000,
  });
}

export function useEnrolmentTokens(enabled: boolean) {
  return useQuery({
    queryKey: qk.enrolmentTokens,
    queryFn: () => unwrap(api.GET("/api/v1/enrolment-tokens")),
    staleTime: STALE.config,
    enabled,
  });
}

function useInvalidateFleet() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: qk.hosts });
    void client.invalidateQueries({ queryKey: qk.gpus });
    void client.invalidateQueries({ queryKey: qk.live });
    void client.invalidateQueries({ queryKey: qk.enrolmentTokens });
    void client.invalidateQueries({ queryKey: qk.overview });
  };
}

export function useCreateEnrolmentToken() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (body: EnrolmentTokenIn) => unwrap(api.POST("/api/v1/enrolment-tokens", { body })),
    onSuccess: done,
  });
}

export function useRevokeEnrolmentToken() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/v1/enrolment-tokens/{token_id}/revoke", { params: { path: { token_id: id } } })),
    onSuccess: done,
  });
}

export function useUpdateHost() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: HostUpdate }) =>
      unwrap(api.PATCH("/api/v1/hosts/{host_id}", { params: { path: { host_id: id } }, body })),
    onSuccess: done,
  });
}

export function useRevokeHost() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/hosts/{host_id}/revoke", { params: { path: { host_id: id } } })),
    onSuccess: done,
  });
}

export function useRetireGpu() {
  const done = useInvalidateFleet();
  return useMutation({
    mutationFn: ({ id, retired }: { id: string; retired: boolean }) =>
      unwrap(api.PATCH("/api/v1/gpus/{gpu_id}", { params: { path: { gpu_id: id } }, body: { retired } })),
    onSuccess: done,
  });
}
