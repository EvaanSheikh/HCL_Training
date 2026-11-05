import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { createServer as createNetServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { randomBytes } from 'node:crypto';

const projectRoot = resolve(import.meta.dirname, '..');
const nextBin = resolve(projectRoot, 'node_modules/next/dist/bin/next');
const authDbPath = join(tmpdir(), `noha-bff-test-${process.pid}.db`);
const encryptionKey = randomBytes(32).toString('base64');

async function freePort() {
  const server = createNetServer();
  await new Promise((resolvePromise, reject) => server.listen(0, '127.0.0.1', resolvePromise).once('error', reject));
  const { port } = server.address();
  await new Promise((resolvePromise) => server.close(resolvePromise));
  return port;
}

const upstreamRequests = [];
const upstream = createServer((request, response) => {
  upstreamRequests.push({ method: request.method, url: request.url, authorization: request.headers.authorization });
  if (request.url === '/api/health') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ status: 'ok', service: 'autonomous-data-analyst' }));
    return;
  }
  response.writeHead(500, { 'content-type': 'text/plain' });
  response.end('internal test upstream error');
});
await new Promise((resolvePromise) => upstream.listen(0, '127.0.0.1', resolvePromise));
const upstreamPort = upstream.address().port;
const port = await freePort();
const baseUrl = `http://127.0.0.1:${port}`;

const child = spawn(process.execPath, [nextBin, 'dev', '--hostname', '127.0.0.1', '--port', String(port)], {
  cwd: projectRoot,
  env: {
    ...process.env,
    APP_BASE_URL: baseUrl,
    AUTH0_DOMAIN: 'tenant.example.invalid',
    AUTH0_CLIENT_ID: 'bff-http-test-client',
    AUTH0_CLIENT_SECRET: 'test-only-placeholder',
    AUTH0_SECRET: 'test-only-secret-that-is-not-for-production',
    AUTH0_AUDIENCE: 'https://api.noha.example',
    AUTH0_ISSUER: 'https://tenant.example.invalid/',
    AUTH_SESSION_DB_PATH: authDbPath,
    AUTH_SESSION_ENCRYPTION_KEY: encryptionKey,
    NOHA_API_BASE_URL: `http://127.0.0.1:${upstreamPort}`,
  },
  stdio: 'ignore',
});

async function request(path, init) {
  return fetch(`${baseUrl}${path}`, { ...init, signal: AbortSignal.timeout(15_000) });
}

try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Next.js exited before readiness (${child.exitCode}).`);
    try {
      const response = await request('/api/auth/session');
      if (response.status === 200) { ready = true; break; }
    } catch { /* The server is still starting. */ }
    await delay(500);
  }
  assert.equal(ready, true, 'Next.js must start with test-only placeholder configuration');

  const session = await request('/api/auth/session');
  assert.equal(session.status, 200);
  assert.deepEqual(await session.json(), { authenticated: false });

  const health = await request('/api/health');
  assert.equal(health.status, 200);
  assert.deepEqual(await health.json(), { status: 'ok' });

  const unauthUpload = await request('/api/noha/upload', { method: 'POST', body: 'test-data' });
  assert.equal(unauthUpload.status, 401);
  assert.deepEqual(await unauthUpload.json(), { detail: 'Authentication required.' });

  const unknown = await request('/api/noha/admin/secrets');
  assert.equal(unknown.status, 404);
  assert.deepEqual(await unknown.json(), { detail: 'Not found.' });

  const unsupportedMethod = await request('/api/noha/upload', { method: 'PUT' });
  assert.equal(unsupportedMethod.status, 405);

  const protectedResource = await request('/api/noha/analysis/00000000-0000-4000-8000-000000000000');
  assert.equal(protectedResource.status, 401);
  assert.deepEqual(await protectedResource.json(), { detail: 'Authentication required.' });

  const tooLarge = await request('/api/noha/analyze', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: 'x'.repeat(2 * 1024 * 1024 + 1),
  });
  assert.equal(tooLarge.status, 413);
  assert.match(await tooLarge.text(), /configured limit/);
  const nohaUpstreamRequests = upstreamRequests.filter((r) => r.url !== '/api/health');
  assert.deepEqual(nohaUpstreamRequests, [], 'unauthenticated and oversized requests must not reach upstream');
  const healthRequests = upstreamRequests.filter((r) => r.url === '/api/health');
  assert.equal(healthRequests.length, 1, 'health check must query upstream /api/health');

  console.log('BFF HTTP checks passed: unauthenticated session, path/method allowlist, auth gate, body bound, no upstream forwarding.');
} finally {
  child.kill();
  await new Promise((resolvePromise) => {
    if (child.exitCode !== null) return resolvePromise();
    child.once('exit', resolvePromise);
    setTimeout(resolvePromise, 3_000).unref();
  });
  await new Promise((resolvePromise) => upstream.close(resolvePromise));
}
