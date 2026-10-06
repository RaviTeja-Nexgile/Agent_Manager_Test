import * as React from 'react';
import type { CurrentUser } from '@/lib/types';
import { authApi } from '@/lib/endpoints';
import { ApiError, currentUserId, tokenStorage } from '@/lib/api';
import { setGroupings } from '@/lib/permissions';

/**
 * Tear down a session completely.
 *
 * The offline read cache holds crash records carrying PII and CIPSEA-protected
 * data. Field devices are shared, so that cache must not outlive the session —
 * and a session can end by sign-out OR by the token being rejected, not just by
 * someone pressing the button. Every path that clears the token goes through
 * here so the cache can never be left behind.
 *
 * The outbox is deliberately preserved: it holds work captured at a crash scene
 * that has not reached the server. It is tagged with its author, so it can only
 * ever be replayed by the user who created it.
 */
async function endSession(): Promise<void> {
  tokenStorage.clear();
  try {
    const { clearCache } = await import('@/lib/offline/db');
    await clearCache();
  } catch {
    /* IndexedDB unavailable — nothing cached to clear */
  }
}

/** Persist the identity so an offline cold start can restore it. */
async function cacheUser(me: CurrentUser): Promise<void> {
  try {
    const { putCache } = await import('@/lib/offline/db');
    await putCache(`auth:me:${currentUserId() ?? 'anon'}`, me);
  } catch {
    /* best-effort */
  }
}

/** Last-known-good identity, used to stay signed in during an offline start. */
async function getCachedUser(): Promise<CurrentUser | null> {
  try {
    const { getCache } = await import('@/lib/offline/db');
    const uid = currentUserId();
    return (await getCache<CurrentUser>(`auth:me:${uid ?? 'anon'}`)) ?? null;
  } catch {
    return null;
  }
}

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  error: string | null;
  /** Dev login by email + password. */
  login: (email: string, password: string) => Promise<void>;
  /** Async: the offline PII cache is cleared before navigating away. */
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthCtx = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<CurrentUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // AUTH-8: load the role/access groupings + PII permission codes once, from the
  // backend source of truth, and feed them to the permissions helpers. Best-effort:
  // a failure leaves the safe fallback in place so the app still renders.
  const loadGroupings = React.useCallback(async () => {
    try {
      setGroupings(await authApi.groupings());
    } catch {
      /* keep the bundled fallback groupings */
    }
  }, []);

  const refresh = React.useCallback(async () => {
    if (!tokenStorage.getAccess()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const [me] = await Promise.all([authApi.me(), loadGroupings()]);
      setUser(me);
      void cacheUser(me);
    } catch (e) {
      // Only a genuine auth failure ends the session. Anything else — no signal
      // (ApiError status 0), a proxy error, a 5xx — is a reachability problem,
      // and treating it as a rejected token signed the inspector out on every
      // offline cold start. That defeats the point of an offline-first app:
      // they open it at a crash scene with no bars and cannot get past login.
      const status = e instanceof ApiError ? e.status : 0;
      const authRejected = status === 401 || status === 403;
      if (!authRejected) {
        // Keep the session and restore the identity from the cached /auth/me so
        // the app is usable for data collection until the link returns.
        const cached = await getCachedUser();
        if (cached) setUser(cached);
        return;
      }
      await endSession();
    } finally {
      setLoading(false);
    }
  }, [loadGroupings]);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const login = React.useCallback(async (email: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const resp = await authApi.login(email, password);
      // A different user may have signed in on this device. Drop the previous
      // session's cached crash data before loading this one's.
      const { clearCache } = await import('@/lib/offline/db');
      await clearCache().catch(() => {});
      tokenStorage.set(resp.access_token);
      // Load the full permission/scope context plus the served groupings (AUTH-8).
      const [me] = await Promise.all([authApi.me(), loadGroupings()]);
      setUser(me);
      void cacheUser(me);
    } catch (e) {
      const msg = (e as Error).message || 'Login failed';
      setError(msg);
      await endSession();
      setUser(null);
      throw e;
    } finally {
      setLoading(false);
    }
  }, [loadGroupings]);

  const logout = React.useCallback(async () => {
    authApi.logout().catch(() => {
      /* best-effort; clear local state regardless */
    });
    setUser(null);
    // Awaited before navigating: assigning window.location tears the page down
    // immediately, which would cancel an in-flight clear and leave the previous
    // user's PII on the device.
    await endSession();
    window.location.href = '/login';
  }, []);

  const value = React.useMemo(
    () => ({ user, loading, error, login, logout, refresh }),
    [user, loading, error, login, logout, refresh],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthCtx);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
