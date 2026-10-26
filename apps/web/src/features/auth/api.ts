"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { canManageUsers, canWrite } from "@/lib/roles";

export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
    staleTime: STALE.static,
    retry: false,
  });
}

/** Role flags for the signed-in user. While loading, everything is read only. */
export function usePermissions(): { user: User | undefined; canWrite: boolean; canManageUsers: boolean } {
  const { data } = useMe();
  return { user: data, canWrite: canWrite(data?.role), canManageUsers: canManageUsers(data?.role) };
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) => unwrap(api.POST("/api/v1/auth/login", { body })),
    onSuccess: (session) => {
      client.clear();
      client.setQueryData(qk.me, session.user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
    onSettled: () => client.clear(),
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      unwrap(api.POST("/api/v1/auth/password", { body })),
    onSuccess: (session) => client.setQueryData(qk.me, session.user),
  });
}
