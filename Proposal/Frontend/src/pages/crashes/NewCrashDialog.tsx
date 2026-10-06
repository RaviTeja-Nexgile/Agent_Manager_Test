import * as React from 'react';
import { useNavigate } from 'react-router-dom';

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { useApi } from '@/lib/useApi';
import { crashApi, studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { US_STATES } from '@/lib/constants';

export interface NewCrashDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultState?: string;
  onCreated: () => void;
}

const EMPTY_FORM = {
  study_id: '',
  local_report_number: '',
  crash_date: '',
  crash_time: '',
  state_code: '',
  city: '',
  county: '',
  street_highway: '',
  num_vehicles: '',
  num_persons: '',
  num_fatalities: '',
};

export function NewCrashDialog({ open, onOpenChange, defaultState, onCreated }: NewCrashDialogProps) {
  const navigate = useNavigate();
  // GET /studies is auth-only server-side (crash-creating roles like the MCSAP
  // CMV Inspector don't hold study:read), so fetch for every user — never fall
  // back to raw study UUIDs. The backend already scopes the list for
  // study-restricted principals (AUTH-2).
  const { data: studies, loading: studiesLoading, error: studiesError, reload: reloadStudies } =
    useApi(() => studyApi.list(), []);

  // ACTIVE studies collect new crashes; a CLOSED study stays selectable so an
  // inspector can still file a late report for a crash that occurred within
  // its window (backend-enforced against the study's end date). PLANNING /
  // PUBLISHED studies never accept crashes and are not offered.
  const studyOptions = React.useMemo(() => {
    const all = studies ?? [];
    return [
      ...all.filter((s) => s.status === 'ACTIVE').map((s) => ({ id: s.id, label: `${s.name} (${s.code})` })),
      ...all.filter((s) => s.status === 'CLOSED').map((s) => ({ id: s.id, label: `${s.name} (${s.code}) — closed` })),
    ];
  }, [studies]);

  // The default is the first ACTIVE study: the backend orders by phase, so
  // this is the current phase (Phase 1 HDTS today, later phases automatically
  // once earlier ones close). A closed study is never the default.
  const defaultStudyId = React.useMemo(
    () => (studies ?? []).find((s) => s.status === 'ACTIVE')?.id ?? '',
    [studies],
  );

  const [form, setForm] = React.useState(EMPTY_FORM);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Reset the whole form when the dialog closes so every open starts clean on
  // the default study (no stale draft bleeding into the next crash record);
  // while open, apply the default as soon as studies load but preserve a
  // manual selection for as long as it remains a valid option.
  React.useEffect(() => {
    if (!open) {
      setForm(EMPTY_FORM);
      return;
    }
    setError(null);
    setForm((f) => ({
      ...f,
      study_id: f.study_id && studyOptions.some((o) => o.id === f.study_id)
        ? f.study_id
        : defaultStudyId,
      state_code: defaultState ?? f.state_code,
    }));
  }, [open, studyOptions, defaultStudyId, defaultState]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const valid = form.study_id && form.state_code;

  async function submit() {
    if (!valid) return;
    setSubmitting(true);
    setError(null);
    try {
      const crash = await crashApi.create({
        study_id: form.study_id,
        local_report_number: form.local_report_number || null,
        crash_date: form.crash_date || null,
        crash_time: form.crash_time || null,
        state_code: form.state_code || null,
        city: form.city || null,
        county: form.county || null,
        street_highway: form.street_highway || null,
        num_vehicles: form.num_vehicles ? Number(form.num_vehicles) : null,
        num_persons: form.num_persons ? Number(form.num_persons) : null,
        num_fatalities: form.num_fatalities ? Number(form.num_fatalities) : null,
      });
      onOpenChange(false);
      onCreated();
      navigate(`/crashes/${crash.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to create crash');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader className="mb-0">
          <DialogTitle>New crash record</DialogTitle>
          <DialogDescription>Creates a crash shell and assigns a unique CCFP identifier.</DialogDescription>
        </DialogHeader>

        <div className="-mr-6 max-h-[60vh] space-y-4 overflow-y-auto py-4 pr-6">
          {studiesError ? (
            <Alert variant="destructive">
              <AlertDescription className="flex items-center justify-between gap-3">
                <span>Couldn&apos;t load the study list.</span>
                <Button size="xs" variant="outline" onClick={reloadStudies}>Retry</Button>
              </AlertDescription>
            </Alert>
          ) : !studiesLoading && studyOptions.length === 0 ? (
            <Alert variant="warning"><AlertDescription>No study in your scope is currently accepting new crash records.</AlertDescription></Alert>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="study">Study *</Label>
              <Select id="study" value={form.study_id} onChange={set('study_id')} disabled={studiesLoading || studyOptions.length === 0}>
                {studiesLoading ? (
                  <option value="">Loading studies…</option>
                ) : (
                  <>
                    {form.study_id ? null : <option value="" disabled hidden>Select a study…</option>}
                    {studyOptions.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                  </>
                )}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="state">State *</Label>
              <Select id="state" value={form.state_code} onChange={set('state_code')} disabled={!!defaultState}>
                <option value="">Select…</option>
                {US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="local">Local report #</Label>
              <Input id="local" value={form.local_report_number} onChange={set('local_report_number')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="date">Crash date</Label>
              <Input id="date" type="date" value={form.crash_date} onChange={set('crash_date')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="time">Crash time</Label>
              <Input id="time" type="time" value={form.crash_time} onChange={set('crash_time')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="city">City</Label>
              <Input id="city" value={form.city} onChange={set('city')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="county">County</Label>
              <Input id="county" value={form.county} onChange={set('county')} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="road">Street / highway</Label>
              <Input id="road" value={form.street_highway} onChange={set('street_highway')} placeholder="e.g. I-70 near MM 252" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="veh"># Vehicles</Label>
              <Input id="veh" type="number" min={0} value={form.num_vehicles} onChange={set('num_vehicles')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="per"># Persons</Label>
              <Input id="per" type="number" min={0} value={form.num_persons} onChange={set('num_persons')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fat"># Fatalities</Label>
              <Input id="fat" type="number" min={0} value={form.num_fatalities} onChange={set('num_fatalities')} />
            </div>
          </div>
          {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
        </div>

        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>Cancel</Button>
          <Button onClick={submit} disabled={!valid || submitting}>
            {submitting ? <Spinner className="h-4 w-4" /> : null} Create crash
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
