/** Shared dashboard widgets composed by the role-specific dashboards. */
import * as React from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  CarFront,
  CheckCircle2,
  Skull,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { StatTile } from '@/components/shell/StatTile';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PhaseBadge } from '@/components/shell/StatusBadge';
import { HorizontalBars, DonutChart, CHART_PALETTE, SERIES_COLORS, type DonutDatum } from '@/components/charts';
import { LIFECYCLE_PHASES, PHASE_LABEL } from '@/lib/constants';
import { formatDate, formatNumber, humanize } from '@/lib/format';
import type { Crash, PcrCoverage, QueryResult } from '@/lib/types';

export function CrashKpis({ crashes, loading }: { crashes?: Crash[]; loading?: boolean }) {
  const k = React.useMemo(() => {
    const list = crashes ?? [];
    const fatal = list.filter((c) => (c.num_fatalities ?? 0) > 0).length;
    const inAnalysis = list.filter((c) => c.lifecycle_phase === 'ANALYSIS' || c.lifecycle_phase === 'PUBLICATION').length;
    const fatalities = list.reduce((s, c) => s + (c.num_fatalities ?? 0), 0);
    return { total: list.length, fatal, inAnalysis, fatalities };
  }, [crashes]);
  const tiles: { label: string; value: React.ReactNode; icon: LucideIcon; tone: string; hint: string }[] = [
    { label: 'Crashes in scope', value: loading ? '—' : k.total, icon: CarFront, tone: 'bg-federal-blue/10 text-federal-blue', hint: 'Visible to you' },
    { label: 'Fatal crashes', value: loading ? '—' : k.fatal, icon: Skull, tone: 'bg-alert-red/15 text-alert-red-700', hint: '≥ 1 fatality' },
    { label: 'In analysis / published', value: loading ? '—' : k.inAnalysis, icon: TrendingUp, tone: 'bg-success-green/15 text-success-green-700', hint: 'Late lifecycle' },
    { label: 'Total fatalities', value: loading ? '—' : k.fatalities, icon: AlertTriangle, tone: 'bg-alert-amber/15 text-alert-amber-700', hint: 'Across visible crashes' },
  ];
  return (
    <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
      {tiles.map((t) => (
        <StatTile key={t.label} label={t.label} value={t.value} icon={t.icon} tone={t.tone} hint={t.hint} />
      ))}
    </div>
  );
}

export function PhaseDistribution({ crashes, loading }: { crashes?: Crash[]; loading?: boolean }) {
  const counts = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const p of LIFECYCLE_PHASES) map.set(p.key, 0);
    for (const c of crashes ?? []) map.set(c.lifecycle_phase, (map.get(c.lifecycle_phase) ?? 0) + 1);
    return LIFECYCLE_PHASES.map((p, i) => ({
      key: p.key,
      label: `${p.short}`,
      value: map.get(p.key) ?? 0,
      color: i === 6 ? CHART_PALETTE.successGreen : i >= 4 ? CHART_PALETTE.alertAmber : CHART_PALETTE.federalBlue,
    }));
  }, [crashes]);
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardHeading icon={TrendingUp} title="Crash pipeline by phase" description="Lifecycle distribution." />
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">{loading ? <Skeleton className="h-48 w-full" /> : <HorizontalBars data={counts} labelWidth="w-24" fill />}</CardContent>
    </Card>
  );
}

export function QueryBarsCard({
  title,
  description,
  icon,
  result,
  labelKey,
  valueKey,
  loading,
  mapLabel,
}: {
  title: string;
  description?: string;
  icon: LucideIcon;
  result?: QueryResult;
  labelKey: string;
  valueKey: string;
  loading?: boolean;
  mapLabel?: (v: string) => string;
}) {
  // Ranked, color-coded bars: sort highest→lowest and give each category a
  // distinct color from the federal palette so the chart reads at a glance.
  const data = (result?.rows ?? [])
    .map((r) => ({
      key: String(r[labelKey] ?? ''),
      label: mapLabel ? mapLabel(String(r[labelKey] ?? '')) : String(r[labelKey] ?? '—'),
      value: Number(r[valueKey] ?? 0),
    }))
    .sort((a, b) => b.value - a.value)
    .map((d, i) => ({ ...d, color: SERIES_COLORS[i % SERIES_COLORS.length] }));
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardHeading icon={icon} title={title} description={description} />
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
        {loading ? <Skeleton className="h-48 w-full" /> : data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No data.</p>
        ) : (
          <HorizontalBars data={data} labelWidth="auto" barSize={20} fill />
        )}
      </CardContent>
    </Card>
  );
}

