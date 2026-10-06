/**
 * Outbox replay.
 *
 * Queued writes are sent in the order they were made, one at a time. Order
 * matters: an incident vehicle must exist before a person that references its
 * vehicle number, and the inspector's own sequence is the only ordering we can
 * trust offline.
 *
 * Replay safety rests on the server: create endpoints accept a client-supplied
 * `client_uuid` and return the row created by the first attempt instead of
 * inserting a second one. That is what makes a retry safe after a response is
 * lost — which is the common failure on a flaky roadside connection, and which
 * would otherwise duplicate a person and corrupt the fatality count that drives
 * qualifying-crash classification.
 */
import { API_BASE, ApiError, currentUserId, tokenStorage } from '@/lib/api';
import { listOutbox, removeEntry, updateEntry, type OutboxEntry } from './db';

export interface SyncResult {
  synced: number;
  failed: number;
  remaining: number;
}

let syncing = false;

/** True while a replay pass is in flight; prevents overlapping runs. */
export function isSyncing(): boolean {
  return syncing;
}

/** A response meaning the write landed and the entry can be discarded. */
function isSettled(status: number): boolean {
  return status >= 200 && status < 300;
}

/**
 * A response that will never succeed on replay.
 *
 * 409 is deliberately included. It once counted as "settled" on the reasoning
 * that a replayed vehicle create would collide with its own earlier attempt —
 * but every queued create now carries a `client_uuid`, and the server checks
 * that key *before* the natural-key guard, so a genuine replay comes back 2xx.
 * A 409 therefore means a real conflict: a different record already holds that
 * vehicle number, or the form was routed and locked while the device was
 * offline. Discarding the entry in that case would silently destroy data
 * captured at a crash scene, so it is retained as FAILED with the server's
 * message for someone to resolve.
 *
 * 401 is excluded: the token may simply have expired mid-shift, and the write
 * must survive until the inspector signs back in.
 */
function isTerminalFailure(status: number): boolean {
  return status >= 400 && status < 500 && status !== 401;
}

/**
 * Attempts allowed against a server-side (5xx) failure before the entry is
 * surfaced as failed.
 *
 * A 5xx is worth retrying — it is usually transient — but retrying forever
 * would leave the record showing "unsynced" indefinitely, which reads as "it
 * will go through eventually" when it never will. After this many attempts the
 * entry moves to FAILED, where the sync panel offers Try again or Discard and
 * the server's message is visible.
 *
 * Network errors (status 0) and 401 are deliberately exempt and retry forever:
 * a device with no signal, or a shift that outlasted its token, must keep its
 * work queued until conditions actually change.
 */
const MAX_SERVER_ERROR_ATTEMPTS = 5;

async function send(entry: OutboxEntry): Promise<{ ok: boolean; status: number; message?: string }> {
  const token = tokenStorage.getAccess();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${entry.path}`, {
      method: entry.method,
      headers,
      body: entry.body === undefined ? undefined : JSON.stringify(entry.body),
    });
  } catch (e) {
    // Still offline / network dropped mid-flight — keep it queued.
    return { ok: false, status: 0, message: (e as Error).message };
  }

  if (isSettled(res.status)) return { ok: true, status: res.status };

  let message = res.statusText;
  try {
    const data = await res.json();
    if (data && typeof data === 'object' && 'detail' in data) {
      const d = (data as Record<string, unknown>).detail;
      message = Array.isArray(d)
        ? d.map((x) => (x as { msg?: string }).msg ?? JSON.stringify(x)).join('; ')
        : String(d);
    }
  } catch {
    /* keep statusText */
  }
  return { ok: false, status: res.status, message };
}

/** Replay every queued write. Safe to call repeatedly. */
export async function syncOutbox(): Promise<SyncResult> {
  if (syncing) return { synced: 0, failed: 0, remaining: (await listOutbox()).length };
  syncing = true;
  let synced = 0;
  let failed = 0;
  try {
    const me = currentUserId();
    const entries = await listOutbox();
    for (const entry of entries) {
      if (entry.status === 'FAILED') {
        failed += 1;
        continue;
      }
      // Hold, do not replay, work captured by a different user on this device.
      // Replaying it under the current token would misattribute the record in
      // the audit log and could write to a crash this user cannot access.
      // It is kept so the original user can sync it when they sign back in.
      if (entry.userId && me && entry.userId !== me) continue;
      await updateEntry(entry.id, { status: 'SYNCING' });
      const result = await send(entry);
      if (result.ok) {
        await removeEntry(entry.id);
        synced += 1;
      } else if (isTerminalFailure(result.status)) {
        await updateEntry(entry.id, {
          status: 'FAILED',
          attempts: entry.attempts + 1,
          lastError: result.message,
        });
        failed += 1;
      } else {
        // Network error, 5xx, or 401 — retryable. Return it to PENDING and stop
        // this pass; continuing would just fail the rest against the same
        // condition and burn the attempt counters.
        const attempts = entry.attempts + 1;
        const exhausted = result.status >= 500 && attempts >= MAX_SERVER_ERROR_ATTEMPTS;
        await updateEntry(entry.id, {
          status: exhausted ? 'FAILED' : 'PENDING',
          attempts,
          lastError: result.message,
        });
        if (exhausted) failed += 1;
        break;
      }
    }
  } finally {
    syncing = false;
  }
  const remaining = (await listOutbox()).length;
  return { synced, failed, remaining };
}

export { ApiError };
