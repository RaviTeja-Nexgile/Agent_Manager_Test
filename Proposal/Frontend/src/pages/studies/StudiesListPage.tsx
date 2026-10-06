import * as React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Boxes, Plus, ShieldAlert, Truck } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useApi } from '@/lib/useApi';
import { studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { formatDate, humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { cn } from '@/lib/utils';

type BadgeVariant = 'success' | 'info' | 'neutral' | 'warning' | 'danger';
const STUDY_STATUS_STYLE: Record<string, { chip: string; badge: BadgeVariant }> = {
  ACTIVE: { chip: 'bg-success-green/10 text-success-green-700', badge: 'success' },
  PLANNING: { chip: 'bg-federal-blue/10 text-federal-blue', badge: 'info' },
  CLOSED: { chip: 'bg-neutral-base/15 text-neutral-base-700', badge: 'neutral' },
  PUBLISHED: { chip: 'bg-dot-navy/10 text-dot-navy', badge: 'info' },
};

function severityVariant(sev: string): BadgeVariant {
  const s = sev.toLowerCase();
  if (s.includes('fatal') && s.includes('serious')) return 'warning';
  if (s.includes('fatal')) return 'danger';
  if (s.includes('serious')) return 'warning';
  return 'neutral';
}

export function StudiesListPage() {
  const { user } = useAuth();
  const canCreate = hasPermission(user, 'study:create');
  const { data, loading, reload } = useApi(() => studyApi.list(), []);
  const [open, setOpen] = React.useState(false);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Study & Data" icon={Boxes} title="Studies" subtitle="CCFP study phases and their configuration."
        actions={canCreate ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New study</Button> : null} />

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-40 w-full" />)}</div>
      ) : (data?.length ?? 0) === 0 ? (
        <EmptyState icon={Boxes} title="No studies" description="Create a study to begin." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data!.map((s) => {
            const st = STUDY_STATUS_STYLE[s.status] ?? STUDY_STATUS_STYLE.PLANNING;
            return (
              <Link key={s.id} to={`/studies/${s.id}`} className="group block">
                <Card className="flex h-full flex-col transition-all hover:-translate-y-0.5 hover:border-federal-blue/40 hover:shadow-pop">
                  <CardContent className="flex flex-1 flex-col p-5">
                    <div className="flex items-start gap-3">
                      <span className={cn('inline-flex h-11 w-11 shrink-0 flex-col items-center justify-center rounded-lg', st.chip)}>
                        <span className="text-[8px] font-semibold uppercase leading-none tracking-wider">Phase</span>
                        <span className="text-lg font-bold leading-none">{s.phase_number}</span>
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <span className="truncate font-mono text-[11px] uppercase tracking-wide text-muted-foreground">{s.code}</span>
                          <Badge variant={st.badge}>{humanize(s.status)}</Badge>
                        </div>
                        <h3 className="mt-1 text-base font-semibold leading-snug text-foreground">{s.name}</h3>
                      </div>
                    </div>

                    <div className="mt-4 rounded-lg border border-border bg-muted/30 p-3">
                      <div className="flex items-start gap-2.5">
                        <Truck className="mt-0.5 h-4 w-4 shrink-0 text-federal-blue" />
                        <div className="min-w-0">
                          <div className="text-eyebrow">Vehicle class</div>
                          <div className="text-sm leading-snug text-foreground">{s.vehicle_type}</div>
                        </div>
                      </div>
                      <div className="mt-2.5 flex items-center gap-2.5">
                        <ShieldAlert className="h-4 w-4 shrink-0 text-federal-blue" />
                        <span className="text-eyebrow">Severity</span>
                        <Badge variant={severityVariant(s.crash_severity)} size="sm">{s.crash_severity}</Badge>
                      </div>
                    </div>

                    <div className="mt-auto flex items-end justify-between gap-3 pt-4">
                      <div className="grid grid-cols-2 gap-x-6">
                        <div>
                          <div className="text-eyebrow">Start</div>
                          <div className="text-xs font-medium tabular-nums text-foreground">{formatDate(s.start_date)}</div>
                        </div>
                        <div>
                          <div className="text-eyebrow">Pilot</div>
                          <div className="text-xs font-medium tabular-nums text-foreground">{formatDate(s.pilot_start_date)}</div>
                        </div>
                      </div>
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-federal-blue transition-transform group-hover:translate-x-0.5">
                        Open <ArrowRight className="h-3.5 w-3.5" />
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}

      {open ? <NewStudyDialog onClose={() => setOpen(false)} onSaved={reload} /> : null}
    </div>
  );
}

function NewStudyDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = React.useState({ code: '', name: '', phase_number: '1', vehicle_type: '', crash_severity: '', description: '' });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const valid = f.code && f.name && f.vehicle_type && f.crash_severity;

  async function save() {
    setBusy(true); setError(null);
    try {
      await studyApi.create({ code: f.code, name: f.name, phase_number: Number(f.phase_number), vehicle_type: f.vehicle_type, crash_severity: f.crash_severity, description: f.description || null });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Create failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>New study</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Code *</Label><Input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="PHASE2-MDT" /></div>
          <div className="space-y-1.5"><Label>Phase #</Label><Input type="number" min={1} value={f.phase_number} onChange={(e) => setF({ ...f, phase_number: e.target.value })} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label>Name *</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Vehicle type *</Label><Input value={f.vehicle_type} onChange={(e) => setF({ ...f, vehicle_type: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Crash severity *</Label><Input value={f.crash_severity} onChange={(e) => setF({ ...f, crash_severity: e.target.value })} /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label>Description</Label><Textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter className="mt-0"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button onClick={save} disabled={!valid || busy}>Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
