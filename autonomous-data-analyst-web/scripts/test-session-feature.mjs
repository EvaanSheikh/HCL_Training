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

// Test 1: Fetch valid session
const sessionId = 'e65156ab-f37c-4a6c-a4f2-fbdd42ed3c4b';
const res1 = await fetch(`http://localhost:3000/api/noha/analysis/${sessionId}`, {
  headers: { 'Cookie': `noha-session=${cookieJwe}` }
});
console.log('1. Valid session GET status:', res1.status);
const json1 = await res1.json();
console.log('   Retrieved status:', json1.status);
console.log('   Retrieved query:', json1.user_query);
console.log('   Has tool calls:', json1.tool_calls?.length > 0);
console.log('   Has report:', typeof json1.final_report === 'string' && json1.final_report.length > 0);

// Test 2: Fetch non-existent session
const res2 = await fetch(`http://localhost:3000/api/noha/analysis/00000000-0000-0000-0000-000000000000`, {
  headers: { 'Cookie': `noha-session=${cookieJwe}` }
});
console.log('2. Non-existent session GET status:', res2.status);
const json2 = await res2.json();
console.log('   Detail:', json2.detail);

// Test 3: Fetch unauthenticated
const res3 = await fetch(`http://localhost:3000/api/noha/analysis/${sessionId}`);
console.log('3. Unauthenticated session GET status:', res3.status);
const json3 = await res3.json();
console.log('   Detail:', json3.detail);
