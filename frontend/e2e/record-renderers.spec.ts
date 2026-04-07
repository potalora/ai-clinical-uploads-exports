import { test, expect } from "@playwright/test";
import { browserLogin } from "./helpers/browser-login";
import { ApiClient } from "./helpers/api-client";
import { testEmail, TEST_PASSWORD, PATHS } from "./helpers/test-data";

const email = testEmail("record-renderers");

test.describe("Type-specific Renderers", () => {
  const api = new ApiClient();
  let recordsByType: Record<string, string[]> = {};

  test.beforeAll(async () => {
    await api.register(email, TEST_PASSWORD);
    await api.login(email, TEST_PASSWORD);
    const result = await api.uploadStructured(PATHS.fhirBundle, "sample_fhir_bundle.json");
    await api.pollUploadStatus(result.upload_id, 60_000);

    // Fetch all records grouped by type (page_size=100 covers the full FHIR bundle)
    const data = await api.getRecords({ page: 1, page_size: 100 });
    for (const item of data.items) {
      const type = item.record_type;
      if (!recordsByType[type]) recordsByType[type] = [];
      recordsByType[type].push(item.id);
    }
  });

  // Helper: login and navigate to a record of a given type
  async function verifyRecordType(
    page: import("@playwright/test").Page,
    recordType: string,
    assertions: (page: import("@playwright/test").Page) => Promise<void>
  ) {
    const ids = recordsByType[recordType];
    if (!ids || ids.length === 0) {
      test.skip();
      return;
    }

    await browserLogin(page, email, TEST_PASSWORD);

    // Navigate to record page
    await page.goto(`/records/${ids[0]}`);
    await page.waitForSelector("h1, [data-testid='record-title']", { timeout: 10_000 });

    await assertions(page);
  }

  test("Condition: shows clinical status badge", async ({ page }) => {
    await verifyRecordType(page, "condition", async (p) => {
      // Should have a clinical status indicator (active/resolved/inactive)
      const statusText = p.locator("text=/active|resolved|inactive/i");
      await expect(statusText.first()).toBeVisible({ timeout: 5_000 });
    });
  });

  test("Lab Observation: displays large numeric value", async ({ page }) => {
    await verifyRecordType(page, "observation", async (p) => {
      // Should have a mono-font value display (JetBrains Mono via --font-mono)
      const monoValue = p.locator("[style*='font-mono'], .font-mono, [style*='--font-mono']");
      await expect(monoValue.first()).toBeVisible({ timeout: 5_000 });
    });
  });

  test("Medication: shows dosage info", async ({ page }) => {
    await verifyRecordType(page, "medication", async (p) => {
      // Should show medication name and dosage strip
      const content = await p.textContent("body");
      expect(content).toMatch(/metformin|dosage|oral|prescriber|dr\./i);
    });
  });

  test("Encounter: shows department and provider", async ({ page }) => {
    await verifyRecordType(page, "encounter", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/department|provider|dr\./i);
    });
  });

  test("Immunization: shows vaccine name", async ({ page }) => {
    await verifyRecordType(page, "immunization", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/covid|vaccine|lot/i);
    });
  });

  test("Allergy: shows severity indicator and reactions", async ({ page }) => {
    await verifyRecordType(page, "allergy", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/penicillin|hives|severe/i);
    });
  });

  test("Procedure: shows procedure name and status", async ({ page }) => {
    await verifyRecordType(page, "procedure", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/appendectomy|completed/i);
    });
  });

  test("Service Request: shows provider flow", async ({ page }) => {
    await verifyRecordType(page, "service_request", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/referral|cardiology|dr\./i);
    });
  });

  test("Document: shows document type and author", async ({ page }) => {
    await verifyRecordType(page, "document", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/progress note|author|dr\./i);
    });
  });

  test("Diagnostic Report: shows conclusion", async ({ page }) => {
    await verifyRecordType(page, "diagnostic_report", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/conclusion|normal limits|blood count/i);
    });
  });

  test("Imaging: shows modality badges", async ({ page }) => {
    await verifyRecordType(page, "imaging", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/CT|X-Ray|abdomen/i);
    });
  });

  test("Care Plan: shows activity checklist", async ({ page }) => {
    await verifyRecordType(page, "care_plan", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/diabetes management|metformin|exercise/i);
    });
  });

  test("Communication: shows message content", async ({ page }) => {
    await verifyRecordType(page, "communication", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/lab results|follow-up/i);
    });
  });

  test("Appointment: shows time and participants", async ({ page }) => {
    await verifyRecordType(page, "appointment", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/diabetes follow-up|dr\. smith|participant/i);
    });
  });

  test("Care Team: shows member list", async ({ page }) => {
    await verifyRecordType(page, "care_team", async (p) => {
      const content = await p.textContent("body");
      expect(content).toMatch(/diabetes care team|dr\. smith|dietitian/i);
    });
  });
});
