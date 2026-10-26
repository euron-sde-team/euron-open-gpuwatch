"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function CopyButton({
  value,
  label = "Copy",
  className,
  iconOnly = false,
  variant = "outline",
}: {
  value: string;
  label?: string;
  className?: string;
  iconOnly?: boolean;
  variant?: "outline" | "ghost" | "subtle" | "default";
}) {
  const [copied, setCopied] = React.useState(false);
  React.useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(t);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      toast.error("Copy failed. Select the text and copy it manually.");
    }
  }

  return (
    <Button
      type="button"
      variant={variant}
      size={iconOnly ? "icon-xs" : "xs"}
      className={cn(className)}
      onClick={copy}
      aria-label={iconOnly ? label : undefined}
    >
      {copied ? <CheckIcon className="text-savings" /> : <CopyIcon />}
      {!iconOnly && (copied ? "Copied" : label)}
    </Button>
  );
}
