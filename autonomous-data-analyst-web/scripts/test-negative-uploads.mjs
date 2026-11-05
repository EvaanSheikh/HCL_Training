import Database from 'better-sqlite3';
import { readFileSync } from 'node:fs';
import { encrypt } from '../node_modules/@auth0/nextjs-auth0/dist/server/cookies.js';

let auth0Secret = null;
let authSessionDbPath = '../data/sessions.db';
for (const line of readFileSync('.env.local', 'utf8').split(/\r?\n/)) {
  if (line.startsWith('AUTH0_SECRET=')) {
    auth0Secret = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
  if (line.startsWith('AUTH_SESSION_DB_PATH=')) {
    authSessionDbPath = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
}
const db = new Database(authSessionDbPath);
const row = db.prepare('SELECT id FROM auth_sessions LIMIT 1').get();
const cookieJwe = await encrypt({ id: row.id }, auth0Secret, Math.floor(Date.now() / 1000) + 3600);

// Get CSRF
const sessionRes = await fetch('http://localhost:3000/api/auth/session', {
  headers: { 'Cookie': 'noha-session=' + cookieJwe }
});
const setCookie = sessionRes.headers.get('set-cookie') || '';
const csrfToken = (setCookie.match(/noha-csrf=([^;]+)/) || [])[1];

// Test 1: Unsupported file extension (.txt)
const form1 = new FormData();
form1.append('file', new Blob(['hello world'], { type: 'text/plain' }), 'test.txt');
const res1 = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken
  },
  body: form1
});
console.log('Unsupported extension status:', res1.status);
console.log('Unsupported extension body:', await res1.text());

// Test 2: Empty file (.csv)
const form2 = new FormData();
form2.append('file', new Blob([''], { type: 'text/csv' }), 'empty.csv');
const res2 = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken
  },
  body: form2
});
console.log('Empty file status:', res2.status);
console.log('Empty file body:', await res2.text());

// Test 3: Wrong Origin header
const res3 = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://malicious.example',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken
  },
  body: form1
});
console.log('Wrong origin status:', res3.status);
console.log('Wrong origin body:', await res3.text());

// Test 4: Missing CSRF token
const res4 = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}`
  },
  body: form1
});
console.log('Missing CSRF status:', res4.status);
console.log('Missing CSRF body:', await res4.text());
