import * as React from 'react';
import { ClipboardCheck, Compass, FileWarning, Gauge, MapPin } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Select } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { DefList } from '@/components/crash/DefList';
import {
  CompletenessBadge, PhaseBadge, QcStatusBadge, ScopeBadge,
} from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { crashApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { LIFECYCLE_PHASES, PHASE_INDEX, SCOPE_OPTIONS, US_STATES } from '@/lib/constants';
import { formatDate, formatTime } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type { Crash, CrashLifecyclePhase } from '@/lib/types';
import { useCrash } from './CrashContext';

export function CrashOverviewTab() {
  const { crash, reload } = useCrash();
  const { user } = useAuth();
  const canClassify = hasPermission(user, 'crash:update');
  // Re-running a derived classification is not the same privilege as overriding
  // it. The MCSAP CMV Inspector authors the incident facts the classifier reads
  // but holds no crash:update, so gating the re-run button on crash:update left
  // the role that files the form unable to correct the classification its own
  // submission produced. Mirrors require("crash:update","initial_incident:write")
  // on POST /crashes/{id}/scope/reclassify.
  const canReclassify = canClassify || hasPermission(user, 'initial_incident:write');

  const { data: scope, loading: scopeLoading, reload: reloadScope } = useApi(() => crashApi.scope(crash.id).catch(() => null), [crash.id]);
  const { data: completeness, loading: compLoading } = useApi(() => crashApi.completeness(crash.id).catch(() => null), [crash.id]);
  const { data: quality, loading: qcLoading } = useApi(() => crashApi.quality(crash.id).catch(() => []), [crash.id]);

  const [scopeOpen, setScopeOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [reclassifying, setReclassifying] = React.useState(false);
  const [advancing, setAdvancing] = React.useState(false);
  const [phaseError, setPhaseError] = React.useState<string | null>(null);

  // Next forward lifecycle phase (CRAS-4); null once the crash reaches PUBLICATION.
  const currentPhaseIndex = PHASE_INDEX[crash.lifecycle_phase];
  const nextPhase: CrashLifecyclePhase | null =
    LIFECYCLE_PHASES.find((p) => p.index === currentPhaseIndex + 1)?.key ?? null;

  async function reclassify() {
    setReclassifying(true);
    try {
      await crashApi.reclassifyScope(crash.id);
      reloadScope();
      reload();
    } finally {
      setReclassifying(false);
    }
  }

  async function advance() {
    if (!nextPhase) return;
    setAdvancing(true); setPhaseError(null);
    try {
      await crashApi.advancePhase(crash.id, nextPhase);
      reload();
    } catch (e) {
      setPhaseError(e instanceof ApiError ? e.message : 'Failed to advance phase');
    } finally {
      setAdvancing(false);
    }
  }

  const qcSummary = React.useMemo(() => {
    const list = quality ?? [];
    return {
      pass: list.filter((r) => r.status === 'PASS').length,
      fail: list.filter((r) => r.status === 'FAIL').length,
      warn: list.filter((r) => r.status === 'WARNING').length,
    };
  }, [quality]);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardHeading
            icon={MapPin}
            title="Crash details"
            description="Core attributes of this crash record."
            actions={canClassify ? (
              <div className="flex items-center gap-2">
                <Button size="xs" variant="outline" onClick={() => setEditOpen(true)}>Edit</Button>
                {nextPhase ? (
                  <Button size="xs" variant="outline" onClick={advance} disabled={advancing}>
                    {advancing ? 'Advancing…' : `Advance to ${LIFECYCLE_PHASES[currentPhaseIndex + 1].short}`}
                  </Button>
                ) : null}
              </div>
            ) : undefined}
          />
        </CardHeader>
        <CardContent>
          {phaseError ? <p className="mb-3 text-sm text-destructive">{phaseError}</p> : null}
          <DefList
            items={[
              { label: 'CCFP identifier', value: <span className="font-medium">{crash.ccfp_identifier}</span> },
              { label: 'Lifecycle phase', value: <PhaseBadge phase={crash.lifecycle_phase} /> },
              { label: 'Crash date', value: formatDate(crash.crash_date) },
              { label: 'Crash time', value: formatTime(crash.crash_time) },
              { label: 'City', value: crash.city },
              { label: 'County', value: crash.county },
              { label: 'State', value: crash.state_code },
              { label: 'Street / highway', value: crash.street_highway },
              { label: 'Local report #', value: crash.local_report_number },
              { label: 'Coordinates', value: crash.latitude && crash.longitude ? `${crash.latitude}, ${crash.longitude}` : '—' },
              { label: 'Vehicles', value: crash.num_vehicles },
              { label: 'Persons', value: crash.num_persons },
              { label: 'Fatalities', value: crash.num_fatalities },
            ]}
          />
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardHeading
              icon={Compass}
              title="Scope"
              description="Qualifying / in-scope classification."
              actions={canReclassify ? (
                <div className="flex items-center gap-2">
                  <Button size="xs" variant="outline" onClick={reclassify} disabled={reclassifying}>
                    {reclassifying ? 'Classifying…' : 'Re-run classification'}
                  </Button>
                  {canClassify ? (
                    <Button size="xs" variant="outline" onClick={() => setScopeOpen(true)}>Edit</Button>
                  ) : null}
                </div>
              ) : undefined}
            />
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {scopeLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : scope ? (
              <>
                <div className="flex items-center gap-2"><ScopeBadge scope={scope.scope} />{scope.is_supplemental ? <span className="text-xs text-muted-foreground">Supplemental</span> : null}</div>
                <div className="text-muted-foreground">{scope.is_qualifying ? 'Qualifying crash' : 'Not marked qualifying'}</div>
                {scope.classification_reason ? <p className="text-xs text-muted-foreground">{scope.classification_reason}</p> : null}
                {/* A manually set value is deliberately excluded from automatic
                    re-derivation, so say so rather than letting it look stale. */}
                {scope.is_manual_override ? (
                  <p className="text-xs text-muted-foreground">Manually set — not updated automatically. Re-run classification to return to automatic upkeep.</p>
                ) : null}
              </>
            ) : (
              <p className="text-muted-foreground">Not classified.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardHeading icon={ClipboardCheck} title="Completeness" description="Current completeness status." />
          </CardHeader>
          <CardContent className="text-sm">
            {compLoading ? <Skeleton className="h-10 w-full" /> : completeness ? (
              <CompletenessBadge status={completeness.status} locked={completeness.is_locked} />
            ) : <span className="text-muted-foreground">Not yet evaluated.</span>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardHeading icon={Gauge} title="Quality control" description="Latest QC results." />
          </CardHeader>
          <CardContent className="text-sm">
            {qcLoading ? <Skeleton className="h-10 w-full" /> : (quality?.length ?? 0) === 0 ? (
              <span className="inline-flex items-center gap-1 text-muted-foreground"><FileWarning className="h-4 w-4" /> Not yet evaluated.</span>
            ) : (
              <div className="flex flex-wrap gap-2">
                <QcStatusBadge status="PASS" /> <span className="tabular-nums">{qcSummary.pass}</span>
                <QcStatusBadge status="FAIL" /> <span className="tabular-nums">{qcSummary.fail}</span>
                <QcStatusBadge status="WARNING" /> <span className="tabular-nums">{qcSummary.warn}</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {canClassify && scopeOpen ? (
        <ScopeDialog crashId={crash.id} current={scope ?? null} onClose={() => setScopeOpen(false)} onSaved={() => { reloadScope(); reload(); }} />
      ) : null}
      {canClassify && editOpen ? (
        <CrashMetadataDialog crash={crash} onClose={() => setEditOpen(false)} onSaved={reload} />
      ) : null}
    </div>
  );
}

function ScopeDialog({
  crashId, current, onClose, onSaved,
}: {
  crashId: string;
  current: { scope: string; is_qualifying: boolean; is_supplemental: boolean; classification_reason: string | null } | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [scope, setScope] = React.useState(current?.scope ?? 'UNDETERMINED');
  const [qualifying, setQualifying] = React.useState(current?.is_qualifying ?? false);
  const [supplemental, setSupplemental] = React.useState(current?.is_supplemental ?? false);
  const [reason, setReason] = React.useState(current?.classification_reason ?? '');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    try {
      await crashApi.setScope(crashId, { scope, is_qualifying: qualifying, is_supplemental: supplemental, classification_reason: reason || null });
      onSaved(); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save scope');
    } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Classify crash scope</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="scope">Scope</Label>
              <Select id="scope" value={scope} onChange={(e) => setScope(e.target.value)}>
                {SCOPE_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </div>
            <label className="flex items-center gap-2 text-sm"><Checkbox checked={qualifying} onChange={(e) => setQualifying(e.target.checked)} /> Qualifying crash (≥1 fatality + Class 7/8 truck)</label>
            <label className="flex items-center gap-2 text-sm"><Checkbox checked={supplemental} onChange={(e) => setSupplemental(e.target.checked)} /> Supplemental (out-of-scope retained record)</label>
            <div className="space-y-1.5">
              <Label htmlFor="reason">Classification reason</Label>
              <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={busy}>Save classification</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Editable general-info / location metadata over the existing PATCH /crashes/{id}
// route (CRAS-3). Numeric fields (num_*, latitude, longitude) are held as strings
// while editing and coerced on save; lifecycle_phase is intentionally omitted
// (that is CRAS-4's job and is handled by the forward-only Advance control above).
type MetaField =
  | 'local_report_number' | 'crash_date' | 'crash_time'
  | 'city' | 'county' | 'state_code' | 'street_highway'
  | 'latitude' | 'longitude'
  | 'num_vehicles' | 'num_persons' | 'num_fatalities';

const NUMERIC_FIELDS: ReadonlySet<MetaField> = new Set<MetaField>([
  'latitude', 'longitude', 'num_vehicles', 'num_persons', 'num_fatalities',
]);

/** Render a crash value as the string an `<input>`/`<select>` expects. */
function toInput(v: Crash[MetaField]): string {
  return v == null ? '' : String(v);
}

function CrashMetadataDialog({
  crash, onClose, onSaved,
}: {
  crash: Crash;
  onClose: () => void;
  onSaved: () => void;
}) {
  const initial = React.useMemo<Record<MetaField, string>>(() => ({
    local_report_number: toInput(crash.local_report_number),
    crash_date: toInput(crash.crash_date),
    crash_time: toInput(crash.crash_time),
    city: toInput(crash.city),
    county: toInput(crash.county),
    state_code: toInput(crash.state_code),
    street_highway: toInput(crash.street_highway),
    latitude: toInput(crash.latitude),
    longitude: toInput(crash.longitude),
    num_vehicles: toInput(crash.num_vehicles),
    num_persons: toInput(crash.num_persons),
    num_fatalities: toInput(crash.num_fatalities),
  }), [crash]);

  const [form, setForm] = React.useState<Record<MetaField, string>>(initial);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const set = (k: MetaField) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save() {
    // Send only changed fields; coerce numerics to number | null, strings to
    // their value | null so a cleared input clears the column.
    const body: Record<string, string | number | null> = {};
    (Object.keys(initial) as MetaField[]).forEach((k) => {
      if (form[k] === initial[k]) return;
      const raw = form[k].trim();
      if (NUMERIC_FIELDS.has(k)) {
        body[k] = raw === '' ? null : Number(raw);
      } else {
        body[k] = raw === '' ? null : raw;
      }
    });
    if (Object.keys(body).length === 0) { onClose(); return; }

    setBusy(true); setError(null);
    try {
      await crashApi.update(crash.id, body);
      onSaved(); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to update crash details');
    } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader className="mb-0"><DialogTitle>Edit crash details</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] space-y-4 overflow-y-auto py-4 pr-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="m-state">State</Label>
              <Select id="m-state" value={form.state_code} onChange={set('state_code')}>
                <option value="">Select…</option>
                {US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-local">Local report #</Label>
              <Input id="m-local" value={form.local_report_number} onChange={set('local_report_number')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-date">Crash date</Label>
              <Input id="m-date" type="date" value={form.crash_date} onChange={set('crash_date')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-time">Crash time</Label>
              <Input id="m-time" type="time" value={form.crash_time} onChange={set('crash_time')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-city">City</Label>
              <Input id="m-city" value={form.city} onChange={set('city')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-county">County</Label>
              <Input id="m-county" value={form.county} onChange={set('county')} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="m-road">Street / highway</Label>
              <Input id="m-road" value={form.street_highway} onChange={set('street_highway')} placeholder="e.g. I-70 near MM 252" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-lat">Latitude</Label>
              <Input id="m-lat" type="number" step="any" value={form.latitude} onChange={set('latitude')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-lng">Longitude</Label>
              <Input id="m-lng" type="number" step="any" value={form.longitude} onChange={set('longitude')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-veh"># Vehicles</Label>
              <Input id="m-veh" type="number" min={0} value={form.num_vehicles} onChange={set('num_vehicles')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-per"># Persons</Label>
              <Input id="m-per" type="number" min={0} value={form.num_persons} onChange={set('num_persons')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-fat"># Fatalities</Label>
              <Input id="m-fat" type="number" min={0} value={form.num_fatalities} onChange={set('num_fatalities')} />
            </div>
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
