import * as React from 'react';
import { Building2, Plus } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { orgApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { US_STATES } from '@/lib/constants';
import { humanize } from '@/lib/format';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';

const ORG_TYPES = ['FMCSA', 'BTS', 'STATE_AGENCY', 'VOLPE', 'NHTSA', 'FHWA', 'NOAA', 'AAMVA', 'EXTERNAL', 'OTHER'];

export function OrganizationsPage() {
  const { user } = useAuth();
  const canEdit = hasAnyPermission(user, ['admin:users', 'admin:system']);
  const { data, loading, reload } = useApi(() => orgApi.list({ limit: 200 }), []);
  const [open, setOpen] = React.useState(false);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" icon={Building2} title="Organizations" subtitle="FMCSA, BTS, State agencies, and external partners."
        actions={canEdit ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New organization</Button> : null} />

      <Card>
        <CardContent className="p-0">
          {loading ? <div className="p-5"><Skeleton className="h-40 w-full" /></div> : (data?.items?.length ?? 0) === 0 ? (
            <div className="p-5"><EmptyState icon={Building2} title="No organizations" /></div>
          ) : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">Name</TableHead><TableHead>Type</TableHead><TableHead>State</TableHead><TableHead className="pr-5 text-center">Active</TableHead></TableRow></TableHeader>
              <TableBody>
                {data!.items.map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="pl-5 font-medium">{o.name}</TableCell>
                    <TableCell><Badge variant="info" size="sm">{humanize(o.org_type)}</Badge></TableCell>
                    <TableCell className="text-muted-foreground">{o.state_code ?? '—'}</TableCell>
                    <TableCell className="pr-5 text-center">{o.is_active ? <Badge variant="success" size="sm">Active</Badge> : <Badge variant="neutral" size="sm">Inactive</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {open ? <NewOrgDialog onClose={() => setOpen(false)} onSaved={reload} /> : null}
    </div>
  );
}

function NewOrgDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = React.useState({ name: '', org_type: 'STATE_AGENCY', state_code: '', description: '' });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    try { await orgApi.create({ name: f.name, org_type: f.org_type, state_code: f.state_code || null, description: f.description || null }); onSaved(); onClose(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Create failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>New organization</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Name *</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Type</Label><Select value={f.org_type} onChange={(e) => setF({ ...f, org_type: e.target.value })}>{ORG_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</Select></div>
            <div className="space-y-1.5"><Label>State</Label><Select value={f.state_code} onChange={(e) => setF({ ...f, state_code: e.target.value })}><option value="">—</option>{US_STATES.map((s) => <option key={s.code} value={s.code}>{s.code}</option>)}</Select></div>
          </div>
          <div className="space-y-1.5"><Label>Description</Label><Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!f.name || busy}>Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
