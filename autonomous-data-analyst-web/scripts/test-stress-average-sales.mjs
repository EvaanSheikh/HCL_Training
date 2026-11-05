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

console.log('1. Fetching session and CSRF token from /api/auth/session...');
const sessionRes = await fetch('http://localhost:3000/api/auth/session', {
  headers: { 'Cookie': `noha-session=${cookieJwe}` }
});
console.log('Session status:', sessionRes.status);
const setCookie = sessionRes.headers.get('set-cookie') || '';
const csrfToken = (setCookie.match(/noha-csrf=([^;]+)/) || [])[1];
const sessionJson = await sessionRes.json();
console.log('User authenticated:', sessionJson.authenticated, sessionJson.user?.email);

console.log('\n2. Uploading autonomous_business_sales_dataset_stress.csv (500,003 rows)...');
const csvBuffer = readFileSync('../data/test/autonomous_business_sales_dataset_stress.csv');
const form = new FormData();
form.append('file', new Blob([csvBuffer], { type: 'text/csv' }), 'autonomous_business_sales_dataset_stress.csv');

const tUploadStart = Date.now();
const uploadRes = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken
  },
  body: form
});
console.log(`Upload status: ${uploadRes.status} (took ${Date.now() - tUploadStart}ms)`);
const uploadJson = await uploadRes.json();
console.log('Upload response dataset_id:', uploadJson.dataset_id);
console.log('Upload validation valid:', uploadJson.validation?.valid, 'rows:', uploadJson.validation?.rows);

console.log('\n3. Asking: "What are the average sales across all records?"...');
const tAnalyzeStart = Date.now();
const analyzeRes = await fetch('http://localhost:3000/api/noha/analyze', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    user_query: 'What are the average sales across all records?',
    dataset_id: uploadJson.dataset_id
  })
});
console.log(`Analyze status: ${analyzeRes.status} (took ${Date.now() - tAnalyzeStart}ms)`);
const analyzeJson = await analyzeRes.json();
console.log('Analysis Status:', analyzeJson.status);
console.log('Analysis plan:', JSON.stringify(analyzeJson.analysis_plan, null, 2));
console.log('Tool calls count:', analyzeJson.tool_calls?.length);
console.log('Findings:', JSON.stringify(analyzeJson.findings, null, 2));
console.log('Validation results:', JSON.stringify(analyzeJson.validation_results, null, 2));
console.log('Final report preview:\n', analyzeJson.final_report?.slice(0, 500));
