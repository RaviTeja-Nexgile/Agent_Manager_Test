/**
 * Typed fetch wrapper around the CCFP FastAPI backend.
 *
 * The dev mock-IdP issues a single bearer access token (no refresh token).
 * The token lives in localStorage; on 401 the auth provider clears it and
 * redirects to /login.
 */

export const ACCESS_TOKEN_KEY = 'ccfp.access_token';

export const API_BASE = (import.meta.env.VITE_API_BASE as string) || '/api/v1';

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function getAccessToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

export interface ApiFetchInit extends Omit<RequestInit, 'body'> {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  /**
   * Offline behaviour for this call. Opt-in per endpoint: only data-collection
   * calls set it, so analytics, reporting and admin stay online-only exactly as
   * before (that is the scope the SOO describes).
   *
   *  cache - GET only. Store the response and serve it when offline.
   *  queue - mutations only. Enqueue in the outbox when offline and replay on
   *          reconnect. `label` names the record in the sync panel.
   */
  offline?: {
    cache?: boolean;
    queue?: boolean;
    label?: string;
    crashId?: string;
    /** Optimistic value returned to the caller while the write is queued. */
    optimistic?: unknown;
  };
}

export class OfflineQueuedError extends Error {
  constructor(public readonly label: string) {
    super(`Saved on this device — will sync when back online: ${label}`);
  }
}

function buildQuery(query?: ApiFetchInit['query']): string {
  if (!query) return '';
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue;
    params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

function isOffline(): boolean {
  return typeof navigator !== 'undefined' && navigator.onLine === false;
}

/**
 * The signed-in user's id, read from the access token's `sub` claim.
 *
 * Used to stamp queued writes so they are only ever replayed by the user who
 * captured them. Decoding is unverified and purely for local bookkeeping — the
 * server still validates the token on every request.
 */
export function currentUserId(): string | null {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return (JSON.parse(json) as { sub?: string }).sub ?? null;
  } catch {
    return null;
  }
}

/**
 * Namespace a cached response by the signed-in user.
 *
 * Cached crash reads contain PII. Keying on the path alone means one user's
 * cached record could be served to whoever signs in next on a shared device;
 * with the user id in the key a cross-user hit is impossible by construction,
 * independently of whether the clear-on-sign-out ran.
 */
function cacheKey(path: string): string {
  return `${currentUserId() ?? 'anon'}::${path}`;
}

