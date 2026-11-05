import Database from 'better-sqlite3';
import { compactDecrypt } from 'jose';
import { readFileSync } from 'node:fs';
import { encrypt } from '../node_modules/@auth0/nextjs-auth0/dist/server/cookies.js';

const envFile = '.env.local';
let keyB64 = null;
let auth0Secret = null;
let authSessionDbPath = '../data/sessions.db';
for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
  if (line.startsWith('AUTH_SESSION_ENCRYPTION_KEY=')) {
    keyB64 = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
  if (line.startsWith('AUTH0_SECRET=')) {
    auth0Secret = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
  if (line.startsWith('AUTH_SESSION_DB_PATH=')) {
    authSessionDbPath = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
}

const key = Buffer.from(keyB64, 'base64');
const db = new Database(authSessionDbPath);
const row = db.prepare('SELECT id, payload FROM auth_sessions LIMIT 1').get();

if (!row) {
  console.log('No session');
  process.exit(0);
}

const sessionId = row.id;
console.log('Session ID exists (length):', sessionId.length);

// Generate properly sealed Auth0 session cookie
const nowEpoch = Math.floor(Date.now() / 1000);
const cookieJwe = await encrypt({ id: sessionId }, auth0Secret, nowEpoch + 8 * 3600);

// Step 1: Query GET /api/auth/session to get CSRF cookie
const sessionRes = await fetch('http://localhost:3000/api/auth/session', {
  headers: {
    'Cookie': `noha-session=${cookieJwe}`
  }
});

console.log('--- Stage 1: GET /api/auth/session ---');
console.log('HTTP Status:', sessionRes.status);
const setCookie = sessionRes.headers.get('set-cookie') || '';
console.log('Set-Cookie received:', setCookie.includes('noha-csrf'));

let csrfToken = '';
const match = setCookie.match(/noha-csrf=([^;]+)/);
if (match) csrfToken = match[1];

const sessionData = await sessionRes.json();
console.log('Session authenticated:', sessionData.authenticated);
console.log('Session user:', sessionData.user ? { name: sessionData.user.name, email: sessionData.user.email } : null);

// Step 2: POST /api/noha/upload through Next.js BFF
console.log('\n--- Stage 2: POST /api/noha/upload (Next.js BFF) ---');
const csvContent = 'id,product,price\n101,Widget A,15.99\n102,Widget B,24.50\n103,Widget C,9.99\n';
const form = new FormData();
form.append('file', new Blob([csvContent], { type: 'text/csv' }), 'products.csv');

const bffRes = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken,
  },
  body: form
});

console.log('BFF HTTP Status:', bffRes.status);
const bffText = await bffRes.text();
console.log('BFF Response Body:', bffText);
