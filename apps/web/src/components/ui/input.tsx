import * as React from "react";

import { cn } from "@/lib/cn";

const fieldBase = [
  "w-full min-w-0 rounded-lg bg-card text-sm text-foreground shadow-[var(--elev-1)] ring-1 ring-input ring-inset",
  "transition-[box-shadow,background-color] duration-150 outline-none",
  "placeholder:text-faint",
  "focus-visible:ring-2 focus-visible:ring-ring",
  "disabled:cursor-not-allowed disabled:opacity-60",
  "aria-invalid:ring-2 aria-invalid:ring-danger",
  "dark:bg-muted/60",
].join(" ");

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return <input type={type} data-slot="input" className={cn(fieldBase, "h-9 px-3", className)} {...props} />;
}

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(fieldBase, "min-h-20 px-3 py-2 leading-relaxed", className)}
      {...props}
    />
  );
}

export { Input, Textarea, fieldBase };
