import { ApiError, SIGN_IN_ERRORS } from "./api/errors";

/**
 * Decide what a 401 means. Wrong credentials, a locked or a disabled account on the login
 * or password form are a form error, not an expired session; everything else sends the
 * person back to sign in.
 */
export function isSessionExpired(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401 && !SIGN_IN_ERRORS.has(err.code);
}

/** Build /login?next=... for the current location, never looping back to /login. */
export function loginUrl(pathname: string, search = "", reason?: "expired"): string {
  const params = new URLSearchParams();
  const target = `${pathname}${search}`;
  if (pathname && pathname !== "/login" && pathname !== "/") params.set("next", target);
  if (reason) params.set("reason", reason);
  const qs = params.toString();
  return qs ? `/login?${qs}` : "/login";
}

const SENTINEL = "http://local.invalid";

/**
 * Only accept same-origin paths as a post-login destination. Parsing (rather than prefix
 * checks) also rejects tricks such as "/\\evil.com" or "/\t/evil.com", which browsers
 * resolve to another host.
 */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/")) return "/";
  let url: URL;
  try {
    url = new URL(next, SENTINEL);
  } catch {
    return "/";
  }
  if (url.origin !== SENTINEL || url.pathname.startsWith("/login")) return "/";
  return `${url.pathname}${url.search}${url.hash}`;
}
