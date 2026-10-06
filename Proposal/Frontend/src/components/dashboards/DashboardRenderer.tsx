/**
 * DashboardRenderer (ANAL-7, documentation §8.9).
 *
 * Turns a DASHBOARD report's validated panel definition into composed
 * Recharts visualizations. Each panel binds to a whitelisted analytics query
 * (server-validated via GET /analytics/dashboards/{id}) and is executed through
 * the existing, State-scoped POST /analytics/queries endpoint — this component
 * never runs free-form SQL and never introduces a new chart library; it reuses
 * the QueryBarsCard / QueryDonutCard widgets and the @/components/charts
 * primitives the role dashboards already use.
 */
import * as React from 'react';
import { BarChart3, LayoutDashboard, LineChart as LineChartIcon, PieChart, Table as TableIcon, type LucideIcon } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { QueryBarsCard, QueryDonutCard } from '@/components/dashboards/shared';
import { LineChart } from '@/components/charts';
import { analyticsApi } from '@/lib/endpoints';
import { useApi } from '@/lib/useApi';
import { humanize } from '@/lib/format';
import type { QueryResult, Report } from '@/lib/types';

/** Panel viz kinds the renderer supports — mirrors the backend ALLOWED_PANEL_VIZ. */
export type PanelViz = 'bars' | 'donut' | 'line' | 'table';

export interface PanelQuery {
  query_name: string;
  study_id?: string | null;
}

export interface PanelDef {
  id: string;
  title: string;
  viz: PanelViz;
  query: PanelQuery;
  labelKey?: string | null;
  valueKey?: string | null;
}

export interface DashboardDefinition {
  layout?: string;
  panels: PanelDef[];
}

const VIZ_ICON: Record<PanelViz, LucideIcon> = {
  bars: BarChart3,
  donut: PieChart,
  line: LineChartIcon,
  table: TableIcon,
};

/** Best-effort extraction of a typed dashboard definition from a Report. */
export function dashboardDefinition(report: Report | undefined | null): DashboardDefinition {
  const def = (report?.definition ?? {}) as Partial<DashboardDefinition>;
  const panels = Array.isArray(def.panels) ? def.panels : [];
  return { layout: def.layout ?? 'grid', panels: panels as PanelDef[] };
}

/** Pick the row keys to chart, falling back to the QueryResult column order. */
function resolveKeys(panel: PanelDef, result: QueryResult | undefined): { labelKey: string; valueKey: string } {
  const cols = result?.columns ?? [];
  return {
    labelKey: panel.labelKey ?? cols[0] ?? 'label',
    valueKey: panel.valueKey ?? cols[1] ?? 'value',
  };
}

function PanelTable({ title, icon, result, loading }: { title: string; icon: LucideIcon; result?: QueryResult; loading?: boolean }) {
  const cols = result?.columns ?? [];
  const rows = result?.rows ?? [];
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardHeading icon={icon} title={title} description={`${rows.length} row(s).`} />
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
        {loading ? (
          <Skeleton className="h-48 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No data.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {cols.map((c) => (
                  <TableHead key={c}>{humanize(c)}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, i) => (
                <TableRow key={i}>
                  {cols.map((c) => (
                    <TableCell key={c} className="tabular-nums">{String(row[c] ?? '—')}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function PanelLine({ title, icon, result, labelKey, valueKey, loading }: { title: string; icon: LucideIcon; result?: QueryResult; labelKey: string; valueKey: string; loading?: boolean }) {
  const data = (result?.rows ?? []).map((r) => ({ x: String(r[labelKey] ?? ''), y: Number(r[valueKey] ?? 0) }));
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardHeading icon={icon} title={title} />
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col justify-center">
        {loading ? <Skeleton className="h-48 w-full" /> : <LineChart data={data} />}
      </CardContent>
    </Card>
  );
}

/** One panel: runs its whitelisted query, then renders the chosen viz. */
function Panel({ panel }: { panel: PanelDef }) {
  const { data: result, loading } = useApi(
    () => analyticsApi.runQuery(panel.query.query_name, panel.query.study_id ?? undefined),
    [panel.query.query_name, panel.query.study_id],
  );
  const icon = VIZ_ICON[panel.viz] ?? LayoutDashboard;
  const { labelKey, valueKey } = resolveKeys(panel, result);

  switch (panel.viz) {
    case 'donut':
      return <QueryDonutCard title={panel.title} icon={icon} result={result} labelKey={labelKey} valueKey={valueKey} loading={loading} mapLabel={humanize} />;
    case 'line':
      return <PanelLine title={panel.title} icon={icon} result={result} labelKey={labelKey} valueKey={valueKey} loading={loading} />;
    case 'table':
      return <PanelTable title={panel.title} icon={icon} result={result} loading={loading} />;
    case 'bars':
    default:
      return <QueryBarsCard title={panel.title} icon={icon} result={result} labelKey={labelKey} valueKey={valueKey} loading={loading} mapLabel={humanize} />;
  }
}

/**
 * Render a dashboard report's panels. Accepts either the loaded Report or an
 * already-extracted DashboardDefinition.
 */
export function DashboardRenderer({ report, definition }: { report?: Report | null; definition?: DashboardDefinition }) {
  const def = definition ?? dashboardDefinition(report);
  if (def.panels.length === 0) {
    return <p className="text-sm text-muted-foreground">This dashboard has no panels yet.</p>;
  }
  return (
    <div className="grid items-stretch gap-4 lg:grid-cols-2">
      {def.panels.map((panel) => (
        <Panel key={panel.id} panel={panel} />
      ))}
    </div>
  );
}
