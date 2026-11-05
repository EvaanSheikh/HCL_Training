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

const sessionRes = await fetch('http://localhost:3000/api/auth/session', {
  headers: { 'Cookie': `noha-session=${cookieJwe}` }
});
const setCookie = sessionRes.headers.get('set-cookie') || '';
const csrfToken = (setCookie.match(/noha-csrf=([^;]+)/) || [])[1];

console.log('Testing query on 500k row dataset...');
const t0 = Date.now();
const res = await fetch('http://localhost:3000/api/noha/analyze', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    user_query: 'What is the total sales quantity and average discount by region?',
    dataset_id: 'e848b639-15ac-4ea7-8ad0-89cd93b827e5'
  })
});

console.log('Analyze finished in', (Date.now() - t0), 'ms');
console.log('Status:', res.status);
const json = await res.json();
console.log('Session ID:', json.session_id);
console.log('Status:', json.status);
console.log('Plan steps count:', json.analysis_plan?.length);
console.log('Tool calls count:', json.tool_calls?.length);
console.log('Visualizations count:', json.visualizations?.length);
console.log('Final report length:', json.final_report?.length);
