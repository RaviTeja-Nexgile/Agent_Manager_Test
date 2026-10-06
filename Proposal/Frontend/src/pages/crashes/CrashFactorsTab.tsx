import * as React from 'react';
import { FileText, ListChecks, Save } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { useApi } from '@/lib/useApi';
import { dataMgmtApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';
import type { FactorSummaryValue } from '@/lib/types';

interface Row {
  factor_group_code: string;
  factor_value: string;
}

/** Render a collected attribute's value for the summary list. */
function displayValue(v: FactorSummaryValue): string {
  if (v.redacted) return 'Restricted';
  if (v.value_text) return v.value_text;
  if (v.value_json === null || v.value_json === undefined) return '—';
  // MULTI_CODE attributes carry an array; anything else renders as compact JSON.
  return Array.isArray(v.value_json) ? v.value_json.join(', ') : JSON.stringify(v.value_json);
}

/** "Trailer 2" — the repeat unit a value belongs to, or null for crash-level. */
function unitLabel(v: FactorSummaryValue): string | null {
  if (!v.unit_type) return null;
  const t = v.unit_type.charAt(0) + v.unit_type.slice(1).toLowerCase();
  return v.unit_number === null ? t : `${t} ${v.unit_number}`;
}

export function CrashFactorsTab() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canEdit = hasPermission(user, 'contributing_factor:select');

  const { data: groups, loading: gLoading } = useApi(() => dataMgmtApi.factorGroups().catch(() => []), []);
  // DATA-7: catalog of allowed per-group factor values; fetched once and filtered
  // client-side by the row's selected group so the Factor field is a structured dropdown.
  const { data: values, loading: vLoading } = useApi(() => dataMgmtApi.factorValues().catch(() => []), []);
  const { data: existing, loading, reload } = useApi(() => dataMgmtApi.contributingFactors(crash.id).catch(() => []), [crash.id]);
  // BRD DL4: the analyst ranks the three factors *from* this summary, so the
  // PCR-section data has to be on the same screen as the selectors.
  const { data: summary, loading: sLoading } = useApi(
    () => dataMgmtApi.contributingFactorSummary(crash.id).catch(() => null),
    [crash.id],
  );

  const valuesForGroup = React.useCallback(
    (code: string) => {
      if (!code || !groups || !values) return [];
      const g = groups.find((x) => x.code === code);
      if (!g) return [];
      return values.filter((v) => v.factor_group_id === g.id);
    },
    [groups, values],
  );

  const [rows, setRows] = React.useState<Row[]>([
    { factor_group_code: '', factor_value: '' },
    { factor_group_code: '', factor_value: '' },
    { factor_group_code: '', factor_value: '' },
  ]);
  React.useEffect(() => {
    if (!existing || !groups) return;
    const next: Row[] = [
      { factor_group_code: '', factor_value: '' },
      { factor_group_code: '', factor_value: '' },
      { factor_group_code: '', factor_value: '' },
    ];
    for (const f of existing) {
      if (f.rank >= 1 && f.rank <= 3) {
        const g = groups.find((x) => x.id === f.factor_group_id);
        next[f.rank - 1] = { factor_group_code: g?.code ?? '', factor_value: f.factor_value };
      }
    }
    setRows(next);
  }, [existing, groups]);

  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ kind: 'error' | 'success'; text: string } | null>(null);

  async function save() {
    setBusy(true); setMsg(null);
    const factors = rows
      .map((r, i) => ({ factor_group_code: r.factor_group_code || null, factor_value: r.factor_value.trim(), rank: i + 1 }))
      .filter((r) => r.factor_value);
    try {
      await dataMgmtApi.setContributingFactors(crash.id, factors);
      reload(); setMsg({ kind: 'success', text: `Saved ${factors.length} contributing factor(s).` });
    } catch (e) { setMsg({ kind: 'error', text: e instanceof ApiError ? e.message : 'Save failed' }); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading
            icon={FileText}
            title="PCR section summary"
            description="Data collected in the PCR sections that inform the contributing-factor ranking."
          />
        </CardHeader>
        <CardContent>
          {sLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !summary || summary.sections.length === 0 ? (
            <p className="text-sm text-muted-foreground">No PCR sections are configured for this study.</p>
          ) : summary.collected === 0 ? (
            <Alert>
              <AlertDescription>
                No data has been collected yet in these PCR sections
                {' '}({summary.sections.map((s) => s.name).join(', ')}). Rank the factors once source
                data has been mapped, or record your selection below if it is known from another source.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="space-y-4">
              {summary.sections.map((section) => (
                <div key={section.code}>
                  <div className="flex items-baseline justify-between gap-3 border-b border-border pb-1">
                    <h3 className="text-sm font-semibold">{section.name}</h3>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {section.collected} of {section.total} collected
                    </span>
                  </div>
                  {section.values.length === 0 ? (
                    <p className="mt-2 text-sm text-muted-foreground">Nothing collected in this section.</p>
                  ) : (
                    <dl className="mt-2 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                      {section.values.map((v) => (
                        <div key={`${v.attribute_id}-${v.unit_type ?? ''}-${v.unit_number ?? ''}`} className="flex gap-2 text-sm">
                          <dt className="min-w-0 flex-1 text-muted-foreground">
                            {v.name}
                            {unitLabel(v) ? <span className="ml-1 text-xs">({unitLabel(v)})</span> : null}
                          </dt>
                          <dd className={v.redacted ? 'shrink-0 italic text-muted-foreground' : 'shrink-0 font-medium'}>
                            {displayValue(v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
      <CardHeader>
        <CardHeading icon={ListChecks} title="Top three contributing factors" description="Based on the PCR section summary above, select and rank the primary contributing factors." />
      </CardHeader>
      <CardContent className="space-y-4">
        {loading || gLoading || vLoading ? <Skeleton className="h-40 w-full" /> : (
          <>
            {rows.map((row, i) => (
              <div key={i} className="grid items-end gap-3 rounded-md border border-border p-3 sm:grid-cols-12">
                <div className="sm:col-span-1"><div className="text-eyebrow">Rank</div><div className="mt-1 text-lg font-semibold">{i + 1}</div></div>
                <div className="space-y-1.5 sm:col-span-4">
                  <Label>Factor group</Label>
                  <Select value={row.factor_group_code} disabled={!canEdit} onChange={(e) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, factor_group_code: e.target.value, factor_value: '' } : r)))}>
                    <option value="">— Select group —</option>
                    {(groups ?? []).map((g) => <option key={g.id} value={g.code}>{g.name}</option>)}
                  </Select>
                </div>
                <div className="space-y-1.5 sm:col-span-7">
                  <Label>Factor</Label>
                  <Select value={row.factor_value} disabled={!canEdit || !row.factor_group_code} onChange={(e) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, factor_value: e.target.value } : r)))}>
                    <option value="">{row.factor_group_code ? '— Select factor —' : '— Choose a group first —'}</option>
                    {valuesForGroup(row.factor_group_code).map((v) => <option key={v.id} value={v.label}>{v.label}</option>)}
                  </Select>
                </div>
              </div>
            ))}
            {msg ? <Alert variant={msg.kind === 'error' ? 'destructive' : 'success'}><AlertDescription>{msg.text}</AlertDescription></Alert> : null}
            {canEdit ? (
              <Button onClick={save} disabled={busy}>{busy ? <Spinner className="h-4 w-4" /> : <Save className="h-4 w-4" />} Save factors</Button>
            ) : (
              <p className="text-sm text-muted-foreground">You don't have permission to edit contributing factors.</p>
            )}
          </>
        )}
      </CardContent>
      </Card>
    </div>
  );
}
