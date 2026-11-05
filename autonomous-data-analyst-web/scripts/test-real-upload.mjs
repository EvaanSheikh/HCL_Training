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

const csvContent = 'id,name,value\n1,alpha,10.5\n2,beta,20.0\n3,gamma,35.2\n';
const form = new FormData();
form.append('file', new Blob([csvContent], { type: 'text/csv' }), 'sample.csv');

console.log('Sending upload request with real token to http://127.0.0.1:8000/api/upload...');
const res = await fetch('http://127.0.0.1:8000/api/upload', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${at}`
  },
  body: form
});

console.log('Upload response status:', res.status);
const resText = await res.text();
console.log('Upload response body:', resText);
