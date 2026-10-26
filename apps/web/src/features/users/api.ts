"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { User, UserCreate, UserUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useUsers(enabled = true) {
  return useQuery({ queryKey: qk.users, queryFn: () => unwrap(api.GET("/api/v1/users")), staleTime: STALE.config, enabled });
}

export function useCreateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreate) => unwrap(api.POST("/api/v1/users", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.users }),
  });
}

/** Role and enabled changes apply optimistically and roll back on error. */
export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserUpdate }) =>
      unwrap(api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body })),
    onMutate: async ({ id, body }) => {
      await client.cancelQueries({ queryKey: qk.users });
      const previous = client.getQueryData<User[]>(qk.users);
      client.setQueryData<User[]>(qk.users, (list) =>
        list?.map((u) =>
          u.id === id
            ? { ...u, ...(body.role ? { role: body.role } : {}), ...(body.disabled != null ? { disabled: body.disabled } : {}) }
            : u,
        ),
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) client.setQueryData(qk.users, ctx.previous);
    },
    onSettled: () => void client.invalidateQueries({ queryKey: qk.users }),
  });
}
