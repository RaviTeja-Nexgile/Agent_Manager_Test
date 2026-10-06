import * as React from 'react';
import { MapPinned, Pencil, Plus } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { US_STATES } from '@/lib/constants';
import { formatDate, humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useStudy } from './StudyDetailPage';
import type { StudyState } from '@/lib/types';

export function StudyStatesTab() {
  const { study } = useStudy();
  const { user } = useAuth();
  const canConfig = hasPermission(user, 'study:configure');
  const { data, loading, reload } = useApi(() => studyApi.states(study.id).catch(() => []), [study.id]);
  const [dialog, setDialog] = React.useState<StudyState | 'new' | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={MapPinned} title="Participating States" description="State participation and data-sharing agreement status."
          actions={canConfig ? <Button size="sm" onClick={() => setDialog('new')}><Plus className="h-4 w-4" /> Add State</Button> : undefined} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-24 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={MapPinned} title="No States configured" /></div>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">State</TableHead><TableHead className="text-center">Participating</TableHead><TableHead>Agreement</TableHead><TableHead>Onboarded</TableHead>{canConfig ? <TableHead className="pr-5 text-right">Action</TableHead> : null}</TableRow></TableHeader>
            <TableBody>
              {data!.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="pl-5 font-medium">{US_STATES.find((x) => x.code === s.state_code)?.name ?? s.state_code}</TableCell>
                  <TableCell className="text-center">{s.is_participating ? <Badge variant="success" size="sm">Yes</Badge> : <Badge variant="neutral" size="sm">No</Badge>}</TableCell>
                  <TableCell>{humanize(s.agreement_status)}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(s.onboarded_at)}</TableCell>
                  {canConfig ? <TableCell className="pr-5 text-right"><Button size="icon-sm" variant="ghost" onClick={() => setDialog(s)}><Pencil className="h-3.5 w-3.5" /></Button></TableCell> : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {dialog ? <StateDialog studyId={study.id} state={dialog === 'new' ? null : dialog} onClose={() => setDialog(null)} onSaved={reload} /> : null}
    </Card>
  );
}

function StateDialog({ studyId, state, onClose, onSaved }: { studyId: string; state: StudyState | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = React.useState({
    state_code: state?.state_code ?? '',
    is_participating: state?.is_participating ?? false,
    agreement_status: state?.agreement_status ?? 'PENDING',
    onboarded_at: state?.onboarded_at ?? '',
    notes: state?.notes ?? '',
  });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    const body = { state_code: f.state_code, is_participating: f.is_participating, agreement_status: f.agreement_status, onboarded_at: f.onboarded_at || null, notes: f.notes || null };
    try {
      if (state) await studyApi.updateState(studyId, state.state_code, body);
      else await studyApi.addState(studyId, body);
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>{state ? 'Edit State' : 'Add State'}</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>State *</Label><Select value={f.state_code} disabled={!!state} onChange={(e) => setF({ ...f, state_code: e.target.value })}><option value="">Select…</option>{US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}</Select></div>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={f.is_participating} onChange={(e) => setF({ ...f, is_participating: e.target.checked })} /> Participating</label>
          <div className="space-y-1.5"><Label>Agreement status</Label><Select value={f.agreement_status} onChange={(e) => setF({ ...f, agreement_status: e.target.value })}><option value="PENDING">Pending</option><option value="SIGNED">Signed</option><option value="EXPIRED">Expired</option></Select></div>
          <div className="space-y-1.5"><Label>Onboarded date</Label><Input type="date" value={f.onboarded_at} onChange={(e) => setF({ ...f, onboarded_at: e.target.value })} /></div>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!f.state_code || busy}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
