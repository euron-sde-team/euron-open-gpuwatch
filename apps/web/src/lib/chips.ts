/**
 * One mapping from states to a chip tone, label and explanation, so a status reads the same
 * on every screen.
 */

export type Tone = "success" | "savings" | "info" | "primary" | "warning" | "danger" | "neutral";

export interface ChipSpec {
  label: string;
  tone: Tone;
  hint: string;
}

const HOST: Record<string, ChipSpec> = {
  online: { label: "Online", tone: "success", hint: "The agent reported within the last minute." },
  disconnected: { label: "Disconnected", tone: "danger", hint: "The agent stopped reporting. Check the machine, the agent and the network." },
  pending: { label: "Waiting", tone: "neutral", hint: "Enrolled, but no data yet. The agent sends its first batch within seconds." },
  revoked: { label: "Revoked", tone: "neutral", hint: "Its token was revoked; data is no longer accepted. History stays." },
};

const GPU: Record<string, ChipSpec> = {
  ok: { label: "Reporting", tone: "success", hint: "Readings arrive every few seconds." },
  lost: { label: "Lost", tone: "danger", hint: "The host still reports, but this GPU stopped appearing (fell off the bus, driver reset)." },
  offline: { label: "Host offline", tone: "warning", hint: "Its host stopped reporting." },
  retired: { label: "Retired", tone: "neutral", hint: "Taken out of service. It comes back if it reports again." },
};

const SEVERITY: Record<string, ChipSpec> = {
  critical: { label: "Critical", tone: "danger", hint: "Needs attention now." },
  warning: { label: "Warning", tone: "warning", hint: "Costs money or performance; worth fixing soon." },
  info: { label: "Info", tone: "info", hint: "An opportunity to save or speed up." },
};

const INSIGHT_STATUS: Record<string, ChipSpec> = {
  open: { label: "Open", tone: "primary", hint: "Detected and not yet looked at." },
  acknowledged: { label: "Acknowledged", tone: "info", hint: "Someone is on it. Still re-evaluated every few minutes." },
  dismissed: { label: "Dismissed", tone: "neutral", hint: "Hidden until the condition clears and returns." },
  resolved: { label: "Resolved", tone: "success", hint: "The condition cleared by itself." },
};

const INSIGHT_KIND: Record<string, string> = {
  idle_loaded: "Idle with a model loaded",
  idle_empty: "Nothing running",
  underused: "Underused while busy",
  oversized_vram: "Oversized memory",
  throttled: "Throttled",
  memory_pressure: "Memory pressure",
  gpu_errors: "Hardware errors",
  inference_queueing: "Inference queueing",
  inference_overprovisioned: "Inference overprovisioned",
};

function fallback(value: string): ChipSpec {
  const label = value ? value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ") : "Unknown";
  return { label, tone: "neutral", hint: "" };
}

export const hostChip = (v: string | null | undefined): ChipSpec => HOST[v ?? ""] ?? fallback(v ?? "");
export const gpuChip = (v: string | null | undefined): ChipSpec => GPU[v ?? ""] ?? fallback(v ?? "");
export const severityChip = (v: string | null | undefined): ChipSpec => SEVERITY[v ?? ""] ?? fallback(v ?? "");
export const insightStatusChip = (v: string | null | undefined): ChipSpec => INSIGHT_STATUS[v ?? ""] ?? fallback(v ?? "");
export const insightKindLabel = (v: string): string => INSIGHT_KIND[v] ?? fallback(v).label;

/** Utilization as a tone: idle is neutral, busy is good, pegged is fine too. */
export function tempTone(c: number | null | undefined): Tone {
  if (c == null) return "neutral";
  if (c >= 85) return "danger";
  if (c >= 78) return "warning";
  return "neutral";
}

/** NVML clocks event reasons that slow a busy GPU down, decoded for people. */
export function throttleReasons(bits: number | null | undefined): string[] {
  if (bits == null) return [];
  const out: string[] = [];
  if (bits & 0x4 || bits & 0x80) out.push("Power cap");
  if (bits & 0x20 || bits & 0x40) out.push("Thermal");
  if (bits & 0x8) out.push("Hardware slowdown");
  return out;
}
