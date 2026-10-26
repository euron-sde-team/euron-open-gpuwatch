/**
 * The API answers every failure with one envelope:
 *   {"error": {"code", "type", "message", "details"}}
 * ApiError carries it through React Query so views can render the message and,
 * where useful, the structured details (limit, retry hint).
 */

export interface ErrorEnvelope {
  error: {
    code: string;
    type?: string;
    message: string;
    details?: Record<string, unknown> | null;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly type: string;
  readonly details: Record<string, unknown>;

  constructor(opts: {
    status: number;
    code: string;
    message: string;
    type?: string;
    details?: Record<string, unknown> | null;
  }) {
    super(opts.message);
    this.name = "ApiError";
    this.status = opts.status;
    this.code = opts.code;
    this.type = opts.type ?? "api_error";
    this.details = opts.details ?? {};
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }
}

export function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const err = (body as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { message?: unknown }).message === "string" &&
    typeof (err as { code?: unknown }).code === "string"
  );
}

interface ValidationItem {
  loc?: Array<string | number>;
  msg?: string;
}

/** Turn the validation details into one readable line per field. */
export function validationMessages(details: Record<string, unknown>): string[] {
  const errors = details.errors;
  if (!Array.isArray(errors)) return [];
  return (errors as ValidationItem[])
    .filter((e) => typeof e?.msg === "string")
    .map((e) => {
      const loc = (e.loc ?? []).filter((p) => p !== "body" && p !== "query" && p !== "path");
      const field = loc.length ? `${loc.join(".")}: ` : "";
      return `${field}${e.msg}`;
    });
}

/** Build an ApiError from a status and whatever body came back (JSON or not). */
export function parseApiError(status: number, body: unknown): ApiError {
  if (isErrorEnvelope(body)) {
    const { code, type, message, details } = body.error;
    return new ApiError({ status, code, type, message, details: details ?? {} });
  }
  // FastAPI's default validation body, in case a route bypasses the envelope.
  if (typeof body === "object" && body !== null && Array.isArray((body as { detail?: unknown }).detail)) {
    return new ApiError({
      status,
      code: "validation_error",
      type: "invalid_request_error",
      message: "Request validation failed",
      details: { errors: (body as { detail: unknown[] }).detail },
    });
  }
  return new ApiError({ status, code: `http_${status}`, message: fallbackMessage(status) });
}

function fallbackMessage(status: number): string {
  if (status === 0) return "Cannot reach the GPUWatch API. Check that it is running, then retry.";
  if (status === 401) return "Your session expired. Sign in again.";
  if (status === 403) return "Your role does not allow this action. Ask an owner or admin.";
  if (status === 404) return "This item no longer exists. It may have been deleted.";
  if (status === 429) return "Too many requests. Wait a moment, then retry.";
  if (status >= 500) return "The API hit an unexpected error. Retry, and check the API logs if it persists.";
  return `Request failed (HTTP ${status}).`;
}

/**
 * 401s that answer a sign-in or password form: the person is told exactly why (wrong
 * password, locked, disabled) instead of "your session expired".
 */
export const SIGN_IN_ERRORS: ReadonlySet<string> = new Set(["invalid_credentials", "account_locked", "account_disabled"]);

/** The message to show a person for any thrown value, always actionable. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "validation_error") {
      const lines = validationMessages(err.details);
      if (lines.length) return lines.join(". ");
    }
    if (err.status === 401 && !SIGN_IN_ERRORS.has(err.code)) return fallbackMessage(401);
    return err.message || fallbackMessage(err.status);
  }
  if (err instanceof TypeError) return fallbackMessage(0);
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Retry in a moment.";
}
