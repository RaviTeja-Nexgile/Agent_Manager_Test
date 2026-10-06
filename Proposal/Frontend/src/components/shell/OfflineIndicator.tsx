import * as React from 'react';
import { CloudOff, RefreshCw, TriangleAlert } from 'lucide-react';

import { useOffline } from '@/lib/offline/useOffline';
import { cn } from '@/lib/utils';
import { SyncPanel } from './SyncPanel';

/**
 * Connectivity and unsynced-work indicator.
 *
 * An inspector at a crash scene must be able to tell whether what they entered
 * has actually reached the server. Silence would read as "saved", so this stays
 * visible whenever there is queued work — not only while offline.
 */
export function OfflineIndicator({ className }: { className?: string }) {
  const { online, pending, failed, syncing } = useOffline();
  const [panelOpen, setPanelOpen] = React.useState(false);

  // Nothing to say when connected with an empty outbox.
  if (online && pending === 0 && failed === 0) return null;

  const label = !online
    ? pending > 0
      ? `Offline · ${pending} unsynced`
      : 'Offline'
    : failed > 0
      ? `${failed} failed to sync`
      : `${pending} unsynced`;

  const tone = !online
    ? 'bg-alert-amber text-white'
    : failed > 0
      ? 'bg-destructive text-white'
      : 'bg-federal-blue text-white';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setPanelOpen((v) => !v)}
        aria-live="polite"
        aria-expanded={panelOpen}
        aria-label={
          !online
            ? `Working offline. ${pending} change${pending === 1 ? '' : 's'} waiting to sync. Select to review.`
            : `${label}. Select to review unsynced work.`
        }
        title="Review unsynced work"
        className={cn(
          'inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-bold uppercase tracking-wide shadow-sm',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white',
          tone,
          className,
        )}
      >
        {!online ? (
          <CloudOff className="h-3.5 w-3.5" aria-hidden />
        ) : failed > 0 ? (
          <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
        ) : (
          <RefreshCw className={cn('h-3.5 w-3.5', syncing && 'animate-spin')} aria-hidden />
        )}
        <span>{syncing ? 'Syncing…' : label}</span>
      </button>
      {panelOpen ? <SyncPanel onClose={() => setPanelOpen(false)} /> : null}
    </div>
  );
}
