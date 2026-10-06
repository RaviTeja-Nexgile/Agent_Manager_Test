import * as React from 'react';
import { Megaphone, Pencil } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { DefList } from '@/components/crash/DefList';
import { studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { humanize } from '@/lib/format';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useStudy } from './StudyDetailPage';

// STUD-5 — per-study publication settings (§8.1 / §5 Phase 7). These fields live
// on the `Study` interface (lib/types.ts); the local shape keeps the tab typed
// and resilient if the study payload is read before the spine type lands.
export type DeidentificationPolicy = 'STANDARD' | 'STRICT' | 'NONE';
export type PublicScope = 'NONE' | 'AGGREGATE_ONLY' | 'DEIDENTIFIED_RECORDS';
interface StudyPublication {
  deidentification_policy: DeidentificationPolicy;
  public_scope: PublicScope;
  publication_enabled: boolean;
  publication_notes: string | null;
}

const DEID_OPTIONS: { value: DeidentificationPolicy; label: string }[] = [
  { value: 'STANDARD', label: 'Standard' },
  { value: 'STRICT', label: 'Strict' },
  { value: 'NONE', label: 'None' },
];
const SCOPE_OPTIONS: { value: PublicScope; label: string }[] = [
  { value: 'NONE', label: 'None (no public output)' },
  { value: 'AGGREGATE_ONLY', label: 'Aggregate only' },
  { value: 'DEIDENTIFIED_RECORDS', label: 'De-identified records' },
];

function pub(study: unknown): StudyPublication {
  const s = study as Partial<StudyPublication>;
  return {
    deidentification_policy: (s.deidentification_policy ?? 'STANDARD') as DeidentificationPolicy,
    public_scope: (s.public_scope ?? 'AGGREGATE_ONLY') as PublicScope,
    publication_enabled: Boolean(s.publication_enabled),
    publication_notes: s.publication_notes ?? null,
  };
}

export function StudyPublicationTab() {
  const { study, reload } = useStudy();
  const { user } = useAuth();
  // Mirror the backend gate on PATCH /studies/{id} (study:update OR study:configure).
  const canEdit = hasAnyPermission(user, ['study:update', 'study:configure']);
  const [open, setOpen] = React.useState(false);
  const p = pub(study);

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={Megaphone}
          title="Publication settings"
          description="Per-study de-identification policy and public-sharing scope."
          actions={canEdit ? <Button size="xs" variant="outline" onClick={() => setOpen(true)}><Pencil className="h-3.5 w-3.5" /> Edit</Button> : undefined}
        />
      </CardHeader>
      <CardContent>
        <DefList
          items={[
            { label: 'De-identification policy', value: humanize(p.deidentification_policy) },
            { label: 'Public scope', value: humanize(p.public_scope) },
            {
              label: 'Publication enabled',
              value: p.publication_enabled
                ? <Badge variant="success" size="sm">Enabled</Badge>
                : <Badge variant="neutral" size="sm">Disabled</Badge>,
            },
            { label: 'Publication notes', value: p.publication_notes },
          ]}
        />
      </CardContent>
      {open ? <EditDialog onClose={() => setOpen(false)} onSaved={reload} studyId={study.id} initial={p} /> : null}
    </Card>
  );
}

function EditDialog({
  studyId,
  initial,
  onClose,
  onSaved,
}: {
  studyId: string;
  initial: StudyPublication;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [f, setF] = React.useState<StudyPublication>({
    deidentification_policy: initial.deidentification_policy,
    public_scope: initial.public_scope,
    publication_enabled: initial.publication_enabled,
    publication_notes: initial.publication_notes ?? '',
  });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await studyApi.update(studyId, {
        deidentification_policy: f.deidentification_policy,
        public_scope: f.public_scope,
        publication_enabled: f.publication_enabled,
        publication_notes: f.publication_notes ? f.publication_notes : null,
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
        <DialogHeader><DialogTitle>Edit publication settings</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="deid-policy">De-identification policy</Label>
            <Select
              id="deid-policy"
              value={f.deidentification_policy}
              onChange={(e) => setF({ ...f, deidentification_policy: e.target.value as DeidentificationPolicy })}
            >
              {DEID_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="public-scope">Public scope</Label>
            <Select
              id="public-scope"
              value={f.public_scope}
              onChange={(e) => setF({ ...f, public_scope: e.target.value as PublicScope })}
            >
              {SCOPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={f.publication_enabled}
              onChange={(e) => setF({ ...f, publication_enabled: e.target.checked })}
            />
            Publication enabled
          </label>
          <div className="space-y-1.5">
            <Label htmlFor="pub-notes">Publication notes</Label>
            <Textarea
              id="pub-notes"
              rows={3}
              value={f.publication_notes ?? ''}
              onChange={(e) => setF({ ...f, publication_notes: e.target.value })}
            />
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={busy}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
