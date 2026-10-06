import * as React from 'react';
import { Gauge, Play } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Spinner } from '@/components/ui/spinner';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { QcStatusBadge, SeverityBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { crashApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';
import type { QcEvalResult } from '@/lib/types';

export function CrashQualityTab() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canRun = hasPermission(user, 'data_mgmt:qc');
  const { data, loading, reload } = useApi(() => crashApi.quality(crash.id).catch(() => []), [crash.id]);
  const [running, setRunning] = React.useState(false);
  const [evalResult, setEvalResult] = React.useState<QcEvalResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Mirrors the Completeness tab: a failed run must say so. Previously the
  // rejection escaped as an unhandled promise, so a 403/500 left the button
  // re-enabled with the stale table still on screen — indistinguishable from
  // the click never having registered.
  async function run() {
    setRunning(true); setError(null); setEvalResult(null);
    try { const r = await crashApi.evaluateQuality(crash.id); setEvalResult(r); reload(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Evaluation failed'); } finally { setRunning(false); }
  }

  const summary = evalResult
    ? Object.entries(evalResult.summary).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${k.toLowerCase().replace(/_/g, ' ')}`).join(' · ')
    : null;

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={Gauge}
          title="Quality control"
          description="Configurable QC rules: missing data, format, compliance, cross-field."
          actions={canRun ? <Button size="sm" onClick={run} disabled={running}>{running ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />} {running ? 'Evaluating…' : 'Run evaluation'}</Button> : undefined}
        />
        {error ? <Alert variant="destructive" className="mt-3"><AlertDescription>{error}</AlertDescription></Alert> : null}
        {summary ? <p className="mt-3 text-sm text-muted-foreground" role="status">Evaluation complete — {summary}.</p> : null}
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-32 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={Gauge} title="No QC results yet" description={canRun ? 'Run an evaluation to compute quality-control results.' : 'Quality-control results will appear here once evaluated.'} /></div>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-5">Rule</TableHead><TableHead className="text-center">Severity</TableHead>
              <TableHead className="text-center">Status</TableHead><TableHead>Message</TableHead>
              <TableHead className="pr-5 text-right">Evaluated</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data!.map((r) => (
                <TableRow key={r.rule_code}>
                  <TableCell className="pl-5"><div className="font-medium">{r.rule_name}</div><div className="text-xs text-muted-foreground">{r.rule_code}</div></TableCell>
                  <TableCell className="text-center"><SeverityBadge severity={r.severity} /></TableCell>
                  <TableCell className="text-center"><QcStatusBadge status={r.status} /></TableCell>
                  <TableCell className="text-muted-foreground">{r.message ?? '—'}</TableCell>
                  <TableCell className="pr-5 text-right text-xs text-muted-foreground">{formatDateTime(r.evaluated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
