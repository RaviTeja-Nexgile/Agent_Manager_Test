import * as React from 'react';
import { ChevronDown, KeyRound, Pencil, Plus, ShieldCheck } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { permissionApi, roleApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { cn } from '@/lib/utils';
import { humanize } from '@/lib/format';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type { Permission, RoleDetail } from '@/lib/types';

/** A permission code chip with the module prefix tinted and the action muted. */
function PermChip({ code }: { code: string }) {
  const i = code.indexOf(':');
  const mod = i >= 0 ? code.slice(0, i) : code;
  const action = i >= 0 ? code.slice(i) : '';
  return (
    <span className="inline-flex items-center rounded-md border border-border bg-muted/40 px-2 py-0.5 font-mono text-[11px] leading-5">
      <span className="font-semibold text-federal-blue">{mod}</span>
      <span className="text-muted-foreground">{action}</span>
    </span>
  );
}

/** A toggleable permission chip used by the role permission editor. */
function PermToggle({ code, on, onToggle }: { code: string; on: boolean; onToggle: () => void }) {
  const i = code.indexOf(':');
  const mod = i >= 0 ? code.slice(0, i) : code;
  const action = i >= 0 ? code.slice(i) : '';
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={on}
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] leading-5 transition-colors',
        on
          ? 'border-federal-blue/40 bg-federal-blue/10'
          : 'border-border bg-muted/20 opacity-60 hover:opacity-100',
      )}
    >
      <span className={cn('font-semibold', on ? 'text-federal-blue' : 'text-muted-foreground')}>{mod}</span>
      <span className="text-muted-foreground">{action}</span>
    </button>
  );
}

