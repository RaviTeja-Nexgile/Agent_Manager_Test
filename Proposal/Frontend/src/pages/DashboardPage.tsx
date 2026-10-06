import * as React from 'react';
import { Link } from 'react-router-dom';
import {
  Bell,
  CarFront,
  CheckCircle2,
  FileBarChart2,
  FlaskConical,
  Globe,
  MapPin,
  Skull,
  TrendingUp,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Button } from '@/components/ui/button';
import { useApi } from '@/lib/useApi';
import { useAuth } from '@/app/auth';
import {
  analyticsApi,
  crashApi,
  notificationApi,
  publicApi,
  reportApi,
  studyApi,
} from '@/lib/endpoints';
import {
  getPrimaryRole,
  getPrimaryRoleLabel,
  hasPermission,
  isStateScoped,
} from '@/lib/permissions';
import { humanize, formatDate } from '@/lib/format';
import type { Crash, Notification, PcrCoverage, PublicReport, QueryResult, Report } from '@/lib/types';
import {
  AttentionCard,
  CrashKpis,
  PcrCoverageCard,
  PhaseDistribution,
  QueryBarsCard,
  QueryDonutCard,
  RecentCrashesCard,
  type AttentionItem,
} from '@/components/dashboards/shared';

interface Bundle {
  crashes?: Crash[];
  notifications?: Notification[];
  byState?: QueryResult;
  byPhase?: QueryResult;
  fatalities?: QueryResult;
  qc?: QueryResult;
  coverage?: PcrCoverage[];
  reports?: Report[];
  publicOutputs?: PublicReport[];
}

