/**
 * Local durable store for offline data collection.
 *
 * The SOO requires the application to "function and collect data normally when
 * not connected to the Internet". The MCSAP CMV Inspector completes the Initial
 * Incident Form at the crash scene within 24-48 hours of a fatal truck crash,
 * frequently with no signal, so writes must survive both a lost connection and
 * a browser restart. localStorage is unsuitable (synchronous, ~5 MB, string
 * only); IndexedDB is the durable option available to a web app.
 *
 * Two object stores:
 *   outbox    - queued mutations awaiting the server, in submission order.
 *   cache     - last-known-good GET responses, so previously-visited screens
 *               still render offline.
 *
 * Scope is deliberately data collection only, per the SOO's own framing.
 * Analytics, reporting and admin remain online-only.
 */
import { openDB, type IDBPDatabase } from 'idb';

export const DB_NAME = 'ccfp-offline';
export const DB_VERSION = 1;
export const OUTBOX_STORE = 'outbox';
export const CACHE_STORE = 'cache';

/** A mutation captured while offline, replayed against the API on reconnect. */
export interface OutboxEntry {
  /** Client-generated id; also sent as the server-side idempotency key. */
  id: string;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  body?: unknown;
  /**
   * The user who captured this write.
   *
   * Devices get shared. If inspector A leaves unsynced work and inspector B
   * signs in on the same tablet, B's token must not be used to replay A's
   * entries — that would misattribute the work in the audit log and could write
   * to a crash B has no access to. Entries belonging to another user are held,
   * not replayed and not discarded.
   */
  userId?: string;
  /** Crash this write belongs to, so the UI can show per-record sync state. */
  crashId?: string;
  /** Human-readable label for the sync panel, e.g. "Person: J. Smith". */
  label: string;
  createdAt: number;
  status: 'PENDING' | 'SYNCING' | 'FAILED';
  attempts: number;
  lastError?: string;
}

export interface CacheEntry {
  path: string;
  body: unknown;
  cachedAt: number;
}

let dbPromise: Promise<IDBPDatabase> | null = null;

export function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(OUTBOX_STORE)) {
          const store = db.createObjectStore(OUTBOX_STORE, { keyPath: 'id' });
          store.createIndex('createdAt', 'createdAt');
          store.createIndex('crashId', 'crashId');
        }
        if (!db.objectStoreNames.contains(CACHE_STORE)) {
          db.createObjectStore(CACHE_STORE, { keyPath: 'path' });
        }
      },
    });
  }
  return dbPromise;
}

// ─────────────────────────────── outbox ───────────────────────────────

/**
 * Fired whenever the outbox changes so the UI can re-read it.
 *
 * The queue is written from the API layer, which has no React context. Without
 * this the indicator keeps reporting the count it last saw — and an indicator
 * that says "0 waiting" while work is queued is worse than no indicator at all.
 */
export const OUTBOX_CHANGED_EVENT = 'ccfp:outbox-changed';

function notifyChanged(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(OUTBOX_CHANGED_EVENT));
  }
}

export async function enqueue(entry: Omit<OutboxEntry, 'createdAt' | 'status' | 'attempts'>): Promise<OutboxEntry> {
  const db = await getDb();
  const row: OutboxEntry = { ...entry, createdAt: Date.now(), status: 'PENDING', attempts: 0 };
  await db.put(OUTBOX_STORE, row);
  notifyChanged();
  return row;
}

/**
 * Pending creates for a given collection path, newest last.
 *
 * Used to show the inspector the records they entered offline — without it the
 * list reloads from the server, the queued person is absent, and the entry looks
 * lost.
 *
 * `userId` is required, not optional: these rows are merged straight into a
 * rendered list and carry unredacted names, addresses and phone numbers. On a
 * shared device, returning another user's queued records would put one
 * inspector's PII on another's screen, bypassing the server-side redaction
 * entirely. Entries with no recorded author predate user tagging and are treated
 * as belonging to nobody.
 */
export async function pendingCreatesFor(path: string, userId: string | null): Promise<OutboxEntry[]> {
  const all = await listOutbox();
  return all.filter(
    (e) =>
      e.method === 'POST' &&
      e.path === path &&
      e.status !== 'FAILED' &&
      Boolean(userId) &&
      e.userId === userId,
  );
}

/** Queued writes in submission order — order matters (a vehicle before the
 *  person that references it). */
export async function listOutbox(): Promise<OutboxEntry[]> {
  const db = await getDb();
  const all = (await db.getAll(OUTBOX_STORE)) as OutboxEntry[];
  return all.sort((a, b) => a.createdAt - b.createdAt);
}

/** Count of queued work the given user can actually replay.
 *
 *  Scoped by author for the same reason sync is: counting another user's stranded
 *  entries would show a number that never goes down, because sync will never
 *  send them. */
export async function countPending(userId: string | null): Promise<number> {
  const all = await listOutbox();
  return all.filter((e) => e.status !== 'FAILED' && (!e.userId || e.userId === userId)).length;
}

/** Entries belonging to the given user, for the sync panel. */
export async function listOutboxFor(userId: string | null): Promise<OutboxEntry[]> {
  const all = await listOutbox();
  return all.filter((e) => !e.userId || e.userId === userId);
}

export async function updateEntry(id: string, patch: Partial<OutboxEntry>): Promise<void> {
  const db = await getDb();
  const existing = (await db.get(OUTBOX_STORE, id)) as OutboxEntry | undefined;
  if (!existing) return;
  await db.put(OUTBOX_STORE, { ...existing, ...patch });
  notifyChanged();
}

export async function removeEntry(id: string): Promise<void> {
  const db = await getDb();
  await db.delete(OUTBOX_STORE, id);
  notifyChanged();
}

export async function clearOutbox(): Promise<void> {
  const db = await getDb();
  await db.clear(OUTBOX_STORE);
  notifyChanged();
}

// ─────────────────────────────── read cache ───────────────────────────────

export async function putCache(path: string, body: unknown): Promise<void> {
  const db = await getDb();
  await db.put(CACHE_STORE, { path, body, cachedAt: Date.now() } satisfies CacheEntry);
}

/**
 * Drop every cached read. Called on sign-out.
 *
 * The cache holds crash records, which carry PII and CIPSEA-protected data.
 * Leaving it on a shared tablet after sign-out would expose one user's data to
 * the next. The OUTBOX is deliberately NOT cleared here — it holds work the
 * inspector has not yet been able to send, and discarding it would destroy data
 * captured at a crash scene. Unsynced entries are instead held and replayed only
 * for the user who created them.
 */
export async function clearCache(): Promise<void> {
  const db = await getDb();
  await db.clear(CACHE_STORE);
}

export async function getCache<T>(path: string): Promise<T | undefined> {
  const db = await getDb();
  const row = (await db.get(CACHE_STORE, path)) as CacheEntry | undefined;
  return row?.body as T | undefined;
}
