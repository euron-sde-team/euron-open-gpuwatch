import * as React from "react";

import { cn } from "@/lib/cn";

export function PageHeader({
  title,
  description,
  actions,
  className,
  eyebrow,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  eyebrow?: React.ReactNode;
}) {
  return (
    <div className={cn("mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5">{eyebrow}</div>}
        <h1 className="text-[22px] leading-tight font-semibold tracking-[-0.02em] text-foreground">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
