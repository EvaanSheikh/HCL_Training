import Database from 'better-sqlite3';
import { compactDecrypt } from 'jose';
import { readFileSync, existsSync } from 'node:fs';

const envFile = '.env.local';
let keyB64 = null;
let authSessionDbPath = '../data/sessions.db';
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    if (line.startsWith('AUTH_SESSION_ENCRYPTION_KEY=')) {
      keyB64 = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
    }
    if (line.startsWith('AUTH_SESSION_DB_PATH=')) {
      authSessionDbPath = line.split('=', 2)[1].trim().replace(/^["']|["']$/g, '');
    }
  }
}

if (!keyB64) {
  console.log('No key in .env.local');
  process.exit(0);
}

const key = Buffer.from(keyB64, 'base64');
const db = new Database(authSessionDbPath);
const rows = db.prepare('SELECT id, payload FROM auth_sessions').all();
console.log('Active sessions in DB:', rows.length);

for (const row of rows) {
  try {
    const { plaintext } = await compactDecrypt(row.payload, key);
    const data = JSON.parse(Buffer.from(plaintext).toString());
    console.log('Session top keys:', Object.keys(data));
    if (data.tokenSet) {
      console.log('tokenSet keys:', Object.keys(data.tokenSet));
      const at = data.tokenSet.accessToken;
      if (at) {
        const parts = at.split('.');
        console.log('accessToken length:', at.length, 'is_jwt:', parts.length === 3);
        if (parts.length === 3) {
          const h = JSON.parse(Buffer.from(parts[0], 'base64url').toString());
          const p = JSON.parse(Buffer.from(parts[1], 'base64url').toString());
          console.log('JWT header:', h);
          console.log('JWT iss:', p.iss);
          console.log('JWT aud:', p.aud);
          console.log('JWT azp:', p.azp);
          console.log('JWT scope:', p.scope);
        } else {
          console.log('accessToken is NOT a JWT (it is opaque or unexpected)');
        }
      }
      if (data.tokenSet.idToken) {
        const parts = data.tokenSet.idToken.split('.');
        if (parts.length === 3) {
          const p = JSON.parse(Buffer.from(parts[1], 'base64url').toString());
          console.log('idToken iss:', p.iss);
          console.log('idToken aud:', p.aud);
          console.log('idToken azp:', p.azp);
        }
      }
    }
  } catch (err) {
    console.log('Decrypt error:', err.message);
  }
}
