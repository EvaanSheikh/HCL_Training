import Database from 'better-sqlite3';
import { compactDecrypt } from 'jose';
import { readFileSync } from 'node:fs';

const envFile = '.env.local';
let keyB64 = null;
for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
  if (line.startsWith('AUTH_SESSION_ENCRYPTION_KEY=')) {
    keyB64 = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
  }
}
const key = Buffer.from(keyB64, 'base64');
const db = new Database('../data/sessions.db');
const row = db.prepare('SELECT id, payload, expires_at FROM auth_sessions LIMIT 1').get();
const { plaintext } = await compactDecrypt(row.payload, key);
const data = JSON.parse(Buffer.from(plaintext).toString());
console.log('Successfully decrypted session from ../data/sessions.db!');
console.log('Session ID:', row.id.slice(0, 8));
console.log('User email:', data.user?.email);
console.log('Expires at:', new Date(row.expires_at).toISOString());