function NotificationsPreview({ items, loading }: { items?: Notification[]; loading?: boolean }) {
  const list = (items ?? []).slice(0, 6);
  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Bell} title="Recent notifications" description="Routing, QC, and lifecycle alerts." />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-5"><Skeleton className="h-28 w-full" /></div>
        ) : list.length === 0 ? (
          <div className="p-5 text-sm text-muted-foreground">No notifications.</div>
        ) : (
          <ul className="divide-y divide-border">
            {list.map((n) => (
              <li key={n.id} className="px-4 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{n.title}</div>
                    <div className="text-xs text-muted-foreground">{humanize(n.notification_type)} · {formatDate(n.created_at)}</div>
                  </div>
                  {!n.read_at ? <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-federal-blue" /> : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function ReportsPreview({ reports, loading }: { reports?: Report[]; loading?: boolean }) {
  const list = (reports ?? []).slice(0, 8);
  return (
    <Card>
      <CardHeader>
        <CardHeading icon={FileBarChart2} title="Reports available to you" description="Dashboards, tables, and published outputs." />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-5"><Skeleton className="h-28 w-full" /></div>
        ) : list.length === 0 ? (
          <div className="p-5 text-sm text-muted-foreground">No reports shared with you yet.</div>
        ) : (
          <ul className="divide-y divide-border">
            {list.map((r) => (
              <li key={r.id} className="flex items-center justify-between px-4 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{r.name}</div>
                  <div className="text-xs text-muted-foreground">{humanize(r.report_type)} · {humanize(r.visibility)}</div>
                </div>
                {r.is_published ? <span className="text-xs font-medium text-success-green-700">Published</span> : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PublicOutputsPreview({ outputs, loading }: { outputs?: PublicReport[]; loading?: boolean }) {
  const list = outputs ?? [];
  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Globe} title="Published de-identified outputs" description="Public summaries released after study publication." />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-5"><Skeleton className="h-28 w-full" /></div>
        ) : list.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={Globe} title="No published outputs yet" description="De-identified study summaries appear here after publication." />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {list.map((r) => (
              <li key={r.id} className="px-4 py-2.5">
                <div className="text-sm font-medium">{r.name}</div>
                {r.description ? <div className="text-xs text-muted-foreground">{r.description}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const role = getPrimaryRole(user);
  const persona = personaFor(role);
  // The program-persona charts run server-side analytics queries that require
  // `analytics:query`. Roles without it (e.g. CCFP Database Administrator) would
  // otherwise see four permanently-empty "No data" cards — so we instead derive
  // the equivalents from the crashes they CAN read (crash:read) and never render
  // an unpopulatable card.
  const canQuery = hasPermission(user, 'analytics:query');

  const { data, loading } = useApi<Bundle>(async () => {
    const out: Bundle = {};
    // Fetch every independent source concurrently, each self-guarded so one slow
    // or failing (403/500) request can never stall the others or leave the whole
    // dashboard stuck on skeletons. Permission-gated calls are only issued when
    // the role can make them, so we never fire a request the backend will 403.
    const tasks: Promise<unknown>[] = [];
    if (hasPermission(user, 'crash:read')) {
      tasks.push(
        crashApi.list({ limit: 200 }).then((r) => { out.crashes = r.items; }).catch(() => { out.crashes = []; }),
      );
    }
    if (hasPermission(user, 'analytics:query')) {
      tasks.push(
        Promise.all([
          analyticsApi.runQuery('crash_counts_by_state').catch(() => undefined),
          analyticsApi.runQuery('crash_counts_by_phase').catch(() => undefined),
          analyticsApi.runQuery('fatalities_by_state').catch(() => undefined),
          analyticsApi.runQuery('qc_failure_summary').catch(() => undefined),
        ]).then(([byState, byPhase, fatalities, qc]) => {
          out.byState = byState; out.byPhase = byPhase; out.fatalities = fatalities; out.qc = qc;
        }),
      );
    }
    if (hasPermission(user, 'report:read')) {
      tasks.push(reportApi.list().then((r) => { out.reports = r; }).catch(() => { out.reports = []; }));
    }
    // Public outputs (single open-data endpoint, available to all roles).
    if (hasPermission(user, 'public:read')) {
      tasks.push(publicApi.allOutputs().then((r) => { out.publicOutputs = r; }).catch(() => { out.publicOutputs = []; }));
    }
    tasks.push(notificationApi.list().then((r) => { out.notifications = r; }).catch(() => { out.notifications = []; }));
    await Promise.all(tasks);

    // State PCR coverage depends on a visible crash's study id, so it runs once
    // crashes resolve. Empty results are fine — the card hides itself.
    if (isStateScoped(user) && out.crashes && out.crashes.length) {
      const studyId = out.crashes[0].study_id;
      const state = user?.allowed_states?.[0];
      out.coverage = await studyApi.pcrCoverage(studyId, state).catch(() => []);
    }
    return out;
  }, [user?.id]);

  // Client-derived stand-ins for the server analytics queries, computed from the
  // crashes the user is authorized to read. Used only when the user lacks
  // `analytics:query`, so a permission-blocked card is replaced with real data
  // rather than an empty one. (QC-by-rule has no crash-list equivalent, so it is
  // simply omitted instead of shown empty.)
  const derived = React.useMemo(() => {
    const list = data?.crashes ?? [];
    const byStateMap = new Map<string, number>();
    const fatMap = new Map<string, number>();
    for (const c of list) {
      const s = c.state_code ?? '—';
      byStateMap.set(s, (byStateMap.get(s) ?? 0) + 1);
      fatMap.set(s, (fatMap.get(s) ?? 0) + (c.num_fatalities ?? 0));
    }
    const toResult = (m: Map<string, number>, valueKey: string): QueryResult => ({
      query_name: 'derived',
      columns: ['state_code', valueKey],
      rows: [...m.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([state_code, v]) => ({ state_code, [valueKey]: v })),
    });
    return { byState: toResult(byStateMap, 'count'), fatalities: toResult(fatMap, 'fatalities') };
  }, [data?.crashes]);

  // State-persona PCR coverage is empty for State/study combinations with no
  // seeded coverage catalog — hide the card once loaded-empty instead of showing
  // a "No coverage data" shell, and let the phase chart take the full row.
  const coverageVisible = loading || (data?.coverage?.length ?? 0) > 0;

  const attention = React.useMemo<AttentionItem[]>(() => {
    const items: AttentionItem[] = [];
    const unread = (data?.notifications ?? []).filter((n) => !n.read_at).length;
    if (unread) items.push({ key: 'notif', icon: Bell, title: 'Unread notifications', description: 'New routing / QC alerts', count: unread, tone: 'blue', to: '/notifications' });
    const incident = (data?.crashes ?? []).filter((c) => c.lifecycle_phase === 'INITIAL_INCIDENT').length;
    if (incident) items.push({ key: 'incident', icon: CarFront, title: 'Crashes in initial-incident phase', description: 'Awaiting routing / data collection', count: incident, tone: 'amber', to: '/crashes' });
    return items;
  }, [data]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={getPrimaryRoleLabel(user)}
        icon={persona.icon}
        title={`Welcome, ${user?.full_name?.split(' ')[0] ?? 'there'}`}
        subtitle={persona.subtitle}
        actions={
          hasPermission(user, 'crash:read') ? (
            <Button asChild variant="outline"><Link to="/crashes">View crashes</Link></Button>
          ) : null
        }
      />

      {persona.kind === 'public' ? (
        <PublicOutputsPreview outputs={data?.publicOutputs} loading={loading} />
      ) : persona.kind === 'federal' ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <ReportsPreview reports={data?.reports} loading={loading} />
            <PublicOutputsPreview outputs={data?.publicOutputs} loading={loading} />
          </div>
          <NotificationsPreview items={data?.notifications} loading={loading} />
        </>
      ) : persona.kind === 'cipsea' ? (
        <>
          <CrashKpis crashes={data?.crashes} loading={loading} />
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2"><RecentCrashesCard crashes={data?.crashes} loading={loading} title="In-scope crashes" /></div>
            <div className="space-y-4">
              <AttentionCard items={attention} loading={loading} />
              <NotificationsPreview items={data?.notifications} loading={loading} />
            </div>
          </div>
        </>
      ) : persona.kind === 'program' ? (
        <>
          <CrashKpis crashes={data?.crashes} loading={loading} />
          {canQuery ? (
            <div className="chart-grid grid gap-4 lg:grid-cols-2">
              <QueryBarsCard title="Crashes by State" icon={MapPin} result={data?.byState} labelKey="state_code" valueKey="count" loading={loading} />
              <QueryDonutCard title="Crashes by lifecycle phase" icon={TrendingUp} result={data?.byPhase} labelKey="lifecycle_phase" valueKey="count" loading={loading} centerLabel="CRASHES" mapLabel={humanize} />
              <QueryBarsCard title="Fatalities by State" icon={Skull} result={data?.fatalities} labelKey="state_code" valueKey="fatalities" loading={loading} />
              <QueryBarsCard title="QC failures by rule" icon={CheckCircle2} result={data?.qc} labelKey="rule_code" valueKey="failures" loading={loading} />
            </div>
          ) : (
            <div className="chart-grid grid gap-4 lg:grid-cols-2">
              <QueryBarsCard title="Crashes by State" description="From crashes visible to you." icon={MapPin} result={derived.byState} labelKey="state_code" valueKey="count" loading={loading} />
              <PhaseDistribution crashes={data?.crashes} loading={loading} />
              <QueryBarsCard title="Fatalities by State" description="From crashes visible to you." icon={Skull} result={derived.fatalities} labelKey="state_code" valueKey="fatalities" loading={loading} />
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2"><RecentCrashesCard crashes={data?.crashes} loading={loading} /></div>
            <NotificationsPreview items={data?.notifications} loading={loading} />
          </div>
        </>
      ) : (
        // state persona
        <>
          <CrashKpis crashes={data?.crashes} loading={loading} />
          <div className={`chart-grid grid gap-4 ${coverageVisible ? 'lg:grid-cols-2' : 'lg:grid-cols-1'}`}>
            <PhaseDistribution crashes={data?.crashes} loading={loading} />
            {coverageVisible ? <PcrCoverageCard coverage={data?.coverage} loading={loading} /> : null}
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2"><RecentCrashesCard crashes={data?.crashes} loading={loading} /></div>
            <div className="space-y-4">
              <AttentionCard items={attention} loading={loading} />
              <NotificationsPreview items={data?.notifications} loading={loading} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

type PersonaKind = 'program' | 'state' | 'cipsea' | 'federal' | 'public';
function personaFor(role: ReturnType<typeof getPrimaryRole>): { kind: PersonaKind; icon: typeof FlaskConical; subtitle: string } {
  switch (role) {
    case 'PUBLIC_USER':
      return { kind: 'public', icon: Globe, subtitle: 'Published, de-identified study outputs.' };
    case 'FEDERAL_USER':
      return { kind: 'federal', icon: FileBarChart2, subtitle: 'Role-approved reports and published outputs.' };
    case 'BTS_CIPSEA_AGENT':
    case 'FMCSA_CIPSEA_AGENT':
      return { kind: 'cipsea', icon: Bell, subtitle: 'In-scope crash notifications and CIPSEA-governed data.' };
    case 'MCSAP_INSPECTOR':
    case 'STATE_CMV_ANALYST':
    case 'STATE_USER':
      return { kind: 'state', icon: MapPin, subtitle: 'Your State crash queue, coverage, and quality.' };
    default:
      return { kind: 'program', icon: FlaskConical, subtitle: 'Program-wide crash analytics and operations.' };
  }
}
