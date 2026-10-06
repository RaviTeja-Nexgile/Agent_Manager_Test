import * as React from 'react';
import {
  Database,
  Download,
  Layers,
  Lock,
  Plus,
  RefreshCw,
  Share2,
  Sigma,
  Table2,
  Trash2,
  Users,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { CardHeading } from '@/components/shell/CardHeading';
import { StatTile } from '@/components/shell/StatTile';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { HorizontalBars } from '@/components/charts';
import { useApi } from '@/lib/useApi';
import { analysisEnvApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { formatDateTime, formatNumber, humanize, relativeTime } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type {
  AnalysisAudience,
  AnalysisDataset,
  AnalysisEnvironment,
  AnalysisPiiLevel,
} from '@/lib/types';

/**
 * CCFP Analysis Environment (GAP-BRD-02).
 *
 * The tier the January 2026 BRD introduces: CCFP Aggregated Data is materialized
 * into the environment as versioned datasets, derived views are built on top of
 * it, and each dataset is shared outward to one of four audiences with different
 * PII rules.
 *
 * Refresh model — opening this page IS the refresh trigger. The backend returns
 * the stored snapshot immediately and, when it has aged past the environment's
 * cadence, starts a refresh in the background. So the page must always be honest
 * about *which* of the two it is showing: every number carries an "as of", a
 * stale snapshot says so rather than passing itself off as current, and while a
 * background refresh is in flight the page polls and updates itself instead of
 * leaving the analyst to guess whether to reload.
 */
export function AnalysisEnvironmentPage() {
  const { user } = useAuth();
  const canManage = hasPermission(user, 'analysis_env:manage');
  const canAuthor = hasPermission(user, 'analysis_env:dataset');
  const canShare = hasPermission(user, 'analysis_env:share');

  const { data: environments, loading: envLoading, reload: reloadEnv } = useApi(
    () => analysisEnvApi.environments(),
    [],
  );
  const environment = environments?.[0];

  const { data: datasets, loading: dsLoading, reload: reloadDatasets } = useApi(
    () => analysisEnvApi.datasets(),
    [],
  );

  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [newOpen, setNewOpen] = React.useState(false);
  const [banner, setBanner] = React.useState<string | null>(null);

  // Default the selection to the first visible dataset, and drop a selection
  // that has gone away (deleted, or a share revoked out from under a State user)
  // so the detail panel can never point at something the list no longer holds.
  React.useEffect(() => {
    if (!datasets?.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !datasets.some((d) => d.id === selectedId)) {
      setSelectedId(datasets[0].id);
    }
  }, [datasets, selectedId]);

  const selected = datasets?.find((d) => d.id === selectedId);

  /**
   * While the backend reports a refresh in flight, poll until it finishes and
   * then reload the datasets so the new row counts appear on their own. Without
   * this the analyst whose page-open triggered the refresh would be the one
   * person who never sees its result.
   */
  const refreshing = environment?.refresh_in_progress ?? false;
  React.useEffect(() => {
    if (!refreshing) return;
    let cancelled = false;
    const id = window.setInterval(async () => {
      try {
        const envs = await analysisEnvApi.environments();
        if (cancelled) return;
        if (!envs[0]?.refresh_in_progress) {
          window.clearInterval(id);
          reloadEnv();
          reloadDatasets();
        }
      } catch {
        // A failed poll is not worth surfacing — the next tick retries, and the
        // snapshot on screen is still valid data either way.
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [refreshing, reloadEnv, reloadDatasets]);

  async function refreshNow() {
    if (!environment) return;
    setBanner(null);
    try {
      const result = await analysisEnvApi.refreshEnvironment(environment.id);
      setBanner(
        result.status === 'SKIPPED'
          ? 'A refresh was already running — its result will appear here shortly.'
          : `${result.message} (${humanize(result.status)})`,
      );
      reloadEnv();
      reloadDatasets();
    } catch (e) {
      setBanner(e instanceof ApiError ? e.message : 'Refresh failed');
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Analysis & Reporting"
        icon={Layers}
        title="Analysis Environment"
        subtitle="CCFP Aggregated Data shared into a managed analysis tier, with derived views, statistics and audience-scoped sharing (BRD — Data Analysis and Sharing)."
        actions={
          canAuthor && environment ? (
            <Button onClick={() => setNewOpen(true)}>
              <Plus className="h-4 w-4" /> New derived view
            </Button>
          ) : null
        }
      />

      {banner ? (
        <div className="rounded-md border border-border bg-muted/40 px-4 py-2 text-sm text-foreground">
          {banner}
        </div>
      ) : null}

      {envLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : !environment ? (
        <EmptyState
          icon={Layers}
          title="No Analysis Environment"
          description="No environment has been provisioned yet."
        />
      ) : (
        <EnvironmentCard
          environment={environment}
          datasetCount={datasets?.length ?? 0}
          canManage={canManage}
          onRefresh={refreshNow}
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <DatasetList
          datasets={datasets}
          loading={dsLoading}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        {selected ? (
          <DatasetDetail
            key={selected.id}
            dataset={selected}
            canShare={canShare}
            canAuthor={canAuthor}
            onChanged={reloadDatasets}
          />
        ) : (
          <Card>
            <CardContent className="p-6">
              <EmptyState
                icon={Database}
                title="No dataset selected"
                description="Choose a dataset to view its rows, statistics and sharing."
              />
            </CardContent>
          </Card>
        )}
      </div>

      {environment ? <RefreshRunsCard environmentId={environment.id} /> : null}

      {newOpen && environment ? (
        <NewDatasetDialog
          environmentId={environment.id}
          onClose={() => setNewOpen(false)}
          onSaved={() => {
            setNewOpen(false);
            reloadDatasets();
          }}
        />
      ) : null}
    </div>
  );
}

// ─────────────── Environment ───────────────

function EnvironmentCard({
  environment,
  datasetCount,
  canManage,
  onRefresh,
}: {
  environment: AnalysisEnvironment;
  datasetCount: number;
  canManage: boolean;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = React.useState(false);

  // Three distinct states, deliberately not collapsed into one: a refresh in
  // flight, a snapshot that has aged past its cadence, and a current snapshot.
  // "Stale" is not an error — the data is valid, just not the latest — so it
  // reads as information rather than a warning.
  const state = environment.refresh_in_progress
    ? { label: 'Refreshing…', variant: 'progress' as const }
    : environment.is_stale
      ? { label: 'Snapshot stale', variant: 'warning' as const }
      : { label: 'Snapshot current', variant: 'success' as const };

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={Layers}
          title={environment.name}
          description={environment.description ?? undefined}
        />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={environment.status === 'ACTIVE' ? 'success' : 'neutral'}>
            {humanize(environment.status)}
          </Badge>
          <Badge variant={state.variant}>{state.label}</Badge>
          <Badge variant="outline">Cadence: {humanize(environment.refresh_cadence)}</Badge>
          {canManage ? (
            <Button
              size="sm"
              variant="outline"
              className="ml-auto"
              disabled={busy || environment.refresh_in_progress}
              onClick={async () => {
                setBusy(true);
                try {
                  await onRefresh();
                } finally {
                  setBusy(false);
                }
              }}
            >
              <RefreshCw
                className={`h-4 w-4 ${environment.refresh_in_progress ? 'animate-spin' : ''}`}
              />
              {environment.refresh_in_progress ? 'Refreshing…' : 'Refresh now'}
            </Button>
          ) : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile icon={Database} label="Datasets" value={formatNumber(datasetCount)} />
          <StatTile
            icon={RefreshCw}
            label="Snapshot as of"
            value={environment.last_refreshed_at ? relativeTime(environment.last_refreshed_at) : 'Never'}
            hint={environment.last_refreshed_at ? formatDateTime(environment.last_refreshed_at) : undefined}
          />
          <StatTile
            icon={Layers}
            label="Refreshes after"
            value={
              environment.refresh_cadence === 'MANUAL'
                ? 'Manual only'
                : environment.next_refresh_due
                  ? relativeTime(environment.next_refresh_due)
                  : 'Next open'
            }
            hint={
              environment.refresh_cadence === 'MANUAL'
                ? 'Only the Refresh now control'
                : 'Refreshed in the background when someone opens this page'
            }
          />
          <StatTile icon={Lock} label="Source data" value="Read-only" hint="Operational records are never modified" />
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────── Dataset list ───────────────

const PII_BADGE: Record<AnalysisPiiLevel, { label: string; variant: 'danger' | 'info' | 'success' }> = {
  PII: { label: 'PII', variant: 'danger' },
  NO_PII: { label: 'No PII', variant: 'info' },
  DEIDENTIFIED_SUMMARY: { label: 'De-identified', variant: 'success' },
};

function DatasetList({
  datasets,
  loading,
  selectedId,
  onSelect,
}: {
  datasets?: AnalysisDataset[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardHeading
          icon={Database}
          title="Datasets"
          description="Aggregated Data shared into the environment, and views derived from it."
        />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-40 w-full" />
        ) : !datasets?.length ? (
          <p className="text-sm text-muted-foreground">
            No datasets have been shared to you in this environment.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {datasets.map((d) => {
              const pii = PII_BADGE[d.pii_level];
              const active = d.id === selectedId;
              return (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(d.id)}
                    aria-current={active}
                    className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                      active
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/40'
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{d.name}</span>
                      <Badge variant={pii.variant} size="sm">
                        {pii.label}
                      </Badge>
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {d.kind === 'AGGREGATED_SNAPSHOT' ? 'Aggregated snapshot' : 'Derived view'}
                      {' · '}
                      {d.version_no
                        ? `v${d.version_no} · ${formatNumber(d.row_count ?? 0)} row${d.row_count === 1 ? '' : 's'}`
                        : 'never refreshed'}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────── Dataset detail ───────────────

function DatasetDetail({
  dataset,
  canShare,
  canAuthor,
  onChanged,
}: {
  dataset: AnalysisDataset;
  canShare: boolean;
  canAuthor: boolean;
  onChanged: () => void;
}) {
  const [tab, setTab] = React.useState<'data' | 'stats' | 'sharing'>('data');

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading
            icon={Table2}
            title={dataset.name}
            description={dataset.description ?? undefined}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" size="sm">{dataset.code}</Badge>
            <Badge variant={PII_BADGE[dataset.pii_level].variant} size="sm">
              {PII_BADGE[dataset.pii_level].label}
            </Badge>
            {dataset.is_state_partitioned ? (
              <Badge variant="neutral" size="sm">State-partitioned</Badge>
            ) : null}
            <span>
              Grouped by {dataset.definition?.dimensions?.map(humanize).join(', ') || '—'} ·
              measuring {dataset.definition?.measures?.map(humanize).join(', ') || '—'}
            </span>
          </div>

          <div className="flex gap-1 border-b border-border" role="tablist">
            {(['data', 'stats', 'sharing'] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={`-mb-px border-b-2 px-3 py-1.5 text-sm font-medium transition-colors ${
                  tab === t
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {t === 'data' ? 'Data' : t === 'stats' ? 'Statistics' : 'Sharing'}
              </button>
            ))}
          </div>

          {tab === 'data' ? <DatasetRows dataset={dataset} canAuthor={canAuthor} onChanged={onChanged} /> : null}
          {tab === 'stats' ? <DatasetStatistics dataset={dataset} /> : null}
          {tab === 'sharing' ? <DatasetShares dataset={dataset} canShare={canShare} /> : null}
        </CardContent>
      </Card>
    </div>
  );
}

function DatasetRows({
  dataset,
  canAuthor,
  onChanged,
}: {
  dataset: AnalysisDataset;
  canAuthor: boolean;
  onChanged: () => void;
}) {
  // Keyed on the version, not just the dataset: a refresh mints a new version
  // without changing the dataset id, so keying on the id alone would leave this
  // panel showing the previous version's rows under its own "as of" while the
  // list beside it already reported the new one. Two different answers to "as of
  // when?" on one screen is precisely the failure this tier exists to avoid.
  const { data, loading } = useApi(
    () => analysisEnvApi.rows(dataset.id, 100),
    [dataset.id, dataset.current_version_id],
  );
  const [msg, setMsg] = React.useState<string | null>(null);

  async function download(format: 'csv' | 'json') {
    setMsg(null);
    try {
      const body = await analysisEnvApi.exportData(dataset.id, format);
      // CSV comes back as raw text; JSON is already parsed by `api()`, so it is
      // re-serialised here rather than pretending both are strings.
      const text = typeof body === 'string' ? body : JSON.stringify(body, null, 2);
      const blob = new Blob([text], {
        type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${dataset.code.toLowerCase()}_v${dataset.version_no ?? 0}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : 'Export failed');
    }
  }

  if (loading) return <Skeleton className="h-48 w-full" />;
  if (!data || !data.version_no) {
    return (
      <EmptyState
        icon={Database}
        title="Never refreshed"
        description="This dataset has no materialized version yet. It will populate on the next refresh."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          Version {data.version_no} · {formatNumber(data.total)} row(s) · as of{' '}
          {formatDateTime(data.materialized_at)}
        </span>
        {data.state_scoped ? (
          <Badge variant="info" size="sm">
            Filtered to your State scope
          </Badge>
        ) : null}
        <span className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={() => download('csv')}>
            <Download className="h-4 w-4" /> CSV
          </Button>
          <Button size="sm" variant="outline" onClick={() => download('json')}>
            <Download className="h-4 w-4" /> JSON
          </Button>
          {canAuthor ? (
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                setMsg(null);
                try {
                  await analysisEnvApi.refreshDataset(dataset.id);
                  onChanged();
                } catch (e) {
                  setMsg(e instanceof ApiError ? e.message : 'Refresh failed');
                }
              }}
            >
              <RefreshCw className="h-4 w-4" /> Re-materialize
            </Button>
          ) : null}
        </span>
      </div>

      {msg ? <p className="text-sm text-alert-red-700">{msg}</p> : null}

      {data.rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No rows in your scope.</p>
      ) : (
        <div className="max-h-96 overflow-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                {data.columns.map((c) => (
                  <TableHead key={c}>{humanize(c)}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row, i) => (
                <TableRow key={i}>
                  {data.columns.map((c) => (
                    <TableCell key={c} className="tabular-nums">
                      {row[c] === null || row[c] === undefined ? '—' : String(row[c])}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Exportable to Python, SAS, R, Tableau or ArcGIS. Analysis never modifies the
        underlying CCFP or SafeSpect records.
      </p>
    </div>
  );
}

/** Descriptive statistics — the BRD's "central tendency and dispersion, data
 * distributions" over Analysis Environment data. Only the dataset's own measure
 * columns are offered, because a dimension like State has no meaningful mean. */
function DatasetStatistics({ dataset }: { dataset: AnalysisDataset }) {
  const measures = dataset.definition?.measures ?? [];
  const [column, setColumn] = React.useState(measures[0] ?? '');

  React.useEffect(() => {
    if (measures.length && !measures.includes(column)) setColumn(measures[0]);
  }, [measures, column]);

  // Version-keyed for the same reason as the rows panel: statistics computed
  // over the previous snapshot must not stay on screen, labelled with that
  // snapshot's timestamp, once a refresh has replaced it.
  const { data, loading, error } = useApi(
    () =>
      column
        ? analysisEnvApi.statistics(dataset.id, column)
        : Promise.resolve(undefined),
    [dataset.id, dataset.current_version_id, column],
  );

  if (!measures.length) {
    return <p className="text-sm text-muted-foreground">This dataset has no numeric measures.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="stat-col">Measure</Label>
          <Select id="stat-col" value={column} onChange={(e) => setColumn(e.target.value)}>
            {measures.map((m) => (
              <option key={m} value={m}>
                {humanize(m)}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : error ? (
        <p className="text-sm text-alert-red-700">Could not compute statistics.</p>
      ) : !data || data.n === 0 ? (
        <p className="text-sm text-muted-foreground">No numeric values in scope for this column.</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile icon={Sigma} label="Observations" value={formatNumber(data.n)} />
            <StatTile icon={Sigma} label="Mean" value={fmt(data.mean)} hint="Central tendency" />
            <StatTile icon={Sigma} label="Median" value={fmt(data.median)} hint="50th percentile" />
            <StatTile icon={Sigma} label="Std. deviation" value={fmt(data.stddev)} hint="Dispersion" />
            <StatTile icon={Sigma} label="Minimum" value={fmt(data.minimum)} />
            <StatTile icon={Sigma} label="Maximum" value={fmt(data.maximum)} />
            <StatTile icon={Sigma} label="IQR" value={fmt(data.iqr)} hint={`P25 ${fmt(data.p25)} · P75 ${fmt(data.p75)}`} />
            <StatTile icon={Sigma} label="Total" value={fmt(data.total)} />
          </div>

          <Card>
            <CardHeader>
              <CardHeading
                icon={Sigma}
                title="Distribution"
                description={`${humanize(column)} across ${formatNumber(data.n)} row(s), as of ${formatDateTime(data.materialized_at)}.`}
              />
            </CardHeader>
            <CardContent>
              <HorizontalBars
                data={data.histogram.map((b) => ({
                  key: String(b.bin),
                  label: `${fmt(b.lower)} – ${fmt(b.upper)}`,
                  value: b.count,
                }))}
                labelWidth="w-32"
                emptyMessage="No distribution to display."
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return Number.isInteger(v) ? formatNumber(v) : v.toFixed(2);
}

// ─────────────── Sharing ───────────────

const AUDIENCE_LABEL: Record<AnalysisAudience, string> = {
  FMCSA_FEDERAL: 'FMCSA Federal users',
  OTHER_FEDERAL: 'Other Federal (BTS, NHTSA, NTSB)',
  PARTICIPATING_STATE: 'Participating State',
  PUBLIC: 'Public',
};

function DatasetShares({ dataset, canShare }: { dataset: AnalysisDataset; canShare: boolean }) {
  const { data: shares, loading, reload } = useApi(() => analysisEnvApi.shares(dataset.id), [dataset.id]);
  const [audience, setAudience] = React.useState<AnalysisAudience>('FMCSA_FEDERAL');
  const [stateCode, setStateCode] = React.useState('');
  const [msg, setMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function add() {
    setBusy(true);
    setMsg(null);
    try {
      await analysisEnvApi.createShare(dataset.id, {
        audience,
        state_code: audience === 'PARTICIPATING_STATE' ? stateCode.toUpperCase() : null,
      });
      setStateCode('');
      reload();
    } catch (e) {
      // The PII and State-partitioning rules are enforced in the database, so
      // this message is the actual constraint text — worth showing verbatim
      // rather than replacing with a generic failure.
      setMsg(e instanceof ApiError ? e.message : 'Share failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : !shares?.length ? (
        <p className="text-sm text-muted-foreground">This dataset has not been shared.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Audience</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Refresh</TableHead>
              <TableHead>Status</TableHead>
              {canShare ? <TableHead aria-label="Actions" /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {shares.map((s) => (
              <TableRow key={s.id}>
                <TableCell>{AUDIENCE_LABEL[s.audience] ?? humanize(s.audience)}</TableCell>
                <TableCell>{s.state_code ?? '—'}</TableCell>
                <TableCell>{humanize(s.refresh_cadence)}</TableCell>
                <TableCell>
                  <Badge variant={s.status === 'ACTIVE' ? 'success' : 'neutral'} size="sm">
                    {humanize(s.status)}
                  </Badge>
                </TableCell>
                {canShare ? (
                  <TableCell>
                    {s.status === 'ACTIVE' ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          try {
                            await analysisEnvApi.revokeShare(s.id);
                            reload();
                          } catch (e) {
                            setMsg(e instanceof ApiError ? e.message : 'Revoke failed');
                          }
                        }}
                      >
                        <Trash2 className="h-4 w-4" /> Revoke
                      </Button>
                    ) : null}
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {canShare ? (
        <div className="space-y-2 rounded-md border border-border p-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="share-audience">Share with</Label>
              <Select
                id="share-audience"
                value={audience}
                onChange={(e) => setAudience(e.target.value as AnalysisAudience)}
              >
                {(Object.keys(AUDIENCE_LABEL) as AnalysisAudience[]).map((a) => (
                  <option key={a} value={a}>
                    {AUDIENCE_LABEL[a]}
                  </option>
                ))}
              </Select>
            </div>
            {audience === 'PARTICIPATING_STATE' ? (
              <div className="space-y-1.5">
                <Label htmlFor="share-state">State</Label>
                <Input
                  id="share-state"
                  className="w-24"
                  maxLength={2}
                  placeholder="KS"
                  value={stateCode}
                  onChange={(e) => setStateCode(e.target.value)}
                />
              </div>
            ) : null}
            <Button onClick={add} disabled={busy || (audience === 'PARTICIPATING_STATE' && stateCode.length !== 2)}>
              <Share2 className="h-4 w-4" /> Share
            </Button>
          </div>
          {msg ? <p className="text-sm text-alert-red-700">{msg}</p> : null}
          <p className="text-xs text-muted-foreground">
            <Users className="mr-1 inline h-3 w-3" />
            States and the public may never receive a dataset carrying PII, and public
            sharing additionally requires a de-identified summary. Enforced in the database.
          </p>
        </div>
      ) : null}
    </div>
  );
}

// ─────────────── Refresh log ───────────────

function RefreshRunsCard({ environmentId }: { environmentId: string }) {
  const { data, loading } = useApi(() => analysisEnvApi.refreshRuns(environmentId, 8), [environmentId]);

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={RefreshCw}
          title="Refresh history"
          description="So a stale snapshot can be told apart from a failing refresh."
        />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : !data?.length ? (
          <p className="text-sm text-muted-foreground">No refreshes recorded yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Started</TableHead>
                <TableHead>Trigger</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Datasets</TableHead>
                <TableHead>Rows</TableHead>
                <TableHead>Message</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="whitespace-nowrap">{formatDateTime(r.started_at)}</TableCell>
                  <TableCell>{r.trigger === 'MANUAL' ? 'Refresh now' : 'Cadence'}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        r.status === 'SUCCEEDED' ? 'success' : r.status === 'FAILED' ? 'danger' : 'progress'
                      }
                      size="sm"
                    >
                      {humanize(r.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">{formatNumber(r.datasets_refreshed)}</TableCell>
                  <TableCell className="tabular-nums">{formatNumber(r.rows_written)}</TableCell>
                  <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                    {r.message ?? '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────── New derived view ───────────────

/**
 * Builds a dataset definition from the server's allow-listed vocabulary. The
 * options come from `/analysis-datasets/fields` rather than being hardcoded, so
 * the form cannot offer a dimension the backend would reject — and the backend
 * re-validates anyway, because this form is not the only possible caller.
 */
function NewDatasetDialog({
  environmentId,
  onClose,
  onSaved,
}: {
  environmentId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { data: fields } = useApi(() => analysisEnvApi.fields(), []);
  const [name, setName] = React.useState('');
  const [code, setCode] = React.useState('');
  const [dimension, setDimension] = React.useState('state_code');
  const [measure, setMeasure] = React.useState('crash_count');
  const [pii, setPii] = React.useState<AnalysisPiiLevel>('NO_PII');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await analysisEnvApi.createDataset({
        environment_id: environmentId,
        code: code || name.replace(/\s+/g, '_').toUpperCase(),
        name,
        kind: 'DERIVED_VIEW',
        pii_level: pii,
        definition: { dimensions: [dimension], measures: [measure], filters: [] },
      });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the dataset');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New derived view</DialogTitle>
          <DialogDescription>
            Create a view derived from CCFP Aggregated Data. It is materialized
            immediately and refreshed with the environment.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="nd-name">Name</Label>
            <Input id="nd-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Fatalities by county" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-code">Code</Label>
            <Input id="nd-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="FATALITIES_BY_COUNTY" />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nd-dim">Group by</Label>
              <Select id="nd-dim" value={dimension} onChange={(e) => setDimension(e.target.value)}>
                {(fields?.dimensions ?? []).map((d) => (
                  <option key={d} value={d}>{humanize(d)}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nd-measure">Measure</Label>
              <Select id="nd-measure" value={measure} onChange={(e) => setMeasure(e.target.value)}>
                {(fields?.measures ?? []).map((m) => (
                  <option key={m} value={m}>{humanize(m)}</option>
                ))}
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-pii">Sensitivity</Label>
            <Select id="nd-pii" value={pii} onChange={(e) => setPii(e.target.value as AnalysisPiiLevel)}>
              {(fields?.pii_levels ?? []).map((p) => (
                <option key={p} value={p}>{PII_BADGE[p]?.label ?? humanize(p)}</option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">
              Determines which audiences this view may be shared with.
            </p>
          </div>
          {error ? <p className="text-sm text-alert-red-700">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || !name.trim()}>
            {busy ? 'Creating…' : 'Create view'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
