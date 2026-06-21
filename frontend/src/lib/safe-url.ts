/**
 * URL-scheme allowlist for untrusted hrefs (SEC-FE-01).
 *
 * FHIR `DocumentReference` attachment URLs come from uploaded / AI-extracted
 * bundles, so they are untrusted. Rendering one directly as `<a href={url}>`
 * lets a `javascript:` or `data:text/html` URL become click-gated XSS that can
 * exfiltrate the localStorage JWTs. This helper only emits URLs whose scheme is
 * http(s); everything else (javascript:, data:, vbscript:, file:, blob:,
 * mixed-case, leading-whitespace tricks, control-char obfuscation, relative
 * paths, empty/nullish) is rejected so callers can render the raw value as
 * inert text instead of a live link.
 *
 * @param url - Untrusted URL string (or null/undefined).
 * @returns The trimmed URL when it is a http(s) URL, otherwise `undefined`.
 */
export function safeHref(url: string | null | undefined): string | undefined {
  if (typeof url !== "string") return undefined;

  const trimmed = url.trim();
  if (!trimmed) return undefined;

  // Require an explicit http(s):// prefix on the trimmed string. `.trim()`
  // strips leading-whitespace tricks; the anchored regex rejects every other
  // scheme (javascript:, data:, vbscript:, file:, blob:, …), relative paths,
  // and control-char-obfuscated variants like "java\tscript:".
  return /^https?:\/\//i.test(trimmed) ? trimmed : undefined;
}
