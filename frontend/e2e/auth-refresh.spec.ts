import { test, expect } from "@playwright/test";
import { ApiClient } from "./helpers/api-client";
import { browserLogin } from "./helpers/browser-login";
import { uniqueEmail, TEST_PASSWORD } from "./helpers/test-data";

/**
 * Regression for the missing token-refresh: the frontend stored a refreshToken
 * but never called /auth/refresh, so once the 15-min access token expired every
 * API call 401'd and pages silently rendered empty. The api client should now
 * transparently refresh on a 401 and retry the original request.
 */
test.describe("Access token auto-refresh", () => {
  // Two UI logins back-to-back; run serially so they don't race the backend
  // login rate limiter (5/60s per IP).
  test.describe.configure({ mode: "serial" });

  test("expired access token is transparently refreshed on a 401", async ({
    page,
  }) => {
    const email = uniqueEmail("authrefresh");
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);

    // Log in via the UI so real access + refresh tokens land in localStorage.
    await browserLogin(page, email, TEST_PASSWORD);

    // Corrupt ONLY the access token (keep the valid refresh token) to simulate
    // a 15-min expiry. The next API call must 401 → refresh → retry.
    await page.evaluate(() => {
      const raw = localStorage.getItem("medtimeline-auth");
      const parsed = JSON.parse(raw as string);
      parsed.state.accessToken = "invalid.expired.token";
      localStorage.setItem("medtimeline-auth", JSON.stringify(parsed));
    });

    // The refresh endpoint must be hit and succeed...
    const refreshOk = page.waitForResponse(
      (r) => r.url().includes("/auth/refresh") && r.status() === 200,
      { timeout: 20_000 }
    );
    // ...and the original request must be retried successfully (not left at 401).
    const overviewOk = page.waitForResponse(
      (r) => r.url().includes("/dashboard/overview") && r.status() === 200,
      { timeout: 20_000 }
    );

    await page.goto("/");

    await refreshOk;
    await overviewOk;

    // The stored access token was rotated to a fresh, valid one.
    const newToken = await page.evaluate(() => {
      const parsed = JSON.parse(
        localStorage.getItem("medtimeline-auth") as string
      );
      return parsed.state.accessToken as string;
    });
    expect(newToken).not.toBe("invalid.expired.token");
    expect(newToken.length).toBeGreaterThan(20);

    // The dashboard rendered (no forced redirect back to /login).
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText("Records:")).toBeVisible({ timeout: 10_000 });
  });

  test("a 401 with no usable refresh token redirects to login", async ({
    page,
  }) => {
    const email = uniqueEmail("authrefresh-fail");
    const api = new ApiClient();
    await api.register(email, TEST_PASSWORD);
    await browserLogin(page, email, TEST_PASSWORD);

    // Invalidate BOTH tokens — refresh cannot succeed, so the app must bounce
    // the user to /login rather than silently showing empty data.
    await page.evaluate(() => {
      const parsed = JSON.parse(
        localStorage.getItem("medtimeline-auth") as string
      );
      parsed.state.accessToken = "invalid.expired.token";
      parsed.state.refreshToken = "invalid.refresh.token";
      localStorage.setItem("medtimeline-auth", JSON.stringify(parsed));
    });

    // The redirect to /login can fire mid-navigation and interrupt goto(),
    // which is itself proof the guard kicked in — tolerate it and assert the
    // end state.
    await page.goto("/").catch(() => {});
    await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });
  });
});
