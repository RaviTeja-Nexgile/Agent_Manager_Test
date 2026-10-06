import * as React from 'react';
import { ClipboardList, Database, FileSearch, Gavel, Layers, Pencil, Plus, Trash2, Upload, Waypoints } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Spinner } from '@/components/ui/spinner';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MappingBadge, StatusChip } from '@/components/shell/StatusBadge';
import { Badge } from '@/components/ui/badge';
import { useApi } from '@/lib/useApi';
import { sourceApi, dataAttributeApi, dataMgmtApi, documentApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { US_STATES } from '@/lib/constants';
import { formatDate, formatDateTime, humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';
import { InvestigationForm } from './investigation/InvestigationForm';
import type {
  DataAttribute,
  EldFile,
  EldIssueSeverity,
  EldValidation,
  PostCrashInvestigation,
} from '@/lib/types';

export function CrashSourceDataTab() {
  return (
    <Tabs defaultValue="inspections">
      <TabsList>
        <TabsTrigger value="inspections">Inspections</TabsTrigger>
        <TabsTrigger value="investigations">Investigations</TabsTrigger>
        <TabsTrigger value="pcr">Police Crash Reports</TabsTrigger>
        <TabsTrigger value="reconstruction">Reconstruction</TabsTrigger>
        <TabsTrigger value="eld">ELD / eRODS</TabsTrigger>
        <TabsTrigger value="raw-aggregated">Raw / Aggregated</TabsTrigger>
      </TabsList>
      <TabsContent value="inspections"><InspectionsSection /></TabsContent>
      <TabsContent value="investigations"><InvestigationsSection /></TabsContent>
      <TabsContent value="pcr"><PcrSection /></TabsContent>
      <TabsContent value="reconstruction"><ReconstructionSection /></TabsContent>
      <TabsContent value="eld"><EldSection /></TabsContent>
      <TabsContent value="raw-aggregated"><RawAggregatedSection /></TabsContent>
    </Tabs>
  );
}

function useIngest() {
  const { user } = useAuth();
  return hasPermission(user, 'source_data:ingest');
}

// ─────────────── Inspections ───────────────
// §8.3: post-crash inspection data is expected within 7 days of the inspection.
// The backend derives `is_overdue`/`days_to_upload` against that window; this is a
// visibility badge only (late uploads are still accepted, never blocked).
function InspectionSlaBadge({ isOverdue, days }: { isOverdue: boolean; days: number | null }) {
  if (days === null) return <span className="text-xs text-muted-foreground">—</span>;
  const label = `${days}d`;
  return isOverdue ? (
    <Badge variant="destructive" title={`Uploaded ${days} days after inspection (over the 7-day window)`}>
      Overdue · {label}
    </Badge>
  ) : (
    <Badge variant="success" title={`Uploaded within the 7-day window (${days}d)`}>
      On time · {label}
    </Badge>
  );
}

function InspectionsSection() {
  const { crash } = useCrash();
  const canIngest = useIngest();
  const { data, loading, reload } = useApi(() => sourceApi.inspections(crash.id).catch(() => []), [crash.id]);
  const [open, setOpen] = React.useState(false);
  const [f, setF] = React.useState({ source_system: 'SafeSpect', inspection_number: '', inspection_date: '', inspector_name: '', violations_count: '', defects_count: '' });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    try {
      await sourceApi.addInspection(crash.id, {
        source_system: f.source_system, inspection_number: f.inspection_number || null, inspection_date: f.inspection_date || null,
        inspector_name: f.inspector_name || null, violations_count: f.violations_count ? Number(f.violations_count) : 0, defects_count: f.defects_count ? Number(f.defects_count) : 0,
      });
      setOpen(false); reload();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={FileSearch} title="Post-crash inspections" description="SafeSpect / approved inspection software."
          actions={canIngest ? <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Add</Button> : undefined} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={FileSearch} title="No inspections" description="Link post-crash inspection data." /></div>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">Inspection #</TableHead><TableHead>Source</TableHead><TableHead>Date</TableHead><TableHead>Inspector</TableHead><TableHead className="text-center">SLA (7-day)</TableHead><TableHead className="text-right">Violations</TableHead><TableHead className="pr-5 text-right">Defects</TableHead></TableRow></TableHeader>
            <TableBody>
              {data!.map((r) => (
                <TableRow key={r.id}><TableCell className="pl-5 font-medium">{r.inspection_number ?? '—'}</TableCell><TableCell>{r.source_system}</TableCell><TableCell>{formatDate(r.inspection_date)}</TableCell><TableCell>{r.inspector_name ?? '—'}</TableCell><TableCell className="text-center"><InspectionSlaBadge isOverdue={r.is_overdue} days={r.days_to_upload} /></TableCell><TableCell className="text-right tabular-nums">{r.violations_count ?? 0}</TableCell><TableCell className="pr-5 text-right tabular-nums">{r.defects_count ?? 0}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {open ? (
        <Dialog open onOpenChange={(v) => !v && setOpen(false)}>
          <DialogContent>
            <DialogHeader className="mb-0"><DialogTitle>Add inspection</DialogTitle></DialogHeader>
            <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5"><Label>Source system</Label><Input value={f.source_system} onChange={(e) => setF({ ...f, source_system: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Inspection #</Label><Input value={f.inspection_number} onChange={(e) => setF({ ...f, inspection_number: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Date</Label><Input type="date" value={f.inspection_date} onChange={(e) => setF({ ...f, inspection_date: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Inspector</Label><Input value={f.inspector_name} onChange={(e) => setF({ ...f, inspector_name: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Violations</Label><Input type="number" min={0} value={f.violations_count} onChange={(e) => setF({ ...f, violations_count: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Defects</Label><Input type="number" min={0} value={f.defects_count} onChange={(e) => setF({ ...f, defects_count: e.target.value })} /></div>
              </div>
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
            <DialogFooter className="mt-0"><Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button><Button onClick={save} disabled={busy}>Save</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </Card>
  );
}

// ─────────────── Investigations ───────────────
// PCI-2: the post-crash investigation is the full §19.2 (Appendix B) field
// inventory. The list table is the entry point: a small "Add" dialog creates the
// shell (header fields), then the sectioned editor (InvestigationForm) captures
// the structured single-valued sections, repeating structures (PCI-4),
// conditional hazmat/towed sections (PCI-5), required markers (PCI-3), and ELD
// summary inputs (PCI-7). Editing is gated by source_data:ingest; read-only users
// open the same editor to view values.
function InvestigationsSection() {
  const { crash } = useCrash();
  const canIngest = useIngest();
  const { data, loading, reload } = useApi(() => sourceApi.investigations(crash.id).catch(() => []), [crash.id]);
  const [addOpen, setAddOpen] = React.useState(false);
  const [f, setF] = React.useState({ case_number: '', inspection_number: '', officer_name: '', officer_id: '', post_crash_date: '' });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // The investigation currently open in the sectioned editor (null = closed).
  const [editing, setEditing] = React.useState<PostCrashInvestigation | null>(null);

  async function createShell() {
    setBusy(true); setError(null);
    try {
      // Create the shell with just the header fields, then open it in the editor
      // so the section data can be filled in and saved via PATCH.
      const created = await sourceApi.addInvestigation(crash.id, {
        case_number: f.case_number || null, inspection_number: f.inspection_number || null,
        officer_name: f.officer_name || null, officer_id: f.officer_id || null, post_crash_date: f.post_crash_date || null,
      });
      setAddOpen(false);
      setF({ case_number: '', inspection_number: '', officer_name: '', officer_id: '', post_crash_date: '' });
      reload();
      setEditing(created);
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={ClipboardList} title="Post-crash investigations" description="Heavy-Duty Truck Study investigation form."
          actions={canIngest ? <Button size="sm" onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Add</Button> : undefined} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={ClipboardList} title="No investigations" /></div>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">Case #</TableHead><TableHead>Officer</TableHead><TableHead>Date</TableHead><TableHead className="text-center">Status</TableHead><TableHead className="pr-5 text-right">Action</TableHead></TableRow></TableHeader>
            <TableBody>
              {data!.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="pl-5 font-medium">{r.case_number ?? '—'}</TableCell><TableCell>{r.officer_name ?? '—'}</TableCell><TableCell>{formatDate(r.post_crash_date)}</TableCell>
                  <TableCell className="text-center"><StatusChip status={r.status} /></TableCell>
                  <TableCell className="pr-5 text-right">
                    <Button size="xs" variant="outline" onClick={() => setEditing(r)}>
                      <Pencil className="h-3.5 w-3.5" /> {canIngest ? 'Open' : 'View'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {addOpen ? (
        <Dialog open onOpenChange={(v) => !v && setAddOpen(false)}>
          <DialogContent>
            <DialogHeader className="mb-0"><DialogTitle>Add investigation</DialogTitle></DialogHeader>
            <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
              <p className="mb-3 text-sm text-muted-foreground">Create the investigation, then fill in the detail sections in the editor.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5"><Label>Case #</Label><Input value={f.case_number} onChange={(e) => setF({ ...f, case_number: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Inspection #</Label><Input value={f.inspection_number} onChange={(e) => setF({ ...f, inspection_number: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Officer name</Label><Input value={f.officer_name} onChange={(e) => setF({ ...f, officer_name: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Officer ID</Label><Input value={f.officer_id} onChange={(e) => setF({ ...f, officer_id: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Post-crash date</Label><Input type="date" value={f.post_crash_date} onChange={(e) => setF({ ...f, post_crash_date: e.target.value })} /></div>
              </div>
              {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}
            </div>
            <DialogFooter className="mt-0"><Button variant="outline" onClick={() => setAddOpen(false)} disabled={busy}>Cancel</Button><Button onClick={createShell} disabled={busy}>Create & open</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
      {editing ? (
        <InvestigationForm
          crashId={crash.id}
          studyId={crash.study_id}
          record={editing}
          canIngest={canIngest}
          onClose={() => setEditing(null)}
          onSaved={reload}
        />
      ) : null}
    </Card>
  );
}

// ─────────────── Police Crash Reports ───────────────
// PCR-4 (§8.5): the structured ingestion path captured on each PCR. The MCMIS
// round-trip (PCR -> State repository -> MCSAP push to SafeSpect -> MCMIS) vs. a
// direct connection to the State crash repository that bypasses the round-trip.
const INGESTION_PATH_OPTIONS: { value: string; label: string }[] = [
  { value: 'MCMIS_ROUNDTRIP', label: 'MCMIS round-trip' },
  { value: 'DIRECT_STATE', label: 'Direct State connection' },
];
const INGESTION_PATH_LABELS: Record<string, string> = Object.fromEntries(
  INGESTION_PATH_OPTIONS.map((o) => [o.value, o.label]),
);

function PcrSection() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canIngest = hasPermission(user, 'source_data:ingest');
  const canMap = hasPermission(user, 'pcr:map');
  const { data, loading, reload } = useApi(() => sourceApi.pcrs(crash.id).catch(() => []), [crash.id]);
  const [open, setOpen] = React.useState(false);
  // PCR-1 (§8.5): the PCR currently open in the "Map fields" dialog (null = closed).
  const [mapFor, setMapFor] = React.useState<string | null>(null);
  const [f, setF] = React.useState({ source_repository: '', pcr_number: '', report_date: '', state_code: crash.state_code ?? '', ingestion_path: 'MCMIS_ROUNDTRIP' });
  const [busy, setBusy] = React.useState(false);

  async function save() {
    setBusy(true);
    try { await sourceApi.addPcr(crash.id, { source_repository: f.source_repository || null, pcr_number: f.pcr_number || null, report_date: f.report_date || null, state_code: f.state_code || null, ingestion_path: f.ingestion_path }); setOpen(false); reload(); }
    finally { setBusy(false); }
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Gavel} title="Police Crash Reports" description="MCMIS / State repository PCR data, mapped to CCFP attributes."
          actions={canIngest ? <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Add</Button> : undefined} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={Gavel} title="No PCRs linked" /></div>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">PCR #</TableHead><TableHead>Repository</TableHead><TableHead>Ingestion path</TableHead><TableHead>State</TableHead><TableHead>Report date</TableHead><TableHead className="text-center">Mapping</TableHead>{canMap ? <TableHead className="pr-5 text-right">Action</TableHead> : null}</TableRow></TableHeader>
            <TableBody>
              {data!.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="pl-5 font-medium">{r.pcr_number ?? '—'}</TableCell><TableCell>{r.source_repository ?? '—'}</TableCell><TableCell>{INGESTION_PATH_LABELS[r.ingestion_path] ?? (r.ingestion_path ? humanize(r.ingestion_path) : '—')}</TableCell><TableCell>{r.state_code ?? '—'}</TableCell><TableCell>{formatDate(r.report_date)}</TableCell>
                  <TableCell className="text-center"><MappingBadge status={r.mapping_status} /></TableCell>
                  {canMap ? <TableCell className="pr-5 text-right"><Button size="xs" variant="outline" onClick={() => setMapFor(r.id)}><Waypoints className="h-3.5 w-3.5" /> Map fields</Button></TableCell> : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {open ? (
        <Dialog open onOpenChange={(v) => !v && setOpen(false)}>
          <DialogContent>
            <DialogHeader className="mb-0"><DialogTitle>Add police crash report</DialogTitle></DialogHeader>
            <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5"><Label>Repository</Label><Input value={f.source_repository} onChange={(e) => setF({ ...f, source_repository: e.target.value })} placeholder="MCMIS / State repository" /></div>
                <div className="space-y-1.5"><Label>Ingestion path</Label><Select value={f.ingestion_path} onChange={(e) => setF({ ...f, ingestion_path: e.target.value })}>{INGESTION_PATH_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></div>
                <div className="space-y-1.5"><Label>PCR #</Label><Input value={f.pcr_number} onChange={(e) => setF({ ...f, pcr_number: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>State</Label><Select value={f.state_code} onChange={(e) => setF({ ...f, state_code: e.target.value })}><option value="">—</option>{US_STATES.map((s) => <option key={s.code} value={s.code}>{s.code}</option>)}</Select></div>
                <div className="space-y-1.5"><Label>Report date</Label><Input type="date" value={f.report_date} onChange={(e) => setF({ ...f, report_date: e.target.value })} /></div>
              </div>
            </div>
            <DialogFooter className="mt-0"><Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button><Button onClick={save} disabled={busy}>Save</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
      {mapFor ? (
        <MapFieldsDialog crashId={crash.id} recId={mapFor} onClose={() => setMapFor(null)} onSaved={reload} />
      ) : null}
    </Card>
  );
}

// PCR-1 (§8.5/§19.4): map fields on the State's EXISTING PCR to CCFP attributes.
// A repeatable add-row (State field name + position + CCFP attribute picker grouped
// by PCR section) writes one mapping at a time; existing mappings render in a table
// with delete. The State form is never altered — only the field correspondence is
// recorded. Once ≥1 mapping exists, the PCR's mapping badge can become MAPPED via
// the existing /map action (server-enforced).
interface MapRow { state_field_name: string; state_field_position: string; attribute_code: string; notes: string }
const EMPTY_MAP_ROW: MapRow = { state_field_name: '', state_field_position: '', attribute_code: '', notes: '' };

function MapFieldsDialog({ crashId, recId, onClose, onSaved }: { crashId: string; recId: string; onClose: () => void; onSaved: () => void }) {
  const { data: mappings, loading, reload } = useApi(() => sourceApi.pcrFieldMappings(crashId, recId).catch(() => []), [crashId, recId]);
  // Reuse the CCFP attribute catalog (GET /data-attributes) for the picker.
  const { data: attributes, loading: attrsLoading } = useApi(() => dataAttributeApi.list().catch(() => []), []);
  const [row, setRow] = React.useState<MapRow>({ ...EMPTY_MAP_ROW });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Group attributes by PCR section so the picker mirrors the PCR's structure.
  const grouped = React.useMemo(() => {
    const by = new Map<string, DataAttribute[]>();
    for (const a of attributes ?? []) {
      const key = a.pcr_section ?? 'Unassigned';
      if (!by.has(key)) by.set(key, []);
      by.get(key)!.push(a);
    }
    return [...by.entries()].sort((x, y) => x[0].localeCompare(y[0]));
  }, [attributes]);

  async function add() {
    if (!row.state_field_name || !row.attribute_code) {
      setError('State field name and a CCFP attribute are required.');
      return;
    }
    setBusy(true); setError(null);
    try {
      await sourceApi.addPcrFieldMapping(crashId, recId, {
        state_field_name: row.state_field_name,
        state_field_position: row.state_field_position || null,
        attribute_code: row.attribute_code,
        notes: row.notes || null,
      });
      setRow({ ...EMPTY_MAP_ROW });
      reload();
      onSaved();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  async function remove(id: string) {
    setBusy(true); setError(null);
    try { await sourceApi.deletePcrFieldMapping(crashId, recId, id); reload(); onSaved(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Delete failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader className="mb-0"><DialogTitle>Map PCR fields to CCFP attributes</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[65vh] overflow-y-auto py-4 pr-6">
          <p className="mb-3 text-sm text-muted-foreground">
            Record how fields on the State's existing police crash report correspond to CCFP attributes. The State form is not changed.
          </p>

          <div className="space-y-2">
            <Label>Add a field mapping</Label>
            <div className="grid grid-cols-[1fr_1fr_1fr_auto] items-end gap-2">
              <div className="space-y-1"><Input aria-label="State field name" value={row.state_field_name} onChange={(e) => setRow({ ...row, state_field_name: e.target.value })} placeholder="State field name" /></div>
              <div className="space-y-1"><Input aria-label="State position" value={row.state_field_position} onChange={(e) => setRow({ ...row, state_field_position: e.target.value })} placeholder="Position (e.g. Page 1, Box 3)" /></div>
              <div className="space-y-1">
                {attrsLoading ? <Skeleton className="h-10 w-full" /> : (
                  <Select aria-label="CCFP attribute" value={row.attribute_code} onChange={(e) => setRow({ ...row, attribute_code: e.target.value })}>
                    <option value="">Select CCFP attribute…</option>
                    {grouped.map(([section, attrs]) => (
                      <optgroup key={section} label={section}>
                        {(attrs ?? []).map((a) => (
                          <option key={a.code} value={a.code}>{a.name} ({a.code})</option>
                        ))}
                      </optgroup>
                    ))}
                  </Select>
                )}
              </div>
              <Button size="sm" onClick={add} disabled={busy}><Plus className="h-4 w-4" /> Add</Button>
            </div>
            <Input aria-label="Notes" value={row.notes} onChange={(e) => setRow({ ...row, notes: e.target.value })} placeholder="Notes (optional)" />
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>

          <div className="mt-5 space-y-2">
            <Label>Existing mappings</Label>
            {loading ? <Skeleton className="h-16 w-full" /> : (mappings?.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">No field mappings yet. Add at least one to mark the PCR as mapped.</p>
            ) : (
              <div className="overflow-hidden rounded-lg border">
                <Table>
                  <TableHeader><TableRow><TableHead className="pl-5">State field</TableHead><TableHead>Position</TableHead><TableHead>CCFP attribute</TableHead><TableHead>Notes</TableHead><TableHead className="pr-5 text-right">Action</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {mappings!.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell className="pl-5 font-medium">{m.state_field_name}</TableCell>
                        <TableCell>{m.state_field_position ?? '—'}</TableCell>
                        <TableCell>{m.attribute_name ? `${m.attribute_name} (${m.attribute_code})` : (m.attribute_code ?? '—')}</TableCell>
                        <TableCell className="text-muted-foreground">{m.notes ?? '—'}</TableCell>
                        <TableCell className="pr-5 text-right"><Button variant="ghost" size="icon" aria-label="Remove mapping" onClick={() => remove(m.id)} disabled={busy}><Trash2 className="h-4 w-4" /></Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────── Reconstruction ───────────────
function ReconstructionSection() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canUpload = hasPermission(user, 'recon:upload');
  const canCode = hasPermission(user, 'recon:code');
  const { data, loading, reload } = useApi(() => sourceApi.reconstructions(crash.id).catch(() => []), [crash.id]);
  const [open, setOpen] = React.useState(false);
  const [codeFor, setCodeFor] = React.useState<string | null>(null);
  const [f, setF] = React.useState({ title: '', received_date: '' });
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    try {
      // A reconstruction is fundamentally a narrative document (§8.6). When a file is
      // attached it is uploaded multipart, scanned, stored, and linked via document_id.
      await sourceApi.addReconstruction(crash.id, { title: f.title || null, received_date: f.received_date || null }, file ?? undefined);
      setOpen(false); setF({ title: '', received_date: '' }); setFile(null); reload();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  async function openDocument(documentId: string) {
    const { signed_url } = await documentApi.downloadLink(documentId);
    window.open(signed_url, '_blank', 'noopener');
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Waypoints} title="Reconstruction reports" description="Narrative reconstruction with manual coding into CCFP attributes."
          actions={canUpload ? <Button size="sm" onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Add</Button> : undefined} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={Waypoints} title="No reconstruction reports" /></div>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">Title</TableHead><TableHead>Received</TableHead><TableHead>Document</TableHead><TableHead className="text-center">Coding</TableHead>{canCode ? <TableHead className="pr-5 text-right">Action</TableHead> : null}</TableRow></TableHeader>
            <TableBody>
              {data!.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="pl-5 font-medium">{r.title ?? '—'}</TableCell><TableCell>{formatDate(r.received_date)}</TableCell>
                  <TableCell>{r.document_id ? <Button size="xs" variant="ghost" onClick={() => openDocument(r.document_id!)}><Upload className="h-3.5 w-3.5 rotate-180" /> Download</Button> : <span className="text-muted-foreground">—</span>}</TableCell>
                  <TableCell className="text-center"><StatusChip status={r.coding_status} /></TableCell>
                  {canCode ? <TableCell className="pr-5 text-right"><Button size="xs" variant="outline" onClick={() => setCodeFor(r.id)}>Code findings</Button></TableCell> : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {open ? (
        <Dialog open onOpenChange={(v) => !v && setOpen(false)}>
          <DialogContent>
            <DialogHeader className="mb-0"><DialogTitle>Add reconstruction report</DialogTitle></DialogHeader>
            <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
              <div className="space-y-3">
                <div className="space-y-1.5"><Label>Title</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Received date</Label><Input type="date" value={f.received_date} onChange={(e) => setF({ ...f, received_date: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Report file</Label><Input type="file" accept=".pdf,.doc,.docx,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /><p className="text-xs text-muted-foreground">Optional — attach the reconstruction narrative (scanned and stored as a linked document).</p></div>
              </div>
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
            <DialogFooter className="mt-0"><Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button><Button onClick={save} disabled={busy}>Save</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
      {codeFor ? <CodeDialog crashId={crash.id} recId={codeFor} onClose={() => setCodeFor(null)} onSaved={reload} /> : null}
    </Card>
  );
}

// One coded-finding row in the picker: a CCFP attribute + its coded value.
interface CodedRow { attribute_code: string; value_text: string; confidence: string }
const EMPTY_ROW: CodedRow = { attribute_code: '', value_text: '', confidence: '' };

function CodeDialog({ crashId, recId, onClose, onSaved }: { crashId: string; recId: string; onClose: () => void; onSaved: () => void }) {
  const [status, setStatus] = React.useState('CODED');
  // Reuse the Data-Management attribute catalog (GET /data-attributes) for the picker.
  const { data: attributes, loading: attrsLoading } = useApi(() => dataAttributeApi.list().catch(() => []), []);
  const [rows, setRows] = React.useState<CodedRow[]>([{ ...EMPTY_ROW }]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function setRow(i: number, patch: Partial<CodedRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function addRow() { setRows((prev) => [...prev, { ...EMPTY_ROW }]); }
  function removeRow(i: number) { setRows((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev)); }

  async function save() {
    setBusy(true); setError(null);
    // Only send rows where an attribute was actually picked; coding the status
    // alone (no findings) stays valid so the existing status chip keeps working.
    const coded_attributes = rows
      .filter((r) => r.attribute_code)
      .map((r) => ({
        attribute_code: r.attribute_code,
        value_text: r.value_text || null,
        confidence: r.confidence ? Number(r.confidence) : null,
      }));
    try {
      await sourceApi.codeReconstruction(crashId, recId, { coding_status: status, coded_attributes });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Code reconstruction findings</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
          <div className="space-y-3">
            <div className="space-y-1.5"><Label>Coding status</Label><Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="PENDING">Pending</option><option value="IN_PROGRESS">In progress</option><option value="CODED">Coded</option></Select></div>
            <div className="space-y-2">
              <Label>Coded findings (CCFP attributes)</Label>
              {attrsLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : (
                rows.map((row, i) => (
                  <div key={i} className="grid grid-cols-[1fr_1fr_auto_auto] items-end gap-2">
                    <div className="space-y-1">
                      <Select aria-label="Attribute" value={row.attribute_code} onChange={(e) => setRow(i, { attribute_code: e.target.value })}>
                        <option value="">Select attribute…</option>
                        {(attributes ?? []).map((a) => (
                          <option key={a.code} value={a.code}>{a.name} ({a.code})</option>
                        ))}
                      </Select>
                    </div>
                    <Input aria-label="Value" value={row.value_text} onChange={(e) => setRow(i, { value_text: e.target.value })} placeholder="Coded value" />
                    <Input aria-label="Confidence" className="w-20" type="number" min={0} max={1} step={0.1} value={row.confidence} onChange={(e) => setRow(i, { confidence: e.target.value })} placeholder="Conf." />
                    <Button variant="ghost" size="icon" aria-label="Remove finding" onClick={() => removeRow(i)} disabled={rows.length === 1}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                ))
              )}
              <Button variant="outline" size="xs" onClick={addRow}><Plus className="h-3.5 w-3.5" /> Add finding</Button>
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={busy}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────── ELD ───────────────
// RECO-2: surface whether an ELD file is truly linked to the crash. The link is
// derived from the CCFP code parsed out of the file's output-file comment and is
// a real match only when it equals the crash identifier — "Linked" vs
// "Code mismatch" vs "No code" (no code parsed from the file yet).
function EldLinkBadge({ code, expected }: { code: string | null; expected: string }) {
  if (!code) return <Badge variant="neutral" size="sm">No code</Badge>;
  if (code === expected) return <Badge variant="success" size="sm">Linked</Badge>;
  return <Badge variant="warning" size="sm">Code mismatch</Badge>;
}

// BRD Appendix E: a status chip alone is not feedback. When a file did not
// extract cleanly, the stored reason and the fix are shown inline, next to the
// action that resolves it.
function EldFileProblem({ file }: { file: EldFile }) {
  if (!file.error_message) return null;
  const failed = file.upload_status === 'FAILED';
  return (
    <div
      className={`rounded-md border px-3 py-2 text-xs ${failed ? 'border-destructive/40 bg-destructive/5 text-destructive' : 'border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-400'}`}
      role={failed ? 'alert' : undefined}
    >
      <span className="font-medium">{failed ? 'Extraction failed' : 'Extracted with problems'}:</span>{' '}
      {file.error_message}
      <span className="ml-1 font-mono opacity-70">({file.error_code})</span>
    </div>
  );
}

const ISSUE_TONE: Record<EldIssueSeverity, 'danger' | 'warning' | 'neutral'> = {
  ERROR: 'danger',
  WARNING: 'warning',
  INFO: 'neutral',
};

// `humanize` would render these as "Fmcsa Eld Output" / "Flat Csv".
const ELD_FORMAT_LABELS: Record<string, string> = {
  FMCSA_ELD_OUTPUT: 'ELD output file (49 CFR 395 App. A)',
  FLAT_CSV: 'flat hours-of-service CSV',
  UNKNOWN: 'unrecognized format',
};

function eldFormatLabel(format: string | null): string {
  if (!format) return 'unrecognized format';
  return ELD_FORMAT_LABELS[format] ?? humanize(format);
}

// The full diagnostic account for one file. Every problem the extraction found
// is addressable here: what, where (line/column), how many times, and the value
// that could not be read.
function EldIssuesDialog({ crashId, file, onClose }: { crashId: string; file: EldFile; onClose: () => void }) {
  const { data: issues, loading } = useApi(
    () => sourceApi.eldFileIssues(crashId, file.id).catch(() => []),
    [crashId, file.id],
  );
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader className="mb-0"><DialogTitle>Extraction report — {file.file_name}</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[65vh] overflow-y-auto py-4 pr-6">
          <dl className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
            <EldFact label="Format" value={file.file_format ? eldFormatLabel(file.file_format) : '—'} />
            <EldFact label="Encoding" value={file.encoding ?? '—'} />
            <EldFact label="Lines read" value={file.line_count?.toLocaleString() ?? '—'} />
            <EldFact label="Rows examined" value={file.row_count?.toLocaleString() ?? '—'} />
            <EldFact label="Events stored" value={(file.event_count ?? 0).toLocaleString()} />
            <EldFact label="Errors" value={file.error_count.toLocaleString()} />
            <EldFact label="Warnings" value={file.warning_count.toLocaleString()} />
            <EldFact label="Extraction runs" value={String(file.parse_attempts)} />
          </dl>
          <EldFileProblem file={file} />
          {loading ? (
            <Skeleton className="mt-4 h-24 w-full" />
          ) : (issues?.length ?? 0) === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground">
              No problems were recorded — every row and value in this file was read as expected.
            </p>
          ) : (
            <Table className="mt-4">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Severity</TableHead>
                  <TableHead>What happened</TableHead>
                  <TableHead className="text-right">Line</TableHead>
                  <TableHead className="pr-5 text-right">Times</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {issues!.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell className="pl-5 align-top">
                      <Badge variant={ISSUE_TONE[i.severity]} size="sm">{i.severity}</Badge>
                    </TableCell>
                    <TableCell className="align-top">
                      <div>{i.message}</div>
                      <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                        {i.code}
                        {i.section ? ` · ${humanize(i.section)}` : ''}
                        {i.column_name ? ` · column ${i.column_name}` : ''}
                        {i.raw_value ? ` · value "${i.raw_value}"` : ''}
                      </div>
                    </TableCell>
                    <TableCell className="text-right align-top tabular-nums">{i.line_number ?? '—'}</TableCell>
                    <TableCell className="pr-5 text-right align-top tabular-nums">{i.occurrences}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EldFact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

// The half of Appendix E that is "so the data can be analyzed": who was driving,
// for which carrier, in which unit — and the hours-of-service totals derived
// from the events, with edited-out records excluded.
function EldFileDetail({ file }: { file: EldFile }) {
  const hos = file.hos_summary;
  const dutyHours = hos?.duty_hours ?? {};
  const hasIdentity = file.driver_name || file.carrier_name || file.vin;
  if (!hasIdentity && !hos?.timed_event_count) return null;
  return (
    <div className="grid gap-4 border-t p-5 sm:grid-cols-2">
      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          From the ELD file header
        </h4>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <EldFact label="Driver" value={file.driver_name ?? '—'} />
          <EldFact label="CDL" value={file.driver_license_number ? `${file.driver_license_number} (${file.driver_license_state ?? '—'})` : '—'} />
          <EldFact label="Co-driver" value={file.co_driver_name ?? '—'} />
          <EldFact label="Carrier" value={file.carrier_name ?? '—'} />
          <EldFact label="U.S. DOT" value={file.carrier_usdot ?? '—'} />
          <EldFact label="VIN" value={file.vin ?? '—'} />
          <EldFact label="Power unit" value={file.power_unit_number ?? '—'} />
          <EldFact label="Time zone (h from UTC)" value={file.time_zone_offset ?? '—'} />
        </dl>
      </div>
      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Hours of service extracted
        </h4>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <EldFact label="Driving" value={`${(dutyHours.DRIVING ?? 0).toFixed(2)} h`} />
          <EldFact label="On duty, not driving" value={`${(dutyHours.ON_DUTY_NOT_DRIVING ?? 0).toFixed(2)} h`} />
          <EldFact label="Sleeper berth" value={`${(dutyHours.SLEEPER_BERTH ?? 0).toFixed(2)} h`} />
          <EldFact label="Off duty" value={`${(dutyHours.OFF_DUTY ?? 0).toFixed(2)} h`} />
          <EldFact label="Duty-status changes" value={hos?.duty_status_changes ?? 0} />
          <EldFact label="Days covered" value={hos?.distinct_days ?? 0} />
          <EldFact label="Edited-out records" value={hos?.inactive_records ?? 0} />
          <EldFact label="Unidentified-driver records" value={hos?.unidentified_driver_records ?? 0} />
          <EldFact label="First event" value={formatDateTime(hos?.first_event_at ?? null)} />
          <EldFact label="Last event" value={formatDateTime(hos?.last_event_at ?? null)} />
        </dl>
      </div>
    </div>
  );
}

function EldSection() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canUpload = hasPermission(user, 'eld:upload');
  const { data: files, loading, reload } = useApi(() => sourceApi.eldFiles(crash.id).catch(() => []), [crash.id]);
  const { data: events, loading: eLoading, reload: reloadEvents } = useApi(() => sourceApi.eldEvents(crash.id).catch(() => []), [crash.id]);
  const [open, setOpen] = React.useState(false);
  const [issuesFor, setIssuesFor] = React.useState<EldFile | null>(null);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [reparsing, setReparsing] = React.useState<string | null>(null);
  const [reparseError, setReparseError] = React.useState<string | null>(null);

  async function reparse(fileId: string) {
    setReparsing(fileId); setReparseError(null);
    try { await sourceApi.reparseEldFile(crash.id, fileId); reload(); reloadEvents(); }
    catch (e) { setReparseError(e instanceof ApiError ? e.message : 'Re-run failed'); }
    finally { setReparsing(null); }
  }

  // Extraction runs AFTER the upload response returns, so the row first appears
  // as UPLOADED with 0 events and settles a moment later. A single fixed delay
  // is not enough — a real ELD output file against a loaded database takes
  // several seconds — and a row left showing "Uploaded / 0" is exactly the
  // "nothing tells me what happened" state this screen exists to remove. Poll
  // until every file reaches a terminal status, with a bounded number of
  // attempts so a stuck file cannot poll forever.
  const watching = React.useRef(false);
  React.useEffect(() => () => { watching.current = false; }, []);

  async function watchExtraction() {
    if (watching.current) return;
    watching.current = true;
    try {
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        if (!watching.current) return;
        const rows = await sourceApi.eldFiles(crash.id).catch(() => null);
        if (!watching.current) return;
        reload();
        reloadEvents();
        const pending = rows?.some(
          (r) => r.upload_status === 'UPLOADED' || r.upload_status === 'PARSING',
        );
        if (!pending) return;
      }
    } finally {
      watching.current = false;
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardHeading icon={Upload} title="ELD / eRODS files" description="Hours-of-service output files, extracted and linked by CCFP code."
            actions={canUpload ? <Button size="sm" onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Upload CSV</Button> : undefined} />
        </CardHeader>
        <CardContent className="p-0">
          {loading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (files?.length ?? 0) === 0 ? (
            <div className="p-5"><EmptyState icon={Upload} title="No ELD files" description="Upload an ELD output CSV to extract HOS events." /></div>
          ) : (
            <>
              {reparseError ? <p className="px-5 pt-4 text-sm text-destructive">{reparseError}</p> : null}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">File</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                    <TableHead>CCFP code</TableHead>
                    <TableHead className="text-center">Link</TableHead>
                    <TableHead className="text-right">Events</TableHead>
                    <TableHead className="text-center">Issues</TableHead>
                    <TableHead className="pr-5 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {files!.map((r) => (
                    <React.Fragment key={r.id}>
                      <TableRow>
                        <TableCell className="pl-5 font-medium">
                          <button
                            type="button"
                            className="text-left hover:underline"
                            aria-expanded={expanded === r.id}
                            aria-label={`${expanded === r.id ? 'Hide' : 'Show'} extracted details for ${r.file_name}`}
                            onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                          >
                            {r.file_name}
                          </button>
                          <div className="text-xs text-muted-foreground">{formatDateTime(r.parsed_at)}</div>
                        </TableCell>
                        <TableCell>{r.provider ?? '—'}</TableCell>
                        <TableCell className="text-center"><StatusChip status={r.upload_status} /></TableCell>
                        <TableCell className="font-mono text-xs">{r.ccfp_code_in_file ?? '—'}</TableCell>
                        <TableCell className="text-center"><EldLinkBadge code={r.ccfp_code_in_file} expected={crash.ccfp_identifier} /></TableCell>
                        <TableCell className="text-right tabular-nums">{r.event_count ?? 0}</TableCell>
                        <TableCell className="text-center">
                          {r.error_count > 0 ? <Badge variant="danger" size="sm">{r.error_count} error{r.error_count === 1 ? '' : 's'}</Badge> : null}
                          {r.warning_count > 0 ? <Badge variant="warning" size="sm" className="ml-1">{r.warning_count} warning{r.warning_count === 1 ? '' : 's'}</Badge> : null}
                          {r.error_count === 0 && r.warning_count === 0 ? <span className="text-xs text-muted-foreground">None</span> : null}
                        </TableCell>
                        <TableCell className="pr-5 text-right">
                          <Button size="xs" variant="outline" onClick={() => setIssuesFor(r)}>
                            <FileSearch className="h-3.5 w-3.5" /> Report
                          </Button>
                          {canUpload ? (
                            <Button size="xs" variant="outline" className="ml-1" disabled={reparsing === r.id} onClick={() => reparse(r.id)}>
                              {reparsing === r.id ? <Spinner className="h-3.5 w-3.5" /> : <Waypoints className="h-3.5 w-3.5" />} Re-run
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                      {r.error_message ? (
                        <TableRow>
                          <TableCell colSpan={8} className="px-5 pb-3 pt-0"><EldFileProblem file={r} /></TableCell>
                        </TableRow>
                      ) : null}
                      {expanded === r.id ? (
                        <TableRow>
                          <TableCell colSpan={8} className="p-0"><EldFileDetail file={r} /></TableCell>
                        </TableRow>
                      ) : null}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardHeading icon={ClipboardList} title="Extracted ELD events" description="Hours-of-service event rows extracted from uploaded files. Edited-out (inactive) records are shown but excluded from the duty totals." /></CardHeader>
        <CardContent className="p-0">
          {eLoading ? <div className="p-5"><Skeleton className="h-20 w-full" /></div> : (events?.length ?? 0) === 0 ? (
            <div className="p-5 text-sm text-muted-foreground">No extracted events yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">Seq</TableHead>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Event</TableHead>
                    <TableHead>Duty</TableHead>
                    <TableHead>Record</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead className="text-right">Miles</TableHead>
                    <TableHead className="pr-5 text-right">Engine hrs</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events!.map((e) => (
                    <TableRow key={e.id} className={e.record_status && e.record_status !== 'ACTIVE' ? 'opacity-60' : undefined}>
                      <TableCell className="pl-5 tabular-nums">
                        {e.event_sequence}
                        {e.is_duplicate ? <Badge variant="warning" size="sm" className="ml-1">dup</Badge> : null}
                      </TableCell>
                      <TableCell className="text-xs">{formatDateTime(e.event_timestamp)}</TableCell>
                      <TableCell className="text-xs">
                        {e.event_type ? humanize(e.event_type) : '—'}
                        {e.annotation ? <div className="text-muted-foreground">{e.annotation}</div> : null}
                      </TableCell>
                      <TableCell>{e.duty ? humanize(e.duty) : '—'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {e.record_status ? humanize(e.record_status) : '—'}
                        {e.record_origin ? ` · ${humanize(e.record_origin)}` : ''}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {e.location ?? (e.latitude != null && e.longitude != null ? `${e.latitude}, ${e.longitude}` : '—')}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{e.miles_driven ?? '—'}</TableCell>
                      <TableCell className="pr-5 text-right tabular-nums">{e.engine_hours ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {open ? <EldUploadDialog crashId={crash.id} onClose={() => setOpen(false)} onSaved={() => { reload(); watchExtraction(); }} /> : null}
      {issuesFor ? <EldIssuesDialog crashId={crash.id} file={issuesFor} onClose={() => setIssuesFor(null)} /> : null}
    </div>
  );
}

function EldUploadDialog({ crashId, onClose, onSaved }: { crashId: string; onClose: () => void; onSaved: () => void }) {
  const [file, setFile] = React.useState<File | null>(null);
  const [provider, setProvider] = React.useState('');
  const [model, setModel] = React.useState('');
  const [version, setVersion] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [checking, setChecking] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [check, setCheck] = React.useState<EldValidation | null>(null);

  // Dry run: report exactly what the background extraction would produce, before
  // the file is committed to the crash record. Same parser, same mappings.
  async function validate() {
    if (!file) return;
    setChecking(true); setError(null); setCheck(null);
    try { setCheck(await sourceApi.validateEld(crashId, file, provider || undefined)); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Check failed'); }
    finally { setChecking(false); }
  }

  async function upload() {
    if (!file) return;
    setBusy(true); setError(null);
    try { await sourceApi.uploadEld(crashId, file, { provider: provider || undefined, model: model || undefined, version: version || undefined }); onSaved(); onClose(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Upload failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader className="mb-0"><DialogTitle>Upload ELD output file</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="eld-file">CSV file *</Label>
              <Input id="eld-file" type="file" accept=".csv,.txt,text/csv,text/plain" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setCheck(null); setError(null); }} />
            </div>
            <div className="space-y-1.5"><Label htmlFor="eld-provider">Provider</Label><Input id="eld-provider" value={provider} onChange={(e) => setProvider(e.target.value)} /></div>
            <div className="space-y-1.5"><Label htmlFor="eld-model">Model</Label><Input id="eld-model" value={model} onChange={(e) => setModel(e.target.value)} /></div>
            <div className="space-y-1.5"><Label htmlFor="eld-version">Version</Label><Input id="eld-version" value={version} onChange={(e) => setVersion(e.target.value)} /></div>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Both the sectioned ELD output file defined by 49 CFR 395 Appendix A and a flat
            hours-of-service CSV are accepted. Use <strong>Check file</strong> to see what would be
            extracted before uploading. Extraction runs in the background; its report is available on
            the file afterwards either way.
          </p>
          {check ? (
            <div className={`mt-3 rounded-md border p-3 text-xs ${check.ok ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-destructive/40 bg-destructive/5'}`}>
              <p className="font-medium">
                {check.ok
                  ? `Looks good — ${check.event_count.toLocaleString()} event(s) would be extracted. Format: ${eldFormatLabel(check.file_format)}.`
                  : `This file would not extract cleanly: ${check.error_message}`}
              </p>
              <p className="mt-1 text-muted-foreground">
                CCFP code: {check.ccfp_code_in_file ?? 'none found'}
                {check.ccfp_code_in_file ? (check.ccfp_code_matches_crash ? ' — matches this crash' : ' — does NOT match this crash') : ''}
                {' · '}{check.error_count} error(s), {check.warning_count} warning(s)
              </p>
              {check.issues.length > 0 ? (
                <ul className="mt-2 list-disc space-y-0.5 pl-4">
                  {check.issues.slice(0, 6).map((i, idx) => (
                    <li key={`${i.code}-${idx}`}>
                      <span className="font-medium">{i.severity}:</span> {i.message}
                      {i.line_number ? ` (line ${i.line_number})` : ''}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy || checking}>Cancel</Button>
          <Button variant="outline" onClick={validate} disabled={!file || busy || checking}>
            {checking ? <Spinner className="h-4 w-4" /> : <FileSearch className="h-4 w-4" />} Check file
          </Button>
          <Button onClick={upload} disabled={!file || busy}>{busy ? <Spinner className="h-4 w-4" /> : null} Upload</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────── Raw / Aggregated (DATA-3) ───────────────
// §8.8 lines 310-311: authorized users can view raw data from all source systems
// and view aggregated/canonical crash data. Both endpoints already exist
// (GET /crashes/{id}/raw-data, GET /crashes/{id}/aggregated); this surfaces them.
// The two blocks are independently permission-gated, and each call degrades
// gracefully via .catch(() => null) so a 403 (e.g. read_raw without read_aggregated,
// or vice-versa) hides only its own block rather than breaking the tab.

// Human-friendly labels for the per-system raw counts (keys returned by raw-data).
const RAW_COUNT_LABELS: Record<string, string> = {
  inspections: 'Inspections',
  investigations: 'Investigations',
  police_crash_reports: 'Police Crash Reports',
  reconstruction_reports: 'Reconstruction Reports',
  eld_files: 'ELD Files',
  source_records: 'Source Records',
};

function StatTile({ label, value, tone }: { label: string; value: number; tone?: 'present' | 'missing' }) {
  const valueClass =
    tone === 'present' ? 'text-emerald-600' : tone === 'missing' ? 'text-destructive' : 'text-foreground';
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className={`text-2xl font-semibold tabular-nums ${valueClass}`}>{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function RawAggregatedSection() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canReadRaw = hasPermission(user, 'data_mgmt:read_raw');
  const canReadAggregated = hasPermission(user, 'data_mgmt:read_aggregated');

  // Only call an endpoint the user is allowed to read; otherwise resolve to null
  // so neither the network nor the render path throws on a 403.
  const { data: raw, loading: rawLoading } = useApi(
    () => (canReadRaw ? dataMgmtApi.rawData(crash.id).catch(() => null) : Promise.resolve(null)),
    [crash.id, canReadRaw],
  );
  const { data: agg, loading: aggLoading } = useApi(
    () => (canReadAggregated ? dataMgmtApi.aggregated(crash.id).catch(() => null) : Promise.resolve(null)),
    [crash.id, canReadAggregated],
  );

  const counts = raw?.counts ?? {};
  const countEntries = Object.keys(RAW_COUNT_LABELS).filter((k) => k in counts);
  const sourceRecords = raw?.source_records ?? [];

  if (!canReadRaw && !canReadAggregated) {
    return (
      <Card>
        <CardContent className="p-5">
          <EmptyState icon={Layers} title="No access" description="You do not have permission to view raw or aggregated crash data." />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {canReadAggregated ? (
        <Card>
          <CardHeader>
            <CardHeading icon={Layers} title="Aggregated crash data" description="Canonical CCFP attribute coverage for this crash." />
          </CardHeader>
          <CardContent>
            {aggLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : agg ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatTile label="Required present" value={agg.required_present} tone="present" />
                <StatTile label="Required missing" value={agg.required_missing} tone="missing" />
                <StatTile label="Required attributes" value={agg.required_attribute_count} />
                <StatTile label="Current attributes" value={agg.current_attribute_count} />
              </div>
            ) : (
              <EmptyState icon={Layers} title="Aggregated summary unavailable" description="The aggregated view could not be loaded for this crash." />
            )}
          </CardContent>
        </Card>
      ) : null}

      {canReadRaw ? (
        <Card>
          <CardHeader>
            <CardHeading icon={Database} title="Raw source data" description="Source-system record counts and lineage across all ingested systems." />
          </CardHeader>
          <CardContent className="space-y-4">
            {rawLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : raw ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  {countEntries.map((k) => (
                    <StatTile key={k} label={RAW_COUNT_LABELS[k]} value={counts[k] ?? 0} />
                  ))}
                </div>
                {sourceRecords.length === 0 ? (
                  <EmptyState icon={Database} title="No source records" description="No raw source records have been ingested for this crash." />
                ) : (
                  <div className="overflow-hidden rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="pl-5">Source system</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>External ID</TableHead>
                          <TableHead className="pr-5">Provenance URI</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sourceRecords.map((s, i) => (
                          <TableRow key={(s.external_id as string) ?? `src-${i}`}>
                            <TableCell className="pl-5 font-medium">{(s.source_system as string) ?? '—'}</TableCell>
                            <TableCell>{(s.source_type as string) ?? '—'}</TableCell>
                            <TableCell className="tabular-nums">{(s.external_id as string) ?? '—'}</TableCell>
                            <TableCell className="pr-5 font-mono text-xs text-muted-foreground">{(s.uri as string) ?? '—'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </>
            ) : (
              <EmptyState icon={Database} title="Raw data unavailable" description="The raw source data could not be loaded for this crash." />
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
