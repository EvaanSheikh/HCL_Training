/**
 * Startup configuration validation for NOHA.
 *
 * This module is imported at server module initialisation time by lib/auth0.ts.
 * It validates required environment variables and production-specific security
 * requirements WITHOUT logging secret values.
 *
 * Rules:
 *  - In production (NODE_ENV === 'production') at runtime:
 *      - Required variables must be present and non-placeholder.
 *      - APP_BASE_URL must use https://.
 *      - AUTH_SESSION_ENCRYPTION_KEY must decode to exactly 32 bytes.
 *  - During `next build` (NEXT_PHASE === 'phase-production-build') the module
 *    is loaded without real env vars; validation is skipped to allow the build
 *    to complete.  Validation runs at server startup when the built app starts.
 *  - In development these checks are advisory warnings only so local dev
 *    remains possible without a fully configured Auth0 tenant.
 */

// next/dist/shared/lib/constants exports NEXT_PHASE_PRODUCTION_BUILD.
// Use a string literal to avoid a hard dependency on that module.
const IS_BUILD_PHASE = process.env.NEXT_PHASE === 'phase-production-build';
const IS_PRODUCTION = process.env.NODE_ENV === 'production';

type ValidationResult = { ok: true } | { ok: false; errors: string[] };

// Variables that must be non-empty and non-placeholder in production.
const REQUIRED_VARS: readonly string[] = [
  'AUTH0_DOMAIN',
  'AUTH0_CLIENT_ID',
  'AUTH0_CLIENT_SECRET',
  'AUTH0_SECRET',
  'APP_BASE_URL',
  'AUTH_SESSION_ENCRYPTION_KEY',
  'AUTH_SESSION_DB_PATH',
];

// Placeholder values that indicate the variable was never set properly.
const PLACEHOLDER_PATTERN = /^(your[-_]|change[-_]me|example|placeholder|xxx|<|TODO)/i;

function validateStartupConfig(): ValidationResult {
  const errors: string[] = [];

  for (const name of REQUIRED_VARS) {
    const value = process.env[name];
    if (!value || value.trim() === '') {
      errors.push(`${name} is not set.`);
    } else if (PLACEHOLDER_PATTERN.test(value)) {
      errors.push(`${name} appears to be a placeholder value.`);
    }
  }

  // HTTPS enforcement for production.
  const appBaseUrl = process.env.APP_BASE_URL;
  if (appBaseUrl && !appBaseUrl.startsWith('https://')) {
    errors.push(
      `APP_BASE_URL must use https:// in production. Got: ${appBaseUrl.split('://')[0]}://...`,
    );
  }

  // Encryption key length check (32 bytes from base64).
  const keyValue = process.env.AUTH_SESSION_ENCRYPTION_KEY;
  if (keyValue && keyValue.trim() !== '') {
    try {
      const decoded = Buffer.from(keyValue, 'base64');
      if (decoded.length !== 32) {
        errors.push(
          `AUTH_SESSION_ENCRYPTION_KEY must decode to 32 bytes; got ${decoded.length} bytes.`,
        );
      }
    } catch {
      errors.push('AUTH_SESSION_ENCRYPTION_KEY is not valid base64.');
    }
  }

  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

// Skip all checks during `next build`.  The build runner imports server
// modules to collect page data but does not supply real env vars.
// Validation runs at server startup when the built application is started.
if (!IS_BUILD_PHASE) {
  const result = validateStartupConfig();

  if (!result.ok) {
    if (IS_PRODUCTION) {
      // Hard failure: do not start with misconfigured security in production.
      throw new Error(
        `[NOHA] Production configuration is invalid:\n${result.errors.map((e) => `  • ${e}`).join('\n')}\n` +
          'Correct these environment variables before deploying.',
      );
    } else {
      // Advisory only in development.
      console.warn(
        `[NOHA] Development configuration warnings (non-fatal):\n${result.errors.map((e) => `  • ${e}`).join('\n')}`,
      );
    }
  }
}

export { validateStartupConfig };
