import { test, expect } from "@playwright/test";
import { browserLogin } from "./helpers/browser-login";
import { ApiClient } from "./helpers/api-client";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

const email = testEmail("admin-system");

test.describe("Admin System tab", () => {
  test.beforeAll(async () => {
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);
    await api.login(email, TEST_PASSWORD);
    await api.uploadStructured(PATHS.fhirBundle, "sample_fhir_bundle.json");
  });

  test("account info renders", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "System" }).click();

    await expect(page.getByText("@")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("E2E Test User")).toBeVisible();
    await expect(page.getByText(/[Aa]ctive/)).toBeVisible();
  });

  test("data statistics render", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "System" }).click();

    await expect(page.getByText("Records")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Patients")).toBeVisible();
    await expect(page.getByText("Uploads")).toBeVisible();
  });

  test("sign out button redirects to /login", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "System" }).click();

    const signOutButton = page.locator("button", { hasText: "Sign out" }).first();
    await expect(signOutButton).toBeVisible({ timeout: 10_000 });
    await signOutButton.click();

    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });

  test("user ID displays UUID", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "System" }).click();

    const uuidPattern = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
    await expect(page.getByText(uuidPattern)).toBeVisible({ timeout: 10_000 });
  });
});
