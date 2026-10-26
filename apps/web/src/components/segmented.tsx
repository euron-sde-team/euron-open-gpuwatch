"use client";

import * as React from "react";

import { cn } from "@/lib/cn";

/** Radio group drawn as a segmented control, for 2 to 4 short choices in forms. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  disabled,
  className,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: React.ReactNode; description?: string }[];
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn("grid auto-cols-fr grid-flow-col gap-0.5 rounded-lg bg-muted p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          disabled={disabled}
          title={o.description}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-8 rounded-md px-3 text-[13px] font-medium text-muted-foreground transition-[color,background-color,box-shadow] hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50",
            value === o.value && "bg-card text-foreground shadow-[var(--elev-1)] dark:bg-accent",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