export function RolesPage() {
  const { user } = useAuth();
  const canManage = hasAnyPermission(user, ['admin:roles']);

  // Load roles + their permissions together so we can show counts and expand
  // instantly (admin page; a dozen small parallel reads is fine).
  const { data, loading, reload } = useApi(async () => {
    const roles = await roleApi.list().catch(() => []);
    const details = await Promise.all(roles.map((r) => roleApi.get(r.id).catch(() => null)));
    const byId: Record<string, RoleDetail> = {};
    for (const d of details) if (d) byId[d.id] = d;
    return { roles, byId };
  }, []);
  const { data: perms, loading: pLoading, reload: reloadPerms } = useApi(
    () => permissionApi.list().catch(() => []),
    [],
  );
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<string | null>(null);
  const [newRoleOpen, setNewRoleOpen] = React.useState(false);
  const [newPermOpen, setNewPermOpen] = React.useState(false);

  const permsByCategory = (perms ?? []).reduce<Record<string, Permission[]>>((acc, p) => {
    (acc[p.category] ??= []).push(p);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" icon={ShieldCheck} title="Roles & permissions" subtitle="The 12 CCFP roles and the permission catalog." />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        {/* Roles */}
        <Card>
          <CardHeader>
            <CardHeading
              icon={ShieldCheck}
              title="Roles"
              description="Select a role to view its permissions."
              actions={
                canManage ? (
                  <Button size="sm" onClick={() => setNewRoleOpen(true)}>
                    <Plus className="h-4 w-4" /> New role
                  </Button>
                ) : undefined
              }
            />
          </CardHeader>
          <CardContent className="space-y-2">
            {loading ? (
              [...Array(6)].map((_, i) => <Skeleton key={i} className="h-14 w-full" />)
            ) : (
              (data?.roles ?? []).map((r) => {
                const open = expanded === r.id;
                const rolePerms = data?.byId[r.id]?.permissions ?? [];
                const isEditing = editing === r.id;
                return (
                  <div
                    key={r.id}
                    className={cn(
                      'overflow-hidden rounded-lg border transition-colors',
                      open ? 'border-federal-blue/40 bg-federal-blue/[0.03]' : 'border-border',
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setExpanded(open ? null : r.id);
                        setEditing(null);
                      }}
                      aria-expanded={open}
                      className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/40"
                    >
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-federal-blue/10 text-federal-blue">
                        <ShieldCheck className="h-[18px] w-[18px]" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-foreground">{r.name}</span>
                        <span className="mt-0.5 flex items-center gap-2">
                          <span className="font-mono text-[11px] text-muted-foreground">{r.code}</span>
                          <span className="text-[11px] text-muted-foreground">·</span>
                          <span className="text-[11px] text-muted-foreground">{rolePerms.length} permissions</span>
                        </span>
                      </span>
                      {r.is_system ? <Badge variant="neutral" size="sm">System</Badge> : null}
                      <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
                    </button>
                    {open ? (
                      <div className="border-t border-border bg-background/60 px-3 py-3">
                        {isEditing && canManage ? (
                          <PermissionEditor
                            roleId={r.id}
                            allPerms={perms ?? []}
                            permsByCategory={permsByCategory}
                            current={rolePerms.map((p) => p.code)}
                            onCancel={() => setEditing(null)}
                            onSaved={() => {
                              setEditing(null);
                              reload();
                            }}
                          />
                        ) : (
                          <>
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-eyebrow">Assigned permissions</span>
                              {canManage ? (
                                <Button size="xs" variant="outline" onClick={() => setEditing(r.id)}>
                                  <Pencil className="h-3 w-3" /> Edit permissions
                                </Button>
                              ) : null}
                            </div>
                            <div className="mt-2">
                              {rolePerms.length === 0 ? (
                                <span className="text-xs text-muted-foreground">No permissions assigned.</span>
                              ) : (
                                <div className="flex flex-wrap gap-1.5">
                                  {rolePerms.map((p) => <PermChip key={p.id} code={p.code} />)}
                                </div>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        {/* Permission catalog */}
        <Card>
          <CardHeader>
            <CardHeading
              icon={KeyRound}
              title="Permission catalog"
              description={`${perms?.length ?? 0} permissions across ${Object.keys(permsByCategory).length} modules.`}
              actions={
                canManage ? (
                  <Button size="sm" variant="outline" onClick={() => setNewPermOpen(true)}>
                    <Plus className="h-4 w-4" /> New permission
                  </Button>
                ) : undefined
              }
            />
          </CardHeader>
          <CardContent className="space-y-0">
            {pLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              Object.entries(permsByCategory).map(([cat, list], idx) => (
                <div key={cat} className={cn('py-3', idx > 0 && 'border-t border-border')}>
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-eyebrow">{humanize(cat)}</span>
                    <span className="inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-muted-foreground">
                      {list.length}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {list.map((p) => <PermChip key={p.id} code={p.code} />)}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {newRoleOpen ? (
        <NewRoleDialog
          onClose={() => setNewRoleOpen(false)}
          onSaved={() => {
            setNewRoleOpen(false);
            reload();
          }}
        />
      ) : null}
      {newPermOpen ? (
        <NewPermissionDialog
          onClose={() => setNewPermOpen(false)}
          onSaved={() => {
            setNewPermOpen(false);
            reloadPerms();
          }}
        />
      ) : null}
    </div>
  );
}

/** Inline editor: toggle permission chips on/off and persist via setPermissions. */
function PermissionEditor({
  roleId,
  allPerms,
  permsByCategory,
  current,
  onCancel,
  onSaved,
}: {
  roleId: string;
  allPerms: Permission[];
  permsByCategory: Record<string, Permission[]>;
  current: string[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set(current));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function toggle(code: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await roleApi.setPermissions(roleId, { permission_codes: [...selected] });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  // Show categories in a stable order; fall back to all perms if grouping is empty.
  const categories = Object.keys(permsByCategory).length
    ? Object.entries(permsByCategory)
    : [['all', allPerms] as const];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-eyebrow">Edit permissions</span>
        <span className="text-[11px] text-muted-foreground">{selected.size} selected</span>
      </div>
      <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
        {categories.map(([cat, list]) => (
          <div key={cat}>
            <div className="mb-1.5 text-eyebrow">{humanize(cat)}</div>
            <div className="flex flex-wrap gap-1.5">
              {list.map((p) => (
                <PermToggle key={p.id} code={p.code} on={selected.has(p.code)} onToggle={() => toggle(p.code)} />
              ))}
            </div>
          </div>
        ))}
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button size="sm" onClick={save} disabled={busy}>
          Save permissions
        </Button>
      </div>
    </div>
  );
}

function NewRoleDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [code, setCode] = React.useState('');
  const [name, setName] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await roleApi.create({ code, name, description: description || null });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0">
          <DialogTitle>New role</DialogTitle>
        </DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Code *</Label>
            <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="CUSTOM_ROLE" />
          </div>
          <div className="space-y-1.5">
            <Label>Name *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={save} disabled={!code || !name || busy}>
            Create role
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewPermissionDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [code, setCode] = React.useState('');
  const [name, setName] = React.useState('');
  const [category, setCategory] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await permissionApi.create({ code, name, category, description: description || null });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0">
          <DialogTitle>New permission</DialogTitle>
        </DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Code *</Label>
            <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="module:action" />
          </div>
          <div className="space-y-1.5">
            <Label>Name *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Category *</Label>
            <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="admin" />
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={save} disabled={!code || !name || !category || busy}>
            Create permission
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