export async function api<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const url = `${API_BASE}${path}${buildQuery(init.query)}`;
  const method = (init.method ?? 'GET').toUpperCase();
  const offline = init.offline;
  const pathWithQuery = `${path}${buildQuery(init.query)}`;

  const queueable = Boolean(offline?.queue) && method !== 'GET';

  /**
   * Park a mutation in the outbox instead of losing the user's work.
   *
   * The entry id is the body's `client_uuid` when present, so a replay carries
   * the same idempotency key the first attempt used and the server returns the
   * original row rather than creating a second one.
   */
  const queueWrite = async (): Promise<T> => {
    const { enqueue } = await import('./offline/db');
    const id =
      (init.body && typeof init.body === 'object' && 'client_uuid' in init.body
        ? String((init.body as Record<string, unknown>).client_uuid)
        : null) ?? crypto.randomUUID();
    await enqueue({
      id,
      method: method as 'POST' | 'PUT' | 'PATCH' | 'DELETE',
      path: pathWithQuery,
      body: init.body,
      userId: currentUserId() ?? undefined,
      crashId: offline!.crashId,
      label: offline!.label ?? path,
    });
    if (offline!.optimistic !== undefined) return offline!.optimistic as T;
    throw new OfflineQueuedError(offline!.label ?? path);
  };

  // Known-offline: queue without attempting the request at all.
  if (queueable && isOffline()) return queueWrite();

  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let body: BodyInit | undefined;
  if (init.body !== undefined && init.body !== null) {
    if (init.body instanceof FormData) {
      body = init.body;
    } else {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(init.body);
    }
  }

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers, body });
  } catch (e) {
    // The request never reached the server. This is the ordinary roadside case:
    // a weak or intermittent link, where navigator.onLine still reports true but
    // fetch fails. Queueing only on navigator.onLine === false would silently
    // discard exactly the writes most likely to be lost.
    if (queueable) return queueWrite();
    // Offline read: fall back to the last-known-good copy so a screen the
    // inspector already opened still renders at the roadside.
    if (offline?.cache && method === 'GET') {
      const { getCache } = await import('./offline/db');
      const cached = await getCache<T>(cacheKey(pathWithQuery));
      if (cached !== undefined) return (await mergePendingCreates(pathWithQuery, cached)) as T;
    }
    throw new ApiError(`Network error: ${(e as Error).message}`, 0, null);
  }

  // The API never serviced this request. A 5xx is not a rejection on the merits:
  // the backend was down, or something in front of it — a gateway, a captive
  // portal, the dev proxy — answered instead. `fetch` resolves in that case, so
  // the network-error branch above never runs and `navigator.onLine` still
  // reports true; without this the write is discarded with "Internal Server
  // Error" and the inspector's roadside work is simply lost.
  //
  // Replay is safe: every queued create carries a `client_uuid` and the server
  // returns the row the first attempt made rather than inserting a second one.
  if (res.status >= 500) {
    if (queueable) return queueWrite();
    // Same reasoning for reads — serve the last-known-good copy so a screen the
    // inspector already opened keeps rendering. Only endpoints that opted into
    // caching reach this, and only when a cached copy actually exists.
    if (offline?.cache && method === 'GET') {
      const { getCache } = await import('./offline/db');
      const cached = await getCache<T>(cacheKey(pathWithQuery));
      if (cached !== undefined) return (await mergePendingCreates(pathWithQuery, cached)) as T;
    }
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get('content-type') || '';
  let data: unknown = null;
  if (/\bapplication\/(?:[\w.+-]*\+)?json\b/i.test(contentType)) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  } else {
    data = await res.text();
  }

  if (!res.ok) {
    const detail =
      (data && typeof data === 'object' && 'detail' in data && (data as Record<string, unknown>).detail) ||
      res.statusText;
    // FastAPI validation errors return detail as an array of objects.
    const message = Array.isArray(detail)
      ? detail.map((d) => (d as { msg?: string }).msg ?? JSON.stringify(d)).join('; ')
      : typeof detail === 'string'
        ? detail
        : res.statusText;
    throw new ApiError(message, res.status, data);
  }
  // Keep the last-known-good copy of cache-enabled reads for offline use.
  if (offline?.cache && method === 'GET') {
    const { putCache } = await import('./offline/db');
    void putCache(cacheKey(pathWithQuery), data).catch(() => {
      /* IndexedDB unavailable (private mode) — caching is best-effort */
    });
    return (await mergePendingCreates(pathWithQuery, data)) as T;
  }
  return data as T;
}

/**
 * Fold records still sitting in the outbox into a freshly-read list.
 *
 * A person added offline exists only on the device until it syncs. Returning
 * the server's list alone would make it vanish from the table the moment the
 * screen reloads, which reads as "my entry was lost" — the single worst
 * outcome for someone documenting a fatal crash at the roadside.
 *
 * Only additive: server rows are never altered, and a queued row is dropped as
 * soon as the outbox entry clears on sync.
 */
async function mergePendingCreates(path: string, data: unknown): Promise<unknown> {
  if (!Array.isArray(data)) return data;
  try {
    const { pendingCreatesFor } = await import('./offline/db');
    // Author-scoped: these rows carry unredacted PII and are rendered directly,
    // so merging another user's queued records would leak them on a shared device.
    const queued = await pendingCreatesFor(path, currentUserId());
    if (!queued.length) return data;
    const serverKeys = new Set(
      data
        .map((row) => (row && typeof row === 'object' ? (row as Record<string, unknown>).client_uuid : null))
        .filter(Boolean) as string[],
    );
    const additions = queued
      // Skip anything the server already has — it synced between the read and now.
      .filter((entry) => !serverKeys.has(entry.id))
      .map((entry) => {
        const b = (entry.body ?? {}) as Record<string, unknown>;
        // Mirror the server's derivation of full_name from the name parts so a
        // queued row shows a name rather than a dash.
        const parts = [b.name_first, b.name_middle, b.name_last].filter(Boolean);
        return {
          ...b,
          full_name: b.full_name ?? (parts.length ? parts.join(' ') : undefined),
          id: entry.id,
          _pendingSync: true,
        };
      });
    return [...data, ...additions];
  } catch {
    return data;
  }
}

export const tokenStorage = {
  set(access: string) {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
  },
  clear() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  },
  getAccess() {
    return getAccessToken();
  },
};
