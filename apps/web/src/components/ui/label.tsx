import * as React from "react";

import { cn } from "@/lib/cn";

function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn("flex items-center gap-1.5 text-[13px] font-medium text-foreground select-none", className)}
      {...props}
    />
  );
}

function FieldHint({ className, ...props }: React.ComponentProps<"p">) {
  return <p data-slot="field-hint" className={cn("text-xs leading-snug text-muted-foreground", className)} {...props} />;
}

function FieldError({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p data-slot="field-error" role="alert" className={cn("text-xs leading-snug font-medium text-danger", className)} {...props} />
  );
}

/** Label, control and hint stacked with consistent spacing. */
function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
  labelExtra,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
  labelExtra?: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>
        {label}
        {labelExtra}
      </Label>
      {children}
      {error ? <FieldError>{error}</FieldError> : hint ? <FieldHint>{hint}</FieldHint> : null}
    </div>
  );
}

export { Label, FieldHint, FieldError, Field };
