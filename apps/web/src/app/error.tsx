"use client";

import { ErrorState } from "@/components/error-state";

export default function GlobalRouteError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="surface w-full max-w-lg">
        <ErrorState error={error} title="This page hit an unexpected error" onRetry={reset} />
      </div>
    </div>
  );
}
