"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useOverview() {
  return useQuery({
    queryKey: qk.overview,
    queryFn: () => unwrap(api.GET("/api/v1/overview")),
    staleTime: STALE.analytics,
    refetchInterval: 30_000,
  });
}
