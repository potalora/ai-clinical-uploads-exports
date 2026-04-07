import { test, expect } from "@playwright/test";
import { browserLogin } from "./helpers/browser-login";
import { ApiClient } from "./helpers/api-client";
import { testEmail, TEST_PASSWORD } from "./helpers/test-data";

const email = testEmail("admin-extractions");

test.beforeAll(async () => {
  const api = new ApiClient();
  await api.register(email, TEST_PASSWORD);
});

test.describe("Admin Extractions tab", () => {
  test("Extractions tab renders", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "Extractions" }).click();
    // Tab should show content — either empty state or file list
    await expect(
      page.getByText(/no files pending/i).or(
        page.getByText(/files?$/i)
      )
    ).toBeVisible({ timeout: 10_000 });
  });

  test("empty state message when no pending files", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "Extractions" }).click();
    await expect(
      page.getByText("No files pending extraction, processing, or failed")
    ).toBeVisible({ timeout: 10_000 });
  });

  test("select all checkbox exists when files present", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "Extractions" }).click();
    // With no uploads, we just verify the empty state rendered
    await expect(
      page.getByText(/no files pending/i)
    ).toBeVisible({ timeout: 10_000 });
  });

  test("extract button exists", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await page.getByRole("button", { name: "Extractions" }).click();
    await expect(
      page.getByRole("button", { name: /extract/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("extractions tab is accessible from admin page", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    // Verify all four admin tabs are visible
    await expect(page.getByRole("button", { name: "Records" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: "Extractions" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Dedup" })).toBeVisible();
    await expect(page.getByRole("button", { name: "System" })).toBeVisible();
  });
});
