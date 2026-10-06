import * as React from 'react';
import { Link } from 'react-router-dom';
import {
  AlarmClockOff,
  Boxes,
  Building2,
  Database,
  History,
  PlugZap,
  Settings,
  ShieldCheck,
  Users as UsersIcon,
  type LucideIcon,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { crashApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import { hasAnyPermission, hasRole, type Role } from '@/lib/permissions';
import { useAuth } from '@/app/auth';

interface AdminLink {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
  perms?: string[];
  roles?: Role[];
}

const LINKS: AdminLink[] = [
  { to: '/admin/users', label: 'Users', description: 'Create users and manage role assignments.', icon: UsersIcon, perms: ['admin:users'] },
  { to: '/admin/organizations', label: 'Organizations', description: 'FMCSA, BTS, State agencies, partners.', icon: Building2, perms: ['admin:users', 'admin:system'] },
  { to: '/admin/roles', label: 'Roles & permissions', description: 'Review roles and the permission catalog.', icon: ShieldCheck, perms: ['admin:roles'] },
  { to: '/studies', label: 'Studies', description: 'Configure study phases, states, attributes, rules.', icon: Boxes, perms: ['study:read'] },
  { to: '/data-attributes', label: 'Data attributes', description: 'Browse the CCFP / PCR attribute catalog.', icon: Database, perms: ['study:read'] },
  { to: '/integrations', label: 'Integrations', description: 'External adapter status and validation tools.', icon: PlugZap, perms: ['source_data:ingest', 'admin:system'] },
  { to: '/admin/audit', label: 'Audit log', description: 'Immutable record of state-changing actions.', icon: History, perms: ['audit:read'] },
];

// NOTI-5: on-demand "scan for crashes missing an Initial Incident Form" control.
// Gated to project/admin (admin:system or study:configure — same permissions the
// backend endpoint requires). Calls POST /crashes/scan-missing-iif, which emits
// MISSING_IIF notifications to the responsible State analysts and returns the
// flagged count. The scan is idempotent server-side, so re-running is safe.
function MissingIifScanCard() {
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<{ flagged: number; window_hours: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await crashApi.scanMissingIif());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Scan failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="h-full">
      <CardContent className="flex items-start gap-3 p-5">
        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-federal-blue/10 text-federal-blue"><AlarmClockOff className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold">Missing Initial Incident Forms</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">Scan for crashes past the IIF window with no submitted form and notify the responsible State analysts.</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button size="sm" onClick={run} disabled={busy}>{busy ? <Spinner className="h-4 w-4" /> : <AlarmClockOff className="h-4 w-4" />} Scan for crashes missing IIF</Button>
            {result ? (
              <span className="text-sm text-muted-foreground">Flagged <span className="font-semibold text-foreground tabular-nums">{result.flagged}</span> crash{result.flagged === 1 ? '' : 'es'} (window {result.window_hours}h).</span>
            ) : null}
          </div>
          {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function AdminPage() {
  const { user } = useAuth();
  const visible = LINKS.filter((l) => (l.perms ? hasAnyPermission(user, l.perms) : true) && (l.roles ? hasRole(user, l.roles) : true));
  const canScanMissingIif = hasAnyPermission(user, ['admin:system', 'study:configure']);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" icon={Settings} title="Administration" subtitle="Program configuration and system management." />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((l) => (
          <Link key={l.to} to={l.to}>
            <Card className="h-full transition-shadow hover:shadow-pop">
              <CardContent className="flex items-start gap-3 p-5">
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-federal-blue/10 text-federal-blue"><l.icon className="h-5 w-5" /></span>
                <div>
                  <h3 className="text-base font-semibold">{l.label}</h3>
                  <p className="mt-0.5 text-sm text-muted-foreground">{l.description}</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
      {canScanMissingIif ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MissingIifScanCard />
        </div>
      ) : null}
    </div>
  );
}
