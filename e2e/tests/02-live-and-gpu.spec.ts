import { expect, test } from "@playwright/test";

import { asOwner } from "../helpers";

test("the live view shows every demo GPU, grouped by host, updating by itself", async ({ page }) => {
  await asOwner(page, "/live");
  await expect(page.getByRole("heading", { name: "Live" })).toBeVisible();
  for (const host of ["train-node-01", "infer-node-01", "dev-workstation"]) {
    await expect(page.getByRole("region", { name: host })).toBeVisible();
  }
  await expect(page.locator("[data-qa='gpu-tile']")).toHaveCount(13);
  await expect(page.getByText("Simulated").first()).toBeVisible();
  // The stream connects and pushes snapshots.
  await expect(page.locator("[data-qa='stream-state']")).toHaveText(/Live|Refreshing/, { timeout: 20_000 });
  await page.getByRole("radio", { name: "Problems" }).click();
  await page.getByRole("radio", { name: "All" }).click();
  await page.getByLabel("Search GPUs").fill("L40S");
  await expect(page.locator("[data-qa='gpu-tile']")).toHaveCount(2);
});

test("a GPU page explains its cost, charts its history and never shows a missing metric as zero", async ({ page }) => {
  await asOwner(page, "/live");
  await page.getByRole("region", { name: "train-node-01" }).locator("[data-qa='gpu-tile']").nth(6).click();
  await expect(page.getByRole("heading", { name: /GPU 6 on train-node-01/ })).toBeVisible();
  await expect(page.getByText("Why this GPU costs what it does")).toBeVisible();
  await expect(page.getByText(/It cost \$/)).toBeVisible();
  await expect(page.getByRole("img", { name: "GPU utilization over time" })).toBeVisible();
  await page.getByRole("radio", { name: "7d" }).click();
  await expect(page.getByRole("img", { name: "Memory used over time" })).toBeVisible();
  // H100 SXM cards are passively cooled: the driver reports no fan speed.
  const fan = page.locator("dt", { hasText: "Fan" }).locator("..");
  await expect(fan.getByText("Not available")).toBeVisible();
  await expect(page.getByText("ipykernel").first()).toBeVisible();
});