export function QueryDonutCard({
  title,
  description,
  icon,
  result,
  labelKey,
  valueKey,
  loading,
  centerLabel,
  mapLabel,
}: {
  title: string;
  description?: string;
  icon: LucideIcon;
  result?: QueryResult;
  labelKey: string;
  valueKey: string;
  loading?: boolean;
  centerLabel?: string;
  mapLabel?: (v: string) => string;
}) {
  const data: DonutDatum[] = (result?.rows ?? []).map((r) => ({
    key: String(r[labelKey] ?? ''),
    label: mapLabel ? mapLabel(String(r[labelKey] ?? '')) : String(r[labelKey] ?? '—'),
    value: Number(r[valueKey] ?? 0),
  }));
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardHeading icon={icon} title={title} description={description} />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-center">
        {loading ? <Skeleton className="h-48 w-full" /> : <DonutChart data={data} centerLabel={centerLabel ?? 'TOTAL'} />}
      </CardContent>
    </Card>
  );
}

export function RecentCrashesCard({
  crashes,
  loading,
  title = 'Recent crashes',
}: {
  crashes?: Crash[];
  loading?: boolean;
  title?: string;
}) {
  const rows = (crashes ?? []).slice(0, 8);
  return (
    <Card>
      <CardHeader>
        <CardHeading icon={CarFront} title={title} description="Most recent crash records in your scope." />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-5"><Skeleton className="h-32 w-full" /></div>
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={CarFront} title="No crashes yet" description="Crash records you can access will appear here." />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">CCFP ID</TableHead>
                <TableHead>Location</TableHead>
                <TableHead className="text-center">Phase</TableHead>
                <TableHead className="text-right pr-5">Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="pl-5">
                    <Link to={`/crashes/${c.id}`} className="font-medium text-federal-blue hover:underline">
                      {c.ccfp_identifier}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {[c.city, c.state_code].filter(Boolean).join(', ') || '—'}
                  </TableCell>
                  <TableCell className="text-center"><PhaseBadge phase={c.lifecycle_phase} /></TableCell>
                  <TableCell className="text-right pr-5 text-muted-foreground">{formatDate(c.crash_date)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export interface AttentionItem {
  key: string;
  icon: LucideIcon;
  title: string;
  description: string;
  count: number;
  tone?: 'amber' | 'blue' | 'red' | 'green';
  to?: string;
}
const TONE_BG: Record<NonNullable<AttentionItem['tone']>, string> = {
  amber: 'bg-alert-amber/15 text-alert-amber-700',
  blue: 'bg-federal-blue/10 text-federal-blue',
  red: 'bg-alert-red/15 text-alert-red-700',
  green: 'bg-success-green/15 text-success-green-700',
};
export function AttentionCard({ items, loading }: { items: AttentionItem[]; loading?: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardHeading icon={AlertTriangle} title="Attention required" description="Items that need your eyes." tone="bg-alert-amber/15 text-alert-amber-700" />
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {loading ? (
          [...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)
        ) : items.length === 0 ? (
          <div className="flex items-center gap-2 rounded-md border border-border bg-success-green/5 px-3 py-2.5 text-success-green-700">
            <CheckCircle2 className="h-4 w-4" />
            <span>Nothing requires attention right now.</span>
          </div>
        ) : (
          items.map((it) => {
            const body = (
              <>
                <div className="flex items-start gap-2.5">
                  <span className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${TONE_BG[it.tone ?? 'amber']}`}>
                    <it.icon className="h-3.5 w-3.5" />
                  </span>
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-foreground">{it.title}</span>
                    <span className="text-xs text-muted-foreground">{it.description}</span>
                  </div>
                </div>
                <span className="tabular-nums text-base font-semibold text-foreground">{it.count}</span>
              </>
            );
            return it.to ? (
              <Link key={it.key} to={it.to} className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted/30 px-3 py-2.5 hover:bg-muted/50">
                {body}
              </Link>
            ) : (
              <div key={it.key} className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted/30 px-3 py-2.5">
                {body}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

export function PcrCoverageCard({ coverage, loading }: { coverage?: PcrCoverage[]; loading?: boolean }) {
  const data = (coverage ?? []).map((c) => ({
    key: c.pcr_section_code,
    label: humanize(c.pcr_section_code),
    value: Number(c.completion_pct ?? 0),
    color: Number(c.completion_pct ?? 0) >= 60 ? CHART_PALETTE.successGreen : Number(c.completion_pct ?? 0) >= 30 ? CHART_PALETTE.alertAmber : CHART_PALETTE.alertRed,
  }));
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardHeading icon={CheckCircle2} title="State PCR coverage" description="Required-attribute completion % by PCR section." />
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
        {loading ? <Skeleton className="h-48 w-full" /> : data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No coverage data for your State scope.</p>
        ) : (
          <HorizontalBars data={data} max={100} unit="%" labelWidth="w-44" showValueLabels fill />
        )}
      </CardContent>
    </Card>
  );
}

export { PHASE_LABEL, formatNumber };
