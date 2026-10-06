import { Link } from 'react-router-dom';
import { ShieldX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ROLE_LABEL, type Role } from '@/lib/permissions';
import { humanize } from '@/lib/format';

export function NoAccessPage({ perms, roles }: { perms?: string[]; roles?: Role[] }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <span className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-alert-red/10 text-alert-red">
        <ShieldX className="h-7 w-7" />
      </span>
      <h1 className="text-display-sm font-semibold tracking-tight">Access restricted</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        You don't have permission to view this page. Access is enforced by your assigned role,
        permissions, and State scope.
      </p>
      {roles?.length ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Requires one of: {roles.map((r) => ROLE_LABEL[r]).join(', ')}
        </p>
      ) : null}
      {perms?.length ? (
        <p className="mt-1 text-xs text-muted-foreground">
          Requires permission: {perms.map((p) => humanize(p.replace(':', ' '))).join(' or ')}
        </p>
      ) : null}
      <Button asChild className="mt-6">
        <Link to="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}
