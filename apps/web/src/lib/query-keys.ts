/**
 * Query keys in one place, so invalidation after a mutation names exactly what it
 * touched.
 */
export const qk = {
  me: ["auth", "me"] as const,
  system: ["system"] as const,
  users: ["users"] as const,
  keys: (includeRevoked = false) => ["keys", { includeRevoked }] as const,
  keysAll: ["keys"] as const,
  audit: (action?: string) => ["audit", { action }] as const,

  overview: ["overview"] as const,
  live: ["live"] as const,
  hosts: ["hosts"] as const,
  host: (id: string) => ["hosts", id] as const,
  gpus: ["gpus"] as const,
  gpu: (id: string) => ["gpus", id] as const,
  gpuMetrics: (id: string, range: string) => ["gpus", id, "metrics", range] as const,
  gpuProcesses: (id: string) => ["gpus", id, "processes"] as const,
  explain: (id: string) => ["gpus", id, "explain"] as const,
  fleetSeries: (range: string) => ["fleet", "series", range] as const,
  enrolmentTokens: ["enrolment-tokens"] as const,

  costs: (groupBy: string, range: string) => ["costs", "summary", groupBy, range] as const,
  costSeries: (groupBy: string, range: string) => ["costs", "series", groupBy, range] as const,
  costsAll: ["costs"] as const,
  rates: ["rates"] as const,
  workloadRules: ["workload-rules"] as const,
  reports: ["reports"] as const,

  insights: (status?: string) => ["insights", { status }] as const,
  insightsAll: ["insights"] as const,
  insightSettings: ["settings", "insights"] as const,

  alertRules: ["alerts", "rules"] as const,
  alertEvents: (firing: boolean) => ["alerts", "events", { firing }] as const,
  alertEventsAll: ["alerts", "events"] as const,
  channels: ["alerts", "channels"] as const,
  notifications: ["alerts", "notifications"] as const,

  inference: ["inference"] as const,
  inferenceSeries: (id: string, range: string) => ["inference", id, range] as const,
};

/** staleTime per kind of data, chosen deliberately (see docs/architecture/caching.md). */
export const STALE = {
  analytics: 15_000,
  config: 30_000,
  live: 5_000,
  static: 5 * 60_000,
} as const;
