"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as React from "react";
import { toast } from "sonner";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

import { ApiError } from "./api/errors";
import { isSessionExpired, loginUrl } from "./auth-redirect";
import { qk } from "./query-keys";
import { useUiPrefs } from "./store";

let redirecting = false;

/**
 * Any 401 from a query or mutation ends the session in the UI: one toast, then a hard
 * navigation to /login that keeps where the person was. The very first /auth/me check
 * of a signed-out visitor redirects quietly (nothing "expired").
 */
function handleUnauthorized(err: unknown, client: QueryClient, quiet: boolean) {
  if (!isSessionExpired(err) || redirecting || typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  redirecting = true;
  client.clear();
  if (!quiet) toast.error("Your session expired. Sign in again.", { id: "session-expired" });
  window.location.assign(loginUrl(window.location.pathname, window.location.search, quiet ? undefined : "expired"));
}

function makeClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (err, query) => {
        const isMe = query.queryKey[0] === qk.me[0] && query.queryKey[1] === qk.me[1];
        handleUnauthorized(err, client, isMe && query.state.data === undefined);
      },
    }),
    mutationCache: new MutationCache({
      onError: (err) => handleUnauthorized(err, client, false),
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (count, err) => {
          // Client errors will not fix themselves; retry only network and 5xx, twice.
          if (err instanceof ApiError && err.status >= 400 && err.status < 500) return false;
          return count < 2;
        },
      },
      mutations: { retry: false },
    },
  });
  return client;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeClient);

  React.useEffect(() => {
    void useUiPrefs.persist.rehydrate();
  }, []);

  return (
    <QueryClientProvider client={client}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        <TooltipProvider>
          {children}
          <Toaster />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
