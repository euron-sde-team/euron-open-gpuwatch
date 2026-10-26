/**
 * Named aliases over the generated OpenAPI types (`pnpm gen:api`). Nothing here is
 * hand-written: every shape comes from `schema.d.ts`, which is generated from
 * docs/api/openapi.yaml.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type User = S["UserOut"];
export type UserCreate = S["UserCreate"];
export type UserUpdate = S["UserUpdate"];
export type Session = S["SessionOut"];
export type ApiKey = S["KeyOut"];
export type ApiKeyCreated = S["KeyCreated"];
export type ApiKeyIn = S["KeyIn"];
export type ApiKeyUpdate = S["KeyUpdate"];
export type AuditEntry = S["AuditOut"];
export type SystemInfo = S["SystemInfo"];

export type Overview = S["Overview"];
export type Host = S["HostOut"];
export type HostUpdate = S["HostUpdate"];
export type Gpu = S["GpuOut"];
export type EnrolmentToken = S["EnrolmentTokenOut"];
export type EnrolmentTokenCreated = S["EnrolmentTokenCreated"];
export type EnrolmentTokenIn = S["EnrolmentTokenIn"];

export type MetricSeries = S["MetricSeries"];
export type MetricPoint = S["MetricPoint"];
export type FleetSeries = S["FleetSeries"];
export type FleetPoint = S["FleetPoint"];
export type GpuProcesses = S["GpuProcesses"];
export type ProcessRow = S["ProcessOut"];
export type WorkloadShare = S["WorkloadShare"];

export type CostSummary = S["CostSummary"];
export type CostRow = S["CostRow"];
export type CostSeries = S["CostSeries"];
export type Rate = S["RateOut"];
export type RateIn = S["RateIn"];
export type RateUpdate = S["RateUpdate"];
export type WorkloadRule = S["WorkloadRuleOut"];
export type WorkloadRuleIn = S["WorkloadRuleIn"];
export type Report = S["ReportOut"];
export type ReportIn = S["ReportIn"];

export type Insight = S["InsightOut"];
export type InsightSettings = S["InsightSettings"];
export type Explanation = S["Explanation"];

export type AlertRule = S["RuleOut"];
export type AlertRuleIn = S["RuleIn"];
export type AlertEvent = S["EventOut"];
export type Channel = S["ChannelOut"];
export type ChannelIn = S["ChannelIn"];
export type Notification = S["NotificationOut"];

export type InferenceEndpoint = S["EndpointOut"];
export type InferenceStats = S["InferenceStats"];
export type InferenceSeries = S["InferenceSeries"];
export type InferencePoint = S["InferencePoint"];

export type Role = NonNullable<UserCreate["role"]>;
export type GroupBy = NonNullable<CostSummary["group_by"]>;
export type InsightStatus = Insight["status"];
export type Severity = Insight["severity"];
export type HostStatus = Host["status"];
export type GpuStatus = Gpu["status"];

/** The newest sample of a GPU, as the live view carries it (null fields: not reported). */
export interface LiveSample {
  ts: string;
  interval_s?: number;
  util_gpu?: number | null;
  util_mem?: number | null;
  mem_used_mib?: number | null;
  mem_total_mib?: number | null;
  temp_c?: number | null;
  power_w?: number | null;
  power_limit_w?: number | null;
  fan_pct?: number | null;
  sm_clock_mhz?: number | null;
  mem_clock_mhz?: number | null;
  pstate?: number | null;
  throttle_reasons?: number | null;
  pcie_rx_kbps?: number | null;
  pcie_tx_kbps?: number | null;
  ecc_uncorrected?: number | null;
  xid?: number | null;
  procs?: number | null;
}
