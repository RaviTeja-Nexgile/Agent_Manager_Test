/**
 * Connectivity + outbox state for the UI.
 *
 * An inspector working a crash scene has to be able to see, at a glance,
 * whether what they typed has actually reached the server. "Looks saved" when
 * nothing has synced is the failure mode this exists to prevent, so pending
 * count and sync state are surfaced globally rather than per screen.
 */
import * as React from 'react';

import { currentUserId } from '@/lib/api';
import {
  countPending,
  listOutboxFor,
  OUTBOX_CHANGED_EVENT,
  removeEntry,
  updateEntry,
  type OutboxEntry,
} from './db';
import { syncOutbox } from './sync';

interface OfflineContextValue {
  online: boolean;
  pending: number;
  failed: number;
  syncing: boolean;
  entries: OutboxEntry[];
  refresh: () => Promise<void>;
  syncNow: () => Promise<void>;
  /** Return a failed entry to the queue for another attempt. */
  retryEntry: (id: string) => Promise<void>;
  /** Permanently drop a failed entry the operator has decided to abandon. */
  discardEntry: (id: string) => Promise<void>;
}

const OfflineContext = React.createContext<OfflineContextValue>({
  online: true,
  pending: 0,
  failed: 0,
  syncing: false,
  entries: [],
  refresh: async () => {},
  syncNow: async () => {},
  retryEntry: async () => {},
  discardEntry: async () => {},
});

export function OfflineProvider({ children }: { children: React.ReactNode }) {
  const [online, setOnline] = React.useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );
  const [entries, setEntries] = React.useState<OutboxEntry[]>([]);
  const [pending, setPending] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      // Author-scoped: another user's stranded entries are never sent by sync,
      // so counting them would show a number that never reaches zero.
      const me = currentUserId();
      const [rows, n] = await Promise.all([listOutboxFor(me), countPending(me)]);
      setEntries(rows);
      setPending(n);
    } catch {
      /* IndexedDB unavailable (private mode) — degrade to online-only */
    }
  }, []);

  const syncNow = React.useCallback(async () => {
    setSyncing(true);
    try {
      await syncOutbox();
    } finally {
      setSyncing(false);
      await refresh();
    }
  }, [refresh]);

  // Replay as soon as the connection returns, and re-check on focus: a device
  // that was asleep in a vehicle often reports `online` before it truly has a
  // usable route, so a focus-triggered retry matters in practice.
  React.useEffect(() => {
    function goOnline() {
      setOnline(true);
      void syncNow();
    }
    function goOffline() {
      setOnline(false);
    }
    function onFocus() {
      if (navigator.onLine) void syncNow();
    }
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
      // Named so it can actually be removed — an inline handler leaked a
      // listener on every re-render of the provider.
      window.removeEventListener('focus', onFocus);
    };
  }, [syncNow]);

  // The outbox is written from the API layer, outside React. Without this the
  // indicator would keep showing a stale count — and reporting "0 waiting"
  // while work is queued is precisely the false reassurance to avoid.
  React.useEffect(() => {
    const onChanged = () => void refresh();
    window.addEventListener(OUTBOX_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(OUTBOX_CHANGED_EVENT, onChanged);
  }, [refresh]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  // Drain anything left over from a previous session on first load.
  React.useEffect(() => {
    if (navigator.onLine) void syncNow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const failed = entries.filter((e) => e.status === 'FAILED').length;

  // A write that failed terminally (a validation error, or a conflict such as a
  // routed form) still holds data captured at a crash scene. It must stay
  // visible and recoverable rather than sitting invisibly in the queue.
  const retryEntry = React.useCallback(async (id: string) => {
    await updateEntry(id, { status: 'PENDING', lastError: undefined });
    await syncNow();
  }, [syncNow]);

  const discardEntry = React.useCallback(async (id: string) => {
    await removeEntry(id);
    await refresh();
  }, [refresh]);

  const value = React.useMemo(
    () => ({ online, pending, failed, syncing, entries, refresh, syncNow, retryEntry, discardEntry }),
    [online, pending, failed, syncing, entries, refresh, syncNow, retryEntry, discardEntry],
  );

  return <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>;
}

export function useOffline(): OfflineContextValue {
  return React.useContext(OfflineContext);
}
