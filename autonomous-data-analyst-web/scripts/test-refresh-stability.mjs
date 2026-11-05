import Database from 'better-sqlite3';
import { readFileSync, statSync } from 'node:fs';
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

console.log('Sending 10 consecutive /api/auth/session requests...');
for (let i = 1; i <= 10; i++) {
  const res = await fetch('http://localhost:3000/api/auth/session', {
    headers: { 'Cookie': `noha-session=${cookieJwe}` }
  });
  if (res.status !== 200) {
    console.error(`Request ${i} failed with status:`, res.status);
    process.exit(1);
  }
  // Brief pause to simulate rapid client polling
  await new Promise(r => setTimeout(r, 100));
}
console.log('All 10 /api/auth/session requests returned HTTP 200.');
