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

// Step 1: Session check & CSRF token
console.log('1. Fetching session and CSRF token from /api/auth/session...');
const sessionRes = await fetch('http://localhost:3000/api/auth/session', {
  headers: { 'Cookie': `noha-session=${cookieJwe}` }
});
console.log('Session status:', sessionRes.status);
const setCookie = sessionRes.headers.get('set-cookie') || '';
const csrfToken = (setCookie.match(/noha-csrf=([^;]+)/) || [])[1];
const sessionJson = await sessionRes.json();
console.log('User authenticated:', sessionJson.authenticated, sessionJson.user?.email);

// Step 2: Upload CSV through Next.js BFF
console.log('\n2. Uploading sales.csv via POST /api/noha/upload...');
const csvContent = readFileSync('../data/sample/sales.csv', 'utf8');
const form = new FormData();
form.append('file', new Blob([csvContent], { type: 'text/csv' }), 'sales.csv');

const uploadRes = await fetch('http://localhost:3000/api/noha/upload', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken
  },
  body: form
});
console.log('Upload status:', uploadRes.status);
const uploadJson = await uploadRes.json();
console.log('Upload response dataset_id:', uploadJson.dataset_id);
console.log('Upload validation valid:', uploadJson.validation?.valid, 'rows:', uploadJson.validation?.rows);

// Step 3: Submit analytical question through Next.js BFF
console.log('\n3. Submitting analytical query via POST /api/noha/analyze...');
const analyzeRes = await fetch('http://localhost:3000/api/noha/analyze', {
  method: 'POST',
  headers: {
    'Origin': 'http://localhost:3000',
    'Cookie': `noha-session=${cookieJwe}; noha-csrf=${csrfToken}`,
    'X-CSRF-Token': csrfToken,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    user_query: 'What is the total revenue by region?',
    dataset_id: uploadJson.dataset_id
  })
});
console.log('Analyze status:', analyzeRes.status);
const analyzeJson = await analyzeRes.json();
console.log('Session ID:', analyzeJson.session_id);
console.log('Analysis Status:', analyzeJson.status);
console.log('Plan steps count:', analyzeJson.analysis_plan?.length);
console.log('Tool calls count:', analyzeJson.tool_calls?.length);
console.log('Visualizations count:', analyzeJson.visualizations?.length);
console.log('Visualizations URLs:', analyzeJson.visualizations);
console.log('Final report length:', analyzeJson.final_report?.length);
if (analyzeJson.final_report) {
  console.log('Final report preview:\n' + analyzeJson.final_report.slice(0, 300));
}

// Step 4: Retrieve session details through Next.js BFF
console.log('\n4. Retrieving session details via GET /api/noha/analysis/' + analyzeJson.session_id + '...');
const getSessionRes = await fetch(`http://localhost:3000/api/noha/analysis/${analyzeJson.session_id}`, {
  headers: {
    'Cookie': `noha-session=${cookieJwe}`
  }
});
console.log('Get session status:', getSessionRes.status);
const getSessionJson = await getSessionRes.json();
console.log('Retrieved status:', getSessionJson.status);
console.log('Retrieved session_id matches:', getSessionJson.session_id === analyzeJson.session_id);

// Step 5: Retrieve chart image through Next.js BFF
if (analyzeJson.visualizations?.length > 0) {
  const chartPath = analyzeJson.visualizations[0];
  console.log('\n5. Retrieving chart image via GET http://localhost:3000' + chartPath + '...');
  const chartRes = await fetch('http://localhost:3000' + chartPath, {
    headers: { 'Cookie': `noha-session=${cookieJwe}` }
  });
  console.log('Chart status:', chartRes.status);
  console.log('Chart content-type:', chartRes.headers.get('content-type'));
  const chartBuf = await chartRes.arrayBuffer();
  console.log('Chart byte size:', chartBuf.byteLength);
  const isPng = new Uint8Array(chartBuf)[0] === 137 && new Uint8Array(chartBuf)[1] === 80;
  console.log('Valid PNG binary header:', isPng);
}
