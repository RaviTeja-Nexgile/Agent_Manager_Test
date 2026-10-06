import * as React from 'react';
import { Download, FileText, Upload } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { SensitivityBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { documentApi } from '@/lib/endpoints';
import { API_BASE, ApiError } from '@/lib/api';
import { formatDateTime, humanize } from '@/lib/format';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';

const DOC_TYPES = ['DOCUMENT', 'PDF', 'IMAGE', 'VIDEO', 'SPREADSHEET', 'ELD_CSV', 'REPORT', 'OTHER'];
const SENSITIVITIES = ['INTERNAL', 'PUBLIC', 'PII', 'SENSITIVE', 'CIPSEA'];

export function CrashDocumentsTab() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canUpload = hasAnyPermission(user, ['source_data:ingest', 'crash:update']);
  const { data, loading, reload } = useApi(() => documentApi.forCrash(crash.id).catch(() => []), [crash.id]);
  const [open, setOpen] = React.useState(false);

  async function download(id: string) {
    try {
      const { signed_url } = await documentApi.downloadLink(id);
      // signed_url is an /api/v1/... path; build absolute against the proxy base origin.
      const base = API_BASE.startsWith('http') ? API_BASE.replace(/\/api\/v1$/, '') : '';
      window.open(`${base}${signed_url}`, '_blank', 'noopener');
    } catch {
      /* ignore */
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={FileText}
          title="Documents"
          description="Reports, images, ELD files, and other crash artifacts (encrypted object storage)."
          actions={canUpload ? <Button size="sm" onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Upload</Button> : undefined}
        />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-28 w-full" /></div> : (data?.length ?? 0) === 0 ? (
          <div className="p-5"><EmptyState icon={FileText} title="No documents" description="Uploaded artifacts will appear here." /></div>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-5">File</TableHead><TableHead>Type</TableHead><TableHead>Sensitivity</TableHead>
              <TableHead>Scan</TableHead><TableHead>Uploaded</TableHead><TableHead className="pr-5 text-right">Action</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data!.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="pl-5 font-medium">{d.file_name}</TableCell>
                  <TableCell>{humanize(d.doc_type)}</TableCell>
                  <TableCell><SensitivityBadge level={d.sensitivity} /> {d.sensitivity === 'INTERNAL' || d.sensitivity === 'PUBLIC' ? humanize(d.sensitivity) : null}</TableCell>
                  <TableCell><Badge variant={d.malware_scan === 'CLEAN' ? 'success' : d.malware_scan === 'INFECTED' ? 'danger' : 'neutral'} size="sm">{humanize(d.malware_scan)}</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDateTime(d.uploaded_at)}</TableCell>
                  <TableCell className="pr-5 text-right"><Button size="xs" variant="outline" onClick={() => download(d.id)}><Download className="h-3.5 w-3.5" /> Download</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {open ? <UploadDialog crashId={crash.id} onClose={() => setOpen(false)} onSaved={reload} /> : null}
    </Card>
  );
}

function UploadDialog({ crashId, onClose, onSaved }: { crashId: string; onClose: () => void; onSaved: () => void }) {
  const [file, setFile] = React.useState<File | null>(null);
  const [docType, setDocType] = React.useState('DOCUMENT');
  const [sensitivity, setSensitivity] = React.useState('INTERNAL');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function upload() {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      await documentApi.upload(file, { crash_id: crashId, doc_type: docType, sensitivity });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Upload failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Upload document</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
          <div className="space-y-3">
            <div className="space-y-1.5"><Label>File *</Label><Input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
            <div className="space-y-1.5"><Label>Type</Label><Select value={docType} onChange={(e) => setDocType(e.target.value)}>{DOC_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</Select></div>
            <div className="space-y-1.5"><Label>Sensitivity</Label><Select value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>{SENSITIVITIES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</Select></div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={upload} disabled={!file || busy}>{busy ? <Spinner className="h-4 w-4" /> : null} Upload</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
