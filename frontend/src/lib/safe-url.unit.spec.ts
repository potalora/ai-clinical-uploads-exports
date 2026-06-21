import { test, expect } from "@playwright/test";

import { safeHref } from "@/lib/safe-url";

/**
 * Unit coverage for the SEC-FE-01 URL-scheme allowlist.
 *
 * Only http(s) URLs may flow into an attachment <a href>. Everything else
 * (javascript:, data:, vbscript:, file:, blob:, obfuscated/mixed-case, empty,
 * nullish) must be rejected so a malicious DocumentReference attachment URL
 * can't become click-gated XSS.
 */
test.describe("safeHref (SEC-FE-01)", () => {
  test("passes through an https URL", () => {
    expect(safeHref("https://example.com/a.pdf")).toBe("https://example.com/a.pdf");
  });

  test("passes through an http URL", () => {
    expect(safeHref("http://example.com/a.pdf")).toBe("http://example.com/a.pdf");
  });

  test("rejects javascript: scheme", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
  });

  test("rejects mixed-case JavaScript: scheme", () => {
    expect(safeHref("JavaScript:alert(1)")).toBeUndefined();
  });

  test("rejects javascript: with leading whitespace", () => {
    expect(safeHref("  javascript:alert(1)")).toBeUndefined();
  });

  test("rejects data:text/html payload", () => {
    expect(safeHref("data:text/html,<script>alert(1)</script>")).toBeUndefined();
  });

  test("rejects vbscript: scheme", () => {
    expect(safeHref("vbscript:msgbox(1)")).toBeUndefined();
  });

  test("rejects file: scheme", () => {
    expect(safeHref("file:///etc/passwd")).toBeUndefined();
  });

  test("rejects blob: scheme", () => {
    expect(safeHref("blob:https://example.com/uuid")).toBeUndefined();
  });

  test("rejects control-char obfuscated scheme", () => {
    expect(safeHref("java\tscript:alert(1)")).toBeUndefined();
    expect(safeHref("java\nscript:alert(1)")).toBeUndefined();
  });

  test("rejects an empty string", () => {
    expect(safeHref("")).toBeUndefined();
  });

  test("rejects null", () => {
    expect(safeHref(null)).toBeUndefined();
  });

  test("rejects undefined", () => {
    expect(safeHref(undefined)).toBeUndefined();
  });

  test("rejects a relative path (no scheme)", () => {
    expect(safeHref("/uploads/a.pdf")).toBeUndefined();
  });

  test("round-trips a normal https URL with query and fragment unchanged", () => {
    expect(safeHref("https://ex.com/a.pdf?x=1#y")).toBe("https://ex.com/a.pdf?x=1#y");
  });
});
