import * as React from 'react';
import { Database, Pencil, Plus, Search } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { SensitivityBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { dataAttributeApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { humanize } from '@/lib/format';
import type { DataAttribute } from '@/lib/types';

// Mirror Backend/app/enums.py:85-92 — keep in sync with AttributeDataType / DataSensitivity.
const DATA_TYPES = ['TEXT', 'NUMBER', 'DATE', 'DATETIME', 'BOOLEAN', 'CODE', 'JSON'] as const;
const SENSITIVITIES = ['PUBLIC', 'INTERNAL', 'PII', 'SENSITIVE', 'CIPSEA'] as const;

export function DataAttributesPage() {
  const { user } = useAuth();
  const canManage = hasAnyPermission(user, ['admin:attributes']);
  const { data, loading, reload } = useApi(() => dataAttributeApi.list().catch(() => []), []);
  const [q, setQ] = React.useState('');
  const [section, setSection] = React.useState('');
  const [editing, setEditing] = React.useState<DataAttribute | null | undefined>(undefined);
  // undefined = dialog closed; null = creating a new attribute; object = editing that row.

  // Section catalog (GAP-PCR-01): use the specification's own labels and form
  // order rather than humanizing the internal code — "Large Vehicle and
  // Hazardous Material (HM) Data Elements", not "Large Veh Hazmat". Falls back
  // to deriving sections from the attributes if the catalog can't be loaded.
  const { data: pcrSections } = useApi(() => dataAttributeApi.sections().catch(() => []), []);
  const sectionName = React.useMemo(
    () => new Map((pcrSections ?? []).map((s) => [s.code, s.name])),
    [pcrSections],
  );
  const sections = React.useMemo(() => {
    const present = new Set((data ?? []).map((a) => a.pcr_section).filter(Boolean) as string[]);
    const ordered = (pcrSections ?? []).filter((s) => present.has(s.code)).map((s) => s.code);
    // Any section on an attribute but missing from the catalog still gets an
    // option, so nothing becomes unfilterable.
    return [...ordered, ...[...present].filter((c) => !ordered.includes(c))];
  }, [data, pcrSections]);
  const labelFor = (code: string) => sectionName.get(code) ?? humanize(code);
  const filtered = (data ?? []).filter((a) => {
    if (section && a.pcr_section !== section) return false;
    if (q) { const s = q.toLowerCase(); return a.code.toLowerCase().includes(s) || a.name.toLowerCase().includes(s); }
    return true;
  });

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Study & Data" icon={Database} title="Data attribute catalog" subtitle="Canonical CCFP / PCR attributes."
        actions={canManage ? <Button size="sm" onClick={() => setEditing(null)}><Plus className="h-4 w-4" /> Add attribute</Button> : undefined} />
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search code or name…" className="pl-9" />
            </div>
            <Select value={section} onChange={(e) => setSection(e.target.value)} className="sm:w-56">
              <option value="">All sections</option>
              {sections.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
            </Select>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-0">
          {loading ? <div className="p-5"><Skeleton className="h-64 w-full" /></div> : filtered.length === 0 ? (
            <div className="p-5"><EmptyState icon={Database} title="No attributes match" /></div>
          ) : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">Code</TableHead><TableHead>Name</TableHead><TableHead>Category</TableHead><TableHead>Section</TableHead><TableHead>Type</TableHead><TableHead>Sensitivity</TableHead>{canManage ? <TableHead className="pr-5 text-right">Actions</TableHead> : null}</TableRow></TableHeader>
              <TableBody>
                {filtered.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="pl-5 font-medium tabular-nums">{a.code}</TableCell>
                    <TableCell>{a.name}</TableCell>
                    <TableCell className="text-muted-foreground">{a.category}</TableCell>
                    <TableCell className="text-muted-foreground">{a.pcr_section ? labelFor(a.pcr_section) : '—'}</TableCell>
                    <TableCell><Badge variant="neutral" size="sm">{humanize(a.data_type)}</Badge></TableCell>
                    <TableCell className={canManage ? '' : 'pr-5'}>{a.sensitivity === 'INTERNAL' || a.sensitivity === 'PUBLIC' ? <span className="text-xs text-muted-foreground">{humanize(a.sensitivity)}</span> : <SensitivityBadge level={a.sensitivity} />}</TableCell>
                    {canManage ? (
                      <TableCell className="pr-5 text-right">
                        <Button size="icon-sm" variant="ghost" aria-label={`Edit ${a.code}`} onClick={() => setEditing(a)}><Pencil className="h-3.5 w-3.5" /></Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <p className="text-sm text-muted-foreground">{filtered.length} of {data?.length ?? 0} attributes.</p>
      {editing !== undefined ? <AttributeDialog attribute={editing} onClose={() => setEditing(undefined)} onSaved={reload} /> : null}
    </div>
  );
}

function AttributeDialog({ attribute, onClose, onSaved }: { attribute: DataAttribute | null; onClose: () => void; onSaved: () => void }) {
  const isEdit = attribute !== null;
  const [code, setCode] = React.useState(attribute?.code ?? '');
  const [name, setName] = React.useState(attribute?.name ?? '');
  const [category, setCategory] = React.useState(attribute?.category ?? '');
  const [pcrSection, setPcrSection] = React.useState(attribute?.pcr_section ?? '');
  const [dataType, setDataType] = React.useState<string>(attribute?.data_type ?? 'TEXT');
  const [sensitivity, setSensitivity] = React.useState<string>(attribute?.sensitivity ?? 'INTERNAL');
  const [description, setDescription] = React.useState(attribute?.description ?? '');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    const body = {
      code: code.trim(),
      name: name.trim(),
      category: category.trim(),
      pcr_section: pcrSection.trim() || null,
      data_type: dataType,
      sensitivity,
      description: description.trim() || null,
    };
    try {
      if (isEdit) await dataAttributeApi.update(attribute!.id, body);
      else await dataAttributeApi.create(body);
      onSaved(); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>{isEdit ? 'Edit data attribute' : 'Add data attribute'}</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Code *</Label><Input value={code} onChange={(e) => setCode(e.target.value)} disabled={isEdit} placeholder="e.g. CRASH_SEVERITY" /></div>
            <div className="space-y-1.5"><Label>Category *</Label><Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. crash" /></div>
          </div>
          <div className="space-y-1.5"><Label>Name *</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="space-y-1.5"><Label>PCR section</Label><Input value={pcrSection} onChange={(e) => setPcrSection(e.target.value)} placeholder="Optional" /></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Data type</Label>
              <Select value={dataType} onChange={(e) => setDataType(e.target.value)}>
                {DATA_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Sensitivity</Label>
              <Select value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>
                {SENSITIVITIES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </Select>
            </div>
          </div>
          <div className="space-y-1.5"><Label>Description</Label><Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" /></div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={busy || !code.trim() || !name.trim() || !category.trim()}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
