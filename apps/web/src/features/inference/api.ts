"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";
import { rangeBounds, type Range } from "@/lib/range";

export function useInferenceEndpoints() {
  return useQuery({
    queryKey: qk.inference,
    queryFn: () => unwrap(api.GET("/api/v1/inference/endpoints")),
    staleTime: STALE.analytics,
    refetchInterval: 30_000,
  });
}

export function useInferenceSeries(id: string | null, range: Range) {
  return useQuery({
    queryKey: qk.inferenceSeries(id ?? "", range),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/inference/endpoints/{endpoint_id}/series", {
          params: { path: { endpoint_id: id ?? "" }, query: rangeBounds(range) },
        }),
      ),
    enabled: !!id,
    staleTime: STALE.analytics,
    refetchInterval: 60_000,
  });
}
