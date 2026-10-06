import * as React from 'react';
import {
  BarChart3,
  CheckCircle2,
  Download,
  FileBarChart2,
  FileText,
  Globe,
  LayoutDashboard,
  Plus,
  Share2,
  Table2,
  type LucideIcon,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { reportApi, roleApi } from '@/lib/endpoints';
import { US_STATES } from '@/lib/constants';
import { ApiError } from '@/lib/api';
import { humanize } from '@/lib/format';
import { hasPermission, hasRole } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import type { Report, ShareAudience } from '@/lib/types';

export function ReportsPage() {
  const { user } = useAuth();
  const canCreate = hasPermission(user, 'report:create');
  const canPublish = hasPermission(user, 'report:publish');
  const canShare = hasPermission(user, 'report:share');
  const canDownload = hasPermission(user, 'report:download');
  const { data, loading, reload } = useApi(() => reportApi.list().catch(() => []), []);

  const [newOpen, setNewOpen] = React.useState(false);
  const [shareFor, setShareFor] = React.useState<Report | null>(null);
  const [msg, setMsg] = React.useState<string | null>(null);

  async function publish(r: Report) {
    setMsg(null);
    try { await reportApi.publish(r.id); reload(); setMsg(`Published "${r.name}".`); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : 'Publish failed'); }
  }
  async function download(r: Report) {
    try {
      const csv = await reportApi.download(r.id);
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${r.name.replace(/\s+/g, '_')}.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Analysis & Reporting" icon={FileBarChart2} title="Reports" subtitle="Dashboards, tables, and de-identified public outputs."
        actions={canCreate ? <Button onClick={() => setNewOpen(true)}><Plus className="h-4 w-4" /> New report</Button> : null} />

      {msg ? <Alert variant="info"><AlertDescription>{msg}</AlertDescription></Alert> : null}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-44 w-full rounded-lg" />)}
        </div>
      ) : (data?.length ?? 0) === 0 ? (
        <Card><CardContent className="p-5"><EmptyState icon={FileBarChart2} title="No reports" description="Reports you own, that are shared with you, or published appear here." /></CardContent></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data!.map((r) => (
            <ReportCard
              key={r.id}
              report={r}
              canDownload={canDownload}
              canShare={canShare}
              canPublish={canPublish}
              onDownload={() => download(r)}
              onShare={() => setShareFor(r)}
              onPublish={() => publish(r)}
            />
          ))}
        </div>
      )}

      {newOpen ? <NewReportDialog onClose={() => setNewOpen(false)} onSaved={reload} /> : null}
      {shareFor ? <ShareDialog report={shareFor} onClose={() => setShareFor(null)} /> : null}
    </div>
  );
}

/** Icon + color tint per report type, drawn from the federal palette. */
const TYPE_META: Record<string, { icon: LucideIcon; tone: string }> = {
  DASHBOARD: { icon: LayoutDashboard, tone: 'bg-federal-blue/10 text-federal-blue' },
  REPORT: { icon: FileText, tone: 'bg-dot-navy/10 text-dot-navy' },
  TABLE: { icon: Table2, tone: 'bg-success-green/15 text-success-green-700' },
  VISUALIZATION: { icon: BarChart3, tone: 'bg-alert-amber/15 text-alert-amber-700' },
};

