"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useSystemInfo() {
  return useQuery({ queryKey: qk.system, queryFn: () => unwrap(api.GET("/api/v1/system")), staleTime: STALE.config });
}
