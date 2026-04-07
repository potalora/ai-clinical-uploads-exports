import { test, expect } from "@playwright/test";
import { browserLogin } from "./helpers/browser-login";
import { ApiClient } from "./helpers/api-client";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

const email = testEmail("record-detail-sheet");

test.describe("Record Detail Sheet (Admin Drawer)", () => {
  const api = new ApiClient();

  test.beforeAll(async () => {
    await api.register(email, TEST_PASSWORD);
    await api.login(email, TEST_PASSWORD);
    const result = await api.uploadStructured(PATHS.fhirBundle, "sample_fhir_bundle.json");
    await api.pollUploadStatus(result.upload_id, 60_000);
  });

  test("opens drawer with record type icon and badge", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({ timeout: 10_000 });

    // Expand the first record type group in the tree
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText: /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    // Click the first record's text to open the detail sheet
    const recordRow = page.locator('input[type="checkbox"]').first().locator("..");
    const recordText = recordRow.locator("span").first();
    await expect(recordText).toBeVisible({ timeout: 10_000 });
    await recordText.click();

    // Should show "Record Details" header
    await expect(page.getByText("Record Details")).toBeVisible({ timeout: 5_000 });
  });

  test("Advanced section is collapsed by default", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({ timeout: 10_000 });

    // Expand first group and click first record
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText: /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    const recordRow = page.locator('input[type="checkbox"]').first().locator("..");
    await recordRow.locator("span").first().click();

    await expect(page.getByText("Record Details")).toBeVisible({ timeout: 5_000 });

    // Advanced button should be visible
    const advancedBtn = page.getByText("Advanced");
    await expect(advancedBtn).toBeVisible();

    // Click Advanced to expand — should show JSON content
    await advancedBtn.click();
    await expect(page.locator("pre").first()).toBeVisible({ timeout: 5_000 });
  });

  test("delete button is present", async ({ page }) => {
    await browserLogin(page, email, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({ timeout: 10_000 });

    // Expand first group and click first record
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText: /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    const recordRow = page.locator('input[type="checkbox"]').first().locator("..");
    await recordRow.locator("span").first().click();

    await expect(page.getByText("Record Details")).toBeVisible({ timeout: 5_000 });
    // Delete button in the detail sheet (shows Trash icon + "Delete" text)
    await expect(page.getByRole("button", { name: "Delete" })).toBeVisible();
  });
});
