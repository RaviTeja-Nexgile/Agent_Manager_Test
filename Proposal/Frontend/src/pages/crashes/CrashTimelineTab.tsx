import { Check, History } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { PhaseBadge } from '@/components/shell/StatusBadge';
import { LIFECYCLE_PHASES, PHASE_INDEX } from '@/lib/constants';
import type { CrashLifecyclePhase } from '@/lib/types';
import { useApi } from '@/lib/useApi';
import { crashApi } from '@/lib/endpoints';
import { formatDateTime, humanize } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useCrash } from './CrashContext';

export function CrashTimelineTab() {
  const { crash } = useCrash();
  const { data, loading } = useApi(() => crashApi.timeline(crash.id).catch(() => []), [crash.id]);

  // Where the crash currently sits on the lifecycle rail (documentation §5).
  // Mirrors the phase-progress treatment in dashboards/shared.tsx: compare each
  // phase index against the crash's current phase to mark reached/current/upcoming.
  const currentIndex = PHASE_INDEX[crash.lifecycle_phase] ?? 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading icon={History} title="Lifecycle phase" description="Where this crash sits in the CCFP lifecycle." />
        </CardHeader>
        <CardContent>
          <ol className="flex flex-wrap items-stretch gap-1.5" aria-label="Crash lifecycle phase rail">
            {LIFECYCLE_PHASES.map((p) => {
              const reached = p.index < currentIndex;
              const current = p.index === currentIndex;
              return (
                <li
                  key={p.key}
                  aria-current={current ? 'step' : undefined}
                  className={cn(
                    'flex min-w-0 flex-1 flex-col items-center gap-1 rounded-md border px-2 py-2 text-center',
                    current
                      ? 'border-federal-blue bg-federal-blue/10 text-federal-blue'
                      : reached
                        ? 'border-success-green-100 bg-success-green/5 text-success-green-700'
                        : 'border-border bg-muted/30 text-muted-foreground',
                  )}
                >
                  <span
                    className={cn(
                      'inline-flex h-6 w-6 items-center justify-center rounded-full border text-2xs font-semibold',
                      current
                        ? 'border-federal-blue bg-federal-blue text-white'
                        : reached
                          ? 'border-success-green-100 bg-success-green-100 text-success-green-700'
                          : 'border-border bg-background',
                    )}
                  >
                    {reached ? <Check className="h-3.5 w-3.5" /> : p.index + 1}
                  </span>
                  <span className="text-2xs font-medium leading-tight">{p.short}</span>
                </li>
              );
            })}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardHeading icon={History} title="Audit timeline" description="Every state-changing action on this crash." />
        </CardHeader>
        <CardContent>
          {loading ? <Skeleton className="h-40 w-full" /> : (data?.length ?? 0) === 0 ? (
            <EmptyState icon={History} title="No activity yet" description="Audited actions on this crash will appear here." />
          ) : (
            <ol className="relative ml-3 space-y-5 border-l border-border pl-6">
              {data!.map((e, i) => (
                <li key={i} className="relative">
                  <span
                    className={cn(
                      'absolute -left-[1.65rem] top-1 inline-flex h-3 w-3 items-center justify-center rounded-full border-2 bg-background',
                      e.is_milestone ? 'border-federal-blue bg-federal-blue' : 'border-federal-blue',
                    )}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    {e.is_milestone && e.phase ? (
                      <PhaseBadge phase={e.phase as CrashLifecyclePhase} />
                    ) : (
                      <Badge variant="info" size="sm">{humanize(e.action)}</Badge>
                    )}
                    <span className="text-sm font-medium">{humanize(e.entity_type)}</span>
                    <span className="text-xs text-muted-foreground">{formatDateTime(e.occurred_at)}</span>
                  </div>
                  {e.after_state ? (
                    <pre className="mt-1 overflow-x-auto rounded-sm bg-muted px-2 py-1 text-xs text-muted-foreground">
                      {JSON.stringify(e.after_state)}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
