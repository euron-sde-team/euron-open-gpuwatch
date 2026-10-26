/** Time ranges the dashboard offers, and their start and end for API queries. */

export const RANGES = ["1h", "6h", "24h", "7d", "30d"] as const;
export type Range = (typeof RANGES)[number];

const SECONDS: Record<Range, number> = {
  "1h": 3600,
  "6h": 6 * 3600,
  "24h": 86_400,
  "7d": 7 * 86_400,
  "30d": 30 * 86_400,
};

export const RANGE_LABEL: Record<Range, string> = {
  "1h": "1h",
  "6h": "6h",
  "24h": "24h",
  "7d": "7d",
  "30d": "30d",
};

export function isRange(v: unknown): v is Range {
  return typeof v === "string" && (RANGES as readonly string[]).includes(v);
}

/** Start and end of a range ending now. The end is rounded up to the minute so the query
 * key (and the cache) stays stable within a minute. */
export function rangeBounds(range: Range, now: Date = new Date()): { start: string; end: string } {
  const end = new Date(Math.ceil(now.getTime() / 60_000) * 60_000);
  const start = new Date(end.getTime() - SECONDS[range] * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

export function rangeSeconds(range: Range): number {
  return SECONDS[range];
}
