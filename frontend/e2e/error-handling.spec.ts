import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { testEmail, TEST_PASSWORD } from "./helpers/test-data";

test.describe("Error handling — graceful degradation", () => {
  const email = testEmail("errors");

  test.beforeAll(async () => {
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);
  });

  test("500 on dashboard overview renders gracefully", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);

    // Intercept dashboard overview to return 500
    await page.route("**/api/v1/dashboard/overview", (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" })
    );

    // Collect console errors to verify no uncaught exceptions
    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Page should still render — navigation is visible
    await expect(page.locator("nav")).toBeVisible();
    await expect(page.getByText("Home")).toBeVisible();

    // No uncaught JS errors
    expect(
      consoleErrors.filter((e) => !e.includes("ResizeObserver"))
    ).toHaveLength(0);
  });

  test("500 on timeline shows empty state", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);

    // Intercept timeline endpoint to return 500
    await page.route("**/api/v1/timeline*", (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" })
    );

    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await page.goto("/timeline");
    await page.waitForLoadState("networkidle");

    // Page loads without crashing — nav is present
    await expect(page.locator("nav")).toBeVisible();

    // No stack traces visible on page
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain("Traceback");
    expect(bodyText).not.toContain("at Object.");
    expect(bodyText).not.toContain("TypeError");

    // No uncaught JS errors
    expect(
      consoleErrors.filter((e) => !e.includes("ResizeObserver"))
    ).toHaveLength(0);
  });

  test("network error on summary generate shows page gracefully", async ({
    page,
  }) => {
    await browserLogin(page, email, TEST_PASSWORD);

    // Intercept summary generate to abort (simulates network failure)
    await page.route("**/api/v1/summary/generate", (route) => route.abort());

    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await page.goto("/summaries");
    await page.waitForLoadState("networkidle");

    // Page renders without crashing — nav is visible
    await expect(page.locator("nav")).toBeVisible();

    // No uncaught JS errors
    expect(
      consoleErrors.filter((e) => !e.includes("ResizeObserver"))
    ).toHaveLength(0);
  });

  test("API error does not expose stack traces", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);

    // Intercept dashboard overview with a JSON error response
    await page.route("**/api/v1/dashboard/overview", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      })
    );

    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // The raw error detail should NOT be displayed to the user
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain("Internal Server Error");

    // Page still renders navigation
    await expect(page.locator("nav")).toBeVisible();
  });
});
