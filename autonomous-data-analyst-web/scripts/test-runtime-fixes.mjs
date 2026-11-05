import assert from 'node:assert/strict';

// ─────────────────────────────────────────────────────────────────────────────
// Part 1: Backend URL Configuration and Normalization
// ─────────────────────────────────────────────────────────────────────────────

async function testBackendUrlConfiguration() {
  const { getBackendBaseUrl, buildBackendApiUrl, isAllowedOrigin } = await import('../lib/backend-config.ts');

  const origNoha = process.env.NOHA_API_BASE_URL;
  const origNextPub = process.env.NEXT_PUBLIC_API_BASE_URL;
  const origAppBase = process.env.APP_BASE_URL;

  try {
    // 1. Missing backend URL
    delete process.env.NOHA_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    const missing = getBackendBaseUrl();
    assert.equal(missing.ok, false);
    assert.match(missing.error, /not configured/i);

    // 2. Trailing slash normalization
    process.env.NOHA_API_BASE_URL = 'http://127.0.0.1:8000/';
    assert.equal(getBackendBaseUrl().url, 'http://127.0.0.1:8000');

    // 3. Trailing /api normalization (prevents /api/api duplication)
    process.env.NOHA_API_BASE_URL = 'http://127.0.0.1:8000/api';
    assert.equal(getBackendBaseUrl().url, 'http://127.0.0.1:8000');

    // 4. Trailing /api/ normalization
    process.env.NOHA_API_BASE_URL = 'http://127.0.0.1:8000/api/';
    assert.equal(getBackendBaseUrl().url, 'http://127.0.0.1:8000');

    // 5. Fallback to NEXT_PUBLIC_API_BASE_URL if NOHA_API_BASE_URL absent
    delete process.env.NOHA_API_BASE_URL;
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000/api';
    assert.equal(getBackendBaseUrl().url, 'http://127.0.0.1:8000');

    // 6. Malformed URL protocol
    process.env.NOHA_API_BASE_URL = 'ftp://127.0.0.1:8000';
    assert.equal(getBackendBaseUrl().ok, false);
    assert.match(getBackendBaseUrl().error, /invalid backend url protocol/i);

    // 7. Malformed string
    process.env.NOHA_API_BASE_URL = 'not a valid url';
    assert.equal(getBackendBaseUrl().ok, false);
    assert.match(getBackendBaseUrl().error, /malformed backend url/i);

    // 8. buildBackendApiUrl tests: ensures NO duplicated /api segments
    process.env.NOHA_API_BASE_URL = 'http://127.0.0.1:8000/api';
    assert.equal(buildBackendApiUrl('health').url, 'http://127.0.0.1:8000/api/health');
    assert.equal(buildBackendApiUrl('/health').url, 'http://127.0.0.1:8000/api/health');
    assert.equal(buildBackendApiUrl('api/health').url, 'http://127.0.0.1:8000/api/health');
    assert.equal(buildBackendApiUrl('/api/health').url, 'http://127.0.0.1:8000/api/health');
    assert.equal(buildBackendApiUrl('upload').url, 'http://127.0.0.1:8000/api/upload');
    assert.equal(buildBackendApiUrl('analysis/123/charts/456', '?v=1').url, 'http://127.0.0.1:8000/api/analysis/123/charts/456?v=1');

    // 9. Origin validation
    process.env.APP_BASE_URL = 'http://localhost:3000';
    assert.equal(isAllowedOrigin('http://localhost:3000').allowed, true);
    // In dev: localhost <-> 127.0.0.1 interchange on same port
    assert.equal(isAllowedOrigin('http://127.0.0.1:3000').allowed, true);
    // Different port / host rejected
    assert.equal(isAllowedOrigin('http://localhost:4000').allowed, false);
    assert.equal(isAllowedOrigin('http://attacker.example').allowed, false);
    assert.equal(isAllowedOrigin(null).allowed, false);

    console.log('✓ Part 1: Backend URL configuration, normalization, and origin checks passed.');
  } finally {
    process.env.NOHA_API_BASE_URL = origNoha;
    process.env.NEXT_PUBLIC_API_BASE_URL = origNextPub;
    process.env.APP_BASE_URL = origAppBase;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Part 2: Auth0 Configuration Inspection & Placeholder Detection
// ─────────────────────────────────────────────────────────────────────────────

async function testAuth0ConfigurationCheck() {
  const { checkAuth0Configuration } = await import('../lib/auth-config.ts');

  const origDomain = process.env.AUTH0_DOMAIN;
  const origClientId = process.env.AUTH0_CLIENT_ID;
  const origSecret = process.env.AUTH0_SECRET;
  const origClientSecret = process.env.AUTH0_CLIENT_SECRET;
  const origAppBase = process.env.APP_BASE_URL;

  try {
    // 1. Missing variables
    delete process.env.AUTH0_DOMAIN;
    delete process.env.AUTH0_CLIENT_ID;
    delete process.env.AUTH0_CLIENT_SECRET;
    delete process.env.AUTH0_SECRET;
    delete process.env.APP_BASE_URL;

    const unconfigured = checkAuth0Configuration();
    assert.equal(unconfigured.isConfigured, false);
    assert.ok(unconfigured.missingVariables.includes('AUTH0_DOMAIN'));
    assert.ok(unconfigured.missingVariables.includes('AUTH0_CLIENT_ID'));

    // 2. Placeholder variables detected
    process.env.AUTH0_DOMAIN = 'your-tenant.us.auth0.com';
    process.env.AUTH0_CLIENT_ID = 'replace-me';
    process.env.AUTH0_CLIENT_SECRET = 'replace-me';
    process.env.AUTH0_SECRET = 'change-me';
    process.env.APP_BASE_URL = 'http://localhost:3000';

    const placeholders = checkAuth0Configuration();
    assert.equal(placeholders.isConfigured, false);
    assert.ok(placeholders.missingVariables.includes('AUTH0_DOMAIN'));
    assert.ok(placeholders.missingVariables.includes('AUTH0_CLIENT_ID'));

    // 3. Fully configured
    process.env.AUTH0_DOMAIN = 'custom-corp.auth0.com';
    process.env.AUTH0_CLIENT_ID = 'actual-client-id-xyz';
    process.env.AUTH0_CLIENT_SECRET = 'actual-client-secret-xyz';
    process.env.AUTH0_SECRET = 'actual-session-secret-at-least-32-chars';
    process.env.APP_BASE_URL = 'http://localhost:3000';

    const configured = checkAuth0Configuration();
    assert.equal(configured.isConfigured, true);
    assert.equal(configured.missingVariables.length, 0);

    console.log('✓ Part 2: Auth0 configuration inspection and placeholder detection passed.');
  } finally {
    process.env.AUTH0_DOMAIN = origDomain;
    process.env.AUTH0_CLIENT_ID = origClientId;
    process.env.AUTH0_SECRET = origSecret;
    process.env.AUTH0_CLIENT_SECRET = origClientSecret;
    process.env.APP_BASE_URL = origAppBase;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Part 3: Client-side Validation (e.g. .xls Rejection & Size Checks)
// ─────────────────────────────────────────────────────────────────────────────

async function testClientSideUploadValidation() {
  const { ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES } = await import('../lib/config.ts');

  // Verify supported extensions: CSV, XLSX, JSON
  assert.ok(ALLOWED_EXTENSIONS.includes('.csv'));
  assert.ok(ALLOWED_EXTENSIONS.includes('.xlsx'));
  assert.ok(ALLOWED_EXTENSIONS.includes('.json'));

  // Verify .xls is strictly NOT allowed
  assert.ok(!ALLOWED_EXTENSIONS.includes('.xls'), '.xls must remain rejected');

  // Verify 100 MB limit
  assert.equal(MAX_UPLOAD_BYTES, 100 * 1024 * 1024);

  console.log('✓ Part 3: Upload extension allowlist and .xls exclusion verified.');
}

// ─────────────────────────────────────────────────────────────────────────────
// Runner
// ─────────────────────────────────────────────────────────────────────────────

async function runAll() {
  console.log('Running NOHA Targeted Runtime Bug Fix Verification...\n');
  await testBackendUrlConfiguration();
  await testAuth0ConfigurationCheck();
  await testClientSideUploadValidation();
  console.log('\nAll targeted runtime bug fix unit tests passed successfully.');
}

runAll().catch((err) => {
  console.error('\nTest failure:', err);
  process.exit(1);
});
