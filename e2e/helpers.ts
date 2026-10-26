import { type APIRequestContext, expect, type Page } from "@playwright/test";

export const OWNER = {
  email: process.env.E2E_EMAIL || "owner@gpuwatch.local",
  password: process.env.E2E_PASSWORD || process.env.GW_DEMO_PASSWORD || "",
};

/** The API itself: agents post here directly, never through the dashboard origin. */
export const API_URL = (process.env.API_URL || "http://localhost:4430").replace(/\/+$/, "");

/** A per-run suffix so suites can run repeatedly against the same demo database. */
export const RUN = process.env.E2E_RUN || Date.now().toString(36).slice(-5);

/** Open the dashboard with the shared owner session from global setup. */
export async function asOwner(page: Page, path = "/"): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole("button", { name: "Account menu" })).toBeVisible();
}

/** Sign in through the real form (for auth tests and other users). */
export async function signIn(page: Page, email = OWNER.email, password = OWNER.password): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

/** Pick an option in one of the dashboard's custom selects. */
export async function choose(page: Page, triggerId: string, option: string | RegExp): Promise<void> {
  await page.locator(`#${triggerId}`).click();
  await page.getByRole("option", { name: option }).first().click();
}

/** Owner session for API-level setup and assertions (the browser journeys stay UI-only). */
export async function adminApi(request: APIRequestContext): Promise<Record<string, string>> {
  // The request fixture already carries the owner cookie; mutations add the CSRF header.
  void request;
  return { "x-gpuwatch-csrf": "1" };
}
