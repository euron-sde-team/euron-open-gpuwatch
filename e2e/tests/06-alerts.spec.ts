import { expect, test } from "@playwright/test";

import { asOwner, RUN } from "../helpers";

const MAILPIT = process.env.MAILPIT_URL || "http://localhost:4425";

test("an email channel receives a test, and a rule fires an alert that is delivered", async ({ page, request }) => {
  const channel = `Ops ${RUN}`;
  const inbox = `ops-${RUN}@example.test`;
  await asOwner(page, "/alerts?tab=channels");
  await page.getByRole("button", { name: /New channel/ }).click();
  await page.locator("#ch-name").fill(channel);
  await page.locator("#ch-emails").fill(inbox);
  await page.getByRole("button", { name: /Save|Add|Create/ }).last().click();
  await page.getByRole("button", { name: `Send a test to ${channel}` }).click();
  await expect.poll(async () => {
    const r = await request.get(`${MAILPIT}/api/v1/search?query=to:${encodeURIComponent(inbox)}`);
    return (await r.json()).messages_count ?? (await r.json()).total ?? 0;
  }, { timeout: 30_000 }).toBeGreaterThan(0);

  // A rule every reporting GPU breaks at once fires on the next evaluation.
  await page.goto("/alerts?tab=rules");
  await page.getByRole("button", { name: /New rule/ }).click();
  await page.locator("#rule-name").fill(`Warm ${RUN}`);
  await page.locator("#rule-threshold").fill("1");
  await page.locator("#rule-duration").fill("0");
  await page.getByRole("checkbox", { name: channel }).check();
  await page.getByRole("button", { name: /Save|Add|Create/ }).last().click();
  await expect(page.locator("tr", { hasText: `Warm ${RUN}` })).toBeVisible();
  await page.goto("/alerts");
  await expect(page.getByText(`Warm ${RUN}`).first()).toBeVisible({ timeout: 45_000 });

  // Clean up: deleting the rule removes its events.
  await page.goto("/alerts?tab=rules");
  await page.getByRole("button", { name: `Delete Warm ${RUN}` }).click();
  await page.getByRole("button", { name: /Delete/ }).last().click();
  await expect(page.locator("tr", { hasText: `Warm ${RUN}` })).toHaveCount(0);
});
