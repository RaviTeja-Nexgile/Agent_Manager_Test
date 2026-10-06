import * as React from 'react';
import { Link, NavLink, Outlet, useParams } from 'react-router-dom';
import { ArrowLeft, CarFront, MapPin } from 'lucide-react';

import { useApi } from '@/lib/useApi';
import { crashApi } from '@/lib/endpoints';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { PhaseBadge } from '@/components/shell/StatusBadge';
import { cn } from '@/lib/utils';
import { formatDate, formatTime } from '@/lib/format';

const TABS = [
  { to: 'overview', label: 'Overview' },
  { to: 'initial-incident', label: 'Initial Incident' },
  { to: 'source-data', label: 'Source Data' },
  // This tab now shows the full CCFP Aggregated Data document
  // (canonical attributes + CCFP source records + external-system links). The
  // route stays `attributes` so existing links and the router guard are unaffected.
  { to: 'attributes', label: 'Aggregated Data' },
  { to: 'quality', label: 'Quality' },
  { to: 'completeness', label: 'Completeness' },
  { to: 'contributing-factors', label: 'Contributing Factors' },
  { to: 'documents', label: 'Documents' },
  { to: 'timeline', label: 'Timeline' },
];

export function CrashDetailPage() {
  const { id = '' } = useParams();
  const { data: crash, loading, error, reload } = useApi(() => crashApi.get(id), [id]);

  return (
    <div className="space-y-5">
      <Link to="/crashes" className="inline-flex items-center gap-1.5 text-sm text-federal-blue hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back to crashes
      </Link>

      {error ? (
        <Alert variant="destructive"><AlertDescription>{error.message}</AlertDescription></Alert>
      ) : loading || !crash ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <Card>
          <CardContent className="flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-federal-blue/10 text-federal-blue">
                <CarFront className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-display-sm font-semibold tracking-tight">{crash.ccfp_identifier}</h1>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" />
                    {[crash.city, crash.county && `${crash.county} County`, crash.state_code].filter(Boolean).join(', ') || 'Location unknown'}
                  </span>
                  <span>·</span>
                  <span>{formatDate(crash.crash_date)} {crash.crash_time ? `at ${formatTime(crash.crash_time)}` : ''}</span>
                  {crash.local_report_number ? <><span>·</span><span>Local #{crash.local_report_number}</span></> : null}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <PhaseBadge phase={crash.lifecycle_phase} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tab nav */}
      <div className="overflow-x-auto border-b border-border">
        <nav className="flex min-w-max gap-1" aria-label="Crash sections">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                cn(
                  'whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'border-federal-blue text-federal-blue'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>

      {crash ? <Outlet context={{ crash, reload }} /> : null}
    </div>
  );
}
