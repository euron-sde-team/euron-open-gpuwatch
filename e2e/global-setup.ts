import { request } from "@playwright/test";

import { OWNER } from "./helpers";

/**
 * Sign in once and share the session cookie with every suite. Signing in per test would
 * trip the gateway's per-IP sign-in throttle on repeated runs, which is the throttle
 * working as intended.
 */
export default async function globalSetup(): Promise<void> {
  const baseURL = process.env.WEB_URL || "http://localhost:4410";
  const ctx = await request.newContext({ baseURL });
  const resp = await ctx.post("/api/v1/auth/login", { data: OWNER });
  if (!resp.ok()) throw new Error(`demo sign-in failed (${resp.status()}): run make demo first`);
  await ctx.storageState({ path: ".auth/owner.json" });
  await ctx.dispose();
}
