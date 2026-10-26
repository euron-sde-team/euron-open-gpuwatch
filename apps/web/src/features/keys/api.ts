"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { ApiKeyIn, ApiKeyUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useKeys(includeRevoked = false) {
  return useQuery({
    queryKey: qk.keys(includeRevoked),
    queryFn: () => unwrap(api.GET("/api/v1/keys", { params: { query: { include_revoked: includeRevoked } } })),
    staleTime: STALE.config,
  });
}

function useInvalidateKeys() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: qk.keysAll });
    void client.invalidateQueries({ queryKey: qk.system });
  };
}

export function useCreateKey() {
  const done = useInvalidateKeys();
  return useMutation({ mutationFn: (body: ApiKeyIn) => unwrap(api.POST("/api/v1/keys", { body })), onSuccess: done });
}

export function useUpdateKey() {
  const done = useInvalidateKeys();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ApiKeyUpdate }) =>
      unwrap(api.PATCH("/api/v1/keys/{key_id}", { params: { path: { key_id: id } }, body })),
    onSuccess: done,
  });
}

export function useRevokeKey() {
  const done = useInvalidateKeys();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/keys/{key_id}/revoke", { params: { path: { key_id: id } } })),
    onSuccess: done,
  });
}
