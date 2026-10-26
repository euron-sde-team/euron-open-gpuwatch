"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useAuditLog(action?: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: qk.audit(action),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/audit", { params: { query: { cursor: pageParam, limit: 50, action: action || null } } })),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: STALE.config,
    enabled,
  });
}
