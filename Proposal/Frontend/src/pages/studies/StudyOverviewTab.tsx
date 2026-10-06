import * as React from 'react';
import { Boxes, Pencil } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { DefList } from '@/components/crash/DefList';
import { studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useStudy } from './StudyDetailPage';

export function StudyOverviewTab() {
  const { study, reload } = useStudy();
  const { user } = useAuth();
  const canEdit = hasPermission(user, 'study:update');
  const [open, setOpen] = React.useState(false);

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Boxes} title="Study configuration" description="Phase 0 study setup parameters."
          actions={canEdit ? <Button size="xs" variant="outline" onClick={() => setOpen(true)}><Pencil className="h-3.5 w-3.5" /> Edit</Button> : undefined} />
      </CardHeader>
      <CardContent>
        <DefList items={[
          { label: 'Code', value: study.code },
          { label: 'Phase', value: study.phase_number },
          { label: 'Name', value: study.name },
          { label: 'Status', value: study.status },
          { label: 'Vehicle type', value: study.vehicle_type },
          { label: 'Crash severity', value: study.crash_severity },
          { label: 'Start date', value: formatDate(study.start_date) },
          { label: 'End date', value: formatDate(study.end_date) },
          { label: 'Pilot start', value: formatDate(study.pilot_start_date) },
          { label: 'Description', value: study.description },
        ]} />
      </CardContent>
      {open ? <EditDialog onClose={() => setOpen(false)} onSaved={reload} study={study} /> : null}
    </Card>
  );
}

function EditDialog({ study, onClose, onSaved }: { study: ReturnType<typeof useStudy>['study']; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = React.useState({
    name: study.name, vehicle_type: study.vehicle_type, crash_severity: study.crash_severity,
    status: study.status, description: study.description ?? '',
    start_date: study.start_date ?? '', end_date: study.end_date ?? '', pilot_start_date: study.pilot_start_date ?? '',
  });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    try {
      await studyApi.update(study.id, {
        name: f.name, vehicle_type: f.vehicle_type, crash_severity: f.crash_severity, status: f.status,
        description: f.description || null, start_date: f.start_date || null, end_date: f.end_date || null, pilot_start_date: f.pilot_start_date || null,
      });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Edit study</DialogTitle></DialogHeader>
        <div className="grid max-h-[60vh] gap-3 overflow-y-auto -mr-6 py-4 pr-6 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2"><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Vehicle type</Label><Input value={f.vehicle_type} onChange={(e) => setF({ ...f, vehicle_type: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Crash severity</Label><Input value={f.crash_severity} onChange={(e) => setF({ ...f, crash_severity: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Status</Label><Select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as typeof f.status })}><option value="PLANNING">Planning</option><option value="ACTIVE">Active</option><option value="CLOSED">Closed</option><option value="PUBLISHED">Published</option></Select></div>
          <div className="space-y-1.5"><Label>Start date</Label><Input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>End date</Label><Input type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Pilot start</Label><Input type="date" value={f.pilot_start_date} onChange={(e) => setF({ ...f, pilot_start_date: e.target.value })} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label>Description</Label><Textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={busy}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
