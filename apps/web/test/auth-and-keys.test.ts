import { describe, expect, it } from "vitest";

import { expiryFromDate } from "@/features/keys/components/create-key-dialog";
import { loginUrl, safeNext } from "@/lib/auth-redirect";

describe("safeNext", () => {
  it("keeps same-origin paths with their query and hash", () => {
    expect(safeNext("/runs?run=12#trace")).toBe("/runs?run=12#trace");
    expect(safeNext("/keys")).toBe("/keys");
  });

  it("refuses anything that would leave the origin", () => {
    for (const evil of ["//evil.example", "/\\evil.example", "/\t/evil.example", "https://evil.example", "javascript:alert(1)", "/%5Cevil.example"]) {
      const out = safeNext(evil);
      expect(new URL(out, "http://dashboard.local").origin).toBe("http://dashboard.local");
    }
  });

  it("never loops back to the login page", () => {
    expect(safeNext("/login?next=/x")).toBe("/");
    expect(safeNext(null)).toBe("/");
    expect(safeNext("")).toBe("/");
  });

  it("builds a login URL that returns to where the person was", () => {
    expect(loginUrl("/runs", "?run=3")).toBe("/login?next=%2Fruns%3Frun%3D3");
    expect(loginUrl("/", "", "expired")).toBe("/login?reason=expired");
  });
});

describe("expiryFromDate", () => {
  it("keeps a key valid through the whole chosen day (UTC)", () => {
    expect(expiryFromDate("2026-12-31")).toBe("2026-12-31T23:59:59.000Z");
  });

  it("treats empty or invalid input as no expiry", () => {
    expect(expiryFromDate("")).toBeNull();
    expect(expiryFromDate("not-a-date")).toBeNull();
  });
});
