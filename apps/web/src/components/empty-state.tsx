import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/cn";

/**
 * Never a dead end: says what this place is, why it matters, and offers one action.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  compact = false,
}: {
  icon: LucideIcon;
  title: string;
  description: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center", compact ? "px-6 py-8" : "px-6 py-14", className)}>
      <div className="mb-3.5 flex size-11 items-center justify-center rounded-xl bg-primary-soft text-primary">
        <Icon className="size-5" />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-muted-foreground">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
