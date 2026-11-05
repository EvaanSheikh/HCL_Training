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

console.log('Testing opaque token against Auth0 /userinfo...');
const res = await fetch('https://dev-acg2z7ixw8t6hw8s.us.auth0.com/userinfo', {
  headers: { 'Authorization': `Bearer ${at}` }
});

console.log('/userinfo status:', res.status);
if (res.ok) {
  const profile = await res.json();
  console.log('Userinfo sub:', profile.sub);
  console.log('Userinfo verified successfully!');
} else {
  console.log('/userinfo error body:', await res.text());
}
