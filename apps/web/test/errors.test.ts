import { describe, expect, it } from "vitest";

import { ApiError, errorMessage, isErrorEnvelope, parseApiError, validationMessages } from "@/lib/api/errors";

describe("parseApiError", () => {
  it("reads the API envelope with structured details", () => {
    const err = parseApiError(422, {
      error: {
        code: "batch_too_large",
        type: "invalid_request_error",
        message: "A batch may carry at most 20000 rows; split it",
        details: { rows: 20001, limit: 20000 },
      },
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("batch_too_large");
    expect(err.details).toEqual({ rows: 20001, limit: 20000 });
    expect(errorMessage(err)).toContain("split it");
  });

  it("falls back to an actionable message for non-envelope bodies", () => {
    expect(parseApiError(500, "<html>").message).toMatch(/Retry/);
    expect(parseApiError(403, null).isForbidden).toBe(true);
    expect(parseApiError(0, null).isNetwork).toBe(true);
  });

  it("understands FastAPI's raw validation shape", () => {
    const err = parseApiError(422, { detail: [{ loc: ["body", "max_input_tokens"], msg: "must be positive" }] });
    expect(err.code).toBe("validation_error");
    expect(errorMessage(err)).toBe("max_input_tokens: must be positive");
  });
});

describe("validation and messages", () => {
  it("drops the location prefix and joins fields", () => {
    expect(validationMessages({ errors: [{ loc: ["body", "name"], msg: "required" }, { loc: [], msg: "bad" }] })).toEqual([
      "name: required",
      "bad",
    ]);
    expect(validationMessages({})).toEqual([]);
  });

  it("explains locked and disabled accounts on the sign-in form", () => {
    expect(errorMessage(new ApiError({ status: 401, code: "account_disabled", message: "This account is disabled" }))).toBe("This account is disabled");
    expect(errorMessage(new ApiError({ status: 401, code: "account_locked", message: "Too many failed attempts" }))).toMatch(/Too many/);
  });

  it("tells people to sign in again on 401, except for wrong credentials", () => {
    expect(errorMessage(new ApiError({ status: 401, code: "session_expired", message: "x" }))).toMatch(/Sign in again/);
    expect(errorMessage(new ApiError({ status: 401, code: "invalid_credentials", message: "Email or password is incorrect" }))).toBe(
      "Email or password is incorrect",
    );
  });

  it("maps network failures and unknown throwables", () => {
    expect(errorMessage(new TypeError("fetch failed"))).toMatch(/Cannot reach/);
    expect(errorMessage(new Error("boom"))).toBe("boom");
    expect(isErrorEnvelope({ error: { code: "x" } })).toBe(false);
  });
});
