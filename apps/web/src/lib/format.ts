/**
 * Number and date formatting used everywhere a figure is shown. Money arrives from the API
 * as integer nano-dollars (`*_nusd`); `formatNusd` turns it into dollars. A missing metric
 * is `null` and renders as "Not available", never as 0.
 */

export const NOT_AVAILABLE = "Not available";

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** $1,234.56 for normal amounts, $0.000412 for tiny ones, $0.00 for exactly zero. */
export function formatUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  if (value === 0) return "$0.00";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 100_000) return usd0.format(value);
  if (abs >= 1) return usd2.format(value);
  if (abs < 0.000001) return `${sign}<$0.000001`;
  const decimals = Math.min(8, Math.max(2, 2 - Math.floor(Math.log10(abs))));
  let text = abs.toFixed(decimals);
  text = text.replace(/(\.\d\d\d*?)0+$/, "$1");
  return `${sign}$${text}`;
}

/** Integer nano-dollars (the API's money unit) as dollars. */
export function formatNusd(nusd: number | null | undefined): string {
  if (nusd == null || !Number.isFinite(nusd)) return "n/a";
  return formatUsd(nusd / 1e9);
}

/** "$2.49/h" for an hourly rate in nano-dollars. */
export function formatRate(nusdPerHour: number | null | undefined): string {
  if (nusdPerHour == null) return "No rate";
  return `${formatNusd(nusdPerHour)}/h`;
}

function trim(n: number): string {
  const fixed = n >= 100 ? n.toFixed(0) : n.toFixed(1);
  return fixed.replace(/\.0$/, "");
}

/** 845, 12.4K, 13.9M, 1.2B. */
export function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}${trim(abs / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${sign}${trim(abs / 1_000_000)}M`;
  if (abs >= 1_000) return `${sign}${trim(abs / 1_000)}K`;
  return `${sign}${abs >= 10 ? intFmt.format(abs) : trim(abs)}`;
}

/** 14,923. */
export function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return intFmt.format(value);
}

/** A 0..1 ratio as a percentage: 0.2462 becomes 24.6%. */
export function formatRatio(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return formatPercent(value * 100, digits);
}

/** A value already in percent: 60.4 becomes 60.4%. Whole numbers drop the decimal. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  const fixed = value.toFixed(digits);
  return `${fixed.replace(/\.0+$/, "")}%`;
}

/** Memory in MiB as GiB: 40960 becomes "40 GiB", 512 becomes "512 MiB". */
export function formatMemory(mib: number | null | undefined): string {
  if (mib == null || !Number.isFinite(mib)) return NOT_AVAILABLE;
  if (mib < 1024) return `${Math.round(mib)} MiB`;
  const gib = mib / 1024;
  return `${gib >= 100 ? gib.toFixed(0) : gib.toFixed(1).replace(/\.0$/, "")} GiB`;
}

/** Each metric's unit, with "Not available" for null (the driver did not report it). */
export const metric = {
  pct: (v: number | null | undefined) => (v == null ? NOT_AVAILABLE : formatPercent(v, 0)),
  temp: (v: number | null | undefined) => (v == null ? NOT_AVAILABLE : `${Math.round(v)}°C`),
  watts: (v: number | null | undefined) => (v == null ? NOT_AVAILABLE : `${Math.round(v)} W`),
  mhz: (v: number | null | undefined) => (v == null ? NOT_AVAILABLE : `${formatNumber(v)} MHz`),
  memory: formatMemory,
  count: (v: number | null | undefined) => (v == null ? NOT_AVAILABLE : formatNumber(v)),
  kbps: (v: number | null | undefined) => {
    if (v == null) return NOT_AVAILABLE;
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} GB/s`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)} MB/s`;
    return `${Math.round(v)} KB/s`;
  },
};

/** Hours as "14.2 h", or "45 min" under an hour. */
export function formatHours(hours: number | null | undefined): string {
  if (hours == null || !Number.isFinite(hours)) return "n/a";
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  return hours >= 100 ? `${formatNumber(hours)} h` : `${hours.toFixed(1).replace(/\.0$/, "")} h`;
}

/** Seconds: 0.084 s as "84 ms", 1.24 s as "1.24 s". */
export function formatSeconds(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s)) return NOT_AVAILABLE;
  if (s < 1) return `${Math.round(s * 1000)} ms`;
  return `${s.toFixed(s < 10 ? 2 : 1)} s`;
}

/** 610 ms, 1.24 s. */
export function formatLatency(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "n/a";
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return "n/a";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${trim(bytes / 1024)} KB`;
  return `${trim(bytes / (1024 * 1024))} MB`;
}

export interface Delta {
  /** Signed percentage change, e.g. 36.6 for +36.6%. */
  pct: number;
  direction: "up" | "down" | "flat";
}

/**
 * Change versus the previous period. Returns null when there is no baseline (previous
 * is zero or missing), because "+infinity %" helps nobody.
 */
export function computeDelta(current: number | null | undefined, previous: number | null | undefined): Delta | null {
  if (current == null || previous == null || !Number.isFinite(current) || !Number.isFinite(previous)) return null;
  if (previous === 0) return null;
  const pct = ((current - previous) / Math.abs(previous)) * 100;
  const direction = Math.abs(pct) < 0.05 ? "flat" : pct > 0 ? "up" : "down";
  return { pct, direction };
}

export function formatDelta(delta: Delta): string {
  if (delta.direction === "flat") return "0%";
  const abs = Math.abs(delta.pct);
  const text = abs >= 100 ? abs.toFixed(0) : abs.toFixed(1);
  return `${delta.pct > 0 ? "+" : "-"}${text.replace(/\.0$/, "")}%`;
}

const dateTimeFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : dateTimeFmt.format(d);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : dateFmt.format(d);
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : timeFmt.format(d);
}

/** "just now", "5m ago", "3h ago", "2d ago", then a date. */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "n/a";
  const diff = Math.round((now.getTime() - d.getTime()) / 1000);
  const future = diff < 0;
  const s = Math.abs(diff);
  const wrap = (v: string) => (future ? `in ${v}` : `${v} ago`);
  if (s < 45) return future ? "in a moment" : "just now";
  if (s < 3600) return wrap(`${Math.max(1, Math.round(s / 60))}m`);
  if (s < 86_400) return wrap(`${Math.round(s / 3600)}h`);
  if (s < 86_400 * 14) return wrap(`${Math.round(s / 86_400)}d`);
  return formatDate(iso);
}

/** Initials for an avatar: "Avery Chen" becomes "AC". */
export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}
