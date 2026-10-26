"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { api, unwrap } from "@/lib/api/client";
import type { Gpu } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export type StreamState = "connecting" | "live" | "polling";

/**
 * Every GPU with its newest sample, kept current by the server-sent event stream
 * (/api/v1/live/stream pushes a snapshot whenever an agent reports). If the stream cannot
 * connect (a proxy that buffers, a network blip), the query falls back to polling every
 * five seconds, and the stream retries in the background.
 */
export function useLiveGpus(): { query: ReturnType<typeof useQuery<Gpu[]>>; stream: StreamState } {
  const client = useQueryClient();
  const [stream, setStream] = React.useState<StreamState>("connecting");

  React.useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      setStream("polling");
      return;
    }
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;
    const connect = () => {
      source = new EventSource("/api/v1/live/stream", { withCredentials: true });
      source.addEventListener("snapshot", (event) => {
        try {
          client.setQueryData(qk.live, JSON.parse((event as MessageEvent<string>).data) as Gpu[]);
          setStream("live");
        } catch {
          // A malformed frame is skipped; the next snapshot replaces it.
        }
      });
      source.onerror = () => {
        source?.close();
        setStream("polling");
        if (!closed) retry = setTimeout(connect, 15_000);
      };
    };
    connect();
    return () => {
      closed = true;
      source?.close();
      if (retry) clearTimeout(retry);
    };
  }, [client]);

  const query = useQuery({
    queryKey: qk.live,
    queryFn: () => unwrap(api.GET("/api/v1/live")),
    staleTime: STALE.live,
    refetchInterval: stream === "live" ? false : 5_000,
  });
  return { query, stream };
}
