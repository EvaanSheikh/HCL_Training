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

console.log('--- Starting 60-Second Runtime Observation ---');
console.log('Testing GET / (initial page load)...');
const homeRes = await fetch('http://localhost:3000/');
console.log('GET / status:', homeRes.status);

const startTime = Date.now();
let iteration = 0;
let successCount = 0;

// Poll session endpoint repeatedly for 60 seconds, simulating active browser session with rolling updates
while (Date.now() - startTime < 60000) {
  iteration++;
  const tStart = Date.now();
  const res = await fetch('http://localhost:3000/api/auth/session', {
    headers: { 'Cookie': `noha-session=${cookieJwe}` }
  });
  if (res.status === 200) {
    successCount++;
  }
  const elapsed = Date.now() - tStart;
  if (iteration % 5 === 0 || iteration === 1) {
    console.log(`[${Math.round((Date.now() - startTime) / 1000)}s] Iteration ${iteration}: status ${res.status} (latency ${elapsed}ms)`);
  }
  await new Promise(r => setTimeout(r, 2000));
}

console.log('--- Completed 60-Second Runtime Observation ---');
console.log(`Total session requests made: ${iteration}, successful: ${successCount}`);
