import * as React from 'react';
import { RefreshCw, Trash2, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useOffline } from '@/lib/offline/useOffline';

/**
 * Queued and failed offline work.
 *
 * A write that fails terminally — a validation error, or a conflict such as the
 * form being routed and locked while the device was offline — still contains
 * data the inspector recorded at a crash scene. It must never disappear
 * silently. This panel makes every entry visible with its error, and offers the
 * only two honest choices: try again, or deliberately discard it.
 */
export function SyncPanel({ onClose }: { onClose: () => void }) {
  const { entries, online, syncing, syncNow, retryEntry, discardEntry } = useOffline();

  if (!entries.length) return null;

  return (
    <div className="absolute right-0 top-full z-50 mt-2 w-[26rem] max-w-[calc(100vw-2rem)] rounded-md border border-border bg-background p-3 text-foreground shadow-lg">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold">Unsynced work</div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={!online || syncing} onClick={() => void syncNow()}>
            <RefreshCw className={syncing ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} /> Sync now
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </div>
      </div>

      <ul className="max-h-80 space-y-2 overflow-y-auto">
        {entries.map((e) => (
          <li key={e.id} className="rounded-md border border-border p-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{e.label}</div>
                <div className="text-xs text-muted-foreground">
                  {e.method} · {new Date(e.createdAt).toLocaleString()}
                  {e.attempts > 0 ? ` · ${e.attempts} attempt${e.attempts === 1 ? '' : 's'}` : ''}
                </div>
              </div>
              {e.status === 'FAILED' ? (
                <Badge variant="destructive" size="sm">Failed</Badge>
              ) : (
                <Badge variant="warning" size="sm">Pending</Badge>
              )}
            </div>

            {e.status === 'FAILED' ? (
              <>
                <div className="mt-1.5 flex items-start gap-1.5 text-xs text-alert-red">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span className="break-words">{e.lastError ?? 'The server rejected this change.'}</span>
                </div>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => void retryEntry(e.id)}>Try again</Button>
                  <Button size="sm" variant="ghost" onClick={() => void discardEntry(e.id)}>
                    <Trash2 className="h-3.5 w-3.5 text-alert-red" /> Discard
                  </Button>
                </div>
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
