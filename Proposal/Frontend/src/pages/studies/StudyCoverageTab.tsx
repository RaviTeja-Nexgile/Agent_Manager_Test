import * as React from 'react';
import { BarChart3, ListChecks, Pencil } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { HorizontalBars, CHART_PALETTE } from '@/components/charts';
import { useApi } from '@/lib/useApi';
import { dataAttributeApi, studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type { PcrCoverage } from '@/lib/types';
import { useStudy } from './StudyDetailPage';

// PCR-3 (§8.5): per-State, per-attribute three-way collection status. Typed
// locally — the shared spine type table is owned by another lane.
type AttributeCoverageStatus = 'REQUIRED_COLLECTED' | 'REQUIRED_NOT_COLLECTED' | 'OPTIONAL_NOT_COLLECTED';
interface AttributeCoverage {
  attribute_id: string;
  code: string;
  name: string;
  pcr_section: string | null;
  is_required: boolean;
  is_optional: boolean;
  is_collected: boolean;
  status: AttributeCoverageStatus;
}

// Map each documented colour bucket to the existing chart palette (no new lib).
const STATUS_STYLE: Record<AttributeCoverageStatus, { color: string; label: string }> = {
  REQUIRED_COLLECTED: { color: CHART_PALETTE.successGreen, label: 'Required · collected' },
  REQUIRED_NOT_COLLECTED: { color: CHART_PALETTE.alertRed, label: 'Required · not collected' },
  OPTIONAL_NOT_COLLECTED: { color: CHART_PALETTE.alertAmber, label: 'Optional · not collected' },
};

export function StudyCoverageTab() {
  const { study } = useStudy();
  const { user } = useAuth();
  const canConfig = hasPermission(user, 'study:configure');
  const [state, setState] = React.useState('');
  const { data, loading, reload } = useApi(() => studyApi.pcrCoverage(study.id, state || undefined).catch(() => []), [study.id, state]);
  const { data: attrCoverage, loading: attrLoading } = useApi(
    () => studyApi.attributeCoverage(study.id, state || undefined).catch(() => [] as AttributeCoverage[]),
    [study.id, state],
  );
  const [editing, setEditing] = React.useState<PcrCoverage | null>(null);

  const states = React.useMemo(() => [...new Set((data ?? []).map((c) => c.state_code))], [data]);
  // Section labels from the specification, not humanized codes (GAP-PCR-01).
  const { data: pcrSections } = useApi(() => dataAttributeApi.sections().catch(() => []), []);
  const sectionName = React.useMemo(
    () => new Map((pcrSections ?? []).map((s) => [s.code, s.name])),
    [pcrSections],
  );
  // Which PCR specification the reported rows belong to (GAP-PCR-05).
  const specVersions = React.useMemo(
    () => [...new Set((data ?? []).map((c) => c.spec_version).filter(Boolean))] as string[],
    [data],
  );

  // Group the per-attribute statuses by PCR section for the §8.5 colour list.
  const attrSections = React.useMemo(() => {
    const groups = new Map<string, AttributeCoverage[]>();
    for (const a of attrCoverage ?? []) {
      const section = a.pcr_section ?? 'OTHER';
      if (!groups.has(section)) groups.set(section, []);
      groups.get(section)!.push(a);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [attrCoverage]);
  // Chart only the sections that actually have required attributes (GAP-PCR-05).
  // A section with none is "not applicable", not 0% — plotting it as an empty
  // red bar would read as a State collecting nothing.
  const bars = (data ?? [])
    .filter((c) => c.total_required > 0 && c.completion_pct != null)
    .map((c) => ({
      key: `${c.state_code}-${c.pcr_section_code}`,
      label: sectionName.get(c.pcr_section_code) ?? humanize(c.pcr_section_code),
      value: Number(c.completion_pct),
      color: Number(c.completion_pct) >= 60 ? CHART_PALETTE.successGreen : Number(c.completion_pct) >= 30 ? CHART_PALETTE.alertAmber : CHART_PALETTE.alertRed,
    }));
  const notApplicable = (data ?? []).filter((c) => c.total_required === 0).length;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading icon={BarChart3} title="State PCR coverage" description="Required-attribute completion % by PCR section." />
        </CardHeader>
        <CardContent className="space-y-4">
          {states.length > 1 ? (
            <Select value={state} onChange={(e) => setState(e.target.value)} className="sm:w-48">
              <option value="">All States</option>
              {states.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          ) : null}
          {loading ? <Skeleton className="h-48 w-full" /> : bars.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="No coverage data"
              description="No PCR section has required attributes configured for this study yet."
            />
          ) : (
            <>
              <HorizontalBars data={bars} max={100} unit="%" labelWidth="w-44" showValueLabels />
              {notApplicable > 0 ? (
                <p className="text-xs text-muted-foreground">
                  {notApplicable} section{notApplicable === 1 ? '' : 's'} not charted — no required
                  attributes are configured for {notApplicable === 1 ? 'it' : 'them'} in this study,
                  so there is no completion figure to report.
                </p>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardHeading icon={ListChecks} title="Per-attribute coverage" description="Each attribute's collection status — green required-collected, red required-not-collected, amber optional-not-collected." />
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
            {(Object.keys(STATUS_STYLE) as AttributeCoverageStatus[]).map((s) => (
              <span key={s} className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: STATUS_STYLE[s].color }} aria-hidden />
                {STATUS_STYLE[s].label}
              </span>
            ))}
          </div>
          {attrLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : attrSections.length === 0 ? (
            <EmptyState icon={ListChecks} title="No attribute coverage" description="No required or optional attributes are configured for this State." />
          ) : (
            <div className="space-y-4">
              {attrSections.map(([section, attrs]) => (
                <div key={section} className="space-y-2">
                  <p className="text-sm font-medium">{humanize(section)}</p>
                  <ul className="flex flex-wrap gap-2">
                    {attrs.map((a) => (
                      <li key={a.attribute_id}>
                        <span
                          className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
                          title={`${a.name} — ${STATUS_STYLE[a.status].label}`}
                        >
                          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: STATUS_STYLE[a.status].color }} aria-hidden />
                          <span className="font-medium">{a.code}</span>
                          <span className="text-muted-foreground">{a.name}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {(data?.length ?? 0) > 0 ? (
        <Card>
          {canConfig ? (
            <CardHeader>
              <CardHeading icon={Pencil} title="Reported coverage" description="State-reported collection status — edit a row to reconcile." />
            </CardHeader>
          ) : null}
          <CardContent className="p-0">
            {/* The old KS worksheet quantified readiness per section and had a
                50-item optional tier; the HDTS PCR data form has neither, so a
                percentage from one spec is not comparable with the other
                (GAP-PCR-05). Say so rather than let a step change read as a
                real change in a State's readiness. */}
            {specVersions.length > 0 ? (
              <div className="border-b border-border px-5 py-3 text-xs text-muted-foreground">
                Denominators are derived from this study&apos;s required attributes, against{' '}
                <span className="font-medium text-foreground">{specVersions.join(', ')}</span>. Percentages
                are not comparable across PCR specification versions. The optional tier is not reported —
                the current form defines no optional attributes.
              </div>
            ) : null}
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">State</TableHead><TableHead>Section</TableHead><TableHead className="text-right">Required collected</TableHead><TableHead className="text-right">Total required</TableHead><TableHead className="text-right">Completion</TableHead>{canConfig ? <TableHead className="pr-5 text-right">Action</TableHead> : null}</TableRow></TableHeader>
              <TableBody>
                {data!.map((c) => (
                  <TableRow key={`${c.state_code}-${c.pcr_section_code}`}>
                    <TableCell className="pl-5 font-medium">{c.state_code}</TableCell>
                    <TableCell>{sectionName.get(c.pcr_section_code) ?? humanize(c.pcr_section_code)}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.required_collected}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.total_required}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">
                      {c.completion_pct != null ? (
                        `${c.completion_pct}%`
                      ) : (
                        <span className="font-normal text-muted-foreground" title="No required attributes are configured for this section">
                          n/a
                        </span>
                      )}
                    </TableCell>
                    {canConfig ? (
                      <TableCell className="pr-5 text-right">
                        <Button size="icon-sm" variant="ghost" aria-label={`Edit ${c.state_code} ${c.pcr_section_code} coverage`} onClick={() => setEditing(c)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}

      {editing ? <CoverageDialog studyId={study.id} row={editing} onClose={() => setEditing(null)} onSaved={reload} /> : null}
    </div>
  );
}

function CoverageDialog({ studyId, row, onClose, onSaved }: { studyId: string; row: PcrCoverage; onClose: () => void; onSaved: () => void }) {
  const [requiredCollected, setRequiredCollected] = React.useState(String(row.required_collected));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    try {
      // Optional counts are no longer reported (GAP-PCR-05): the HDTS PCR data
      // form defines no optional tier, so there is nothing for a State to
      // report against. Sent as 0 rather than omitted so an older stored value
      // cannot linger behind the hidden field.
      await studyApi.updatePcrCoverage(studyId, row.state_code, row.pcr_section_code, {
        required_collected: Number(requiredCollected),
        optional_collected: 0,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  const valid =
    requiredCollected !== '' &&
    Number.isFinite(Number(requiredCollected)) &&
    Number(requiredCollected) >= 0;

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Edit coverage — {row.state_code} / {humanize(row.pcr_section_code)}</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Required collected</Label>
            <Input type="number" min={0} value={requiredCollected} onChange={(e) => setRequiredCollected(e.target.value)} />
            <p className="text-xs text-muted-foreground">of {row.total_required} required attributes in this section.</p>
          </div>
          <Alert variant="info">
            <AlertDescription>
              Records what this State reports it collects. Completion % recomputes on save. The
              current PCR form defines no optional tier, so only required attributes are reported.
            </AlertDescription>
          </Alert>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!valid || busy}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
