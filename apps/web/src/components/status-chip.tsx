"use client";

import { FlaskConicalIcon } from "lucide-react";

import { Chip } from "@/components/ui/chip";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { GLOSSARY } from "@/lib/glossary";
import { gpuChip, hostChip, insightStatusChip, severityChip, type ChipSpec } from "@/lib/chips";

export function SpecChip({ spec, withHint = true, dot = true }: { spec: ChipSpec; withHint?: boolean; dot?: boolean }) {
  const chip = (
    <Chip tone={spec.tone} dot={dot}>
      {spec.label}
    </Chip>
  );
  if (!withHint || !spec.hint) return chip;
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} className="inline-flex rounded-full focus-visible:outline-2 focus-visible:outline-ring" />}>
        {chip}
      </TooltipTrigger>
      <TooltipContent>{spec.hint}</TooltipContent>
    </Tooltip>
  );
}

export const HostChip = ({ value }: { value: string }) => <SpecChip spec={hostChip(value)} />;
export const GpuChip = ({ value }: { value: string }) => <SpecChip spec={gpuChip(value)} />;
export const SeverityChip = ({ value }: { value: string }) => <SpecChip spec={severityChip(value)} />;
export const InsightStatusChip = ({ value }: { value: string }) => <SpecChip spec={insightStatusChip(value)} dot={false} />;

/** Marks demo hosts so simulated data is never mistaken for a real GPU. */
export function SimBadge() {
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} className="inline-flex rounded-full focus-visible:outline-2 focus-visible:outline-ring" />}>
        <Chip tone="neutral">
          <FlaskConicalIcon className="size-3" />
          Simulated
        </Chip>
      </TooltipTrigger>
      <TooltipContent>{GLOSSARY.simulated}</TooltipContent>
    </Tooltip>
  );
}
