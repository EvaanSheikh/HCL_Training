import Database from 'better-sqlite3';
import { compactDecrypt } from 'jose';
import { readFileSync } from 'node:fs';

const envFile = '.env.local';
let keyB64 = null;
let authSessionDbPath = '../data/sessions.db';
for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
  if (line.startsWith('AUTH_SESSION_ENCRYPTION_KEY=')) {
    keyB64 = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
  if (line.startsWith('AUTH_SESSION_DB_PATH=')) {
    authSessionDbPath = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
}

const key = Buffer.from(keyB64, 'base64');
const db = new Database(authSessionDbPath);
const row = db.prepare('SELECT payload FROM auth_sessions LIMIT 1').get();

if (!row) {
  console.log('No session');
  process.exit(0);
}

const { plaintext } = await compactDecrypt(row.payload, key);
const data = JSON.parse(Buffer.from(plaintext).toString());
const at = data.tokenSet?.accessToken;

// Upload a dataset first
const csvContent = readFileSync('../data/sample/sales.csv', 'utf8');
const form = new FormData();
form.append('file', new Blob([csvContent], { type: 'text/csv' }), 'sales.csv');

console.log('1. Uploading dataset...');
const uploadRes = await fetch('http://127.0.0.1:8000/api/upload', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${at}` },
  body: form
});

console.log('Upload status:', uploadRes.status);
const uploadData = await uploadRes.json();
console.log('Dataset ID:', uploadData.dataset_id);

// Submit an analytical question
console.log('\n2. Submitting analytical question to /api/analyze...');
const analyzeRes = await fetch('http://127.0.0.1:8000/api/analyze', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${at}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    user_query: 'What is the total revenue by region?',
    dataset_id: uploadData.dataset_id
  })
});

console.log('Analyze status:', analyzeRes.status);
const analyzeData = await analyzeRes.json();
console.log('Session ID:', analyzeData.session_id);
console.log('Analysis status:', analyzeData.status);
console.log('Has final report:', !!analyzeData.final_report);
if (analyzeData.final_report) {
  console.log('Final report excerpt:', analyzeData.final_report.slice(0, 150) + '...');
}
if (analyzeData.errors && analyzeData.errors.length > 0) {
  console.log('Analysis errors:', analyzeData.errors);
}
