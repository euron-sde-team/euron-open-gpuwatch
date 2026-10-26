import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, parseApiError } from "./errors";
import type { paths } from "./schema";

/**
 * Cookie-authenticated mutations must carry this header: a cross-site form cannot
 * set it, which is the API's CSRF defence.
 */
export const CSRF_HEADER = "x-gpuwatch-csrf";

const csrf: Middleware = {
  onRequest({ request }) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      request.headers.set(CSRF_HEADER, "1");
    }
    return request;
  },
};

/**
 * Typed client for the admin API. Same origin: Next rewrites /api to the API service,
 * so the httpOnly session cookie travels automatically.
 */
export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });
api.use(csrf);

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/**
 * Await an openapi-fetch call and return its data, or throw an ApiError built from the
 * envelope. Network failures become status 0 so the UI can say "cannot reach the API".
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw parseApiError(0, null);
  }
  if (!result.response.ok) {
    throw parseApiError(result.response.status, result.error);
  }
  return result.data as T;
}
