import { expect, test } from "@playwright/test";

import { asOwner, RUN } from "../helpers";

test("insights rank waste with evidence, and can be acknowledged", async ({ page }) => {
  await asOwner(page, "/insights");
  await expect(page.getByRole("heading", { name: "Insights" })).toBeVisible();
  const cards = page.locator("[data-qa='insight-card']");
  await expect(cards.first()).toBeVisible();
  await expect(page.getByText(/Open findings cost about/)).toBeVisible();
  const idle = cards.filter({ hasText: "Idle with a model loaded" }).first();
  await idle.getByRole("button", { name: "Show evidence" }).click();
  await expect(idle.getByText("Longest idle periods")).toBeVisible();
  await expect(idle.getByText("What to do:")).toBeVisible();
  const title = (await idle.locator("h3").textContent()) ?? "";
  await idle.getByRole("button", { name: "Acknowledge" }).click();
  await page.getByRole("radio", { name: "Acknowledged" }).click();
  await expect(page.locator("[data-qa='insight-card']", { hasText: title }).first()).toBeVisible();
  const back = page.locator("[data-qa='insight-card']", { hasText: title }).first();
  await back.getByRole("button", { name: "Dismiss" }).click();
  await page.getByRole("radio", { name: "Dismissed" }).click();
  await page.locator("[data-qa='insight-card']", { hasText: title }).first().getByRole("button", { name: "Reopen" }).click();
});

test("costs break spend down by workload and export a CSV", async ({ page }) => {
  await asOwner(page, "/costs");
  await expect(page.getByRole("heading", { name: "Costs" })).toBeVisible();
  await expect(page.getByText("Total cost")).toBeVisible();
  await expect(page.getByText("Idle (nothing running)").first()).toBeVisible();
  await expect(page.getByText("llm-finetune").first()).toBeVisible();
  await page.goto("/costs?tab=reports");
  await page.locator("#report-note").fill(`e2e ${RUN}`);
  await page.getByRole("button", { name: /Export/ }).click();
  const download = page.waitForEvent("download");
  await page.locator("tr", { hasText: `e2e ${RUN}` }).getByRole("link", { name: /Download/ }).click();
  expect((await download).suggestedFilename()).toMatch(/^gpuwatch-costs-by-.*\.csv$/);
});

test("a rate is added, applies, and is removed", async ({ page }) => {
  await asOwner(page, "/costs?tab=rates");
  await page.getByRole("button", { name: /Add rate/ }).click();
  await page.locator("#rate-model").click();
  await page.getByRole("option", { name: /Another model/ }).click();
  await page.locator("#rate-model-text").fill(`E2E GPU ${RUN}`);
  await page.locator("#rate-usd").fill("0.75");
  await page.getByRole("button", { name: /Save|Add/ }).last().click();
  const row = page.locator("tr", { hasText: `E2E GPU ${RUN}` });
  await expect(row.getByText("$0.75/h")).toBeVisible();
  await row.getByRole("button", { name: /Delete rate/ }).click();
  await page.getByRole("button", { name: /Delete/ }).last().click();
  await expect(row).toHaveCount(0);
});
