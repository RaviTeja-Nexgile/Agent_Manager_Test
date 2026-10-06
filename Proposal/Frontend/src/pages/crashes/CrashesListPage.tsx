import * as React from 'react';
import { Link } from 'react-router-dom';
import { CarFront, Filter, Plus, Search } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState } from '@/components/ui/empty-state';
import { PhaseBadge } from '@/components/shell/StatusBadge';
import { NewCrashDialog } from './NewCrashDialog';

import { useApi } from '@/lib/useApi';
import { crashApi, type CrashListParams } from '@/lib/endpoints';
import { LIFECYCLE_PHASES, SCOPE_OPTIONS, US_STATES } from '@/lib/constants';
import { formatDate } from '@/lib/format';
import { useAuth } from '@/app/auth';
import { hasPermission, isStateScoped } from '@/lib/permissions';

const PAGE_SIZE = 25;

export function CrashesListPage() {
  const { user } = useAuth();
  const canCreate = hasPermission(user, 'crash:create');
  const stateScoped = isStateScoped(user);

  const [q, setQ] = React.useState('');
  const [stateCode, setStateCode] = React.useState('');
  const [scope, setScope] = React.useState('');
  const [phase, setPhase] = React.useState('');
  const [page, setPage] = React.useState(0);
  const [newOpen, setNewOpen] = React.useState(false);

  const params: CrashListParams = {
    q: q || undefined,
    state_code: stateCode || undefined,
    scope: scope || undefined,
    lifecycle_phase: phase || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };

  const { data, loading, error, reload } = useApi(
    () => crashApi.list(params),
    [q, stateCode, scope, phase, page],
  );

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const showingFrom = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const showingTo = Math.min(total, (page + 1) * PAGE_SIZE);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Crash Records"
        icon={CarFront}
        title="Crashes"
        subtitle="Every CCFP crash record in your scope — initial incident through publication."
        actions={
          canCreate ? (
            <Button type="button" onClick={() => setNewOpen(true)}>
              <Plus className="h-4 w-4" /> New crash
            </Button>
          ) : null
        }
      />

      {canCreate ? (
        <NewCrashDialog
          open={newOpen}
          onOpenChange={setNewOpen}
          defaultState={stateScoped ? user?.allowed_states?.[0] : undefined}
          onCreated={() => {
            setPage(0);
            reload();
          }}
        />
      ) : null}

      <Card>
        <CardContent className="p-4">
          <div className="grid gap-3 md:grid-cols-12">
            <div className="relative md:col-span-4">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => { setQ(e.target.value); setPage(0); }}
                placeholder="Search CCFP ID or local report #…"
                className="pl-9"
              />
            </div>
            {!stateScoped ? (
              <div className="md:col-span-3">
                <Select value={stateCode} onChange={(e) => { setStateCode(e.target.value); setPage(0); }}>
                  <option value="">All States</option>
                  {US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                </Select>
              </div>
            ) : null}
            <div className={stateScoped ? 'md:col-span-4' : 'md:col-span-2'}>
              <Select value={scope} onChange={(e) => { setScope(e.target.value); setPage(0); }}>
                <option value="">All scopes</option>
                {SCOPE_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </div>
            <div className={stateScoped ? 'md:col-span-4' : 'md:col-span-3'}>
              <Select value={phase} onChange={(e) => { setPhase(e.target.value); setPage(0); }}>
                <option value="">All phases</option>
                {LIFECYCLE_PHASES.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </Select>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <Filter className="h-3.5 w-3.5" />
            <span>
              Showing <span className="font-medium text-foreground">{showingFrom}–{showingTo}</span> of {total}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">CCFP ID</TableHead>
                <TableHead>Location</TableHead>
                <TableHead className="text-center">Phase</TableHead>
                <TableHead className="text-right">Vehicles</TableHead>
                <TableHead className="text-right">Fatalities</TableHead>
                <TableHead className="pr-5 text-right">Crash date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                [...Array(6)].map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6} className="p-3"><Skeleton className="h-6 w-full" /></TableCell>
                  </TableRow>
                ))
              ) : error ? (
                <TableRow><TableCell colSpan={6}><EmptyState icon={CarFront} title="Couldn't load crashes" description={error.message} /></TableCell></TableRow>
              ) : items.length === 0 ? (
                <TableRow><TableCell colSpan={6}><EmptyState icon={CarFront} title="No crashes match your filters" description="Adjust the filters or search above." /></TableCell></TableRow>
              ) : (
                items.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="pl-5">
                      <Link to={`/crashes/${c.id}`} className="font-medium text-federal-blue hover:underline">{c.ccfp_identifier}</Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{[c.city, c.state_code].filter(Boolean).join(', ') || '—'}</TableCell>
                    <TableCell className="text-center"><PhaseBadge phase={c.lifecycle_phase} /></TableCell>
                    <TableCell className="text-right tabular-nums">{c.num_vehicles ?? '—'}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.num_fatalities ?? '—'}</TableCell>
                    <TableCell className="pr-5 text-right text-muted-foreground">{formatDate(c.crash_date)}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {total > PAGE_SIZE ? (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Previous</Button>
          <span className="text-sm text-muted-foreground">Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
          <Button variant="outline" size="sm" disabled={showingTo >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      ) : null}
    </div>
  );
}
