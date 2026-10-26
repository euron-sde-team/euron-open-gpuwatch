import { describe, expect, it } from "vitest";

import {
  computeDelta,
  formatBytes,
  formatCompact,
  formatDelta,
  formatHours,
  formatMemory,
  formatNusd,
  formatPercent,
  formatRate,
  formatRatio,
  formatSeconds,
  formatUsd,
  metric,
  NOT_AVAILABLE,
} from "@/lib/format";

describe("money", () => {
  it("formats dollars with cents and keeps tiny amounts readable", () => {
    expect(formatUsd(1234.5)).toBe("$1,234.50");
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(0.000412)).toBe("$0.000412");
    expect(formatUsd(250_000)).toBe("$250,000");
    expect(formatUsd(null)).toBe("n/a");
  });
  it("turns nano-dollars into dollars", () => {
    expect(formatNusd(2_490_000_000)).toBe("$2.49");
    expect(formatNusd(1_000)).toBe("$0.000001");
    expect(formatNusd(undefined)).toBe("n/a");
  });
  it("labels hourly rates and their absence", () => {
    expect(formatRate(600_000_000)).toBe("$0.60/h");
    expect(formatRate(null)).toBe("No rate");
  });
});

describe("metrics", () => {
  it("never renders a missing metric as zero", () => {
    expect(metric.pct(null)).toBe(NOT_AVAILABLE);
    expect(metric.temp(undefined)).toBe(NOT_AVAILABLE);
    expect(metric.watts(null)).toBe(NOT_AVAILABLE);
    expect(formatMemory(null)).toBe(NOT_AVAILABLE);
    expect(metric.pct(0)).toBe("0%");
  });
  it("formats readings with their units", () => {
    expect(metric.temp(64.6)).toBe("65°C");
    expect(metric.watts(312.4)).toBe("312 W");
    expect(metric.mhz(1410)).toBe("1,410 MHz");
    expect(metric.kbps(12_000)).toBe("12 MB/s");
    expect(metric.kbps(9_800_000)).toBe("9.8 GB/s");
    expect(formatMemory(512)).toBe("512 MiB");
    expect(formatMemory(40_960)).toBe("40 GiB");
    expect(formatMemory(81_559)).toBe("79.6 GiB");
  });
  it("formats durations", () => {
    expect(formatHours(0.5)).toBe("30 min");
    expect(formatHours(14.25)).toBe("14.3 h");
    expect(formatHours(250)).toBe("250 h");
    expect(formatSeconds(0.084)).toBe("84 ms");
    expect(formatSeconds(1.234)).toBe("1.23 s");
    expect(formatSeconds(null)).toBe(NOT_AVAILABLE);
  });
});

describe("numbers", () => {
  it("formats percentages, ratios, compact numbers and bytes", () => {
    expect(formatPercent(60.4)).toBe("60.4%");
    expect(formatPercent(60)).toBe("60%");
    expect(formatRatio(0.2462)).toBe("24.6%");
    expect(formatCompact(13_900_000)).toBe("13.9M");
    expect(formatCompact(7.5)).toBe("7.5");
    expect(formatBytes(2048)).toBe("2 KB");
  });
  it("computes deltas only with a baseline", () => {
    expect(computeDelta(135, 100)).toEqual({ pct: 35, direction: "up" });
    expect(computeDelta(5, 0)).toBeNull();
    expect(formatDelta({ pct: -12.34, direction: "down" })).toBe("-12.3%");
  });
});
