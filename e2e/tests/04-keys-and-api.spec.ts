import { expect, test } from "@playwright/test";

import { asOwner, RUN } from "../helpers";

test("a read-only API key reads the REST API, cannot change anything, and dies when revoked", async ({ page, playwright }) => {
  const name = `e2e-${RUN}`;
  await asOwner(page, "/keys");
  await page.getByRole("button", { name: "New key" }).click();
  await page.locator("#key-name").fill(name);
  await page.getByRole("button", { name: "Create key" }).click();
  const key = (await page.getByTestId("new-key").textContent())?.trim() ?? "";
  expect(key).toMatch(/^gwk_/);
  await page.getByRole("button", { name: "I have copied the key" }).click();

  // A fresh context: no dashboard cookie, only the key.
  const api = await playwright.request.newContext({ baseURL: process.env.WEB_URL || "http://localhost:4410", storageState: { cookies: [], origins: [] } });
  const auth = { authorization: `Bearer ${key}` };
  const gpus = await api.get("/api/v1/gpus", { headers: auth });
  expect(gpus.status()).toBe(200);
  expect((await gpus.json()).length).toBeGreaterThan(0);
  const write = await api.post("/api/v1/rates", { headers: auth, data: { scope: "model", gpu_model: "X", usd_per_hour: "1" } });
  expect(write.status()).toBe(403);
  expect((await write.json()).error.code).toBe("read_only_key");

  await page.locator("tr", { hasText: name }).getByRole("button", { name: `Revoke ${name}` }).click();
  await page.getByRole("button", { name: "Revoke key" }).click();
  expect((await api.get("/api/v1/gpus", { headers: auth })).status()).toBe(401);
  await api.dispose();
});
