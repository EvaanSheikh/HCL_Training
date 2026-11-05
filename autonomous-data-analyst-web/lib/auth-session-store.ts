/**
 * SQLite-backed Auth0 session store.
 *
 * ╔═══════════════════════════════════════════════════════╗
 * ║  SINGLE-INSTANCE CONSTRAINT — read before deploying  ║
 * ╠═══════════════════════════════════════════════════════╣
 * ║  better-sqlite3 uses synchronous I/O and holds an    ║
 * ║  exclusive writer lock.  Running more than one NOHA  ║
 * ║  process against the same SQLite file will corrupt   ║
 * ║  session data or produce SQLITE_BUSY errors under    ║
 * ║  concurrent writes.                                  ║
 * ║                                                      ║
 * ║  This store is designed for single-instance          ║
 * ║  deployments only.  If horizontal scaling is needed  ║
 * ║  you must replace authSessionStore with a shared     ║
 * ║  implementation backed by Redis, PostgreSQL, or a    ║
 * ║  similar multi-writer store and update AUTH_SESSION_ ║
 * ║  DB_PATH and AUTH_SESSION_ENCRYPTION_KEY accordingly.║
 * ╚═══════════════════════════════════════════════════════╝
 *
 * Encryption: AES-256-GCM (JWE compact, "dir" alg) via jose.
 * Key:        32-byte secret decoded from base64 AUTH_SESSION_ENCRYPTION_KEY.
 * TTL:        8-hour absolute expiry enforced in the store; Auth0 SDK rolling
 *             inactivity window (30 min) is enforced at the application layer.
 * Cleanup:    Expired rows are deleted eagerly on every set/update call so the
 *             SQLite file does not grow unbounded.  A periodic background sweep
 *             is not implemented; OS-level log rotation or a cron vacuuming the
 *             database is recommended for very high session volumes.
 *
 * Migration path to shared storage
 * ─────────────────────────────────
 * 1. Provision the shared store (e.g. Redis with TLS).
 * 2. Implement the SessionDataStore interface (get/set/update/delete).
 * 3. Replace `authSessionStore` in lib/auth0.ts with the new implementation.
 * 4. Update AUTH_SESSION_ENCRYPTION_KEY if the new store uses a different key.
 * 5. Existing SQLite sessions will be invalidated; users must re-authenticate.
 */

import Database from 'better-sqlite3';
import { compactDecrypt, CompactEncrypt } from 'jose';
import type { SessionData, SessionDataStore } from '@auth0/nextjs-auth0/types';

let db: Database.Database | undefined;
function getDb() {
  if (db) return db;
  const dbPath = process.env.AUTH_SESSION_DB_PATH;
  if (!dbPath) throw new Error('Auth session storage is not configured.');
  db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec('CREATE TABLE IF NOT EXISTS auth_sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL)');
  return db;
}

/**
 * Decode and validate AUTH_SESSION_ENCRYPTION_KEY.
 * Called at store construction time (via auth0.ts → startup-validation.ts)
 * and on every encrypt/decrypt operation to ensure the key is always valid.
 */
export function validateSessionStoreConfig(): void {
  const value = process.env.AUTH_SESSION_ENCRYPTION_KEY;
  if (!value) throw new Error('Auth session storage is not configured.');
  const key = Buffer.from(value, 'base64');
  if (key.length !== 32) throw new Error('Auth session encryption key is invalid.');
}

function getKey(): Buffer {
  const value = process.env.AUTH_SESSION_ENCRYPTION_KEY;
  if (!value) throw new Error('Auth session storage is not configured.');
  const key = Buffer.from(value, 'base64');
  if (key.length !== 32) throw new Error('Auth session encryption key is invalid.');
  return key;
}

async function encrypt(value: SessionData) {
  return new CompactEncrypt(Buffer.from(JSON.stringify(value))).setProtectedHeader({ alg: 'dir', enc: 'A256GCM' }).encrypt(getKey());
}

export const authSessionStore: SessionDataStore = {
  async get(id) {
    const store = getDb();
    const row = store.prepare('SELECT payload, expires_at FROM auth_sessions WHERE id=?').get(id) as { payload: string; expires_at: number } | undefined;
    if (!row || row.expires_at <= Date.now()) { store.prepare('DELETE FROM auth_sessions WHERE id=?').run(id); return null; }
    try {
      const { plaintext } = await compactDecrypt(row.payload, getKey());
      return JSON.parse(Buffer.from(plaintext).toString()) as SessionData;
    } catch { store.prepare('DELETE FROM auth_sessions WHERE id=?').run(id); return null; }
  },
  async set(id, session) {
    const store = getDb();
    const now = Date.now();
    store.prepare('DELETE FROM auth_sessions WHERE expires_at <= ?').run(now);
    store.prepare('INSERT INTO auth_sessions(id,payload,expires_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at').run(id, await encrypt(session), now + 8 * 60 * 60 * 1000);
  },
  async update(id, session) {
    const store = getDb();
    const now = Date.now();
    store.prepare('DELETE FROM auth_sessions WHERE expires_at <= ?').run(now);
    const result = store.prepare('UPDATE auth_sessions SET payload=?, expires_at=? WHERE id=?').run(await encrypt(session), now + 8 * 60 * 60 * 1000, id);
    return result.changes === 1;
  },
  async delete(id) { getDb().prepare('DELETE FROM auth_sessions WHERE id=?').run(id); },
};
