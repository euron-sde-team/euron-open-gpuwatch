"use client";

import { RotateCwIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

/** What went wrong, in words, plus a retry. Used by every async view. */
export function ErrorState({
  error,
  onRetry,
  title = "Could not load this",
  className,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      role="alert"
      data-qa="error-state"
      className={cn("flex flex-col items-center justify-center text-center", compact ? "px-6 py-8" : "px-6 py-14", className)}
    >
      <div className="mb-3 flex size-10 items-center justify-center rounded-xl bg-danger-soft text-danger">
        <TriangleAlertIcon className="size-5" />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 max-w-md text-[13px] leading-relaxed text-muted-foreground">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          <RotateCwIcon />
          Retry
        </Button>
      )}
    </div>
  );
}
