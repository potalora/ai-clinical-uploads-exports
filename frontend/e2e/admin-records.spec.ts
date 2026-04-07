import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

const EMAIL = testEmail("admin-records");

test.describe.serial("Admin Console — Records Tab", () => {
  const api = new ApiClient();

  test.beforeAll(async () => {
    await api.register(EMAIL, TEST_PASSWORD);
    await api.login(EMAIL, TEST_PASSWORD);

    // Upload FHIR bundle so there are records to display
    const result = await api.uploadStructured(
      PATHS.fhirBundle,
      "sample_fhir_bundle.json"
    );
    await api.pollUploadStatus(result.upload_id, 60_000);
  });

  test("admin page renders with Records tab", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");

    // Heading visible
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Records tab should be active (amber-colored text or highlighted)
    const recordsTab = page.getByRole("button", { name: "Records" }).or(
      page.locator("button", { hasText: "Records" })
    );
    await expect(recordsTab.first()).toBeVisible();
  });

  test("By Type tree renders record type groups", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for the tree to load (at least one record type group should appear)
    // The sample bundle has Conditions, Labs & Vitals, Medications, etc.
    const typeNode = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(typeNode).toBeVisible({ timeout: 15_000 });

    // There should be a count next to at least one type
    // Counts are rendered as sibling spans with numeric content
    const countSpan = page
      .locator("span")
      .filter({ hasText: /^\d+$/ })
      .first();
    await expect(countSpan).toBeVisible();
  });

  test("expand tree node shows records", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for tree to load
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });

    // Click the group row to expand (click the parent div which has the onClick handler)
    const expandableRow = firstGroupRow.locator("..");
    await expandableRow.click();

    // Wait for child records to appear — they have checkboxes
    const childCheckbox = page
      .locator('input[type="checkbox"]')
      .first();
    await expect(childCheckbox).toBeVisible({ timeout: 10_000 });
  });

  test("click record opens detail sheet", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for tree and expand first node
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    // Wait for records to load, then click a record's display text
    // Record leaf nodes have a clickable span with the record's display_text
    // They sit inside a div with padding "6px 12px" after a checkbox
    const recordTextSpan = page
      .locator('input[type="checkbox"]')
      .first()
      .locator("..")
      .locator("span")
      .first();
    await expect(recordTextSpan).toBeVisible({ timeout: 10_000 });
    await recordTextSpan.click();

    // The RecordDetailSheet should appear — look for the dialog content
    await expect(page.getByText("Record Details")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("By Upload toggle works", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for By Type tree to render first
    const typeNode = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(typeNode).toBeVisible({ timeout: 15_000 });

    // Click the "By Upload" button
    const byUploadBtn = page.locator("button", { hasText: "By Upload" });
    await byUploadBtn.click();

    // By Upload view shows upload dates as group headers (e.g. "4/7/2026")
    const uploadDateNode = page
      .locator("span")
      .filter({ hasText: /^\d{1,2}\/\d{1,2}\/\d{4}$/ })
      .first();
    await expect(uploadDateNode).toBeVisible({ timeout: 10_000 });
  });

  test("single delete shows confirm dialog", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Make sure we are on By Type view
    const byTypeBtn = page.locator("button", { hasText: "By Type" });
    await byTypeBtn.click();

    // Wait for tree and expand first node
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    // Wait for records to load
    const firstCheckbox = page.locator('input[type="checkbox"]').first();
    await expect(firstCheckbox).toBeVisible({ timeout: 10_000 });

    // Click the trash icon — it's the button with a Trash2 SVG inside a record row
    // Record rows contain a checkbox, so find the row with a checkbox and get the trash button in it
    const recordRow = page.locator('input[type="checkbox"]').first().locator("..");
    const trashButton = recordRow.locator("button").last();
    await trashButton.click();

    // Confirm dialog should appear with "Delete" text
    await expect(page.getByText("Delete record?")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("cancel delete closes dialog", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Expand first type node
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    // Wait for records
    const firstCheckbox = page.locator('input[type="checkbox"]').first();
    await expect(firstCheckbox).toBeVisible({ timeout: 10_000 });

    // Click trash to open confirm dialog
    const recordRow = firstCheckbox.locator("..");
    const trashButton = recordRow.locator("button").last();
    await trashButton.click();
    await expect(page.getByText("Delete record?")).toBeVisible({
      timeout: 5_000,
    });

    // Click "Cancel"
    const cancelBtn = page.getByRole("button", { name: "Cancel" });
    await cancelBtn.click();

    // Dialog should disappear
    await expect(page.getByText("Delete record?")).not.toBeVisible({
      timeout: 3_000,
    });
  });

  test("confirm delete removes record", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Expand first type node
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    // Wait for records and count them
    const firstCheckbox = page.locator('input[type="checkbox"]').first();
    await expect(firstCheckbox).toBeVisible({ timeout: 10_000 });

    const recordCountBefore = await page
      .locator('input[type="checkbox"]')
      .count();

    // Click trash to open confirm dialog
    const recordRow = firstCheckbox.locator("..");
    const trashButton = recordRow.locator("button").last();
    await trashButton.click();
    await expect(page.getByText("Delete record?")).toBeVisible({
      timeout: 5_000,
    });

    // Click the "Delete" confirm button (not the cancel)
    const deleteBtn = page.getByRole("button", { name: "Delete", exact: true });
    await deleteBtn.click();

    // Dialog should close
    await expect(page.getByText("Delete record?")).not.toBeVisible({
      timeout: 5_000,
    });

    // Wait for refresh — either fewer checkboxes or the tree re-renders
    await page.waitForTimeout(2_000);
    const recordCountAfter = await page
      .locator('input[type="checkbox"]')
      .count();
    expect(recordCountAfter).toBeLessThan(recordCountBefore);
  });

  test("bulk select and delete", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByText("Admin Console")).toBeVisible({
      timeout: 10_000,
    });

    // Expand first type node
    const firstGroupRow = page
      .locator("span")
      .filter({
        hasText:
          /^(Conditions|Labs & Vitals|Medications|Allergies|Procedures|Encounters|Immunizations|Documents|Diagnostic Reports|Service Requests|Communications|Appointments|Care Plans|Care Teams)$/,
      })
      .first();
    await expect(firstGroupRow).toBeVisible({ timeout: 15_000 });
    await firstGroupRow.locator("..").click();

    // Wait for records
    const checkboxes = page.locator('input[type="checkbox"]');
    await expect(checkboxes.first()).toBeVisible({ timeout: 10_000 });

    // Check at least two checkboxes
    const checkboxCount = await checkboxes.count();
    const toCheck = Math.min(checkboxCount, 2);
    for (let i = 0; i < toCheck; i++) {
      await checkboxes.nth(i).check();
    }

    // Floating bar should appear with count and "Delete selected" button
    await expect(
      page.getByRole("button", { name: "Delete selected" })
    ).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/\d+ selected/)).toBeVisible();
  });
});
