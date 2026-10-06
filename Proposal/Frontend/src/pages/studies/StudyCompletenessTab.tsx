import * as React from 'react';
import { ClipboardCheck, Plus, Trash2 } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useStudy } from './StudyDetailPage';
import type { CompletenessTokenSpec } from '@/lib/types';

export function StudyCompletenessTab() {
  const { study } = useStudy();
  const { user } = useAuth();
  const canConfig = hasAnyPermission(user, ['admin:completeness', 'study:configure']);
  const { data, loading, reload } = useApi(() => studyApi.completenessRules(study.id).catch(() => []), [study.id]);
  const [open, setOpen] = React.useState(false);

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={ClipboardCheck} title="Completeness rules" description="Rules defining when a crash record is complete."
          actions={canConfig ? <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Add rule</Button> : undefined} />
      </CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-40 w-full" /> : (data?.length ?? 0) === 0 ? (
          <EmptyState icon={ClipboardCheck} title="No completeness rules" />
        ) : (
          <ul className="space-y-3">
            {data!.map((r) => (
              <li key={r.id} className="flex items-start justify-between gap-3 rounded-md border border-border p-3">
                <div>
                  <div className="flex items-center gap-2"><span className="font-medium">{r.name}</span>{r.is_active ? <Badge variant="success" size="sm">Active</Badge> : <Badge variant="neutral" size="sm">Inactive</Badge>}</div>
                  {r.description ? <p className="text-sm text-muted-foreground">{r.description}</p> : null}
                  {r.definition ? <code className="mt-1 block text-xs text-muted-foreground">{JSON.stringify(r.definition)}</code> : null}
                </div>
                {canConfig ? <Button size="icon-sm" variant="ghost" onClick={async () => { await studyApi.deleteCompletenessRule(r.id); reload(); }}><Trash2 className="h-3.5 w-3.5 text-alert-red" /></Button> : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      {open ? <RuleDialog studyId={study.id} onClose={() => setOpen(false)} onSaved={reload} /> : null}
    </Card>
  );
}

function RuleDialog({ studyId, onClose, onSaved }: { studyId: string; onClose: () => void; onSaved: () => void }) {
  // Token vocabulary is backend-driven (GET /completeness-rule-tokens) so the
  // builder and the data-driven evaluator share one source of truth (STUD-4).
  const { data: catalog, loading: catalogLoading } = useApi(
    () => studyApi.completenessRuleTokens().then((r) => r.tokens).catch(() => [] as CompletenessTokenSpec[]),
    [],
  );

  const [name, setName] = React.useState('');
  const [description, setDescription] = React.useState('');
  // Selected tokens + per-threshold values keyed by param name.
  const [selected, setSelected] = React.useState<Record<string, boolean>>({});
  const [thresholds, setThresholds] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const tokens = catalog ?? [];

  function toggle(token: string) {
    setSelected((s) => ({ ...s, [token]: !s[token] }));
  }

  function buildDefinition(): { definition: Record<string, unknown>; error?: string } {
    const requires = tokens.filter((t) => selected[t.token]).map((t) => t.token);
    if (requires.length === 0) {
      return { definition: {}, error: 'Select at least one completeness token.' };
    }
    const params: Record<string, number> = {};
    for (const t of tokens) {
      if (!selected[t.token]) continue;
      for (const p of t.params) {
        const raw = thresholds[p.name];
        if (raw === undefined || raw === '') continue; // omit -> backend default applies
        const n = Number(raw);
        if (!Number.isInteger(n) || n < 0) {
          return { definition: {}, error: `Threshold "${p.name}" must be a non-negative integer.` };
        }
        params[p.name] = n;
      }
    }
    const definition: Record<string, unknown> = { requires };
    if (Object.keys(params).length > 0) definition.params = params;
    return { definition };
  }

  async function save() {
    setError(null);
    const built = buildDefinition();
    if (built.error) { setError(built.error); return; }
    setBusy(true);
    try {
      await studyApi.createCompletenessRule(studyId, {
        name,
        description: description || null,
        definition: built.definition,
        is_active: true,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Add completeness rule</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Name *</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="space-y-1.5"><Label>Description</Label><Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
          <div className="space-y-1.5">
            <Label>Required checks *</Label>
            {catalogLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : tokens.length === 0 ? (
              <p className="text-sm text-muted-foreground">No completeness tokens available.</p>
            ) : (
              <ul className="space-y-2 rounded-md border border-border p-2">
                {tokens.map((t) => (
                  <li key={t.token} className="space-y-1.5">
                    <label className="flex items-center gap-2 text-sm">
                      <Checkbox checked={!!selected[t.token]} onChange={() => toggle(t.token)} />
                      <code className="text-xs">{t.token}</code>
                    </label>
                    {selected[t.token] && t.params.length > 0 ? (
                      <div className="ml-6 space-y-1">
                        {t.params.map((p) => (
                          <div key={p.name} className="flex items-center gap-2">
                            <Label className="text-xs text-muted-foreground" htmlFor={`thr-${p.name}`}>{p.name}</Label>
                            <Input
                              id={`thr-${p.name}`}
                              type="number"
                              min={0}
                              step={1}
                              className="h-8 w-24"
                              placeholder={String(p.default)}
                              value={thresholds[p.name] ?? ''}
                              onChange={(e) => setThresholds((s) => ({ ...s, [p.name]: e.target.value }))}
                            />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!name || busy}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
