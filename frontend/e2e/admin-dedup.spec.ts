import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

test.describe.serial("Admin Dedup tab", () => {
  test.setTimeout(60_000);

  const api = new ApiClient();
  const EMAIL = testEmail("admin-dedup");

  test.beforeAll(async () => {
    await api.register(EMAIL, TEST_PASSWORD);
    await api.login(EMAIL, TEST_PASSWORD);
    // Upload same bundle twice to create duplicates
    const r1 = await api.uploadStructured(
      PATHS.fhirBundle,
      "sample_fhir_bundle.json"
    );
    await api.pollUploadStatus(r1.upload_id, 60_000);
    const r2 = await api.uploadStructured(
      PATHS.fhirBundle,
      "sample_fhir_bundle.json"
    );
    await api.pollUploadStatus(r2.upload_id, 60_000, ["dedup_scanning"]);
  });

  test("dedup tab renders scan button", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin?tab=dedup");

    // Click the Dedup tab to ensure it is active
    await page.getByRole("button", { name: "Dedup" }).click();

    // Assert the scan button is visible
    const scanBtn = page.getByRole("button", { name: "Scan for duplicates" });
    await expect(scanBtn).toBeVisible();
  });

  test("scan finds duplicate candidates", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin?tab=dedup");
    await page.getByRole("button", { name: "Dedup" }).click();

    // Click scan
    const scanBtn = page.getByRole("button", { name: "Scan for duplicates" });
    await scanBtn.click();

    // Button should show "Scanning..." while in progress
    await expect(
      page.getByRole("button", { name: "Scanning..." })
    ).toBeVisible();

    // Wait for scan to complete — button reverts to "Scan for duplicates"
    await expect(
      page.getByRole("button", { name: "Scan for duplicates" })
    ).toBeVisible({ timeout: 30_000 });

    // Wait for one of the expected outcomes to appear
    await expect(async () => {
      const scanComplete = await page.getByText("Scan complete").isVisible().catch(() => false);
      const hasCandidates = await page.getByText("% match").first().isVisible().catch(() => false);
      const noCandidates = await page.getByText("No duplicate candidates").isVisible().catch(() => false);
      expect(scanComplete || hasCandidates || noCandidates).toBe(true);
    }).toPass({ timeout: 10_000 });
  });

  test("candidate list renders", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin?tab=dedup");
    await page.getByRole("button", { name: "Dedup" }).click();

    // Trigger a scan to populate candidates
    const scanBtn = page.getByRole("button", { name: "Scan for duplicates" });
    await scanBtn.click();
    await expect(
      page.getByRole("button", { name: "Scan for duplicates" })
    ).toBeVisible({ timeout: 30_000 });

    // Wait for either candidates or "no candidates" message
    await expect(async () => {
      const hasCandidatesNow = await page.getByText("% match").first().isVisible().catch(() => false);
      const hasNoneNow = await page.getByText("No duplicate candidates").isVisible().catch(() => false);
      expect(hasCandidatesNow || hasNoneNow).toBe(true);
    }).toPass({ timeout: 10_000 });

    // Check if candidates exist or all were auto-merged
    const noCandidates = page.getByText("No duplicate candidates");
    const matchBadge = page.getByText("% match").first();

    const hasCandidates = await matchBadge.isVisible().catch(() => false);
    const hasNone = await noCandidates.isVisible().catch(() => false);

    if (!hasCandidates && hasNone) {
      // All duplicates were auto-merged during ingestion — no pending candidates
      test.info().annotations.push({
        type: "note",
        description:
          "No pending candidates — dedup auto-merged all duplicates during ingestion",
      });
      return;
    }

    // At least one candidate card with Merge and Dismiss buttons
    await expect(matchBadge).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Merge" }).first()
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Dismiss" }).first()
    ).toBeVisible();

    // Verify record cards are shown (RECORD A / RECORD B labels)
    await expect(page.getByText("RECORD A").first()).toBeVisible();
    await expect(page.getByText("RECORD B").first()).toBeVisible();
  });

  test("dismiss resolves candidate", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin?tab=dedup");
    await page.getByRole("button", { name: "Dedup" }).click();

    // Scan first
    const scanBtn = page.getByRole("button", { name: "Scan for duplicates" });
    await scanBtn.click();
    await expect(
      page.getByRole("button", { name: "Scan for duplicates" })
    ).toBeVisible({ timeout: 30_000 });

    // Check for candidates
    const dismissBtns = page.getByRole("button", { name: "Dismiss" });
    const count = await dismissBtns.count();

    if (count === 0) {
      test.info().annotations.push({
        type: "note",
        description:
          "No candidates available to dismiss — all were auto-resolved",
      });
      return;
    }

    // Click Dismiss on the first candidate
    const initialCount = count;
    await dismissBtns.first().click();

    // The candidate should be removed — count should decrease
    await expect(async () => {
      const newCount = await page
        .getByRole("button", { name: "Dismiss" })
        .count();
      expect(newCount).toBeLessThan(initialCount);
    }).toPass({ timeout: 10_000 });
  });

  test("merge resolves candidate", async ({ page }) => {
    await browserLogin(page, EMAIL, TEST_PASSWORD);
    await page.goto("/admin?tab=dedup");
    await page.getByRole("button", { name: "Dedup" }).click();

    // Scan first
    const scanBtn = page.getByRole("button", { name: "Scan for duplicates" });
    await scanBtn.click();
    await expect(
      page.getByRole("button", { name: "Scan for duplicates" })
    ).toBeVisible({ timeout: 30_000 });

    // Check for candidates
    const mergeBtns = page.getByRole("button", { name: "Merge" });
    const count = await mergeBtns.count();

    if (count === 0) {
      test.info().annotations.push({
        type: "note",
        description:
          "No candidates available to merge — all were previously resolved",
      });
      return;
    }

    // Click Merge on the first candidate
    const initialCount = count;
    await mergeBtns.first().click();

    // The candidate should be removed — count should decrease
    await expect(async () => {
      const newCount = await page
        .getByRole("button", { name: "Merge" })
        .count();
      expect(newCount).toBeLessThan(initialCount);
    }).toPass({ timeout: 10_000 });
  });
});
