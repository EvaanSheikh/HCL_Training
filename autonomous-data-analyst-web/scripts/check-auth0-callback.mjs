#!/usr/bin/env node
/**
 * check-auth0-callback.mjs
 *
 * Verifies that the Auth0 application is correctly configured for the current
 * APP_BASE_URL by printing the exact URLs that must be registered in the
 * Auth0 Dashboard. Does NOT print or expose secrets.
 *
 * Usage:
 *   node scripts/check-auth0-callback.mjs
 */

import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const envFile = resolve(__dirname, '..', '.env.local');

// ── Parse .env.local safely ─────────────────────────────────────────────────
function parseEnvFile(path) {
  const vars = {};
  if (!existsSync(path)) return vars;
  const lines = readFileSync(path, 'utf8').split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx < 1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
    vars[key] = value;
  }
  return vars;
}

const env = parseEnvFile(envFile);

// ── Required variables (checked for presence only, never printed) ────────────
const REQUIRED = ['AUTH0_DOMAIN', 'AUTH0_CLIENT_ID', 'AUTH0_SECRET', 'APP_BASE_URL'];
const missing = REQUIRED.filter((k) => !env[k] || env[k].trim() === '');
if (missing.length > 0) {
  console.error(`\n[ERROR] Missing required variables in .env.local: ${missing.join(', ')}\n`);
  process.exit(1);
}

const domain = env['AUTH0_DOMAIN'];
const appBase = env['APP_BASE_URL'].replace(/\/$/, '');

// ── Derive SDK default routes ────────────────────────────────────────────────
// @auth0/nextjs-auth0 v4 defaults:
//   login    → /auth/login
//   callback → /auth/callback   ← must be in Auth0 Allowed Callback URLs
//   logout   → /auth/logout     (overridden to /api/auth/logout in lib/auth0.ts)
const callbackUrl  = `${appBase}/auth/callback`;
const loginUrl     = `${appBase}/auth/login`;
const logoutUrl    = appBase;          // post-logout redirect

console.log('\n╔══════════════════════════════════════════════════════════════════════╗');
console.log('║         NOHA — Auth0 Dashboard Configuration Check                  ║');
console.log('╚══════════════════════════════════════════════════════════════════════╝\n');

console.log(`Auth0 tenant : https://${domain}`);
console.log(`App base URL : ${appBase}\n`);

console.log('─── Required Auth0 Application Settings ───────────────────────────────\n');

console.log('1.  Allowed Callback URLs  (paste this exactly):');
console.log(`    ${callbackUrl}\n`);

console.log('2.  Allowed Logout URLs:');
console.log(`    ${logoutUrl}\n`);

console.log('3.  Allowed Web Origins / CORS:');
console.log(`    ${appBase}\n`);

console.log('─── How to add the Callback URL ────────────────────────────────────────\n');
console.log('    1. Open the Auth0 Management Dashboard:');
console.log(`       https://manage.auth0.com/dashboard/us/${domain.split('.')[0]}/applications`);
console.log('    2. Select your application (the one whose Client ID is in .env.local).');
console.log('    3. Go to Settings → Application URIs.');
console.log(`    4. In "Allowed Callback URLs" add:  ${callbackUrl}`);
console.log(`    5. In "Allowed Logout URLs"  add:  ${logoutUrl}`);
console.log('    6. Click "Save Changes" at the bottom of the page.\n');

console.log('─── Verification ───────────────────────────────────────────────────────\n');
console.log('    After saving:');
console.log('    1. Restart the Next.js dev server (Ctrl-C then npm run dev).');
console.log('    2. Open http://localhost:3000 and click SIGN IN.');
console.log('    3. Auth0 should show the login page instead of a 403 error.\n');

console.log('[INFO] No secret values were read or printed by this script.\n');
