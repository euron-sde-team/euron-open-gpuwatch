import { expect, type Page, test } from "@playwright/test";

import { asOwner, RUN, signIn } from "../helpers";

async function addUser(page: Page, name: string, email: string, password: string, role?: string) {
  await asOwner(page, "/users");
  await page.getByRole("button", { name: "Add user" }).click();
  await page.locator("#u-name").fill(name);
  await page.locator("#u-email").fill(email);
  if (role) {
    await page.locator("#u-role").click();
    await page.getByRole("option", { name: role }).click();
  }
  await page.locator("#u-pw").fill(password);
  await page.getByRole("button", { name: "Add user" }).last().click();
  await expect(page.locator("tr", { hasText: email })).toBeVisible();
}

test("an owner adds a user, changes the role and name, and disabling stops sign-in", async ({ page, browser }) => {
  const email = `ada-${RUN}@example.test`;
  await addUser(page, `Ada ${RUN}`, email, "Ada-Pass-12345");
  const row = page.locator("tr", { hasText: email });

  await row.getByRole("combobox", { name: `Role for Ada ${RUN}` }).click();
  await page.getByRole("option", { name: "Admin" }).click();
  await expect(page.getByText(`Ada ${RUN} is now Admin.`)).toBeVisible();

  await row.getByRole("button", { name: `Rename Ada ${RUN}` }).click();
  await page.locator("#rename-name").fill(`Ada L ${RUN}`);
  await page.getByRole("button", { name: "Save name" }).click();
  await expect(page.getByText(`Renamed to Ada L ${RUN}.`)).toBeVisible();

  await row.getByRole("switch", { name: `Disable Ada L ${RUN}` }).click();
  await expect(page.getByText(`Ada L ${RUN} was signed out and disabled.`)).toBeVisible();

  const other = await browser.newPage({ storageState: { cookies: [], origins: [] } });
  await other.goto("/login");
  await other.locator("#email").fill(email);
  await other.locator("#password").fill("Ada-Pass-12345");
  await other.getByRole("button", { name: /sign in/i }).click();
  await expect(other.getByText("This account is disabled")).toBeVisible();
  await other.close();

  await page.goto("/audit");
  await page.getByLabel("Filter by action").fill("user.");
  await expect(page.getByText("user.created").first()).toBeVisible();
  await expect(page.getByText("user.updated").first()).toBeVisible();
});

test.describe("own account", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("changing your password works with the new one only", async ({ page, browser }) => {
    const email = `pat-${RUN}@example.test`;
    const ownerPage = await browser.newPage({ storageState: ".auth/owner.json" });
    await addUser(ownerPage, `Pat ${RUN}`, email, "Pat-Old-Pass-123");
    await ownerPage.close();

    await signIn(page, email, "Pat-Old-Pass-123");
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Change password" }).click();
    await page.locator("#pw-current").fill("Pat-Old-Pass-123");
    await page.locator("#pw-new").fill("Pat-New-Pass-456");
    await page.locator("#pw-confirm").fill("Pat-New-Pass-456");
    await page.getByRole("button", { name: "Change password" }).last().click();
    await expect(page.getByText(/Password changed/i)).toBeVisible();

    await page.context().clearCookies();
    await page.goto("/login");
    await page.locator("#email").fill(email);
    await page.locator("#password").fill("Pat-Old-Pass-123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText("Email or password is incorrect")).toBeVisible();
    await signIn(page, email, "Pat-New-Pass-456");
  });

  test("a viewer has no Users or Audit pages", async ({ page, browser }) => {
    const email = `val-${RUN}@example.test`;
    const ownerPage = await browser.newPage({ storageState: ".auth/owner.json" });
    await addUser(ownerPage, `Val ${RUN}`, email, "Val-Viewer-123");
    await ownerPage.close();

    await signIn(page, email, "Val-Viewer-123");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link", { name: "Live" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Users" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "Audit log" })).toHaveCount(0);
    await page.goto("/audit");
    await expect(page.getByText("Admins only")).toBeVisible();
    // Viewers read everything but change nothing: no write actions are offered.
    await page.goto("/hosts");
    await expect(page.getByRole("heading", { name: "Hosts" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add a host" })).toHaveCount(0);
    await page.goto("/costs?tab=rates");
    await expect(page.getByText("Only admins and owners can change rates.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add rate" })).toHaveCount(0);
  });
});

test("the theme switches and the choice sticks", async ({ page }) => {
  await asOwner(page, "/settings");
  const html = page.locator("html");
  await page.getByRole("radiogroup", { name: "Theme" }).getByRole("radio", { name: /dark/i }).click();
  await expect(html).toHaveClass(/dark/);
  await page.reload();
  await expect(html).toHaveClass(/dark/);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(html).not.toHaveClass(/dark/);
});
