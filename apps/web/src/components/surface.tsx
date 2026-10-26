import * as React from "react";

import { cn } from "@/lib/cn";

/** The one container in the system: a filled card with a soft shadow, no outline. */
export function Surface({ className, ...props }: React.ComponentProps<"section">) {
  return <section className={cn("surface min-w-0", className)} {...props} />;
}

export function SurfaceHeader({
  title,
  description,
  action,
  className,
  titleExtra,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  titleExtra?: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3", className)}>
      <div className="min-w-0">
        <h2 className="flex items-center gap-1.5 text-[14px] font-semibold tracking-[-0.01em] text-foreground">
          {title}
          {titleExtra}
        </h2>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}
