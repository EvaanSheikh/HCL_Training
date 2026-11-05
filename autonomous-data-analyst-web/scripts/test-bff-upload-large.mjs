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
  headers: { 'Cookie': `noha-session=${cookieJwe}` }
});
const setCookie = sessionRes.headers.get('set-cookie') || '';
const csrfToken = (setCookie.match(/noha-csrf=([^;]+)/) || [])[1];

console.log('Uploading 88.5 MB CSV through Next.js BFF POST http://localhost:3000/api/noha/upload...');
const csvBuffer = readFileSync('../data/autonomous_business_sales_dataset_fixed.csv');
const form = new FormData();
form.append('file', new Blob([csvBuffer], { type: 'text/csv' }), 'autonomous_business_sales_dataset_fixed.csv');

const t0 = Date.now();
const uploadRes = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken
  },
  body: form
});
console.log('BFF upload finished in', (Date.now() - t0), 'ms');
console.log('BFF status:', uploadRes.status);
console.log('BFF body:', await uploadRes.text());
