import * as React from 'react';
import { Settings2, Trash2 } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useApi } from '@/lib/useApi';
import { studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useStudy } from './StudyDetailPage';

export function StudyParametersTab() {
  const { study } = useStudy();
  const { user } = useAuth();
  const canConfig = hasPermission(user, 'study:configure');
  const { data, loading, reload } = useApi(() => studyApi.parameters(study.id).catch(() => []), [study.id]);
  const [open, setOpen] = React.useState(false);

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Settings2} title="Study parameters" description="Scope rules and configuration values (key / JSON value)."
          actions={canConfig ? <Button size="sm" onClick={() => setOpen(true)}>Add / update</Button> : undefined} />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-24 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={Settings2} title="No parameters" /></div>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead className="pl-5">Key</TableHead><TableHead>Value</TableHead><TableHead>Description</TableHead>{canConfig ? <TableHead className="pr-5 text-right">Action</TableHead> : null}</TableRow></TableHeader>
            <TableBody>
              {data!.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="pl-5 font-medium">{p.param_key}</TableCell>
                  <TableCell><code className="text-xs">{JSON.stringify(p.param_value)}</code></TableCell>
                  <TableCell className="text-muted-foreground">{p.description ?? '—'}</TableCell>
                  {canConfig ? <TableCell className="pr-5 text-right"><Button size="icon-sm" variant="ghost" onClick={async () => { await studyApi.deleteParameter(study.id, p.param_key); reload(); }}><Trash2 className="h-3.5 w-3.5 text-alert-red" /></Button></TableCell> : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {open ? <ParamDialog studyId={study.id} onClose={() => setOpen(false)} onSaved={reload} /> : null}
    </Card>
  );
}

function ParamDialog({ studyId, onClose, onSaved }: { studyId: string; onClose: () => void; onSaved: () => void }) {
  const [key, setKey] = React.useState('');
  const [value, setValue] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    let parsed: unknown = value;
    try { parsed = JSON.parse(value); } catch { /* keep as string */ }
    try { await studyApi.upsertParameter(studyId, { param_key: key.trim(), param_value: parsed, description: description || null }); onSaved(); onClose(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Add / update parameter</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Key *</Label><Input value={key} onChange={(e) => setKey(e.target.value)} placeholder="e.g. min_gvwr_lbs" /></div>
          <div className="space-y-1.5"><Label>Value (JSON or text)</Label><Input value={value} onChange={(e) => setValue(e.target.value)} placeholder='e.g. 26001 or ["7","8"]' /></div>
          <div className="space-y-1.5"><Label>Description</Label><Input value={description} onChange={(e) => setDescription(e.target.value)} /></div>
          <Alert variant="info"><AlertDescription>Values that parse as JSON are stored as JSON; otherwise stored as text.</AlertDescription></Alert>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!key.trim() || busy}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
