import * as React from 'react';
import {
  AlertTriangle,
  BarChart3,
  Download,
  FlaskConical,
  GitCompare,
  Layers,
  Network,
  Play,
  Plus,
  RefreshCw,
  Sigma,
  Target,
  Trash2,
  TrendingUp,
  Users,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { CardHeading } from '@/components/shell/CardHeading';
import { StatTile } from '@/components/shell/StatTile';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { HorizontalBars, LineChart, VerticalBars } from '@/components/charts';
import { useApi } from '@/lib/useApi';
import { analysisStatsApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { formatDateTime, formatNumber, relativeTime } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type {
  AnalysisCohort,
  CohortRole,
  ComparativeResult,
  DescriptiveResult,
  DistributionResult,
  RiskModelResult,
  StatExportFormat,
  ThematicResult,
  TrendResult,
} from '@/lib/types';

/**
 * Statistical analysis in the CCFP Analysis Environment.
 *
 * The January 2026 BRD replaces one unelaborated "statistical analysis" row with
 * four named method families — central tendency and dispersion, data
 * distributions, thematic analysis, and statistical risk modeling "given the
 * availability of control such as non-fatal crashes" — plus the comparative and
 * trend work analysts are expected to do. This page is where an analyst reaches
 * all of them.
 *
 * Two things drive the layout.
 *
 * **A statistic is meaningless without its population and its date.** So a
 * cohort is picked first and stays visible, and every result restates which
 * cohort version it describes. The alternative — a method picker that quietly
 * runs against "the data" — is how two analysts end up with two different
 * answers and no way to tell which is stale.
 *
 * **Caveats are rendered as prominently as the numbers.** At Phase 1 volumes
 * almost every estimate here has an interval too wide to act on, and the failure
 * mode of a statistics screen is not an error message — it is a confident number
 * nobody questions. The backend returns caveats as part of each result; this
 * page shows them above the fold rather than as a footnote.
 */
export function StatisticalAnalysisPage() {
  const { user } = useAuth();
  const canRun = hasPermission(user, 'analysis_stats:run');
  const canManage = hasPermission(user, 'analysis_stats:manage');

  const { data: cohorts, loading, reload } = useApi(() => analysisStatsApi.cohorts(), []);
  const { data: fields } = useApi(() => analysisStatsApi.fields(), []);

  const active = React.useMemo(
    () => (cohorts ?? []).filter((c) => c.status === 'ACTIVE'),
    [cohorts],
  );
  const [selectedId, setSelectedId] = React.useState<string>('');

  // Default to the CASE cohort — the Phase 1 study population is what an analyst
  // almost always wants first, and landing on an arbitrary alphabetical cohort
  // invites analysing the wrong population by accident.
  React.useEffect(() => {
    if (!selectedId && active.length) {
      const preferred = active.find((c) => c.cohort_role === 'CASE') ?? active[0];
      setSelectedId(preferred.id);
    }
  }, [active, selectedId]);

  const selected = active.find((c) => c.id === selectedId);
  const controls = active.filter((c) => c.cohort_role === 'CONTROL');

  if (!canRun) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Statistical Analysis"
          subtitle="Descriptive, distributional, thematic and risk analysis over CCFP Analysis Environment cohorts."
        />
        <EmptyState
          icon={Sigma}
          title="You do not have access to the statistical analysis tools"
          description="The BRD reserves the Analysis Environment's statistical tooling for the CCFP Project Team and CCFP analytic roles. Analysis outputs are published to other users as dashboards, reports and shared tables."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Statistical Analysis"
        subtitle="Descriptive and inferential statistics over versioned crash-level cohorts in the CCFP Analysis Environment."
        icon={Sigma}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={Users}
          label="Cohorts"
          value={loading ? '—' : formatNumber(active.length)}
          hint="Saved crash populations"
        />
        <StatTile
          icon={Target}
          label="Control populations"
          value={loading ? '—' : formatNumber(controls.length)}
          hint={controls.length ? 'Risk modelling available' : 'Required for risk modelling'}
          tone={
            controls.length
              ? 'bg-success-green-50 text-success-green-700'
              : 'bg-alert-amber-light text-alert-amber-700'
          }
        />
        <StatTile
          icon={Layers}
          label="Crashes in selection"
          value={selected?.member_count == null ? '—' : formatNumber(selected.member_count)}
          hint={selected ? selected.name : 'No cohort selected'}
        />
        <StatTile
          icon={RefreshCw}
          label="Snapshot"
          value={selected?.materialized_at ? relativeTime(selected.materialized_at) : '—'}
          hint={
            selected?.version_no != null
              ? `Version ${selected.version_no} · ${formatDateTime(selected.materialized_at)}`
              : 'Not yet materialized'
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <CohortRail
          cohorts={active}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading}
          canManage={canManage}
          onChanged={reload}
          environmentId={active[0]?.environment_id}
          fields={fields}
        />

        {selected ? (
          <MethodPanel
            cohort={selected}
            cohorts={active}
            controls={controls}
            fields={fields}
            canManage={canManage}
          />
        ) : (
          <Card>
            <CardContent className="py-12">
              {loading ? (
                <div className="space-y-3">
                  <Skeleton className="h-5 w-56" />
                  <Skeleton className="h-32 w-full" />
                </div>
              ) : (
                <EmptyState
                  icon={Users}
                  title="No cohorts defined"
                  description="A cohort is a saved population of crashes. Every statistic runs over one, so define a cohort before running an analysis."
                />
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════ Cohort rail ══════════════════════════ */

const ROLE_TONE: Record<CohortRole, string> = {
  CASE: 'bg-federal-blue-50 text-federal-blue-700 border-federal-blue/30',
  CONTROL: 'bg-success-green-50 text-success-green-700 border-success-green-300',
  GENERAL: 'bg-muted text-muted-foreground border-border',
};

const ROLE_HINT: Record<CohortRole, string> = {
  CASE: 'The population under study',
  CONTROL: 'Comparison denominator for risk models',
  GENERAL: 'Descriptive only — not a risk-model arm',
};

function CohortRail({
  cohorts,
  selectedId,
  onSelect,
  loading,
  canManage,
  onChanged,
  environmentId,
  fields,
}: {
  cohorts: AnalysisCohort[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading: boolean;
  canManage: boolean;
  onChanged: () => void;
  environmentId?: string;
  fields?: { filter_columns: string[]; filter_operators: string[]; cohort_roles: CohortRole[] };
}) {
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);

  async function refreshOne(id: string) {
    setBusy(id);
    try {
      await analysisStatsApi.refreshCohort(id);
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-3">
        <CardHeading icon={Users} title="Cohorts" />
        {canManage && environmentId ? (
          <Button size="sm" variant="outline" onClick={() => setDialogOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
            New
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-2">
        {loading ? (
          <>
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </>
        ) : (
          cohorts.map((c) => {
            const isSelected = c.id === selectedId;
            return (
              <div
                key={c.id}
                className={`rounded-md border p-3 transition-colors ${
                  isSelected ? 'border-federal-blue bg-federal-blue-50/50' : 'border-border bg-card'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  aria-pressed={isSelected}
                  className="w-full text-left"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium leading-tight">{c.name}</span>
                    <Badge
                      variant="outline"
                      size="sm"
                      className={ROLE_TONE[c.cohort_role]}
                      title={ROLE_HINT[c.cohort_role]}
                    >
                      {c.cohort_role}
                    </Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {c.member_count == null ? (
                      'Not materialized'
                    ) : (
                      <>
                        {formatNumber(c.member_count)}{' '}
                        {c.member_count === 1 ? 'crash' : 'crashes'} · v{c.version_no} ·{' '}
                        {relativeTime(c.materialized_at)}
                      </>
                    )}
                  </div>
                </button>
                {canManage ? (
                  <div className="mt-2 flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      disabled={busy === c.id}
                      onClick={() => refreshOne(c.id)}
                    >
                      <RefreshCw
                        className={`mr-1 h-3 w-3 ${busy === c.id ? 'animate-spin' : ''}`}
                        aria-hidden
                      />
                      Refresh
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </CardContent>

      {dialogOpen && environmentId ? (
        <NewCohortDialog
          environmentId={environmentId}
          fields={fields}
          onClose={() => setDialogOpen(false)}
          onCreated={() => {
            setDialogOpen(false);
            onChanged();
          }}
        />
      ) : null}
    </Card>
  );
}

/* ══════════════════════════ Method panel ══════════════════════════ */

function MethodPanel({
  cohort,
  cohorts,
  controls,
  fields,
  canManage,
}: {
  cohort: AnalysisCohort;
  cohorts: AnalysisCohort[];
  controls: AnalysisCohort[];
  fields?: {
    numeric_variables: Record<string, string>;
    categorical_variables: Record<string, string>;
    trend_periods: string[];
    trend_measures: string[];
  };
  canManage: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardHeading icon={FlaskConical} title={cohort.name} />
            <p className="mt-1 text-xs text-muted-foreground">
              {cohort.code} · {cohort.cohort_role} ·{' '}
              {cohort.member_count == null
                ? 'not materialized'
                : `${formatNumber(cohort.member_count)} ${
                    cohort.member_count === 1 ? 'crash' : 'crashes'
                  }`}
              {cohort.version_no != null ? ` · version ${cohort.version_no}` : ''}
            </p>
          </div>
          <ExportMenu cohort={cohort} />
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="descriptive">
          <TabsList className="flex-wrap">
            <TabsTrigger value="descriptive">
              <Sigma className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Descriptive
            </TabsTrigger>
            <TabsTrigger value="distribution">
              <BarChart3 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Distribution
            </TabsTrigger>
            <TabsTrigger value="thematic">
              <Network className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Thematic
            </TabsTrigger>
            <TabsTrigger value="trend">
              <TrendingUp className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Trend
            </TabsTrigger>
            <TabsTrigger value="risk">
              <Target className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Risk model
            </TabsTrigger>
            <TabsTrigger value="compare">
              <GitCompare className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Compare
            </TabsTrigger>
            <TabsTrigger value="saved">
              <Play className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Saved
            </TabsTrigger>
          </TabsList>

          <TabsContent value="descriptive" className="pt-4">
            <DescriptiveTab cohort={cohort} variables={fields?.numeric_variables ?? {}} />
          </TabsContent>
          <TabsContent value="distribution" className="pt-4">
            <DistributionTab
              cohort={cohort}
              variables={{
                ...(fields?.categorical_variables ?? {}),
                ...(fields?.numeric_variables ?? {}),
              }}
            />
          </TabsContent>
          <TabsContent value="thematic" className="pt-4">
            <ThematicTab cohort={cohort} />
          </TabsContent>
          <TabsContent value="trend" className="pt-4">
            <TrendTab
              cohort={cohort}
              periods={fields?.trend_periods ?? ['YEAR', 'MONTH']}
              measures={fields?.trend_measures ?? ['crash_count']}
            />
          </TabsContent>
          <TabsContent value="risk" className="pt-4">
            <RiskModelTab cohort={cohort} controls={controls} />
          </TabsContent>
          <TabsContent value="compare" className="pt-4">
            <CompareTab
              cohort={cohort}
              cohorts={cohorts}
              variables={fields?.numeric_variables ?? {}}
            />
          </TabsContent>
          <TabsContent value="saved" className="pt-4">
            <SavedTab canManage={canManage} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

/* ══════════════════════════ Shared bits ══════════════════════════ */

/**
 * Caveats, rendered as an alert rather than small print.
 *
 * These are the difference between a statistics feature and a statistics
 * feature that can be trusted: "n = 26, the interval is a normal approximation"
 * and "Fisher's exact was used because a cell was too small" are not footnotes,
 * they are conditions on reading the number at all.
 */
function Caveats({ items }: { items: string[] }) {
  if (!items?.length) return null;
  return (
    <Alert variant="warning" className="mt-4">
      <AlertTriangle className="h-4 w-4" aria-hidden />
      <AlertTitle>
        {items.length === 1 ? 'Note on interpretation' : 'Notes on interpretation'}
      </AlertTitle>
      <AlertDescription>
        <ul className="mt-1 list-disc space-y-1 pl-4">
          {items.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

/** "As of" line. Every result carries one; without it a number is unreproducible. */
function Provenance({
  versionNo,
  materializedAt,
  n,
}: {
  versionNo?: number;
  materializedAt?: string;
  n?: number;
}) {
  if (versionNo == null) return null;
  return (
    <p className="mt-3 text-xs text-muted-foreground">
      Computed over cohort version {versionNo}
      {n != null ? ` (${formatNumber(n)} ${n === 1 ? 'crash' : 'crashes'})` : ''}, materialized{' '}
      {formatDateTime(materializedAt)}.
    </p>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/20 px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-medium tabular-nums">{value}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function num(v: number | null | undefined, digits = 4): string {
  if (v == null || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

/** p-values below the display floor read as "< 0.0001", never as a rounded 0. */
function pValue(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return '—';
  return p < 0.0001 ? '< 0.0001' : p.toFixed(4);
}

function RunError({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <Alert variant="destructive" className="mt-4">
      <AlertTriangle className="h-4 w-4" aria-hidden />
      <AlertTitle>This analysis could not be run</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}

/* ══════════════════════════ Descriptive ══════════════════════════ */

function DescriptiveTab({
  cohort,
  variables,
}: {
  cohort: AnalysisCohort;
  variables: Record<string, string>;
}) {
  const names = Object.keys(variables);
  const [variable, setVariable] = React.useState('num_fatalities');
  React.useEffect(() => {
    if (names.length && !names.includes(variable)) setVariable(names[0]);
  }, [names, variable]);

  // Keyed on the cohort's version, not just its id: a refresh mints a new
  // version without changing the id, and a panel that did not re-fetch would
  // keep showing the previous snapshot's numbers under the new "as of".
  const { data, loading, error } = useApi<DescriptiveResult>(
    () => analysisStatsApi.describe(cohort.id, variable),
    [cohort.id, cohort.current_version_id, variable],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Label htmlFor="desc-var">Variable</Label>
          <Select id="desc-var" value={variable} onChange={(e) => setVariable(e.target.value)}>
            {names.map((n) => (
              <option key={n} value={n}>
                {variables[n]}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {loading ? <Skeleton className="h-56 w-full" /> : null}
      <RunError error={error} />

      {data && !loading ? (
        <>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Central tendency</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="n" value={formatNumber(data.n)} hint={`${data.n_missing} missing`} />
              <Metric label="Mean" value={num(data.mean)} />
              <Metric label="Median" value={num(data.median)} />
              <Metric label="Mode" value={num(data.mode)} />
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">Dispersion</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Std. deviation (sample)" value={num(data.stddev)} />
              <Metric label="Variance" value={num(data.variance)} />
              <Metric label="Range" value={num(data.range)} hint={`${num(data.minimum)} – ${num(data.maximum)}`} />
              <Metric label="IQR" value={num(data.iqr)} hint={`p25 ${num(data.p25)} · p75 ${num(data.p75)}`} />
              <Metric label="Coefficient of variation" value={num(data.coefficient_of_variation)} />
              <Metric label="Standard error" value={num(data.standard_error)} />
              <Metric
                label={`${Math.round(data.confidence * 100)}% CI of the mean`}
                value={
                  data.ci_lower == null ? '—' : `${num(data.ci_lower)} – ${num(data.ci_upper)}`
                }
              />
              <Metric label="Total" value={num(data.total)} />
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold">Shape</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Metric
                label="Skewness"
                value={num(data.skewness)}
                hint={
                  data.skewness == null
                    ? undefined
                    : Math.abs(data.skewness) < 0.5
                      ? 'roughly symmetric'
                      : data.skewness > 0
                        ? 'right-tailed'
                        : 'left-tailed'
                }
              />
              <Metric
                label="Excess kurtosis"
                value={num(data.kurtosis_excess)}
                hint={
                  data.kurtosis_excess == null
                    ? undefined
                    : data.kurtosis_excess > 0
                      ? 'heavier tails than normal'
                      : 'lighter tails than normal'
                }
              />
              <Metric label="p10" value={num(data.p10)} />
              <Metric label="p90" value={num(data.p90)} />
            </div>
          </div>

          <Caveats items={data.caveats} />
          <Provenance versionNo={data.version_no} materializedAt={data.materialized_at} n={data.n} />
        </>
      ) : null}
    </div>
  );
}

/* ══════════════════════════ Distribution ══════════════════════════ */

function DistributionTab({
  cohort,
  variables,
}: {
  cohort: AnalysisCohort;
  variables: Record<string, string>;
}) {
  const names = Object.keys(variables);
  const [variable, setVariable] = React.useState('state_code');
  React.useEffect(() => {
    if (names.length && !names.includes(variable)) setVariable(names[0]);
  }, [names, variable]);

  const { data, loading, error } = useApi<DistributionResult>(
    () => analysisStatsApi.distribution(cohort.id, variable),
    [cohort.id, cohort.current_version_id, variable],
  );

  return (
    <div className="space-y-4">
      <div className="w-64">
        <Label htmlFor="dist-var">Variable</Label>
        <Select id="dist-var" value={variable} onChange={(e) => setVariable(e.target.value)}>
          {names.map((n) => (
            <option key={n} value={n}>
              {variables[n]}
            </option>
          ))}
        </Select>
      </div>

      {loading ? <Skeleton className="h-64 w-full" /> : null}
      <RunError error={error} />

      {data && !loading ? (
        <>
          {data.entries.length ? (
            <HorizontalBars
              data={data.entries.slice(0, 15).map((e) => ({
                key: e.category,
                label: e.category,
                value: e.frequency,
                hint: `${e.percent.toFixed(1)}% of ${formatNumber(data.n)}`,
              }))}
            />
          ) : null}

          {data.kind === 'NUMERIC' && data.histogram.length > 1 ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold">Histogram</h3>
              <VerticalBars
                categories={data.histogram.map((b) => `${num(b.lower, 1)}–${num(b.upper, 1)}`)}
                series={[{ key: 'count', label: 'Crashes', values: data.histogram.map((b) => b.count) }]}
                height={200}
              />
            </div>
          ) : null}

          <div>
            <h3 className="mb-2 text-sm font-semibold">Frequency distribution</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{data.label}</TableHead>
                  <TableHead className="text-right">Frequency</TableHead>
                  <TableHead className="text-right">Percent</TableHead>
                  <TableHead className="text-right">Cumulative</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.entries.map((e) => (
                  <TableRow key={e.category}>
                    <TableCell className="font-medium">{e.category}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(e.frequency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {e.percent.toFixed(2)}%
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {e.cumulative_percent.toFixed(2)}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <Caveats items={data.caveats} />
          <Provenance versionNo={data.version_no} materializedAt={data.materialized_at} n={data.n} />
        </>
      ) : null}
    </div>
  );
}

/* ══════════════════════════ Thematic ══════════════════════════ */

function ThematicTab({ cohort }: { cohort: AnalysisCohort }) {
  const { data, loading, error } = useApi<ThematicResult>(
    () => analysisStatsApi.thematic(cohort.id),
    [cohort.id, cohort.current_version_id],
  );

  return (
    <div className="space-y-4">
      {loading ? <Skeleton className="h-64 w-full" /> : null}
      <RunError error={error} />

      {data && !loading ? (
        <>
          <div className="grid gap-2 sm:grid-cols-3">
            <Metric label="Crashes in cohort" value={formatNumber(data.n)} />
            <Metric
              label="With factors recorded"
              value={formatNumber(data.n_with_factors)}
              hint={`${data.coded_percent.toFixed(0)}% coded`}
            />
            <Metric label="Distinct themes" value={formatNumber(data.themes.length)} />
          </div>

          {data.themes.length ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold">Recurring themes</h3>
              <HorizontalBars
                data={data.themes.slice(0, 12).map((t) => ({
                  key: t.factor,
                  label: t.factor,
                  value: t.crashes,
                  hint: `${t.percent_of_coded.toFixed(0)}% of coded crashes`,
                }))}
                labelWidth="w-64"
              />
            </div>
          ) : null}

          {data.groups.length ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold">By contributing-factor group</h3>
              <div className="flex flex-wrap gap-2">
                {data.groups.map((g) => (
                  <Badge key={g.group} variant="outline">
                    {g.group}: {formatNumber(g.crashes)}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          {data.co_occurrence.length ? (
            <div>
              <h3 className="mb-1 text-sm font-semibold">Co-occurring factor pairs</h3>
              <p className="mb-2 text-xs text-muted-foreground">
                Lift is the observed joint rate divided by the rate expected if the two were
                independent. Above 1 means they appear together more often than chance — an
                association, not a cause.
              </p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Factor A</TableHead>
                    <TableHead>Factor B</TableHead>
                    <TableHead className="text-right">Crashes</TableHead>
                    <TableHead className="text-right">Lift</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.co_occurrence.slice(0, 20).map((p) => (
                    <TableRow key={`${p.factor_a}||${p.factor_b}`}>
                      <TableCell className="text-sm">{p.factor_a}</TableCell>
                      <TableCell className="text-sm">{p.factor_b}</TableCell>
                      <TableCell className="text-right tabular-nums">{p.crashes}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {p.lift == null ? (
                          '—'
                        ) : (
                          <Badge
                            variant="outline"
                            size="sm"
                            className={
                              p.lift > 1
                                ? 'bg-federal-blue-50 text-federal-blue-700'
                                : 'bg-muted text-muted-foreground'
                            }
                          >
                            {p.lift.toFixed(2)}×
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}

          <Caveats items={data.caveats} />
          <Provenance versionNo={data.version_no} materializedAt={data.materialized_at} n={data.n} />
        </>
      ) : null}
    </div>
  );
}

/* ══════════════════════════ Trend ══════════════════════════ */

function TrendTab({
  cohort,
  periods,
  measures,
}: {
  cohort: AnalysisCohort;
  periods: string[];
  measures: string[];
}) {
  const [period, setPeriod] = React.useState('YEAR');
  const [measure, setMeasure] = React.useState('crash_count');

  const { data, loading, error } = useApi<TrendResult>(
    () => analysisStatsApi.trend(cohort.id, period, measure),
    [cohort.id, cohort.current_version_id, period, measure],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <div className="w-40">
          <Label htmlFor="trend-period">Period</Label>
          <Select id="trend-period" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {periods.map((p) => (
              <option key={p} value={p}>
                {p === 'YEAR' ? 'By year' : 'By calendar month'}
              </option>
            ))}
          </Select>
        </div>
        <div className="w-52">
          <Label htmlFor="trend-measure">Measure</Label>
          <Select id="trend-measure" value={measure} onChange={(e) => setMeasure(e.target.value)}>
            {measures.map((m) => (
              <option key={m} value={m}>
                {m.replace(/_/g, ' ')}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {loading ? <Skeleton className="h-56 w-full" /> : null}
      <RunError error={error} />

      {data && !loading ? (
        <>
          {data.series.length ? (
            <LineChart data={data.series.map((s) => ({ x: s.period, y: s.value }))} height={200} />
          ) : null}

          {data.slope != null ? (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Metric
                label="Direction"
                value={data.direction ?? '—'}
                hint={`${num(data.change_per_period, 3)} per period`}
              />
              <Metric label="Slope" value={num(data.slope, 4)} />
              <Metric
                label="R²"
                value={num(data.r_squared, 3)}
                hint={
                  data.r_squared == null
                    ? undefined
                    : `${(data.r_squared * 100).toFixed(0)}% of variation explained`
                }
              />
              <Metric
                label="p-value"
                value={pValue(data.p_value)}
                hint={data.significant ? 'significant at 0.05' : 'not significant'}
              />
            </div>
          ) : null}

          <Caveats items={data.caveats} />
          <Provenance versionNo={data.version_no} materializedAt={data.materialized_at} />
        </>
      ) : null}
    </div>
  );
}

/* ══════════════════════════ Risk model ══════════════════════════ */

function RiskModelTab({
  cohort,
  controls,
}: {
  cohort: AnalysisCohort;
  controls: AnalysisCohort[];
}) {
  const [controlId, setControlId] = React.useState('');
  const [exposure, setExposure] = React.useState('');
  const [result, setResult] = React.useState<RiskModelResult | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [running, setRunning] = React.useState(false);

  const { data: factors } = useApi(() => analysisStatsApi.factors(), []);

  React.useEffect(() => {
    if (!controlId && controls.length) setControlId(controls[0].id);
  }, [controls, controlId]);
  React.useEffect(() => {
    if (!exposure && factors?.length) setExposure(factors[0].factor);
  }, [factors, exposure]);

  // The BRD makes this method conditional on a control population existing.
  // Saying so plainly — and naming what a control would be — is more useful
  // than a disabled button with no explanation.
  if (!controls.length) {
    return (
      <Alert variant="warning">
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle>No control population is available</AlertTitle>
        <AlertDescription>
          <p className="mt-1">
            The BRD makes statistical risk modelling conditional on{' '}
            <em>“the availability of control such as non-fatal crashes.”</em> No cohort in this
            environment is designated CONTROL, so no risk model can be computed.
          </p>
          <p className="mt-2">
            Define a cohort over a comparison population — non-fatal crashes, or crashes classified
            out of the Phase 1 study — and set its role to CONTROL.
          </p>
        </AlertDescription>
      </Alert>
    );
  }

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setResult(
        await analysisStatsApi.riskModel({
          case_cohort_id: cohort.id,
          control_cohort_id: controlId,
          exposure_factor: exposure,
        }),
      );
    } catch (e) {
      setResult(null);
      setError(e as Error);
    } finally {
      setRunning(false);
    }
  }

  const t = result?.table;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-56">
          <Label>Case cohort</Label>
          <Input value={cohort.name} readOnly className="bg-muted/40" />
        </div>
        <div className="w-56">
          <Label htmlFor="risk-control">Control cohort</Label>
          <Select id="risk-control" value={controlId} onChange={(e) => setControlId(e.target.value)}>
            {controls.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({formatNumber(c.member_count ?? 0)})
              </option>
            ))}
          </Select>
        </div>
        <div className="w-64">
          <Label htmlFor="risk-exposure">Exposure (contributing factor)</Label>
          <Select id="risk-exposure" value={exposure} onChange={(e) => setExposure(e.target.value)}>
            {(factors ?? []).map((f) => (
              <option key={f.factor} value={f.factor}>
                {f.factor} ({f.crashes})
              </option>
            ))}
          </Select>
        </div>
        <Button onClick={run} disabled={running || !controlId || !exposure}>
          {running ? (
            <RefreshCw className="mr-1.5 h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Play className="mr-1.5 h-4 w-4" aria-hidden />
          )}
          Run risk model
        </Button>
      </div>

      <RunError error={error} />

      {result && t ? (
        <>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Contingency table</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Population</TableHead>
                  <TableHead className="text-right">Exposed</TableHead>
                  <TableHead className="text-right">Unexposed</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-right">Exposure rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">
                    Cases — {result.case_cohort?.name ?? cohort.name}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{t.case_exposed}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.case_unexposed}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.case_total}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {result.case_exposure_rate == null
                      ? '—'
                      : `${(result.case_exposure_rate * 100).toFixed(1)}%`}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">
                    Controls — {result.control_cohort?.name ?? ''}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{t.control_exposed}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.control_unexposed}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.control_total}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {result.control_exposure_rate == null
                      ? '—'
                      : `${(result.control_exposure_rate * 100).toFixed(1)}%`}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>

          {result.odds_ratio != null ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold">Risk estimates</h3>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                <Metric
                  label="Odds ratio"
                  value={num(result.odds_ratio, 3)}
                  hint={`${Math.round(result.confidence * 100)}% CI ${num(
                    result.odds_ratio_ci_lower,
                    3,
                  )} – ${num(result.odds_ratio_ci_upper, 3)}`}
                />
                <Metric
                  label="Relative risk"
                  value={num(result.relative_risk, 3)}
                  hint={`CI ${num(result.relative_risk_ci_lower, 3)} – ${num(
                    result.relative_risk_ci_upper,
                    3,
                  )}`}
                />
                <Metric
                  label="Risk difference"
                  value={num(result.risk_difference, 4)}
                  hint={`CI ${num(result.risk_difference_ci_lower, 4)} – ${num(
                    result.risk_difference_ci_upper,
                    4,
                  )}`}
                />
                <Metric
                  label="Attributable fraction (exposed)"
                  value={
                    result.attributable_fraction_exposed == null
                      ? '—'
                      : `${(result.attributable_fraction_exposed * 100).toFixed(1)}%`
                  }
                />
                <Metric
                  label="p-value"
                  value={pValue(result.p_value)}
                  hint={
                    result.test_used === 'FISHER_EXACT'
                      ? "Fisher's exact test"
                      : 'Chi-square with Yates correction'
                  }
                />
                <Metric
                  label="Significant"
                  value={result.significant ? 'Yes' : 'No'}
                  hint={`smallest expected cell ${num(result.min_expected_cell, 2)}`}
                />
              </div>
            </div>
          ) : null}

          <Caveats items={result.caveats} />
          {result.case_cohort && result.control_cohort ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Cases from {result.case_cohort.code} v{result.case_cohort.version_no}; controls from{' '}
              {result.control_cohort.code} v{result.control_cohort.version_no}, materialized{' '}
              {formatDateTime(result.control_cohort.materialized_at)}.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/* ══════════════════════════ Comparative ══════════════════════════ */

function CompareTab({
  cohort,
  cohorts,
  variables,
}: {
  cohort: AnalysisCohort;
  cohorts: AnalysisCohort[];
  variables: Record<string, string>;
}) {
  const others = cohorts.filter((c) => c.id !== cohort.id);
  const [otherId, setOtherId] = React.useState('');
  const [mode, setMode] = React.useState<'variable' | 'factor'>('variable');
  const [variable, setVariable] = React.useState('num_fatalities');
  const [factor, setFactor] = React.useState('');
  const [result, setResult] = React.useState<ComparativeResult | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [running, setRunning] = React.useState(false);

  const { data: factors } = useApi(() => analysisStatsApi.factors(), []);

  React.useEffect(() => {
    if (!otherId && others.length) setOtherId(others[0].id);
  }, [others, otherId]);
  React.useEffect(() => {
    if (!factor && factors?.length) setFactor(factors[0].factor);
  }, [factors, factor]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setResult(
        await analysisStatsApi.compare({
          cohort_a_id: cohort.id,
          cohort_b_id: otherId,
          ...(mode === 'variable' ? { variable } : { factor }),
        }),
      );
    } catch (e) {
      setResult(null);
      setError(e as Error);
    } finally {
      setRunning(false);
    }
  }

  if (!others.length) {
    return (
      <EmptyState
        icon={GitCompare}
        title="Nothing to compare against"
        description="Comparative analysis needs a second cohort. Define another population to compare this one with."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-52">
          <Label>Cohort A</Label>
          <Input value={cohort.name} readOnly className="bg-muted/40" />
        </div>
        <div className="w-52">
          <Label htmlFor="cmp-b">Cohort B</Label>
          <Select id="cmp-b" value={otherId} onChange={(e) => setOtherId(e.target.value)}>
            {others.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({formatNumber(c.member_count ?? 0)})
              </option>
            ))}
          </Select>
        </div>
        <div className="w-40">
          <Label htmlFor="cmp-mode">Compare</Label>
          <Select
            id="cmp-mode"
            value={mode}
            onChange={(e) => setMode(e.target.value as 'variable' | 'factor')}
          >
            <option value="variable">A measurement</option>
            <option value="factor">Factor prevalence</option>
          </Select>
        </div>
        {mode === 'variable' ? (
          <div className="w-52">
            <Label htmlFor="cmp-var">Variable</Label>
            <Select id="cmp-var" value={variable} onChange={(e) => setVariable(e.target.value)}>
              {Object.keys(variables).map((n) => (
                <option key={n} value={n}>
                  {variables[n]}
                </option>
              ))}
            </Select>
          </div>
        ) : (
          <div className="w-60">
            <Label htmlFor="cmp-factor">Contributing factor</Label>
            <Select id="cmp-factor" value={factor} onChange={(e) => setFactor(e.target.value)}>
              {(factors ?? []).map((f) => (
                <option key={f.factor} value={f.factor}>
                  {f.factor}
                </option>
              ))}
            </Select>
          </div>
        )}
        <Button onClick={run} disabled={running || !otherId}>
          {running ? (
            <RefreshCw className="mr-1.5 h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Play className="mr-1.5 h-4 w-4" aria-hidden />
          )}
          Compare
        </Button>
      </div>

      <RunError error={error} />

      {result ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cohort</TableHead>
                <TableHead className="text-right">n</TableHead>
                {result.variable ? (
                  <>
                    <TableHead className="text-right">Mean</TableHead>
                    <TableHead className="text-right">Median</TableHead>
                    <TableHead className="text-right">Std. dev.</TableHead>
                  </>
                ) : (
                  <>
                    <TableHead className="text-right">With factor</TableHead>
                    <TableHead className="text-right">Prevalence</TableHead>
                  </>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {[result.cohort_a, result.cohort_b].map((side, i) => (
                <TableRow key={side.id ?? i}>
                  <TableCell className="font-medium">{side.name ?? (i ? 'B' : 'A')}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(side.n)}</TableCell>
                  {result.variable ? (
                    <>
                      <TableCell className="text-right tabular-nums">{num(side.mean)}</TableCell>
                      <TableCell className="text-right tabular-nums">{num(side.median)}</TableCell>
                      <TableCell className="text-right tabular-nums">{num(side.stddev)}</TableCell>
                    </>
                  ) : (
                    <>
                      <TableCell className="text-right tabular-nums">{side.count ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {side.proportion == null ? '—' : `${(side.proportion * 100).toFixed(1)}%`}
                      </TableCell>
                    </>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Difference"
              value={num(result.mean_difference ?? result.difference)}
              hint={
                result.difference_ci_lower == null
                  ? undefined
                  : `CI ${num(result.difference_ci_lower)} – ${num(result.difference_ci_upper)}`
              }
            />
            <Metric
              label={result.test_used === 'WELCH_T' ? 't statistic' : 'z statistic'}
              value={num(result.t_statistic ?? result.z_statistic, 3)}
              hint={
                result.degrees_of_freedom == null
                  ? undefined
                  : `df ${num(result.degrees_of_freedom, 2)}`
              }
            />
            <Metric
              label="p-value"
              value={pValue(result.p_value)}
              hint={result.test_used === 'WELCH_T' ? "Welch's t-test" : 'Two-proportion z-test'}
            />
            <Metric
              label={result.cohens_d != null ? "Effect size (Cohen's d)" : 'Significant'}
              value={
                result.cohens_d != null ? num(result.cohens_d, 3) : result.significant ? 'Yes' : 'No'
              }
              hint={result.effect_size_magnitude}
            />
          </div>

          <Caveats items={result.caveats} />
        </>
      ) : null}
    </div>
  );
}

/* ══════════════════════════ Saved investigations ══════════════════════════ */

const METHOD_ICON: Record<string, typeof Sigma> = {
  DESCRIPTIVE: Sigma,
  DISTRIBUTION: BarChart3,
  THEMATIC: Network,
  RISK_MODEL: Target,
  COMPARATIVE: GitCompare,
  TREND: TrendingUp,
};

function SavedTab({ canManage }: { canManage: boolean }) {
  const { data, loading, reload } = useApi(() => analysisStatsApi.investigations(), []);
  const [output, setOutput] = React.useState<{ id: string; text: string } | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [running, setRunning] = React.useState<string | null>(null);

  async function run(id: string) {
    setRunning(id);
    setError(null);
    try {
      const result = await analysisStatsApi.runInvestigation(id);
      setOutput({ id, text: summarize(result) });
    } catch (e) {
      setOutput(null);
      setError(e as Error);
    } finally {
      setRunning(null);
    }
  }

  async function remove(id: string) {
    await analysisStatsApi.deleteInvestigation(id);
    reload();
  }

  const active = (data ?? []).filter((i) => i.status === 'ACTIVE');

  if (loading) return <Skeleton className="h-48 w-full" />;
  if (!active.length) {
    return (
      <EmptyState
        icon={Play}
        title="No saved investigations"
        description="A saved investigation stores a method and its parameters so the same question can be asked of newer data. Results are recomputed on each run, never replayed."
      />
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        A saved investigation stores the method and its parameters, not a frozen result — running it
        again re-computes against the current cohort version, so the answer may legitimately differ
        from the last run.
      </p>
      <RunError error={error} />
      {active.map((inv) => {
        const Icon = METHOD_ICON[inv.method] ?? Sigma;
        return (
          <div key={inv.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-federal-blue" aria-hidden />
                  <span className="text-sm font-medium">{inv.name}</span>
                  <Badge variant="outline" size="sm">
                    {inv.method.replace(/_/g, ' ')}
                  </Badge>
                  {inv.visibility === 'PRIVATE' ? (
                    <Badge variant="outline" size="sm" className="bg-muted">
                      Private
                    </Badge>
                  ) : null}
                </div>
                {inv.description ? (
                  <p className="mt-1 text-xs text-muted-foreground">{inv.description}</p>
                ) : null}
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {inv.code}
                  {inv.last_run_at ? ` · last run ${relativeTime(inv.last_run_at)}` : ' · never run'}
                </p>
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" disabled={running === inv.id} onClick={() => run(inv.id)}>
                  {running === inv.id ? (
                    <RefreshCw className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Play className="mr-1 h-3.5 w-3.5" aria-hidden />
                  )}
                  Run
                </Button>
                {canManage ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Archive ${inv.name}`}
                    onClick={() => remove(inv.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </Button>
                ) : null}
              </div>
            </div>
            {output?.id === inv.id ? (
              <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                {output.text}
              </pre>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Render a run result as text.
 *
 * Each method returns a different shape, and a saved-investigation list is not
 * the place to re-implement six result views — the dedicated tabs already do
 * that. What matters here is that the headline numbers and every caveat are
 * legible, so a saved run cannot present a figure without its conditions.
 */
function summarize(result: unknown): string {
  const r = result as Record<string, unknown>;
  const lines: string[] = [];
  const push = (label: string, value: unknown, digits = 4) => {
    if (value === undefined || value === null) return;
    lines.push(
      `${label.padEnd(28)}${typeof value === 'number' ? num(value, digits) : String(value)}`,
    );
  };

  if (r.cohort_name) lines.push(`Cohort: ${r.cohort_name} (v${r.version_no})`);
  if (r.case_cohort && r.control_cohort) {
    const c = r.case_cohort as Record<string, unknown>;
    const k = r.control_cohort as Record<string, unknown>;
    lines.push(`Cases:    ${c.name} v${c.version_no}`);
    lines.push(`Controls: ${k.name} v${k.version_no}`);
  }
  if (lines.length) lines.push('');

  for (const key of [
    'n', 'mean', 'median', 'mode', 'stddev', 'variance', 'skewness', 'kurtosis_excess',
    'distinct_categories', 'coded_percent', 'n_with_factors',
    'odds_ratio', 'odds_ratio_ci_lower', 'odds_ratio_ci_upper', 'relative_risk',
    'risk_difference', 'mean_difference', 'difference', 't_statistic', 'z_statistic',
    'degrees_of_freedom', 'cohens_d', 'slope', 'r_squared', 'pearson_r', 'n_periods',
    'test_used', 'significant',
  ]) {
    if (key in r) push(key.replace(/_/g, ' '), r[key]);
  }
  if ('p_value' in r) lines.push(`${'p value'.padEnd(28)}${pValue(r.p_value as number)}`);

  const themes = r.themes as { factor: string; crashes: number }[] | undefined;
  if (themes?.length) {
    lines.push('', 'Top themes:');
    themes.slice(0, 8).forEach((t) => lines.push(`  ${t.factor.padEnd(42)} ${t.crashes}`));
  }
  const entries = r.entries as { category: string; frequency: number; percent: number }[] | undefined;
  if (entries?.length) {
    lines.push('', 'Distribution:');
    entries.slice(0, 10).forEach((e) =>
      lines.push(`  ${e.category.padEnd(28)} ${String(e.frequency).padStart(5)}  ${e.percent.toFixed(1)}%`),
    );
  }

  const caveats = r.caveats as string[] | undefined;
  if (caveats?.length) {
    lines.push('', 'Notes on interpretation:');
    caveats.forEach((c) => lines.push(`  • ${c}`));
  }
  return lines.join('\n');
}

/* ══════════════════════════ Export ══════════════════════════ */

/**
 * Export to the statistical tools the BRD names (p. 17).
 *
 * The generated loader script and the CSV it reads are downloaded under names
 * that agree — the script hard-codes `<code>_v<version>.csv`, so saving the CSV
 * under anything else would leave the analyst with a script that cannot find
 * its data.
 */
function ExportMenu({ cohort }: { cohort: AnalysisCohort }) {
  const [busy, setBusy] = React.useState<StatExportFormat | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const formats: { key: StatExportFormat; label: string; ext: string; mime: string }[] = [
    { key: 'CSV', label: 'CSV', ext: 'csv', mime: 'text/csv;charset=utf-8' },
    { key: 'PYTHON', label: 'Python', ext: 'py', mime: 'text/x-python;charset=utf-8' },
    { key: 'R', label: 'R', ext: 'R', mime: 'text/plain;charset=utf-8' },
    { key: 'SAS', label: 'SAS', ext: 'sas', mime: 'text/plain;charset=utf-8' },
  ];

  async function download(format: StatExportFormat, ext: string, mime: string) {
    setBusy(format);
    setError(null);
    try {
      const body = await analysisStatsApi.exportData(cohort.id, format);
      const text = typeof body === 'string' ? body : JSON.stringify(body, null, 2);
      const url = URL.createObjectURL(new Blob([text], { type: mime }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${cohort.code.toLowerCase()}_v${cohort.version_no ?? 1}.${ext}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Export failed');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-muted-foreground">Export:</span>
      {formats.map((f) => (
        <Button
          key={f.key}
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
          disabled={busy !== null || cohort.current_version_id == null}
          onClick={() => download(f.key, f.ext, f.mime)}
        >
          <Download className="mr-1 h-3 w-3" aria-hidden />
          {busy === f.key ? '…' : f.label}
        </Button>
      ))}
      {error ? <span className="text-xs text-alert-red">{error}</span> : null}
    </div>
  );
}

/* ══════════════════════════ New cohort ══════════════════════════ */

function NewCohortDialog({
  environmentId,
  fields,
  onClose,
  onCreated,
}: {
  environmentId: string;
  fields?: { filter_columns: string[]; filter_operators: string[]; cohort_roles: CohortRole[] };
  onClose: () => void;
  onCreated: () => void;
}) {
  const [code, setCode] = React.useState('');
  const [name, setName] = React.useState('');
  const [role, setRole] = React.useState<CohortRole>('GENERAL');
  const [filters, setFilters] = React.useState<
    { column: string; op: string; value: string }[]
  >([{ column: 'state_code', op: 'eq', value: '' }]);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const columns = fields?.filter_columns ?? [];
  const operators = fields?.filter_operators ?? ['eq', 'neq', 'gte', 'lte'];

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await analysisStatsApi.createCohort({
        environment_id: environmentId,
        code: code.trim().toUpperCase().replace(/\s+/g, '_'),
        name: name.trim(),
        cohort_role: role,
        definition: {
          filters: filters
            .filter((f) => f.value !== '')
            .map((f) => ({
              column: f.column,
              op: f.op,
              // Numeric-looking values are sent as numbers so `gte 1` compares
              // numerically rather than lexically ("10" < "2" as text).
              value: /^-?\d+(\.\d+)?$/.test(f.value) ? Number(f.value) : f.value,
            })),
        },
      });
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <form
        onSubmit={submit}
        className="relative z-10 max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-lg border border-border bg-card p-5 shadow-lg"
      >
        <h2 className="text-base font-semibold">New cohort</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          A cohort is a saved population of crashes, materialized as a versioned snapshot. Mark it
          CONTROL to make it available as a risk-model comparison population.
        </p>

        <div className="mt-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="nc-code">Code</Label>
              <Input
                id="nc-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="KS_NONFATAL"
                required
              />
            </div>
            <div>
              <Label htmlFor="nc-role">Role</Label>
              <Select
                id="nc-role"
                value={role}
                onChange={(e) => setRole(e.target.value as CohortRole)}
              >
                {(fields?.cohort_roles ?? ['CASE', 'CONTROL', 'GENERAL']).map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div>
            <Label htmlFor="nc-name">Name</Label>
            <Input
              id="nc-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Kansas non-fatal crashes"
              required
            />
          </div>

          <div>
            <Label>Filters</Label>
            <p className="mb-2 text-[11px] text-muted-foreground">
              All filters are combined with AND. Leave a value blank to drop that row.
            </p>
            <div className="space-y-2">
              {filters.map((f, i) => (
                <div key={i} className="flex gap-1.5">
                  <Select
                    aria-label="Filter column"
                    value={f.column}
                    onChange={(e) => {
                      const next = [...filters];
                      next[i] = { ...next[i], column: e.target.value };
                      setFilters(next);
                    }}
                    className="flex-1"
                  >
                    {columns.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </Select>
                  <Select
                    aria-label="Filter operator"
                    value={f.op}
                    onChange={(e) => {
                      const next = [...filters];
                      next[i] = { ...next[i], op: e.target.value };
                      setFilters(next);
                    }}
                    className="w-24"
                  >
                    {operators.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </Select>
                  <Input
                    aria-label="Filter value"
                    value={f.value}
                    onChange={(e) => {
                      const next = [...filters];
                      next[i] = { ...next[i], value: e.target.value };
                      setFilters(next);
                    }}
                    placeholder="value"
                    className="flex-1"
                  />
                </div>
              ))}
            </div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="mt-2"
              onClick={() => setFilters([...filters, { column: 'state_code', op: 'eq', value: '' }])}
            >
              <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
              Add filter
            </Button>
          </div>

          {error ? (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Creating…' : 'Create cohort'}
          </Button>
        </div>
      </form>
    </div>
  );
}