function ReportCard({
  report: r,
  canDownload,
  canShare,
  canPublish,
  onDownload,
  onShare,
  onPublish,
}: {
  report: Report;
  canDownload: boolean;
  canShare: boolean;
  canPublish: boolean;
  onDownload: () => void;
  onShare: () => void;
  onPublish: () => void;
}) {
  const meta = TYPE_META[r.report_type] ?? { icon: FileBarChart2, tone: 'bg-muted text-muted-foreground' };
  const Icon = meta.icon;
  const showPublish = canPublish && !r.is_published;
  const hasActions = canDownload || canShare || showPublish;

  return (
    <Card className="flex flex-col transition-shadow hover:shadow-pop">
      <CardContent className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className={`mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${meta.tone}`}>
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold leading-snug text-foreground" title={r.name}>{r.name}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">{humanize(r.report_type)}</p>
            </div>
          </div>
          {r.is_published ? (
            <Badge variant="success" size="sm" className="shrink-0"><CheckCircle2 className="h-3 w-3" /> Published</Badge>
          ) : (
            <Badge variant="neutral" size="sm" className="shrink-0">Draft</Badge>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" size="sm">{humanize(r.visibility)}</Badge>
          {/* A State-bound report reads only within that State, so
              name the State rather than leaving "State" ambiguous. */}
          {r.state_code ? <Badge variant="info" size="sm">{r.state_code} only</Badge> : null}
          {r.is_deidentified ? <Badge variant="success" size="sm">De-identified</Badge> : null}
        </div>

        <div className="flex-1" />

        {hasActions ? (
          <div className="flex items-center gap-1 border-t border-border/60 pt-3">
            {canDownload ? <Button size="xs" variant="ghost" onClick={onDownload}><Download className="h-3.5 w-3.5" /> Download</Button> : null}
            {canShare ? <Button size="xs" variant="ghost" onClick={onShare}><Share2 className="h-3.5 w-3.5" /> Share</Button> : null}
            {showPublish ? <Button size="xs" variant="outline" className="ml-auto" onClick={onPublish}><Globe className="h-3.5 w-3.5" /> Publish</Button> : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function NewReportDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = React.useState({ name: '', report_type: 'REPORT', visibility: 'PRIVATE', state_code: '', description: '', is_deidentified: false });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save() {
    setBusy(true); setError(null);
    // The State binding only means anything on a STATE report; send
    // null otherwise so switching visibility away from State cannot leave a
    // stale binding behind.
    try { await reportApi.create({ name: f.name, report_type: f.report_type, visibility: f.visibility, state_code: f.visibility === 'STATE' ? (f.state_code || null) : null, description: f.description || null, is_deidentified: f.is_deidentified, definition: {} }); onSaved(); onClose(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Create failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>New report</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Name *</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Type</Label><Select value={f.report_type} onChange={(e) => setF({ ...f, report_type: e.target.value })}><option value="REPORT">Report</option><option value="DASHBOARD">Dashboard</option><option value="TABLE">Table</option><option value="VISUALIZATION">Visualization</option></Select></div>
            {/* The federal audience is now two tiers. "Federal (all)"
                is the pre-split meaning and is kept so existing reports stay
                describable. */}
            <div className="space-y-1.5"><Label>Visibility</Label><Select value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value })}><option value="PRIVATE">Private</option><option value="ORGANIZATION">Organization</option><option value="FMCSA_FEDERAL">FMCSA Federal</option><option value="OTHER_FEDERAL">Other Federal (BTS, NHTSA, NTSB)</option><option value="FEDERAL">Federal (all)</option><option value="STATE">State</option></Select></div>
          </div>
          {/* Which State a STATE report belongs to. Left unset the
              report is not State-bound and every participating State can read
              it — spelled out here so that is a decision, not an accident. */}
          {f.visibility === 'STATE' ? (
            <div className="space-y-1.5">
              <Label htmlFor="report-state">State</Label>
              <Select id="report-state" value={f.state_code} onChange={(e) => setF({ ...f, state_code: e.target.value })}>
                <option value="">All participating States (not State-specific)</option>
                {US_STATES.map((s) => (
                  <option key={s.code} value={s.code}>{s.code} — {s.name}</option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">
                {f.state_code
                  ? `Only ${f.state_code} users will be able to view or download this report.`
                  : 'Every participating State user will be able to view this report.'}
              </p>
            </div>
          ) : null}
          <div className="space-y-1.5"><Label>Description</Label><Textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={f.is_deidentified} onChange={(e) => setF({ ...f, is_deidentified: e.target.checked })} /> De-identified (required before publishing)</label>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!f.name || busy}>Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * A report can be shared to a named role, or *released to an
 * audience tier*. The Jan-2026 BRD assigns every outward release — Other
 * Federal (BTS/NHTSA/NTSB), participating States, and the Public — to the CCFP
 * Database Administrator, so those three options are offered only to a caller
 * who can actually use them. The backend enforces the same rule and 403s
 * regardless; this just avoids presenting an action that would be refused.
 */
const OUTWARD_AUDIENCES: ShareAudience[] = ['OTHER_FEDERAL', 'STATE', 'PUBLIC'];
const AUDIENCE_LABEL: Record<ShareAudience, string> = {
  FMCSA_FEDERAL: 'FMCSA Federal Users (Project Team, DBA, HQ, Enforcement)',
  OTHER_FEDERAL: 'Other Federal Users (BTS, NHTSA, NTSB)',
  STATE: 'Participating State Users (State-specific, no PII)',
  PUBLIC: 'Public Users (de-identified summary only)',
};

function ShareDialog({ report, onClose }: { report: Report; onClose: () => void }) {
  const { data: roles } = useApi(() => roleApi.list().catch(() => []), []);
  const { user } = useAuth();
  // Mirrors OUTWARD_SHARING_ROLE_CODES on the backend.
  const canReleaseOutward = hasRole(user, ['CCFP_DB_ADMIN', 'SYSTEM_ADMIN']);
  const [mode, setMode] = React.useState<'role' | 'audience'>('role');
  const [roleCode, setRoleCode] = React.useState('');
  const [audience, setAudience] = React.useState<ShareAudience>('FMCSA_FEDERAL');
  const [audienceState, setAudienceState] = React.useState('');
  const [canDownload, setCanDownload] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);

  const audiences: ShareAudience[] = canReleaseOutward
    ? (['FMCSA_FEDERAL', ...OUTWARD_AUDIENCES] as ShareAudience[])
    : ['FMCSA_FEDERAL'];
  const incomplete =
    mode === 'role' ? !roleCode : audience === 'STATE' && !audienceState;

  async function share() {
    setBusy(true); setMsg(null); setFailed(false);
    try {
      await reportApi.share(report.id, {
        shared_with_role_code: mode === 'role' ? roleCode || null : null,
        audience: mode === 'audience' ? audience : null,
        audience_state_code: mode === 'audience' && audience === 'STATE' ? audienceState : null,
        can_download: canDownload,
      });
      setMsg('Shared.');
    } catch (e) {
      setFailed(true);
      setMsg(e instanceof ApiError ? e.message : 'Share failed');
    } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Share “{report.name}”</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="space-y-3">
          <div className="space-y-1.5"><Label htmlFor="share-mode">Share by</Label>
            <Select id="share-mode" value={mode} onChange={(e) => setMode(e.target.value as 'role' | 'audience')}>
              <option value="role">Role</option>
              <option value="audience">Audience tier</option>
            </Select>
          </div>

          {mode === 'role' ? (
            <div className="space-y-1.5"><Label htmlFor="share-role">Share with role</Label>
              <Select id="share-role" value={roleCode} onChange={(e) => setRoleCode(e.target.value)}>
                <option value="">Select role…</option>
                {(roles ?? []).map((r) => <option key={r.id} value={r.code}>{r.name}</option>)}
              </Select>
            </div>
          ) : (
            <>
              <div className="space-y-1.5"><Label htmlFor="share-audience">Audience</Label>
                <Select id="share-audience" value={audience} onChange={(e) => setAudience(e.target.value as ShareAudience)}>
                  {audiences.map((a) => <option key={a} value={a}>{AUDIENCE_LABEL[a]}</option>)}
                </Select>
                {!canReleaseOutward ? (
                  <p className="text-xs text-muted-foreground">
                    Releasing to Other Federal, State or Public users is reserved to the
                    CCFP Database Administrator.
                  </p>
                ) : null}
              </div>
              {audience === 'STATE' ? (
                <div className="space-y-1.5"><Label htmlFor="share-audience-state">State</Label>
                  <Select id="share-audience-state" value={audienceState} onChange={(e) => setAudienceState(e.target.value)}>
                    <option value="">Select State…</option>
                    {US_STATES.map((s) => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
                  </Select>
                </div>
              ) : null}
            </>
          )}

          <label className="flex items-center gap-2 text-sm"><Checkbox checked={canDownload} onChange={(e) => setCanDownload(e.target.checked)} /> Allow download</label>
          {msg ? <Alert variant={failed ? 'destructive' : 'info'}><AlertDescription>{msg}</AlertDescription></Alert> : null}
        </div>
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Close</Button><Button onClick={share} disabled={incomplete || busy}>Share</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
