import * as React from 'react';
import { Search, ShieldCheck, UserPlus, Users as UsersIcon } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { orgApi, roleApi, studyApi, userApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { US_STATES } from '@/lib/constants';
import { humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type { User } from '@/lib/types';

const PAGE_SIZE = 25;

export function UsersPage() {
  const { user } = useAuth();
  const canManageRoles = hasPermission(user, 'admin:roles');
  const [q, setQ] = React.useState('');
  const [page, setPage] = React.useState(0);
  const { data, loading, reload } = useApi(() => userApi.list({ q: q || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }), [q, page]);
  const [newOpen, setNewOpen] = React.useState(false);
  const [rolesFor, setRolesFor] = React.useState<User | null>(null);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" icon={UsersIcon} title="Users" subtitle="Manage users, roles, and scoped access."
        actions={<Button onClick={() => setNewOpen(true)}><UserPlus className="h-4 w-4" /> New user</Button>} />

      <Card>
        <CardContent className="p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Search by name or email…" className="pl-9" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? <div className="p-5"><Skeleton className="h-40 w-full" /></div> : items.length === 0 ? (
            <div className="p-5"><EmptyState icon={UsersIcon} title="No users found" /></div>
          ) : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">Name</TableHead><TableHead>Email</TableHead><TableHead>Title</TableHead><TableHead className="text-center">Status</TableHead><TableHead className="pr-5 text-right">Actions</TableHead></TableRow></TableHeader>
              <TableBody>
                {items.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="pl-5 font-medium">{u.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{u.email}</TableCell>
                    <TableCell className="text-muted-foreground">{u.title ?? '—'}</TableCell>
                    <TableCell className="text-center"><Badge variant={u.status === 'ACTIVE' ? 'success' : 'neutral'} size="sm">{humanize(u.status)}</Badge></TableCell>
                    <TableCell className="pr-5 text-right">
                      <div className="flex justify-end gap-1">
                        {canManageRoles ? <Button size="xs" variant="ghost" onClick={() => setRolesFor(u)}><ShieldCheck className="h-3.5 w-3.5" /> Roles</Button> : null}
                        {u.status === 'ACTIVE' ? <Button size="xs" variant="ghost" onClick={async () => { await userApi.deactivate(u.id); reload(); }}>Deactivate</Button> : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {total > PAGE_SIZE ? (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-sm text-muted-foreground">Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
          <Button variant="outline" size="sm" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      ) : null}

      {newOpen ? <NewUserDialog onClose={() => setNewOpen(false)} onSaved={reload} /> : null}
      {rolesFor ? <RolesDialog target={rolesFor} onClose={() => setRolesFor(null)} /> : null}
    </div>
  );
}

function NewUserDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = React.useState({ email: '', full_name: '', title: '', phone: '', piv_cac_required: false });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const valid = /.+@.+\..+/.test(f.email) && f.full_name.trim();

  async function save() {
    setBusy(true); setError(null);
    try { await userApi.create({ email: f.email, full_name: f.full_name, title: f.title || null, phone: f.phone || null, piv_cac_required: f.piv_cac_required }); onSaved(); onClose(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Create failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>New user</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Email *</Label><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Full name *</Label><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Title</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Phone</Label><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></div>
          </div>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={f.piv_cac_required} onChange={(e) => setF({ ...f, piv_cac_required: e.target.checked })} /> PIV/CAC required</label>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!valid || busy}>Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RolesDialog({ target, onClose }: { target: User; onClose: () => void }) {
  const { data: assignments, reload } = useApi(() => userApi.roles(target.id).catch(() => []), [target.id]);
  const { data: roles } = useApi(() => roleApi.list().catch(() => []), []);
  const { data: studies, error: studiesError, reload: reloadStudies } = useApi(() => studyApi.list(), []);
  const { data: orgs } = useApi(() => orgApi.list({ limit: 500 }).then((p) => p.items).catch(() => []), []);
  const [roleCode, setRoleCode] = React.useState('');
  const [scope, setScope] = React.useState('GLOBAL');
  const [stateCode, setStateCode] = React.useState('');
  const [studyId, setStudyId] = React.useState('');
  const [orgId, setOrgId] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const roleName = (id: string) => (roles ?? []).find((r) => r.id === id)?.name ?? id.slice(0, 8);
  const studyName = (id: string) => (studies ?? []).find((s) => s.id === id)?.name ?? '—';

  // Every non-GLOBAL scope needs its target — the backend rejects a scoped
  // assignment without one (it would silently resolve to unrestricted).
  const scopeTargetMissing =
    (scope === 'STATE' && !stateCode) || (scope === 'STUDY' && !studyId) || (scope === 'ORGANIZATION' && !orgId);

  async function add() {
    if (!roleCode || scopeTargetMissing) return;
    setBusy(true); setError(null);
    try {
      await userApi.assignRole(target.id, {
        role_code: roleCode,
        scope_type: scope,
        state_code: scope === 'STATE' ? stateCode || null : null,
        organization_id: scope === 'ORGANIZATION' ? orgId || null : null,
        study_id: scope === 'STUDY' ? studyId || null : null,
      });
      setRoleCode(''); reload();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Assign failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader className="mb-0"><DialogTitle>Roles — {target.full_name}</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-4">
          <div>
            <div className="text-eyebrow mb-2">Current assignments</div>
            {(assignments?.length ?? 0) === 0 ? <p className="text-sm text-muted-foreground">No roles assigned.</p> : (
              <ul className="space-y-1.5">
                {assignments!.map((a) => (
                  <li key={a.id} className="flex items-center justify-between rounded-md border border-border px-3 py-1.5 text-sm">
                    <span>{roleName(a.role_id)} <Badge variant="neutral" size="sm">{humanize(a.scope_type)}{a.state_code ? ` · ${a.state_code}` : ''}{a.study_id ? ` · ${studyName(a.study_id)}` : ''}</Badge></span>
                    <Button size="xs" variant="ghost" onClick={async () => { await userApi.revokeRole(target.id, a.id); reload(); }}>Revoke</Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="space-y-2 rounded-md border border-border p-3">
            <div className="text-eyebrow">Assign role</div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Select aria-label="Role" value={roleCode} onChange={(e) => setRoleCode(e.target.value)}>
                <option value="">Select role…</option>
                {(roles ?? []).map((r) => <option key={r.id} value={r.code}>{r.name}</option>)}
              </Select>
              <Select aria-label="Scope" value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="GLOBAL">Global</option><option value="STATE">State</option><option value="ORGANIZATION">Organization</option><option value="STUDY">Study</option>
              </Select>
              {scope === 'STATE' ? (
                <Select aria-label="State" value={stateCode} onChange={(e) => setStateCode(e.target.value)} className="sm:col-span-2">
                  <option value="">Select State…</option>{US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                </Select>
              ) : null}
              {scope === 'ORGANIZATION' ? (
                <Select aria-label="Organization" value={orgId} onChange={(e) => setOrgId(e.target.value)} className="sm:col-span-2">
                  <option value="">Select organization…</option>
                  {(orgs ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Select>
              ) : null}
              {scope === 'STUDY' ? (
                <Select aria-label="Study" value={studyId} onChange={(e) => setStudyId(e.target.value)} className="sm:col-span-2">
                  <option value="">Select study…</option>
                  {(studies ?? []).map((s) => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
                </Select>
              ) : null}
            </div>
            {scope === 'STUDY' && studiesError ? (
              <p className="text-sm text-destructive">
                Couldn&apos;t load studies. <Button size="xs" variant="outline" onClick={reloadStudies}>Retry</Button>
              </p>
            ) : null}
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button size="sm" onClick={add} disabled={!roleCode || scopeTargetMissing || busy}>Add assignment</Button>
          </div>
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
