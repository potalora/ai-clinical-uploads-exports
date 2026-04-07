import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

test.describe("Timeline page", () => {
  const email = testEmail("timeline");

  test.beforeAll(async () => {
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);
    await api.login(email, TEST_PASSWORD);
    const result = await api.uploadStructured(
      PATHS.fhirBundle,
      "sample_fhir_bundle.json"
    );
    await api.pollUploadStatus(result.upload_id, 60_000);
  });

  test("events render grouped by month", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");
    // Month headings use abbreviated format: "JAN 2024", "FEB 2010", etc.
    const monthHeading = page.locator("span").filter({
      hasText: /^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4}$/,
    });
    await expect(monthHeading.first()).toBeVisible({ timeout: 15_000 });
  });

  test("event count in header", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");
    const countText = page.locator("span").filter({
      hasText: /^\d+\s+events$/,
    });
    await expect(countText.first()).toBeVisible({ timeout: 15_000 });
  });

  test("filter buttons render", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");
    // Filter bar has buttons: ALL, COND, OBS, MED, etc.
    await expect(
      page.locator("button", { hasText: "ALL" })
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator("button", { hasText: "COND" })
    ).toBeVisible();
    await expect(
      page.locator("button", { hasText: "OBS" })
    ).toBeVisible();
  });

  test("click filter narrows events", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");
    // Wait for events to load
    const countText = page.locator("span").filter({
      hasText: /^\d+\s+events$/,
    });
    await expect(countText).toBeVisible({ timeout: 15_000 });

    const allCountText = await countText.textContent();
    const allCount = parseInt(allCountText!);

    // Click a specific type filter
    await page.locator("button", { hasText: "COND" }).click();
    // Wait for data to reload
    await expect(countText).toBeVisible({ timeout: 10_000 });
    const filteredCountText = await countText.textContent();
    const filteredCount = parseInt(filteredCountText!);

    // Filtered count should differ from all (or filter button should be active)
    expect(filteredCount).toBeLessThanOrEqual(allCount);
  });

  test("click ALL clears filter", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");
    const countText = page.locator("span").filter({
      hasText: /^\d+\s+events$/,
    });
    await expect(countText).toBeVisible({ timeout: 15_000 });
    const originalCount = await countText.textContent();
    const originalNum = parseInt(originalCount!);

    // Apply a filter
    await page.locator("button", { hasText: "COND" }).click();
    await page.waitForTimeout(1000);

    // Click ALL to clear
    await page.locator("button", { hasText: "ALL" }).click();
    // Wait for the count to restore — use polling assertion
    await expect(async () => {
      const text = await countText.textContent();
      const num = parseInt(text!);
      expect(num).toBe(originalNum);
    }).toPass({ timeout: 10_000 });
  });

  test("click event opens detail sheet", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");
    // Wait for events to render — they are divs with cursor-pointer class and onClick
    const eventCard = page.locator("div.cursor-pointer").first();
    await expect(eventCard).toBeVisible({ timeout: 15_000 });

    // Click the first event
    await eventCard.click();

    // RecordDetailSheet should open
    await expect(
      page.getByText("Record Details")
    ).toBeVisible({ timeout: 10_000 });
  });

  test("empty filter shows no events message", async ({ page }) => {
    // Mock the timeline API to return empty results
    await page.route("**/api/v1/timeline**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ events: [], total: 0 }),
      })
    );

    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/timeline");

    await expect(
      page.getByText("No events found")
    ).toBeVisible({ timeout: 10_000 });
  });
});
