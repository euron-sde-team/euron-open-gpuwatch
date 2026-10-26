"use client";

import { useId } from "react";

import { cn } from "@/lib/cn";

/** The GPUWatch mark: a GPU die with a pulse line running across it. */
export function WatchMark({ className }: { className?: string }) {
  // A unique gradient id per instance: when the first SVG defining a shared id sits in a
  // hidden subtree (the collapsed sidebar on phones), browsers resolve the fill to nothing.
  const gradient = `gw-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7 shrink-0", className)}>
      <defs>
        <linearGradient id={gradient} x1="4" y1="3" x2="28" y2="29" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--chart-mem)" />
          <stop offset="1" stopColor="var(--primary)" />
        </linearGradient>
      </defs>
      <rect x="2.5" y="2.5" width="27" height="27" rx="8" fill={`url(#${gradient})`} />
      <rect x="8" y="8" width="16" height="16" rx="3" fill="white" fillOpacity="0.18" />
      <path
        d="M6 17h5l2.2-5 3.4 9 2.4-6 1.5 2H26"
        fill="none"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function WatchLogo({ className, collapsed = false }: { className?: string; collapsed?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <WatchMark />
      {!collapsed && <span className="text-[15px] font-semibold tracking-[-0.02em] text-foreground">GPUWatch</span>}
    </span>
  );
}
