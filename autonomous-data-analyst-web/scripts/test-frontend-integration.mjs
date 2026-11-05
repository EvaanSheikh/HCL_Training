import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createServer as createNetServer } from 'node:net';

// Helper to find a free port
async function freePort() {
  const server = createNetServer();
  await new Promise((resolve, reject) => server.listen(0, '127.0.0.1', resolve).once('error', reject));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

// ─────────────────────────────────────────────────────────────────────────────
// Part 1: Test Chart URL Translation & Validation
// ─────────────────────────────────────────────────────────────────────────────

async function testChartUrl() {
  const { chartUrl } = await import('../lib/format.ts');

  const sessionId = '11111111-2222-3333-4444-555555555555';
  const assetId = '66666666-7777-8888-9999-000000000000';

  // 1. Translates backend /api/analysis/{session_id}/charts/{asset_id} to /api/noha/...
  const backendPath = `/api/analysis/${sessionId}/charts/${assetId}`;
  const translated = chartUrl(backendPath);
  assert.equal(
    translated,
    `/api/noha/analysis/${sessionId}/charts/${assetId}`,
    'Backend chart path must be mapped to the /api/noha BFF prefix',
  );

  // 2. Accepts already-prefixed /api/noha/analysis/... path
  const bffPath = `/api/noha/analysis/${sessionId}/charts/${assetId}`;
  assert.equal(
    chartUrl(bffPath),
    bffPath,
    'BFF path must remain unchanged',
  );

  // 3. Attaches version query parameter when supplied
  const withVersion = chartUrl(backendPath, 'v123');
  assert.equal(
    withVersion,
    `/api/noha/analysis/${sessionId}/charts/${assetId}?v=v123`,
    'Version query parameter must be appended',
  );

  // 4. Rejects legacy filesystem paths
  assert.equal(chartUrl('C:\\data\\reports\\chart.png'), null, 'Windows path must be rejected');
  assert.equal(chartUrl('/var/data/reports/chart.png'), null, 'POSIX path must be rejected');
  assert.equal(chartUrl('../../secrets.png'), null, 'Traversal path must be rejected');
  assert.equal(chartUrl('/api/analysis/not-a-uuid/charts/123'), null, 'Non-UUID must be rejected');

  console.log('✓ Part 1: Chart URL translation and validation tests passed.');
}

// ─────────────────────────────────────────────────────────────────────────────
// Part 2: Test HTTP Error Formatting & Status Handling
// ─────────────────────────────────────────────────────────────────────────────

async function testErrorFormatting() {
  const { formatHttpError, detailMessage, ApiError } = await import('../lib/api.ts');

  // Verify ApiError properties
  const err = new ApiError('http', 'Test error', 503);
  assert.equal(err.kind, 'http');
  assert.equal(err.status, 503);
  assert.equal(err.message, 'Test error');

  // Verify specific HTTP status messages
  assert.match(formatHttpError(401), /Authentication required/i);
  assert.match(formatHttpError(403), /Access denied|Request rejected/i);
  assert.match(formatHttpError(404), /not found/i);
  assert.match(formatHttpError(413), /100 MB/i);
  assert.match(formatHttpError(422), /Validation failed/i);
  assert.match(formatHttpError(429), /Too many requests/i);
  assert.match(formatHttpError(500), /Analysis execution failed/i);
  assert.match(formatHttpError(502), /unreachable/i);
  assert.match(formatHttpError(503), /busy/i);

  // Verify detailMessage extracts FastAPI structured errors (loc + msg)
  const pydanticError = {
    detail: [
      { loc: ['body', 'user_query'], msg: 'Field required' },
      { loc: ['body', 'dataset_id'], msg: 'String should have at least 1 character' },
    ],
  };
  const extracted = detailMessage(pydanticError, 'Fallback', 422);
  assert.equal(extracted, 'user_query: Field required; dataset_id: String should have at least 1 character');

  // Verify detailMessage extracts string detail
  const customDetail = { detail: 'Custom engine error message.' };
  assert.equal(detailMessage(customDetail, 'Fallback', 400), 'Custom engine error message.');

  // Verify fallback when body is not JSON or empty
  assert.match(detailMessage(null, 'Fallback error', 503), /busy/i);

  console.log('✓ Part 2: HTTP error formatting and FastAPI detail extraction tests passed.');
}

// ─────────────────────────────────────────────────────────────────────────────
// Part 3: Test Mocked Endpoints (401, 403, 413, 422, 503, 200)
// ─────────────────────────────────────────────────────────────────────────────

async function testMockedApiIntegration() {
  const port = await freePort();
  let lastRequest = null;

  const server = createServer(async (req, res) => {
    lastRequest = { method: req.method, url: req.url, headers: req.headers };
    res.setHeader('Content-Type', 'application/json');

    if (req.url === '/test/auth-error-401') {
      res.writeHead(401);
      res.end(JSON.stringify({ detail: 'Authentication required.' }));
      return;
    }
    if (req.url === '/test/csrf-error-403') {
      res.writeHead(403);
      res.end(JSON.stringify({ detail: 'Request rejected.' }));
      return;
    }
    if (req.url === '/test/payload-error-413') {
      res.writeHead(413);
      res.end(JSON.stringify({ detail: 'File exceeds the 100 MB size limit.' }));
      return;
    }
    if (req.url === '/test/validation-error-422') {
      res.writeHead(422);
      res.end(JSON.stringify({
        detail: [{ loc: ['body', 'user_query'], msg: 'ensure this value has at least 1 characters' }],
      }));
      return;
    }
    if (req.url === '/test/busy-error-503') {
      res.writeHead(503);
      res.end(JSON.stringify({ detail: 'Server is busy. Please retry shortly.' }));
      return;
    }
    if (req.url === '/test/success-analyze') {
      res.writeHead(200);
      res.end(JSON.stringify({
        session_id: '11111111-2222-3333-4444-555555555555',
        status: 'complete',
        user_query: 'Show revenue',
        dataset_id: '99999999-8888-7777-6666-555555555555',
        analysis_plan: [{ step: 1, action: 'group_aggregate' }],
        tool_calls: [{ action: 'group_aggregate', parameters: {} }],
        findings: [{ type: 'group_aggregate', message: 'North generated most' }],
        visualizations: ['/api/analysis/11111111-2222-3333-4444-555555555555/charts/66666666-7777-8888-9999-000000000000'],
        evidence: [{ operation: 'group_aggregate' }],
        validation_results: [{ check: 'no_nulls', passed: true }],
        errors: [],
        final_report: 'Analysis complete.',
      }));
      return;
    }

    res.writeHead(404);
    res.end(JSON.stringify({ detail: 'Not found.' }));
  });

  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));

  try {
    const { detailMessage } = await import('../lib/api.ts');

    // Test 401 response handling
    const res401 = await fetch(`http://127.0.0.1:${port}/test/auth-error-401`);
    assert.equal(res401.status, 401);
    const body401 = await res401.json();
    assert.equal(detailMessage(body401, 'fallback', 401), 'Authentication required.');

    // Test 403 response handling
    const res403 = await fetch(`http://127.0.0.1:${port}/test/csrf-error-403`);
    assert.equal(res403.status, 403);
    const body403 = await res403.json();
    assert.equal(detailMessage(body403, 'fallback', 403), 'Request rejected.');

    // Test 413 response handling
    const res413 = await fetch(`http://127.0.0.1:${port}/test/payload-error-413`);
    assert.equal(res413.status, 413);
    const body413 = await res413.json();
    assert.equal(detailMessage(body413, 'fallback', 413), 'File exceeds the 100 MB size limit.');

    // Test 422 response handling
    const res422 = await fetch(`http://127.0.0.1:${port}/test/validation-error-422`);
    assert.equal(res422.status, 422);
    const body422 = await res422.json();
    assert.equal(detailMessage(body422, 'fallback', 422), 'user_query: ensure this value has at least 1 characters');

    // Test 503 response handling
    const res503 = await fetch(`http://127.0.0.1:${port}/test/busy-error-503`);
    assert.equal(res503.status, 503);
    const body503 = await res503.json();
    assert.equal(detailMessage(body503, 'fallback', 503), 'Server is busy. Please retry shortly.');

    // Test 200 response handling
    const res200 = await fetch(`http://127.0.0.1:${port}/test/success-analyze`);
    assert.equal(res200.status, 200);
    const body200 = await res200.json();
    assert.equal(body200.session_id, '11111111-2222-3333-4444-555555555555');
    assert.equal(body200.status, 'complete');

    console.log('✓ Part 3: Mocked integration response checks (401, 403, 413, 422, 503, 200) passed.');
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Runner
// ─────────────────────────────────────────────────────────────────────────────

async function run() {
  console.log('Running NOHA Frontend Integration and Error Tests...\n');
  await testChartUrl();
  await testErrorFormatting();
  await testMockedApiIntegration();
  console.log('\nAll frontend integration and error tests passed successfully.');
}

run().catch((error) => {
  console.error('Test failure:', error);
  process.exit(1);
});
