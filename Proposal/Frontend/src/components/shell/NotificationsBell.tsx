import * as React from 'react';
import { Bell, CheckCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

import { notificationApi } from '@/lib/endpoints';
import { useApi } from '@/lib/useApi';
import { cn } from '@/lib/utils';
import { formatDateTime, humanize } from '@/lib/format';
import type { Notification } from '@/lib/types';

const POLL_INTERVAL_MS = 60_000;

export function NotificationsBell() {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const { data, reload } = useApi(() => notificationApi.list(), []);

  React.useEffect(() => {
    const id = window.setInterval(() => void reload(), POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [reload]);

  React.useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  const list = data ?? [];
  const unread = list.filter((n) => !n.read_at);
  const unreadCount = unread.length;

  async function handleMarkAll() {
    await notificationApi.markAllRead();
    void reload();
  }
  async function handleMarkRead(id: string) {
    await notificationApi.markRead(id);
    void reload();
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications${unreadCount ? ` (${unreadCount} unread)` : ''}`}
        className="relative inline-flex h-8 w-8 items-center justify-center rounded-md text-white transition-colors hover:bg-dot-navy-700"
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 ? (
          <span
            aria-hidden
            className="absolute -right-1 -top-1 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-alert-amber px-1 text-[10px] font-bold text-white shadow-sm"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Notifications"
          className="absolute right-0 top-10 z-50 max-h-[28rem] w-96 overflow-hidden rounded-md border border-border bg-card text-foreground shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-border bg-muted/30 px-3 py-2">
            <span className="text-eyebrow font-semibold">
              Notifications{' '}
              {unreadCount > 0 ? <span className="text-alert-amber">({unreadCount} unread)</span> : null}
            </span>
            <button
              type="button"
              onClick={() => void handleMarkAll()}
              disabled={unreadCount === 0}
              className="inline-flex items-center gap-1 text-xs text-federal-blue hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline"
            >
              <CheckCheck className="h-3 w-3" /> Mark all read
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {list.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted-foreground">No notifications yet.</div>
            ) : (
              <ul className="divide-y divide-border">
                {list.map((n: Notification) => (
                  <li
                    key={n.id}
                    className={cn('group p-3 transition-colors hover:bg-muted/40', !n.read_at && 'bg-federal-blue/5')}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium leading-snug">{n.title}</div>
                        {n.message ? (
                          <div className="mt-0.5 text-xs text-muted-foreground">{n.message}</div>
                        ) : null}
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {humanize(n.notification_type)} · {formatDateTime(n.created_at)}
                          {n.crash_id ? (
                            <Link
                              onClick={() => setOpen(false)}
                              to={`/crashes/${n.crash_id}`}
                              className="ml-2 text-federal-blue hover:underline"
                            >
                              Open crash
                            </Link>
                          ) : null}
                        </div>
                      </div>
                      {!n.read_at ? (
                        <button
                          type="button"
                          onClick={() => void handleMarkRead(n.id)}
                          className="text-xs text-federal-blue opacity-0 transition-opacity hover:underline group-hover:opacity-100"
                        >
                          Mark read
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="border-t border-border bg-muted/30 px-3 py-2 text-right">
            <Link onClick={() => setOpen(false)} to="/notifications" className="text-xs text-federal-blue hover:underline">
              View all notifications →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
