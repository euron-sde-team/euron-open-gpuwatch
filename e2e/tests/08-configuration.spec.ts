import { expect, test } from "@playwright/test";

import { asOwner, RUN } from "../helpers";

test("a key is edited in place: name, limit and expiry", async ({ page }) => {
  const name = `edit-${RUN}`;
  await asOwner(page, "/keys");
  await page.getByRole("button", { name: "New key" }).click();
  await page.locator("#key-name").fill(name);
  await page.getByRole("button", { name: "Create key" }).click();
  await page.getByRole("button", { name: "I have copied the key" }).click();
  await page.locator("tr", { hasText: name }).getByRole("button", { name: `Edit ${name}` }).click();
  await page.locator("#key-name").fill(`${name}-renamed`);
  await page.locator("#key-rpm").fill("120");
  await page.locator("#key-expires").fill("2099-12-31");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText(`Key "${name}-renamed" updated.`)).toBeVisible();
  const row = page.locator("tr", { hasText: `${name}-renamed` });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: `Revoke ${name}-renamed` }).click();
  await page.getByRole("button", { name: "Revoke key" }).click();
});

test("insight rules are edited from Settings and stick", async ({ page }) => {
  await asOwner(page, "/settings");
  await expect(page.getByRole("heading", { name: "Insight rules" })).toBeVisible();
  const field = page.locator("#is-idle_min_minutes");
  const before = await field.inputValue();
  await field.fill("45");
  await page.getByRole("button", { name: "Save rules" }).click();
  await expect(page.getByText(/Insight rules saved/)).toBeVisible();
  await page.reload();
  await expect(page.locator("#is-idle_min_minutes")).toHaveValue("45");
  await page.locator("#is-idle_min_minutes").fill(before);
  await page.getByRole("button", { name: "Save rules" }).click();
});

test("the inference page shows serving metrics and cost per million tokens", async ({ page }) => {
  await asOwner(page, "/inference");
  await expect(page.getByRole("heading", { name: "Inference" })).toBeVisible();
  await expect(page.getByText("llama-chat").first()).toBeVisible();
  await expect(page.getByText("summarizer").first()).toBeVisible();
  // TGI exposes no time to first token: shown as not available, never as zero.
  await expect(page.getByText("Not available").first()).toBeVisible();
  await page.getByRole("button", { name: "llama-chat" }).first().click();
  await expect(page).toHaveURL(/endpoint=/);
});
