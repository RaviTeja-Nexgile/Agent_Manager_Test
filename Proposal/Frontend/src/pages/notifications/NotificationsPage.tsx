import * as React from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCheck,
  CheckCircle2,
  FileBarChart2,
  Inbox,
  PlugZap,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { useApi } from '@/lib/useApi';
import { notificationApi } from '@/lib/endpoints';
import { cn } from '@/lib/utils';
import { formatDateTime, humanize, relativeTime } from '@/lib/format';
import type { Notification } from '@/lib/types';

/** Map a notification type to an icon + tone so the inbox is scannable.
 * Tones mirror the app's icon-chip house style (soft /10 tint + brand text). */
function notifMeta(type: string): { icon: LucideIcon; tone: string } {
  const t = type.toUpperCase();
  // UNDETERMINED joins the attention bucket: a submitted crash that could not be
  // classified was routed to nobody and needs a human to complete it. Matched on
  // UNDETERMINED rather than SCOPE so IN_/OUT_OF_SCOPE_ROUTING stay informational.
  if (/(QC|FAIL|MISSING|ERROR|DEFICIEN|UNDETERMINED)/.test(t)) return { icon: AlertTriangle, tone: 'bg-alert-red/10 text-alert-red-600' };
  if (/(SYSTEM|SECURITY|MALWARE)/.test(t)) return { icon: ShieldAlert, tone: 'bg-alert-amber/10 text-alert-amber-600' };
  if (/(INTEGRATION|SAFESPECT|CDLIS|MCMIS|ELD|ERODS)/.test(t)) return { icon: PlugZap, tone: 'bg-federal-blue/10 text-federal-blue' };
  if (/(REPORT|PUBLISH)/.test(t)) return { icon: FileBarChart2, tone: 'bg-success-green/10 text-success-green-600' };
  if (/(COMPLETE|ACCEPTED|CLEARED)/.test(t)) return { icon: CheckCircle2, tone: 'bg-success-green/10 text-success-green-600' };
  if (/(ROUTING|IIF|INCIDENT|NEW)/.test(t)) return { icon: Inbox, tone: 'bg-federal-blue/10 text-federal-blue' };
  return { icon: Bell, tone: 'bg-neutral-base/10 text-neutral-base-600' };
}

type Filter = 'all' | 'unread';

export function NotificationsPage() {
  const { data, loading } = useApi(() => notificationApi.list(), []);
  // Track read state locally so marking-read updates in place without a full refetch.
  const [readIds, setReadIds] = React.useState<Set<string>>(new Set());
  const [filter, setFilter] = React.useState<Filter>('all');

  const items = data ?? [];
  const isRead = (n: { id: string; read_at: string | null }) => Boolean(n.read_at) || readIds.has(n.id);
  const unread = items.filter((n) => !isRead(n)).length;
  const visible = filter === 'unread' ? items.filter((n) => !isRead(n)) : items;

  const markOne = async (id: string) => {
    setReadIds((prev) => new Set(prev).add(id)); // optimistic
    try {
      await notificationApi.markRead(id);
    } catch {
      setReadIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const markAll = async () => {
    const previous = readIds;
    setReadIds(new Set(items.map((n) => n.id))); // optimistic
    try {
      await notificationApi.markAllRead();
    } catch {
      setReadIds(previous);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inbox"
        icon={Bell}
        title="Notifications"
        subtitle="Routing, QC, and lifecycle alerts."
        actions={
          unread ? (
            <Button variant="outline" onClick={markAll}>
              <CheckCheck className="h-4 w-4" /> Mark all read
            </Button>
          ) : null
        }
      />

      <Card>
        {/* Filter bar */}
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/40 p-1">
            {(['all', 'unread'] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  'rounded-sm px-3 py-1 text-sm font-medium transition-colors',
                  filter === f ? 'bg-background text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {f === 'all' ? 'All' : 'Unread'}
                {f === 'unread' && unread > 0 ? (
                  <span className="ml-1.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-federal-blue px-1 text-[10px] font-bold text-white">
                    {unread}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
          <span className="text-xs text-muted-foreground">
            {items.length} total · {unread} unread
          </span>
        </div>

        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-3 p-5">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : visible.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon={filter === 'unread' ? CheckCircle2 : Bell}
                title={filter === 'unread' ? 'No unread notifications' : 'No notifications'}
                description="You're all caught up."
              />
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {visible.map((n: Notification) => {
                const read = isRead(n);
                const { icon: Icon, tone } = notifMeta(n.notification_type);
                return (
                  <li
                    key={n.id}
                    className={cn(
                      'group flex gap-3.5 px-5 py-3.5 transition-colors hover:bg-muted/30',
                      !read && 'bg-federal-blue/[0.04]',
                    )}
                  >
                    <span className={cn('mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset ring-black/[0.03]', tone)}>
                      <Icon className="h-[18px] w-[18px]" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={cn('text-sm', read ? 'font-medium text-foreground' : 'font-semibold text-foreground')}>
                            {n.title}
                          </span>
                          <Badge variant="neutral" size="sm">{humanize(n.notification_type)}</Badge>
                          {!read ? (
                            <span className="rounded-full bg-federal-blue/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-federal-blue">
                              New
                            </span>
                          ) : null}
                        </div>
                        <time
                          className="shrink-0 whitespace-nowrap text-xs text-muted-foreground"
                          title={formatDateTime(n.created_at)}
                        >
                          {relativeTime(n.created_at)}
                        </time>
                      </div>
                      {n.message ? <p className="mt-1 text-sm text-muted-foreground">{n.message}</p> : null}
                      <div className="mt-2 flex items-center gap-4">
                        {n.crash_id ? (
                          <Link
                            to={`/crashes/${n.crash_id}`}
                            className="inline-flex items-center gap-1 text-xs font-medium text-federal-blue hover:underline"
                          >
                            Open crash <ArrowRight className="h-3 w-3" />
                          </Link>
                        ) : null}
                        {!read ? (
                          <button
                            type="button"
                            onClick={() => markOne(n.id)}
                            className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                          >
                            Mark as read
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
