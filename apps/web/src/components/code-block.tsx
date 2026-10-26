"use client";

import * as React from "react";

import { cn } from "@/lib/cn";

import { CopyButton } from "./copy-button";

export interface CodeSample {
  id: string;
  label: string;
  code: string;
}

/** Code with a copy button, optionally with language tabs. Always a dark slab. */
export function CodeBlock({ samples, className }: { samples: CodeSample[]; className?: string }) {
  const [active, setActive] = React.useState(samples[0]?.id ?? "");
  const current = samples.find((s) => s.id === active) ?? samples[0];
  if (!current) return null;
  return (
    <div className={cn("overflow-hidden rounded-xl bg-code-bg text-code-fg shadow-[var(--elev-1)] ring-1 ring-white/5", className)}>
      <div className="flex items-center justify-between gap-2 bg-white/[0.03] px-2 py-1.5">
        <div role="tablist" className="flex gap-0.5">
          {samples.map((s) => (
            <button
              key={s.id}
              role="tab"
              type="button"
              aria-selected={s.id === current.id}
              onClick={() => setActive(s.id)}
              className={cn(
                "h-6 rounded-md px-2.5 text-[12px] font-medium text-code-muted transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-ring",
                s.id === current.id && "bg-white/10 text-white",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
        <CopyButton
          value={current.code}
          variant="ghost"
          className="text-code-fg hover:bg-white/10 hover:text-white"
        />
      </div>
      <pre className="overflow-x-auto px-4 py-3.5 font-mono text-[12px] leading-[1.7]">
        <code>{current.code}</code>
      </pre>
    </div>
  );
}
