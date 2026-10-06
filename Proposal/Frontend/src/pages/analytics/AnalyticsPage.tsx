import * as React from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, FlaskConical, LayoutDashboard, MapPin, Play, Skull, TrendingUp, Wrench } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { QueryBarsCard, QueryDonutCard } from '@/components/dashboards/shared';
import { GeoMap } from '@/components/charts/GeoMap';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { HeatmapMatrix, LineChart } from '@/components/charts';
import { DashboardRenderer } from '@/components/dashboards/DashboardRenderer';
import { useApi } from '@/lib/useApi';
import { analyticsApi } from '@/lib/endpoints';
import { humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type { GeoCrashPoint, QueryResult, Report } from '@/lib/types';

export function AnalyticsPage() {
  const { user } = useAuth();
  const canQuery = hasPermission(user, 'analytics:query');

  const { data, loading } = useApi(async () => {
    if (!canQuery) return null;
    const [byState, byPhase, fatalities, qc] = await Promise.all([
      analyticsApi.runQuery('crash_counts_by_state').catch(() => undefined),
      analyticsApi.runQuery('crash_counts_by_phase').catch(() => undefined),
      analyticsApi.runQuery('fatalities_by_state').catch(() => undefined),
      analyticsApi.runQuery('qc_failure_summary').catch(() => undefined),
    ]);
    return { byState, byPhase, fatalities, qc };
  }, [canQuery]);

  const { data: dashboards, loading: dLoading } = useApi(() => analyticsApi.dashboards().catch(() => []), []);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Analysis & Reporting" icon={FlaskConical} title="Analytics" subtitle="Causal-factor and program analytics over the CCFP data lake." />

      {canQuery ? (
        <>
          <div className="grid items-stretch gap-4 lg:grid-cols-2">
            <QueryBarsCard title="Crashes by State" icon={MapPin} result={data?.byState} labelKey="state_code" valueKey="count" loading={loading} />
            <QueryDonutCard title="Crashes by lifecycle phase" icon={TrendingUp} result={data?.byPhase} labelKey="lifecycle_phase" valueKey="count" loading={loading} centerLabel="CRASHES" mapLabel={humanize} />
            <QueryBarsCard title="Fatalities by State" icon={Skull} result={data?.fatalities} labelKey="state_code" valueKey="fatalities" loading={loading} />
            <QueryBarsCard title="QC failures by rule" icon={CheckCircle2} result={data?.qc} labelKey="rule_code" valueKey="failures" loading={loading} />
          </div>

          <GeoMapCard />
          <TrendCard />
          {/* BRD p.15 names "maps, charts, tables, time-series, geospatial layers,
              and interactive filters". Maps/charts/time-series/filters are above;
              these two close the list: a thematic matrix and a tabular view of the
              same results, so a number can be read exactly rather than estimated
              off an axis. Both are driven by the queries already fetched — no
              extra round-trip. */}
          <ThematicMatrixCard byState={data?.byState} fatalities={data?.fatalities} loading={loading} />
          <QueryTableCard
            title="Crashes by State"
            result={data?.byState}
            loading={loading}
            caption="The same result as the chart above, exact rather than estimated off an axis."
          />
          <QueryBuilderCard />
        </>
      ) : (
        <EmptyState icon={FlaskConical} title="No analytics access" description="You don't have permission to run analytical queries." />
      )}

      <Card>
        <CardHeader><CardHeading icon={LayoutDashboard} title="Dashboards" description="Saved dashboards visible to you. Expand a dashboard to render its composed panels." /></CardHeader>
        <CardContent>
          {dLoading ? <Skeleton className="h-20 w-full" /> : (dashboards?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">No dashboards available.</p>
          ) : (
            <ul className="space-y-2">
              {dashboards!.map((d) => (
                <DashboardListItem key={d.id} dashboard={d} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * One row in the Dashboards card. Collapsed it shows the name + visibility;
 * expanded it loads the validated panel definition via
 * `analyticsApi.dashboard(id)` and renders the panels with `DashboardRenderer`
 * (ANAL-7, documentation §8.9).
 */
function DashboardListItem({ dashboard }: { dashboard: Report }) {
  const [open, setOpen] = React.useState(false);
  const { data: detail, loading, error } = useApi(
    () => (open ? analyticsApi.dashboard(dashboard.id) : Promise.resolve(undefined)),
    [open, dashboard.id],
  );

  return (
    <li className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-muted/40"
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          <span className="text-sm font-medium">{dashboard.name}</span>
        </span>
        <Badge variant="info" size="sm">{humanize(dashboard.visibility)}</Badge>
      </button>
      {open && (
        <div className="border-t border-border p-3">
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : error ? (
            <p className="text-sm text-alert-red-700">Could not load this dashboard.</p>
          ) : (
            <DashboardRenderer report={detail} />
          )}
        </div>
      )}
    </li>
  );
}

/**
 * Constrained ad-hoc query builder (ANAL-6, documentation §8.9 / §14).
 * Group-by / aggregation / filter options come from the server allow-list
 * (`/analytics/query-builder/fields`) so the form never hardcodes the columns;
 * the server re-validates every field, so no free-form SQL is possible.
 */
function QueryBuilderCard() {
  const { data: fields } = useApi(() => analyticsApi.queryBuilderFields(), []);

  const [groupBy, setGroupBy] = React.useState('');
  const [aggregation, setAggregation] = React.useState('count');
  const [filterColumn, setFilterColumn] = React.useState('');
  const [filterOp, setFilterOp] = React.useState('eq');
  const [filterValue, setFilterValue] = React.useState('');

  const [result, setResult] = React.useState<QueryResult | undefined>();
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Default the group-by to the first allow-listed dimension once fields load.
  React.useEffect(() => {
    if (fields && !groupBy && fields.group_by.length > 0) setGroupBy(fields.group_by[0]);
  }, [fields, groupBy]);

  const run = async () => {
    if (!groupBy) return;
    setRunning(true);
    setError(null);
    try {
      const filters =
        filterColumn && filterValue !== ''
          ? [{ column: filterColumn, op: filterOp, value: filterValue }]
          : [];
      const res = await analyticsApi.runQueryBuilder({ group_by: groupBy, aggregation, filters });
      setResult(res);
    } catch (e) {
      setResult(undefined);
      setError(e instanceof Error ? e.message : 'Query failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Wrench} title="Build a query" description="Compose a constrained ad-hoc aggregation over whitelisted crash columns. State scope is enforced server-side." />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="qb-group-by">Group by</Label>
            <Select id="qb-group-by" value={groupBy} onChange={(e) => setGroupBy(e.target.value)} disabled={!fields}>
              {(fields?.group_by ?? []).map((c) => (
                <option key={c} value={c}>{humanize(c)}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="qb-aggregation">Aggregation</Label>
            <Select id="qb-aggregation" value={aggregation} onChange={(e) => setAggregation(e.target.value)} disabled={!fields}>
              {(fields?.aggregations ?? []).map((a) => (
                <option key={a} value={a}>{humanize(a)}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="qb-filter-col">Filter column (optional)</Label>
            <Select id="qb-filter-col" value={filterColumn} onChange={(e) => setFilterColumn(e.target.value)} disabled={!fields}>
              <option value="">— none —</option>
              {(fields?.filter_columns ?? []).map((c) => (
                <option key={c} value={c}>{humanize(c)}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="qb-filter-val">Filter value</Label>
            <div className="flex gap-2">
              <Select id="qb-filter-op" className="w-24" value={filterOp} onChange={(e) => setFilterOp(e.target.value)} disabled={!fields || !filterColumn}>
                {(fields?.operators ?? []).map((op) => (
                  <option key={op} value={op}>{op}</option>
                ))}
              </Select>
              <Input id="qb-filter-val" value={filterValue} onChange={(e) => setFilterValue(e.target.value)} placeholder="value" disabled={!filterColumn} />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={run} disabled={!groupBy || running}>
            <Play className="h-4 w-4" />
            {running ? 'Running…' : 'Run query'}
          </Button>
          {error && <span className="text-sm text-alert-red-700">{error}</span>}
        </div>

        {result && (
          <div className="grid items-stretch gap-4 lg:grid-cols-2">
            <QueryBarsCard
              title={`${humanize(result.columns[1] ?? aggregation)} by ${humanize(result.columns[0] ?? groupBy)}`}
              icon={TrendingUp}
              result={result}
              labelKey={result.columns[0]}
              valueKey={result.columns[1]}
              mapLabel={humanize}
            />
            <Card className="flex flex-col">
              <CardHeader>
                <CardHeading icon={LayoutDashboard} title="Results" description={`${result.rows.length} group(s).`} />
              </CardHeader>
              <CardContent className="flex min-h-0 flex-1 flex-col">
                {result.rows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No data.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-muted-foreground">
                          {result.columns.map((c) => (
                            <th key={c} className="py-1.5 pr-4 font-medium">{humanize(c)}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.map((row, i) => (
                          <tr key={i} className="border-b border-border/50">
                            {result.columns.map((c) => (
                              <td key={c} className="py-1.5 pr-4 tabular-nums">{String(row[c] ?? '—')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Geospatial view (GAP-BRD-11). The BRD requires maps and geospatial layers;
 * the application had neither, and crash latitude/longitude — already captured
 * and editable — were never plotted at all.
 *
 * Toggling individual crash points on top of the State aggregate is the
 * drill-down the BRD asks for: totals answer "where is the burden", points
 * answer "which crashes make it up".
 */
/**
 * Thematic matrix (BRD p.15 "thematic analysis" / visualization types).
 *
 * Crashes and fatalities per State side by side. A matrix rather than two bar
 * charts because the question it answers — where is the fatality rate out of
 * step with the crash count — is a comparison across the row, which two
 * separately-scaled charts make the reader do by eye.
 */
function ThematicMatrixCard({
  byState,
  fatalities,
  loading,
}: {
  byState?: QueryResult;
  fatalities?: QueryResult;
  loading: boolean;
}) {
  const matrix = React.useMemo(() => {
    const crashes = new Map<string, number>();
    for (const r of byState?.rows ?? []) {
      const k = String((r as Record<string, unknown>).state_code ?? '');
      if (k) crashes.set(k, Number((r as Record<string, unknown>).count ?? 0));
    }
    const fatal = new Map<string, number>();
    for (const r of fatalities?.rows ?? []) {
      const k = String((r as Record<string, unknown>).state_code ?? '');
      if (k) fatal.set(k, Number((r as Record<string, unknown>).fatalities ?? 0));
    }
    // Busiest States first; capped so the matrix stays readable rather than
    // becoming a wall of every jurisdiction.
    const states = [...crashes.keys()].sort((a, b) => (crashes.get(b) ?? 0) - (crashes.get(a) ?? 0)).slice(0, 12);
    return {
      states,
      rows: [states.map((s) => crashes.get(s) ?? 0), states.map((s) => fatal.get(s) ?? 0)],
    };
  }, [byState, fatalities]);

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={LayoutDashboard}
          title="Thematic matrix — crashes and fatalities by State"
          description="Cross-tab of the two measures per State (documentation: thematic analysis)."
        />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-40 w-full" />
        ) : matrix.states.length === 0 ? (
          <p className="text-sm text-muted-foreground">No State results available.</p>
        ) : (
          <HeatmapMatrix
            rows={matrix.rows}
            rowLabels={['Crashes', 'Fatalities']}
            columnLabels={matrix.states}
            hint={(row, col, value) => `${col} — ${row}: ${value}`}
          />
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Tabular view of a query result (BRD p.15 explicitly names "tables").
 *
 * Charts answer "what is the shape"; a table answers "what is the number". The
 * BRD lists both, and downloads/exports are built from tabular data, so the UI
 * should be able to show it directly rather than only as a plot.
 */
function QueryTableCard({
  title,
  result,
  loading,
  caption,
}: {
  title: string;
  result?: QueryResult;
  loading: boolean;
  caption?: string;
}) {
  const rows = (result?.rows ?? []) as Record<string, unknown>[];
  const columns = React.useMemo(
    () => (rows.length ? Object.keys(rows[0]) : []),
    [rows],
  );

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={TrendingUp} title={`${title} — table`} description={caption} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-5"><Skeleton className="h-24 w-full" /></div>
        ) : rows.length === 0 ? (
          <p className="p-5 text-sm text-muted-foreground">No rows returned.</p>
        ) : (
          // Wide results scroll inside the card rather than pushing the page sideways.
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {columns.map((c, i) => (
                    <TableHead key={c} className={i === 0 ? 'pl-5' : undefined}>{humanize(c)}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, ri) => (
                  <TableRow key={ri}>
                    {columns.map((c, i) => (
                      <TableCell key={c} className={i === 0 ? 'pl-5 font-medium' : undefined}>
                        {r[c] === null || r[c] === undefined ? '—' : String(r[c])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GeoMapCard() {
  const [showPoints, setShowPoints] = React.useState(false);
  const { data: byState, loading: sLoading } = useApi(
    () => analyticsApi.runQuery('crash_counts_by_state').catch(() => undefined), [],
  );
  const { data: geo, loading: gLoading } = useApi(
    () => analyticsApi.geoCrashes({ limit: 2000 }).catch(() => undefined), [],
  );

  const data = (byState?.rows ?? []).map((r) => ({
    key: String(r.state_code ?? ''),
    label: String(r.state_code ?? ''),
    value: Number(r.count ?? 0),
  })).filter((d) => d.key);

  const points = (geo?.points ?? []).map((p: GeoCrashPoint) => ({
    id: p.id,
    label: p.ccfp_identifier,
    latitude: p.latitude,
    longitude: p.longitude,
    value: p.num_fatalities,
    sublabel: p.state_code,
  }));

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={MapPin}
          title="Crash geography"
          description="Crash burden by State, with individual crash locations plotted from recorded coordinates."
          actions={
            <Button size="sm" variant={showPoints ? 'default' : 'outline'} onClick={() => setShowPoints((v) => !v)}>
              {showPoints ? 'Hide' : 'Show'} crash locations
            </Button>
          }
        />
      </CardHeader>
      <CardContent className="space-y-3">
        {sLoading || gLoading ? (
          <Skeleton className="h-80 w-full" />
        ) : data.length === 0 ? (
          <EmptyState icon={MapPin} title="No crash data to map" />
        ) : (
          <>
            <GeoMap data={data} points={points} showPoints={showPoints} valueLabel="Crashes" />
            {/* State the coverage rather than letting an incomplete map imply completeness. */}
            {geo ? (
              <p className="text-xs text-muted-foreground">
                {geo.plotted} of {geo.total_in_scope} crashes in scope have recorded coordinates
                {geo.missing_coordinates > 0 ? ` — ${geo.missing_coordinates} cannot be plotted` : ''}.
              </p>
            ) : null}
            {/* Table view: identity and magnitude are never colour-alone. */}
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                View as table
              </summary>
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                    <th className="py-1">State</th><th className="py-1 text-right">Crashes</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data].sort((a, b) => b.value - a.value).map((d) => (
                    <tr key={d.key} className="border-b border-border/50">
                      <td className="py-1">{d.key}</td>
                      <td className="py-1 text-right tabular-nums">{d.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Time-series (GAP-BRD-11). `crash_date` was filterable but not groupable, so
 * "crashes over time" could not be expressed at all. The grouping key is a real
 * truncated date from SQL, so it sorts chronologically — a formatted string
 * would sort "April" before "January".
 */
function TrendCard() {
  const [grain, setGrain] = React.useState('crash_month');
  const [measure, setMeasure] = React.useState('count');
  const { data, loading } = useApi(
    () => analyticsApi.runQueryBuilder({ group_by: grain, aggregation: measure }).catch(() => undefined),
    [grain, measure],
  );

  // The server returns a plain `YYYY-MM-DD` (cast to DATE precisely so no UTC
  // offset rides along). Parse the parts directly rather than via `new Date()`,
  // which would interpret a bare date as UTC midnight and shift the label back a
  // day for any viewer west of Greenwich.
  const points = (data?.rows ?? []).flatMap((r) => {
    const raw = String(r[grain] ?? '');
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
    // Crashes with no recorded date group to an empty key. Dropping them
    // silently would understate the series; they are surfaced in a note below
    // instead of being drawn as a nameless point at the start of the axis.
    if (!m) return [];
    const [, y, mo, day] = m;
    const d = new Date(Date.UTC(Number(y), Number(mo) - 1, Number(day)));
    const label =
      grain === 'crash_year'
        ? y
        : grain === 'crash_quarter'
          ? `Q${Math.floor((Number(mo) - 1) / 3) + 1} ${y.slice(2)}`
          : grain === 'crash_month'
            ? d.toLocaleDateString(undefined, { month: 'short', year: '2-digit', timeZone: 'UTC' })
            : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
    return [{ x: label, y: Number(r[measure] ?? 0) }];
  });

  const undated = (data?.rows ?? []).filter((r) => !/^\d{4}-\d{2}-\d{2}/.test(String(r[grain] ?? '')));
  const undatedTotal = undated.reduce((sum, r) => sum + Number(r[measure] ?? 0), 0);

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={TrendingUp}
          title="Trend over time"
          description="Crashes and fatalities over time, grouped by a real date so periods order chronologically."
        />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="trend-grain">Period</Label>
            <Select id="trend-grain" value={grain} onChange={(e) => setGrain(e.target.value)} className="w-44">
              <option value="crash_date">Day</option>
              <option value="crash_month">Month</option>
              <option value="crash_quarter">Quarter</option>
              <option value="crash_year">Year</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="trend-measure">Measure</Label>
            <Select id="trend-measure" value={measure} onChange={(e) => setMeasure(e.target.value)} className="w-48">
              <option value="count">Crashes</option>
              <option value="sum_fatalities">Fatalities</option>
              <option value="sum_vehicles">Vehicles</option>
              <option value="avg_fatalities">Average fatalities</option>
            </Select>
          </div>
        </div>
        {loading ? (
          <Skeleton className="h-56 w-full" />
        ) : points.length === 0 ? (
          <EmptyState icon={TrendingUp} title="No data for this period" />
        ) : (
          <>
            <LineChart data={points} height={220} yAxisLabel={measure === 'count' ? 'Crashes' : humanize(measure)} />
            {undatedTotal > 0 ? (
              <p className="text-xs text-muted-foreground">
                Excludes {undatedTotal} with no recorded crash date — undated records cannot be
                placed on a timeline.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
