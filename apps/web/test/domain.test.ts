import { describe, expect, it } from "vitest";

import { gpuChip, hostChip, insightKindLabel, severityChip, tempTone, throttleReasons } from "@/lib/chips";
import { activeNavItem } from "@/lib/nav";
import { isRange, rangeBounds } from "@/lib/range";
import { canManageUsers, canWrite, roleLabel } from "@/lib/roles";

describe("status chips", () => {
  it("maps every state to a tone and an explanation", () => {
    expect(hostChip("online")).toMatchObject({ tone: "success", label: "Online" });
    expect(hostChip("disconnected").tone).toBe("danger");
    expect(gpuChip("lost")).toMatchObject({ tone: "danger", label: "Lost" });
    expect(severityChip("critical").tone).toBe("danger");
    expect(hostChip("weird_state")).toMatchObject({ tone: "neutral", label: "Weird state" });
  });
  it("names insight kinds in plain words", () => {
    expect(insightKindLabel("idle_loaded")).toBe("Idle with a model loaded");
    expect(insightKindLabel("new_kind")).toBe("New kind");
  });
});

describe("driver readings", () => {
  it("decodes throttle reasons that slow a busy GPU", () => {
    expect(throttleReasons(0x4)).toEqual(["Power cap"]);
    expect(throttleReasons(0x20 | 0x8)).toEqual(["Thermal", "Hardware slowdown"]);
    expect(throttleReasons(0x1)).toEqual([]);
    expect(throttleReasons(null)).toEqual([]);
  });
  it("colors temperature only when it matters", () => {
    expect(tempTone(60)).toBe("neutral");
    expect(tempTone(80)).toBe("warning");
    expect(tempTone(88)).toBe("danger");
    expect(tempTone(null)).toBe("neutral");
  });
});

describe("ranges", () => {
  it("rounds the end to the minute so queries cache", () => {
    const { start, end } = rangeBounds("1h", new Date("2026-10-26T10:15:30Z"));
    expect(end).toBe("2026-10-26T10:16:00.000Z");
    expect(start).toBe("2026-10-26T09:16:00.000Z");
    expect(isRange("7d")).toBe(true);
    expect(isRange("2d")).toBe(false);
  });
});

describe("navigation and roles", () => {
  it("highlights the right section, with GPU pages under Live", () => {
    expect(activeNavItem("/")?.label).toBe("Overview");
    expect(activeNavItem("/gpus/abc")?.label).toBe("Live");
    expect(activeNavItem("/costs")?.label).toBe("Costs");
  });
  it("lets viewers read and admins write", () => {
    expect(canWrite("viewer")).toBe(false);
    expect(canWrite("admin")).toBe(true);
    expect(canManageUsers("admin")).toBe(false);
    expect(roleLabel("owner")).toBe("Owner");
  });
});
