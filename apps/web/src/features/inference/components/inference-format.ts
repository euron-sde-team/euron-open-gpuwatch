import { formatCompact } from "@/lib/format";

/** A per-second rate: 0.42, 3.1, 12, 1.4K. */
export function formatRate(v: number): string {
  if (v === 0) return "0";
  if (v < 10) return v.toFixed(2).replace(/\.?0+$/, "");
  return formatCompact(v);
}

export function endpointKindLabel(kind: string): string {
  if (kind === "vllm") return "vLLM";
  if (kind === "tgi") return "TGI";
  return kind.toUpperCase();
}
