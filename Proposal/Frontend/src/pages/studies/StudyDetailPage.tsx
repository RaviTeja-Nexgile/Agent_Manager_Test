import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom';
import { ArrowLeft, Boxes } from 'lucide-react';

import { useApi } from '@/lib/useApi';
import { studyApi } from '@/lib/endpoints';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { humanize } from '@/lib/format';
import type { Study } from '@/lib/types';

const TABS = [
  { to: 'overview', label: 'Overview' },
  { to: 'states', label: 'States' },
  { to: 'parameters', label: 'Parameters' },
  { to: 'attributes', label: 'Attribute Requirements' },
  { to: 'completeness-rules', label: 'Completeness Rules' },
  { to: 'coverage', label: 'PCR Coverage' },
  { to: 'publication', label: 'Publication' },
];

export interface StudyContextValue {
  study: Study;
  reload: () => void;
}
export function useStudy(): StudyContextValue {
  return useOutletContext<StudyContextValue>();
}

export function StudyDetailPage() {
  const { id = '' } = useParams();
  const { data: study, loading, error, reload } = useApi(() => studyApi.get(id), [id]);

  return (
    <div className="space-y-5">
      <Link to="/studies" className="inline-flex items-center gap-1.5 text-sm text-federal-blue hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back to studies
      </Link>
      {error ? <Alert variant="destructive"><AlertDescription>{error.message}</AlertDescription></Alert>
        : loading || !study ? <Skeleton className="h-20 w-full" />
          : (
            <Card>
              <CardContent className="flex items-center justify-between gap-3 p-5">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-md bg-federal-blue/10 text-federal-blue"><Boxes className="h-5 w-5" /></span>
                  <div>
                    <div className="text-eyebrow">Phase {study.phase_number} · {study.code}</div>
                    <h1 className="text-display-sm font-semibold tracking-tight">{study.name}</h1>
                    <p className="text-sm text-muted-foreground">{study.vehicle_type} · {study.crash_severity}</p>
                  </div>
                </div>
                <Badge variant={study.status === 'ACTIVE' ? 'success' : 'neutral'}>{humanize(study.status)}</Badge>
              </CardContent>
            </Card>
          )}

      <div className="overflow-x-auto border-b border-border">
        <nav className="flex min-w-max gap-1" aria-label="Study sections">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} className={({ isActive }) => cn('whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors', isActive ? 'border-federal-blue text-federal-blue' : 'border-transparent text-muted-foreground hover:text-foreground')}>
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>

      {study ? <Outlet context={{ study, reload }} /> : null}
    </div>
  );
}
