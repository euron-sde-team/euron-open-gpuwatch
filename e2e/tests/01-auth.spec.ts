import { expect, test } from "@playwright/test";

import { OWNER, signIn } from "../helpers";

test.describe("sign in", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("wrong password is explained, right password lands on the overview", async ({ page }) => {
    await page.goto("/login");
    await page.locator("#email").fill(OWNER.email);
    await page.locator("#password").fill("not-the-password");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText("Email or password is incorrect")).toBeVisible();
    await signIn(page);
    await expect(page.getByText("Spend, last 7 days")).toBeVisible();
  });

  test("protected pages redirect to sign in, then back to where you were", async ({ page }) => {
    await page.goto("/live");
    await expect(page).toHaveURL(/\/login\?next=%2Flive/);
    await page.locator("#email").fill(OWNER.email);
    await page.locator("#password").fill(OWNER.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/live$/);
    await expect(page.getByRole("heading", { name: "Live" })).toBeVisible();
  });

  test("a crafted next= cannot send you to another site", async ({ page }) => {
    await page.goto("/login?next=/%5Cevil.example");
    await page.locator("#email").fill(OWNER.email);
    await page.locator("#password").fill(OWNER.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    expect(new URL(page.url()).host).toBe(new URL(process.env.WEB_URL || "http://localhost:4410").host);
  });

  test("signing out ends the session for good", async ({ page }) => {
    await signIn(page);
    const cookie = (await page.context().cookies()).find((c) => c.name === "gw_session");
    expect(cookie).toBeTruthy();
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("Signed out.")).toBeVisible();
    // Replaying the old cookie no longer works: the server refused that session.
    await page.context().addCookies([{ ...cookie!, expires: -1 }]);
    const me = await page.request.get("/api/v1/auth/me");
    expect(me.status()).toBe(401);
  });
});
