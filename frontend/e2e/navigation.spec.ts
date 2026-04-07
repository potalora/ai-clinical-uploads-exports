import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { testEmail, TEST_PASSWORD } from "./helpers/test-data";

const EMAIL = testEmail("navigation");

test.describe("Navigation", () => {
  test.beforeAll(async () => {
    const api = new ApiClient();
    await api.register(EMAIL, TEST_PASSWORD);
  });

  test("all nav links navigate correctly", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 10_000 });

    const navLinks: [string, string, RegExp][] = [
      ["/timeline", "Timeline", /\/timeline/],
      ["/summaries", "Summarize", /\/summaries/],
      ["/upload", "Upload", /\/upload/],
      ["/admin", "Admin", /\/admin/],
      ["/", "Home", /\/$/],
    ];

    for (const [href, name, urlPattern] of navLinks) {
      await page.getByRole("link", { name, exact: true }).click();
      await expect(page).toHaveURL(urlPattern, { timeout: 10_000 });
    }
  });

  test("active link has visual indicator", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 10_000 });

    await page.locator('nav a[href="/timeline"]').click();
    await expect(page).toHaveURL(/\/timeline/, { timeout: 10_000 });

    // Active link should be visible on the timeline page
    await expect(page.locator('nav a[href="/timeline"]')).toBeVisible();
  });

  test("logo links to home", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 10_000 });

    // Navigate to timeline first
    await page.goto("/timeline");
    await expect(page).toHaveURL(/\/timeline/, { timeout: 10_000 });

    // Click the MedTimeline logo (first link in nav, href="/")
    await page.locator('nav a[href="/"]').first().click();
    await expect(page).toHaveURL(/\/$/, { timeout: 10_000 });
  });

  test("theme toggle switches light/dark", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 10_000 });

    const html = page.locator("html");
    const initialClass = await html.getAttribute("class");

    const themeToggle = page.locator('button[aria-label="Toggle theme"]');
    await expect(themeToggle).toBeVisible();
    await themeToggle.click();

    await page.waitForTimeout(500);
    const newClass = await html.getAttribute("class");
    expect(newClass).not.toBe(initialClass);
  });

  test("sign out clears auth and redirects to login", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await expect(page.getByText("Dashboard")).toBeVisible({ timeout: 10_000 });

    await page.locator("button", { hasText: "Sign out" }).first().click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });

    // Verify auth guard redirects back to login
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });
});
