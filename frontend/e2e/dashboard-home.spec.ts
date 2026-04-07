import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

test.describe("Dashboard with seeded data", () => {
  const email = testEmail("dashboard");

  test.beforeAll(async () => {
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);
    await api.login(email, TEST_PASSWORD);
    await api.uploadStructured(PATHS.fhirBundle, "sample_fhir_bundle.json");
    await new Promise((r) => setTimeout(r, 3000));
  });

  test("overview stats render", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    // StatusReadout renders label:value pairs
    await expect(page.getByText("Dashboard")).toBeVisible();
    await expect(page.getByText("Patients")).toBeVisible();
    await expect(page.getByText("Uploads")).toBeVisible();
    await expect(page.getByText("Date range")).toBeVisible();
  });

  test("records by category badges render", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Records by category" })
    ).toBeVisible();
    // Badges are spans with "Type: N" format inside the card
    const badges = page.locator("span").filter({ hasText: /^\w[\w\s&]*:\s*\d+$/ });
    await expect(badges.first()).toBeVisible();
  });

  test("recent activity log shows entries", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Recent activity" })
    ).toBeVisible();
    // TerminalLog renders div entries with cursor:pointer style
    // Each entry has a date span, type badge span, and text span
    const logEntries = page.locator("[style*='cursor: pointer']");
    await expect(logEntries.first()).toBeVisible();
  });

  test("Go to Upload navigates to /upload", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await page.getByRole("link", { name: /Go to Upload/ }).click();
    await expect(page).toHaveURL(/\/upload/);
  });

  test("Create summary navigates to /summaries", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await page.getByRole("link", { name: /Create summary/ }).click();
    await expect(page).toHaveURL(/\/summaries/);
  });
});

test.describe("Dashboard empty state", () => {
  const email = testEmail("dashboard-empty");

  test.beforeAll(async () => {
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);
  });

  test("shows No records yet for fresh user", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await expect(page.getByText("No records yet")).toBeVisible();
  });

  test("shows Upload records button in empty state", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: /Upload records/ })
    ).toBeVisible();
  });

  test("upload records button navigates to /upload", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/");
    await page.getByRole("button", { name: /Upload records/ }).click();
    await expect(page).toHaveURL(/\/upload/);
  });
});
