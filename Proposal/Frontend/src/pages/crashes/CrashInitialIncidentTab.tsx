import * as React from 'react';
import { ClipboardList, Eye, EyeOff, MapPin, Pencil, Plus, Send, Trash2, Truck, Users } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { InjuryBadge, StatusChip } from '@/components/shell/StatusBadge';
import { OmbControlNumber } from '@/components/shell/OmbControlNumber';
import { useApi } from '@/lib/useApi';
import { crashApi, iifApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { INJURY_OPTIONS, NON_MOTORIST_KINDS, PERSON_TYPES, PHONE_TYPES, US_STATES, VEHICLE_CLASS_OPTIONS } from '@/lib/constants';
import { humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';
import type { IncidentPerson, IncidentVehicle } from '@/lib/types';

export function CrashInitialIncidentTab() {
  const { crash, reload } = useCrash();
  const { user } = useAuth();
  const canWrite = hasPermission(user, 'initial_incident:write');
  const canSubmit = hasPermission(user, 'initial_incident:submit');
  const canDelete = hasPermission(user, 'initial_incident:delete');
  // INIT-4: the general-info/location card edits fields the FORM collects
  // (documentation §8.2), so form writers may edit it — the MCSAP Inspector owns
  // the form but holds only `crash:read` (§ role table l.127: update on the form,
  // view on crash records). Writers save through the IIF endpoint; holders of
  // `crash:update` who cannot write the form still edit it via PATCH /crashes.
  const canEditCrash = canWrite || hasPermission(user, 'crash:update');

  const { data: iif, loading, error, reload: reloadIif } = useApi(() => iifApi.get(crash.id).catch(() => null), [crash.id]);
  const { data: vehicles, loading: vLoading, reload: reloadVehicles } = useApi(() => iifApi.vehicles(crash.id).catch(() => []), [crash.id]);
  const { data: persons, loading: pLoading, reload: reloadPersons } = useApi(() => iifApi.persons(crash.id).catch(() => []), [crash.id]);

  const [summary, setSummary] = React.useState('');
  React.useEffect(() => { setSummary(iif?.event_summary ?? ''); }, [iif?.event_summary]);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ kind: 'error' | 'success'; text: string } | null>(null);

  const routed = iif?.status === 'ROUTED';

  async function save() {
    setBusy(true); setMsg(null);
    try { await iifApi.save(crash.id, { event_summary: summary }); reloadIif(); setMsg({ kind: 'success', text: 'Form saved.' }); }
    catch (e) { setMsg({ kind: 'error', text: e instanceof ApiError ? e.message : 'Save failed' }); }
    finally { setBusy(false); }
  }
  async function submit() {
    setBusy(true); setMsg(null);
    try {
      const r = await iifApi.submit(crash.id);
      reloadIif(); reload();
      // Name the routing outcome, not just the recipient count. A crash that
      // could not be classified reaches neither CIPSEA routing branch, and
      // reporting only "notified N user(s)" made that indistinguishable from a
      // correctly routed submission — which is how the missing BTS routing went
      // unnoticed. An unclassified result is a warning, not a success.
      const routing = r.routed_to_bts
        ? ' · routed to BTS CIPSEA'
        : r.routed_out_of_scope
          ? ' · retained by the CCFP Project Team (out of scope)'
          : r.routed_unclassified
            ? ' · scope undetermined — NOT routed for interview or retention; the CCFP Project Team was asked to complete the crash facts'
            : '';
      setMsg({
        kind: r.routed_unclassified ? 'error' : 'success',
        text: `Submitted & routed. DOT ${r.dot_number_validated ? 'validated' : 'NOT validated'} via SafeSpect · notified ${r.notified_users} user(s)${routing}.`,
      });
    } catch (e) { setMsg({ kind: 'error', text: e instanceof ApiError ? e.message : 'Submit failed' }); }
    finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setMsg(null);
    try { await iifApi.remove(crash.id); reloadIif(); setMsg({ kind: 'success', text: 'Form deleted.' }); }
    catch (e) { setMsg({ kind: 'error', text: e instanceof ApiError ? e.message : 'Delete failed' }); }
    finally { setBusy(false); }
  }

  const [vehDialog, setVehDialog] = React.useState<IncidentVehicle | 'new' | null>(null);
  const [perDialog, setPerDialog] = React.useState<IncidentPerson | 'new' | null>(null);

  return (
    <div className="space-y-4">
      {/* PRA / OMB control-number notice — this tab is a public information-collection instrument (§14.1). */}
      <OmbControlNumber compact />
      {/* IIF form */}
      <Card>
        <CardHeader>
          <CardHeading
            icon={ClipboardList}
            title="Initial Incident Form"
            description="Created within 24–48 hours of the crash."
            actions={iif ? <StatusChip status={iif.status} /> : <Badge variant="neutral">Not started</Badge>}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? <Skeleton className="h-24 w-full" /> : (
            <>
              {error ? <Alert variant="destructive"><AlertDescription>{error.message}</AlertDescription></Alert> : null}
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                  <div className="text-eyebrow">DOT validated</div>
                  <div className="mt-0.5">{iif?.dot_number_validated ? <span className="text-success-green-700">Yes · {iif.dot_validation_source}</span> : <span className="text-muted-foreground">No</span>}</div>
                </div>
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                  <div className="text-eyebrow">Submitted</div>
                  <div className="mt-0.5 text-muted-foreground">{iif?.submitted_at ? humanize(iif.status) : '—'}</div>
                </div>
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                  <div className="text-eyebrow">Routed</div>
                  <div className="mt-0.5 text-muted-foreground">{iif?.routed_at ? 'Yes' : '—'}</div>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="summary">Event summary</Label>
                <Textarea id="summary" rows={4} value={summary} disabled={!canWrite || routed} onChange={(e) => setSummary(e.target.value)} placeholder="Short description of the crash event…" />
              </div>
              {msg ? <Alert variant={msg.kind === 'error' ? 'destructive' : 'success'}><AlertDescription>{msg.text}</AlertDescription></Alert> : null}
              {canWrite ? (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={save} disabled={busy || routed} variant="outline">Save form</Button>
                  {canSubmit ? <Button onClick={submit} disabled={busy || routed}><Send className="h-4 w-4" /> Submit & route</Button> : null}
                  {canDelete && iif && !routed ? <Button onClick={remove} disabled={busy} variant="destructive"><Trash2 className="h-4 w-4" /> Delete</Button> : null}
                </div>
              ) : null}
              {routed ? <p className="text-xs text-muted-foreground">This form has been routed and is locked from further edits.</p> : null}
            </>
          )}
        </CardContent>
      </Card>

      {/* General information & location (INIT-4) — editable post-creation via PATCH /crashes/{id}. */}
      <GeneralInfoCard canEdit={canEditCrash && !routed} viaForm={canWrite} />

      {/* Vehicles */}
      <Card>
        <CardHeader>
          <CardHeading icon={Truck} title="Vehicles" description="CMV and non-CMV vehicles involved."
            actions={canWrite ? <Button size="xs" onClick={() => setVehDialog('new')}><Plus className="h-3.5 w-3.5" /> Add vehicle</Button> : undefined} />
        </CardHeader>
        <CardContent className="p-0">
          {vLoading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (vehicles?.length ?? 0) === 0 ? (
            <div className="p-5"><EmptyState icon={Truck} title="No vehicles" description="Add the vehicles involved in this crash." /></div>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead className="pl-5">#</TableHead><TableHead>Type</TableHead><TableHead>Class / GVWR</TableHead><TableHead>U.S. DOT</TableHead>
                <TableHead>Make</TableHead><TableHead>Carrier</TableHead><TableHead className="text-right">Occ.</TableHead>
                {canWrite ? <TableHead className="pr-5 text-right">Actions</TableHead> : null}
              </TableRow></TableHeader>
              <TableBody>
                {vehicles!.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="pl-5 tabular-nums">{v.vehicle_number}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1.5">
                        {v.is_cmv ? <Badge variant="info" size="sm">CMV</Badge> : <Badge variant="neutral" size="sm">Non-CMV</Badge>}
                        {v.is_supplemental ? <Badge variant="warning" size="sm">Supplemental</Badge> : null}
                        {v._pendingSync ? <Badge variant="warning" size="sm">Not yet synced</Badge> : null}
                      </span>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {v.vehicle_class ? `Class ${v.vehicle_class}` : v.gvwr_lbs != null ? `${v.gvwr_lbs.toLocaleString()} lbs` : '—'}
                    </TableCell>
                    <TableCell className="tabular-nums">{v.us_dot_number ?? '—'}</TableCell>
                    <TableCell>{v.make ?? '—'}</TableCell>
                    <TableCell>{v.carrier_name ?? '—'}</TableCell>
                    <TableCell className="text-right tabular-nums">{v.num_occupants ?? '—'}</TableCell>
                    {canWrite ? (
                      <TableCell className="pr-5 text-right">
                        {/* No server id until this syncs — see the persons table. */}
                        <Button size="icon-sm" variant="ghost" disabled={v._pendingSync} title={v._pendingSync ? 'Available once this record syncs' : undefined} onClick={() => setVehDialog(v)}><Pencil className="h-3.5 w-3.5" /></Button>
                        <Button size="icon-sm" variant="ghost" disabled={v._pendingSync} title={v._pendingSync ? 'Available once this record syncs' : undefined} onClick={async () => { await iifApi.deleteVehicle(crash.id, v.id); reloadVehicles(); }}><Trash2 className="h-3.5 w-3.5 text-alert-red" /></Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Persons */}
      <Card>
        <CardHeader>
          <CardHeading icon={Users} title="Persons" description="Drivers, occupants, non-motorists, and witnesses."
            actions={canWrite ? <Button size="xs" onClick={() => setPerDialog('new')}><Plus className="h-3.5 w-3.5" /> Add person</Button> : undefined} />
        </CardHeader>
        <CardContent className="p-0">
          {pLoading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (persons?.length ?? 0) === 0 ? (
            <div className="p-5"><EmptyState icon={Users} title="No persons" description="Add drivers, occupants, non-motorists, or witnesses." /></div>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead className="pl-5">Type</TableHead><TableHead>Name</TableHead><TableHead>Veh.</TableHead>
                <TableHead className="text-center">Injury</TableHead><TableHead>Contact</TableHead>
                {canWrite ? <TableHead className="pr-5 text-right">Actions</TableHead> : null}
              </TableRow></TableHeader>
              <TableBody>
                {persons!.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="pl-5">
                      <span className="inline-flex items-center gap-1.5">
                        {humanize(p.person_type)}
                        {p.is_supplemental ? <Badge variant="warning" size="sm">Supplemental</Badge> : null}
                        {/* Entered offline and still queued. Shown so the record is
                            never mistaken for one the server has accepted. */}
                        {p._pendingSync ? <Badge variant="warning" size="sm">Not yet synced</Badge> : null}
                      </span>
                    </TableCell>
                    <TableCell>
                      {p.pii_redacted ? (
                        <span className="inline-flex items-center gap-1 text-muted-foreground"><EyeOff className="h-3.5 w-3.5" /> Restricted (PII)</span>
                      ) : (
                        <span className="inline-flex items-center gap-1"><Eye className="h-3.5 w-3.5 text-muted-foreground" /> {p.full_name ?? '—'}{p.is_minor ? ' · minor' : ''}</span>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">{p.related_vehicle_number ?? '—'}</TableCell>
                    <TableCell className="text-center"><InjuryBadge injury={p.injury} /></TableCell>
                    <TableCell className="text-muted-foreground">{p.pii_redacted ? '—' : p.phone_primary ?? '—'}</TableCell>
                    {canWrite ? (
                      <TableCell className="pr-5 text-right">
                        {/* A record that has not synced has no server id yet — its
                            only identifier is the client key. Editing or deleting
                            it would address a row the server has never seen, 404,
                            and throw the change away. Disabled until it syncs. */}
                        <Button size="icon-sm" variant="ghost" disabled={p._pendingSync} title={p._pendingSync ? 'Available once this record syncs' : undefined} onClick={() => setPerDialog(p)}><Pencil className="h-3.5 w-3.5" /></Button>
                        <Button size="icon-sm" variant="ghost" disabled={p._pendingSync} title={p._pendingSync ? 'Available once this record syncs' : undefined} onClick={async () => { await iifApi.deletePerson(crash.id, p.id); reloadPersons(); }}><Trash2 className="h-3.5 w-3.5 text-alert-red" /></Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {vehDialog ? <VehicleDialog crashId={crash.id} vehicle={vehDialog === 'new' ? null : vehDialog} onClose={() => setVehDialog(null)} onSaved={reloadVehicles} /> : null}
      {perDialog ? <PersonDialog crashId={crash.id} person={perDialog === 'new' ? null : perDialog} onClose={() => setPerDialog(null)} onSaved={reloadPersons} /> : null}
    </div>
  );
}

/**
 * General-information & crash-location card on the IIF tab (INIT-4, documentation
 * §8.2 / §19.1). Pre-fills from the crash and PATCHes the changed fields via the
 * existing `crashApi.update` (PATCH /crashes/{id}); the backend audits every save
 * and `model_dump(exclude_unset=True)` leaves omitted fields untouched. Editing is
 * gated on `crash:update` (the `canEdit` prop) — when false the values render
 * read-only with no Save control. Reuses the same field set as NewCrashDialog.
 */
function GeneralInfoCard({ canEdit, viaForm }: { canEdit: boolean; viaForm: boolean }) {
  const { crash, reload } = useCrash();

  const initial = React.useMemo(
    () => ({
      local_report_number: crash.local_report_number ?? '',
      crash_date: crash.crash_date ?? '',
      crash_time: (crash.crash_time ?? '').slice(0, 5),
      state_code: crash.state_code ?? '',
      city: crash.city ?? '',
      county: crash.county ?? '',
      street_highway: crash.street_highway ?? '',
      num_vehicles: crash.num_vehicles?.toString() ?? '',
      num_persons: crash.num_persons?.toString() ?? '',
      num_fatalities: crash.num_fatalities?.toString() ?? '',
    }),
    [crash],
  );

  const [form, setForm] = React.useState(initial);
  React.useEffect(() => { setForm(initial); }, [initial]);

  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ kind: 'error' | 'success'; text: string } | null>(null);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const dirty = React.useMemo(
    () => (Object.keys(form) as (keyof typeof form)[]).some((k) => form[k] !== initial[k]),
    [form, initial],
  );

  async function save() {
    setBusy(true); setMsg(null);
    // Send only the known general-info/location fields; the backend leaves any
    // omitted field untouched (exclude_unset). Empty text -> null; empty count -> null.
    const body = {
      local_report_number: form.local_report_number || null,
      crash_date: form.crash_date || null,
      crash_time: form.crash_time || null,
      state_code: form.state_code || null,
      city: form.city || null,
      county: form.county || null,
      street_highway: form.street_highway || null,
      num_vehicles: form.num_vehicles ? Number(form.num_vehicles) : null,
      num_persons: form.num_persons ? Number(form.num_persons) : null,
      num_fatalities: form.num_fatalities ? Number(form.num_fatalities) : null,
    };
    try {
      // Form writers save through the IIF endpoint (initial_incident:write), which
      // applies these fields to the crash. Callers who only hold `crash:update`
      // keep the direct PATCH path.
      if (viaForm) await iifApi.save(crash.id, body);
      else await crashApi.update(crash.id, body);
      reload(); // refresh the detail header / Overview with the saved values
      setMsg({ kind: 'success', text: 'General information saved.' });
    } catch (e) {
      setMsg({ kind: 'error', text: e instanceof ApiError ? e.message : 'Save failed' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={MapPin}
          title="General information & location"
          description="Crash report number, date/time, counts, and location."
        />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="gi-state">State</Label>
            <Select id="gi-state" value={form.state_code} onChange={set('state_code')} disabled={!canEdit}>
              <option value="">Select…</option>
              {US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-local">Local report #</Label>
            <Input id="gi-local" value={form.local_report_number} onChange={set('local_report_number')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-date">Crash date</Label>
            <Input id="gi-date" type="date" value={form.crash_date} onChange={set('crash_date')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-time">Crash time</Label>
            <Input id="gi-time" type="time" value={form.crash_time} onChange={set('crash_time')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-city">City</Label>
            <Input id="gi-city" value={form.city} onChange={set('city')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-county">County</Label>
            <Input id="gi-county" value={form.county} onChange={set('county')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="gi-road">Street / highway</Label>
            <Input id="gi-road" value={form.street_highway} onChange={set('street_highway')} disabled={!canEdit} placeholder="e.g. I-70 near MM 252" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-veh"># Vehicles</Label>
            <Input id="gi-veh" type="number" min={0} value={form.num_vehicles} onChange={set('num_vehicles')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-per"># Persons</Label>
            <Input id="gi-per" type="number" min={0} value={form.num_persons} onChange={set('num_persons')} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gi-fat"># Fatalities</Label>
            <Input id="gi-fat" type="number" min={0} value={form.num_fatalities} onChange={set('num_fatalities')} disabled={!canEdit} />
          </div>
        </div>
        {msg ? <Alert variant={msg.kind === 'error' ? 'destructive' : 'success'}><AlertDescription>{msg.text}</AlertDescription></Alert> : null}
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={save} disabled={busy || !dirty} variant="outline">Save general information</Button>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">You do not have permission to edit crash general information.</p>
        )}
      </CardContent>
    </Card>
  );
}

function VehicleDialog({ crashId, vehicle, onClose, onSaved }: { crashId: string; vehicle: IncidentVehicle | null; onClose: () => void; onSaved: () => void }) {
  // Stable for the life of the dialog — see PersonDialog.
  const [clientUuid] = React.useState(() => crypto.randomUUID());
  const [f, setF] = React.useState({
    vehicle_number: vehicle?.vehicle_number?.toString() ?? '',
    is_cmv: vehicle?.is_cmv ?? false,
    vehicle_class: vehicle?.vehicle_class ?? '',
    gvwr_lbs: vehicle?.gvwr_lbs?.toString() ?? '',
    us_dot_number: vehicle?.us_dot_number ?? '',
    make: vehicle?.make ?? '',
    num_occupants: vehicle?.num_occupants?.toString() ?? '',
    num_injured_occupants: vehicle?.num_injured_occupants?.toString() ?? '',
    carrier_name: vehicle?.carrier_name ?? '',
    carrier_phone: vehicle?.carrier_phone ?? '',
    is_supplemental: vehicle?.is_supplemental ?? false,
  });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const dotValid = !f.us_dot_number || /^[0-9]{1,8}$/.test(f.us_dot_number);
  const valid = f.vehicle_number !== '' && dotValid;

  async function save() {
    setBusy(true); setError(null);
    const body = {
      vehicle_number: Number(f.vehicle_number),
      is_cmv: f.is_cmv,
      vehicle_class: f.vehicle_class || null,
      gvwr_lbs: f.gvwr_lbs ? Number(f.gvwr_lbs) : null,
      us_dot_number: f.us_dot_number || null,
      make: f.make || null,
      num_occupants: f.num_occupants ? Number(f.num_occupants) : null,
      num_injured_occupants: f.num_injured_occupants ? Number(f.num_injured_occupants) : null,
      carrier_name: f.carrier_name || null,
      carrier_phone: f.carrier_phone || null,
      is_supplemental: f.is_supplemental,
    };
    try {
      if (vehicle) await iifApi.updateVehicle(crashId, vehicle.id, body);
      // Same key for every Save attempt on this vehicle, so a retry after a lost
      // response replays rather than colliding with its own earlier write.
      else await iifApi.addVehicle(crashId, { ...body, client_uuid: clientUuid });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>{vehicle ? 'Edit vehicle' : 'Add vehicle'}</DialogTitle></DialogHeader>
        <div className="grid max-h-[60vh] -mr-6 gap-3 overflow-y-auto py-4 pr-6 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Vehicle # *</Label><Input type="number" min={1} value={f.vehicle_number} onChange={(e) => setF({ ...f, vehicle_number: e.target.value })} /></div>
          <label className="flex items-end gap-2 pb-2 text-sm"><Checkbox checked={f.is_cmv} onChange={(e) => setF({ ...f, is_cmv: e.target.checked })} /> Commercial motor vehicle</label>
          <div className="space-y-1.5">
            <Label>U.S. DOT #</Label>
            <Input value={f.us_dot_number} onChange={(e) => setF({ ...f, us_dot_number: e.target.value })} />
            {!dotValid ? <p className="text-xs text-destructive">Must be 1–8 digits.</p> : null}
          </div>
          {/* Vehicle class and GVWR are what the qualifying-crash rule is
              actually written against (Class 7/8, GVWR >= 26,001 lbs). Without
              them the classifier could only infer "heavy-duty" from the CMV
              checkbox above, which a Class 3 box truck also satisfies. Optional:
              an inspector filing within 24-48h may not know the GVWR yet. */}
          <div className="space-y-1.5">
            <Label htmlFor="veh-class">Vehicle class</Label>
            <Select id="veh-class" value={f.vehicle_class} onChange={(e) => setF({ ...f, vehicle_class: e.target.value })}>
              <option value="">Not recorded</option>
              {VEHICLE_CLASS_OPTIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="veh-gvwr">GVWR (lbs)</Label>
            <Input id="veh-gvwr" type="number" min={0} value={f.gvwr_lbs} onChange={(e) => setF({ ...f, gvwr_lbs: e.target.value })} />
          </div>
          <div className="space-y-1.5"><Label>Make</Label><Input value={f.make} onChange={(e) => setF({ ...f, make: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Occupants</Label><Input type="number" min={0} value={f.num_occupants} onChange={(e) => setF({ ...f, num_occupants: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Injured occupants</Label><Input type="number" min={0} value={f.num_injured_occupants} onChange={(e) => setF({ ...f, num_injured_occupants: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Carrier name</Label><Input value={f.carrier_name} onChange={(e) => setF({ ...f, carrier_name: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Carrier phone</Label><Input value={f.carrier_phone} onChange={(e) => setF({ ...f, carrier_phone: e.target.value })} /></div>
          <label className="flex items-end gap-2 pb-2 text-sm sm:col-span-2"><Checkbox checked={f.is_supplemental} onChange={(e) => setF({ ...f, is_supplemental: e.target.checked })} /> Supplemental record</label>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={!valid || busy}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PersonDialog({ crashId, person, onClose, onSaved }: { crashId: string; person: IncidentPerson | null; onClose: () => void; onSaved: () => void }) {
  // Stable for the life of the dialog so every Save attempt for this one person
  // carries the same idempotency key.
  const [clientUuid] = React.useState(() => crypto.randomUUID());
  const [f, setF] = React.useState({
    person_type: person?.person_type ?? 'DRIVER',
    related_vehicle_number: person?.related_vehicle_number?.toString() ?? '',
    name_last: person?.name_last ?? '',
    name_first: person?.name_first ?? '',
    name_middle: person?.name_middle ?? '',
    is_minor: person?.is_minor ?? false,
    primary_language: person?.primary_language ?? '',
    address: person?.address ?? '',
    phone_primary: person?.phone_primary ?? '',
    phone_primary_type: person?.phone_primary_type ?? '',
    phone_secondary: person?.phone_secondary ?? '',
    phone_secondary_type: person?.phone_secondary_type ?? '',
    non_motorist_kind: person?.non_motorist_kind ?? '',
    injury: person?.injury ?? '',
    is_supplemental: person?.is_supplemental ?? false,
  });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    const body = {
      person_type: f.person_type,
      related_vehicle_number: f.related_vehicle_number ? Number(f.related_vehicle_number) : null,
      name_last: f.name_last || null,
      name_first: f.name_first || null,
      name_middle: f.name_middle || null,
      is_minor: f.is_minor,
      primary_language: f.primary_language || null,
      address: f.address || null,
      phone_primary: f.phone_primary || null,
      phone_primary_type: f.phone_primary_type || null,
      phone_secondary: f.phone_secondary || null,
      phone_secondary_type: f.phone_secondary_type || null,
      // Only send the non-motorist kind when the type is NON_MOTORIST (the
      // backend rejects it otherwise); clear it for any other type.
      non_motorist_kind: f.person_type === 'NON_MOTORIST' ? f.non_motorist_kind || null : null,
      injury: f.injury || null,
      is_supplemental: f.is_supplemental,
    };
    try {
      if (person) await iifApi.updatePerson(crashId, person.id, body);
      // One key per record, minted when the dialog opens — not per attempt. If
      // the user presses Save again after a lost response, the same key replays
      // and the server returns the row it already created instead of adding a
      // second person.
      else await iifApi.addPerson(crashId, { ...body, client_uuid: clientUuid });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>{person ? 'Edit person' : 'Add person'}</DialogTitle></DialogHeader>
        <div className="grid max-h-[60vh] -mr-6 gap-3 overflow-y-auto py-4 pr-6 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Type *</Label>
            <Select value={f.person_type} onChange={(e) => setF({ ...f, person_type: e.target.value as typeof f.person_type })}>
              {PERSON_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5"><Label>Related vehicle #</Label><Input type="number" min={1} value={f.related_vehicle_number} onChange={(e) => setF({ ...f, related_vehicle_number: e.target.value })} /></div>
          {/* Non-motorist kind (INIT-3): only meaningful when the type is NON_MOTORIST. */}
          {f.person_type === 'NON_MOTORIST' ? (
            <div className="space-y-1.5"><Label>Non-motorist kind</Label>
              <Select value={f.non_motorist_kind} onChange={(e) => setF({ ...f, non_motorist_kind: e.target.value })}>
                <option value="">—</option>
                {NON_MOTORIST_KINDS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </div>
          ) : null}
          {/* Structured name parts (INIT-1); the API derives full_name from these. */}
          <div className="space-y-1.5"><Label>Last name</Label><Input value={f.name_last} onChange={(e) => setF({ ...f, name_last: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>First name</Label><Input value={f.name_first} onChange={(e) => setF({ ...f, name_first: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Middle name</Label><Input value={f.name_middle} onChange={(e) => setF({ ...f, name_middle: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Injury</Label>
            <Select value={f.injury} onChange={(e) => setF({ ...f, injury: e.target.value })}>
              <option value="">—</option>
              {INJURY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5"><Label>Primary language</Label><Input value={f.primary_language} onChange={(e) => setF({ ...f, primary_language: e.target.value })} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label>Address</Label><Input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></div>
          {/* Two phones, each with a Home/Cell/Work type (INIT-2). */}
          <div className="space-y-1.5"><Label>Phone 1</Label><Input value={f.phone_primary} onChange={(e) => setF({ ...f, phone_primary: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Phone 1 type</Label>
            <Select value={f.phone_primary_type} onChange={(e) => setF({ ...f, phone_primary_type: e.target.value })}>
              <option value="">—</option>
              {PHONE_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5"><Label>Phone 2</Label><Input value={f.phone_secondary} onChange={(e) => setF({ ...f, phone_secondary: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Phone 2 type</Label>
            <Select value={f.phone_secondary_type} onChange={(e) => setF({ ...f, phone_secondary_type: e.target.value })}>
              <option value="">—</option>
              {PHONE_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          <label className="flex items-end gap-2 pb-2 text-sm"><Checkbox checked={f.is_minor} onChange={(e) => setF({ ...f, is_minor: e.target.checked })} /> Minor</label>
          <label className="flex items-end gap-2 pb-2 text-sm"><Checkbox checked={f.is_supplemental} onChange={(e) => setF({ ...f, is_supplemental: e.target.checked })} /> Supplemental record</label>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={busy}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
