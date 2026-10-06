import * as React from 'react';
import { CheckCircle2, ClipboardCheck, LockOpen, Play, XCircle } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { CompletenessBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { crashApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { formatDateTime, humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';
import type { CompletenessEvalResult, CompletenessMissingItem } from '@/lib/types';

/**
 * Group unmet requirements by the rule that failed.
 *
 * The rule name is the human-facing label; `unmet` is the evaluator's internal
 * token. Rendering both unconditionally restated the same sentence twice
 * ("Initial Incident Form submitted: Initial Incident Submitted"), so the token
 * is only shown when it carries information the rule name does not: when a
 * single rule has several unmet requirements, when there is no rule name, or
 * when the token is unresolvable (a rule misconfiguration a reviewer must see).
 */
function groupMissing(missing: CompletenessMissingItem[]) {
  const groups = new Map<string, CompletenessMissingItem[]>();
  for (const m of missing) {
    const key = m.rule?.trim() || '';
    const bucket = groups.get(key);
    if (bucket) bucket.push(m);
    else groups.set(key, [m]);
  }
  return [...groups.entries()].map(([rule, items]) => ({
    rule,
    // Show tokens alongside the rule name only when they disambiguate.
    detail: items
      .filter((m) => !rule || items.length > 1 || m.unknown_token)
      .map((m) => humanize(m.unmet) + (m.unknown_token ? ' (unknown requirement)' : '')),
  }));
}

export function CrashCompletenessTab() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canEvaluate = hasPermission(user, 'data_mgmt:complete');
  const canUnlock = hasPermission(user, 'crash:unlock');

  const { data, loading, reload } = useApi(() => crashApi.completeness(crash.id).catch(() => null), [crash.id]);
  const [evalResult, setEvalResult] = React.useState<CompletenessEvalResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function evaluate() {
    setBusy(true); setError(null);
    try { const r = await crashApi.evaluateCompleteness(crash.id); setEvalResult(r); reload(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Evaluation failed'); } finally { setBusy(false); }
  }
  async function unlock() {
    setBusy(true); setError(null);
    try { await crashApi.unlock(crash.id); reload(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Unlock failed'); } finally { setBusy(false); }
  }

  const missing = (evalResult?.missing ??
    (data?.missing_summary?.missing as CompletenessMissingItem[] | undefined) ??
    []) as CompletenessMissingItem[];
  const missingGroups = groupMissing(missing);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading
            icon={ClipboardCheck}
            title="Completeness"
            description="Configurable completeness rules determine when a crash record is complete."
            actions={
              <div className="flex gap-2">
                {canEvaluate ? <Button size="sm" onClick={evaluate} disabled={busy}>{busy ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />} {busy ? 'Evaluating…' : 'Evaluate'}</Button> : null}
                {canUnlock && data?.is_locked ? <Button size="sm" variant="outline" onClick={unlock} disabled={busy}><LockOpen className="h-4 w-4" /> Unlock</Button> : null}
              </div>
            }
          />
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? <Skeleton className="h-12 w-full" /> : data ? (
            <div className="flex items-center gap-3">
              <CompletenessBadge status={data.status} locked={data.is_locked} />
              <span className="text-xs text-muted-foreground">Updated {formatDateTime(data.changed_at)}</span>
            </div>
          ) : <p className="text-sm text-muted-foreground">Not yet evaluated.</p>}
          {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
          {/* Announce the run to assistive tech and give sighted users an
              unambiguous "it finished" signal — the badge and timestamp often
              re-render to the same values when nothing changed. */}
          <p className="sr-only" role="status">
            {busy ? 'Evaluating completeness…' : evalResult ? `Evaluation complete — record is ${evalResult.status.toLowerCase()}.` : ''}
          </p>
        </CardContent>
      </Card>

      {evalResult ? (
        <Card>
          <CardHeader><CardHeading icon={CheckCircle2} title="Completeness checks" description="Result of the latest evaluation." /></CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {Object.entries(evalResult.checks).map(([k, ok]) => (
                <li key={k} className="flex items-center gap-2">
                  {ok ? <CheckCircle2 className="h-4 w-4 text-success-green-700" /> : <XCircle className="h-4 w-4 text-alert-red" />}
                  <span className={ok ? '' : 'text-foreground'}>{humanize(k)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {missing.length ? (
        <Alert variant="warning">
          <AlertDescription>
            <span className="font-medium">Outstanding for completeness:</span>
            <ul className="mt-1 list-inside list-disc">
              {missingGroups.map((g, i) => (
                <li key={i}>
                  {g.rule || g.detail.join(', ')}
                  {g.rule && g.detail.length ? `: ${g.detail.join(', ')}` : ''}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
