"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { AlertRuleIn, ChannelIn } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useAlertEvents(firing = false) {
  return useQuery({
    queryKey: qk.alertEvents(firing),
    queryFn: () => unwrap(api.GET("/api/v1/alerts/events", { params: { query: { firing } } })),
    staleTime: STALE.live,
    refetchInterval: 15_000,
  });
}

export function useAlertRules() {
  return useQuery({ queryKey: qk.alertRules, queryFn: () => unwrap(api.GET("/api/v1/alerts/rules")), staleTime: STALE.config });
}

export function useChannels() {
  return useQuery({ queryKey: qk.channels, queryFn: () => unwrap(api.GET("/api/v1/alerts/channels")), staleTime: STALE.config });
}

export function useNotifications() {
  return useQuery({
    queryKey: qk.notifications,
    queryFn: () => unwrap(api.GET("/api/v1/alerts/notifications")),
    staleTime: STALE.live,
    refetchInterval: 15_000,
  });
}

function useInvalidateAlerts() {
  const client = useQueryClient();
  return () => {
    for (const key of [qk.alertRules, qk.alertEventsAll, qk.channels, qk.notifications, qk.overview]) {
      void client.invalidateQueries({ queryKey: key });
    }
  };
}

export function useSaveAlertRule() {
  const done = useInvalidateAlerts();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: AlertRuleIn }) =>
      id
        ? unwrap(api.PUT("/api/v1/alerts/rules/{rule_id}", { params: { path: { rule_id: id } }, body }))
        : unwrap(api.POST("/api/v1/alerts/rules", { body })),
    onSuccess: done,
  });
}

export function useDeleteAlertRule() {
  const done = useInvalidateAlerts();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/alerts/rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: done,
  });
}

export function useSaveChannel() {
  const done = useInvalidateAlerts();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ChannelIn }) =>
      id
        ? unwrap(api.PUT("/api/v1/alerts/channels/{channel_id}", { params: { path: { channel_id: id } }, body }))
        : unwrap(api.POST("/api/v1/alerts/channels", { body })),
    onSuccess: done,
  });
}

export function useDeleteChannel() {
  const done = useInvalidateAlerts();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/alerts/channels/{channel_id}", { params: { path: { channel_id: id } } })),
    onSuccess: done,
  });
}

export function useTestChannel() {
  const done = useInvalidateAlerts();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/v1/alerts/channels/{channel_id}/test", { params: { path: { channel_id: id } } })),
    onSuccess: done,
  });
}
