import { LibraryBig, ListChecks, Map, ShieldCheck } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useApi } from '@/lib/useApi';
import { dataMgmtApi, permissionApi, roleApi } from '@/lib/endpoints';
import { US_STATES } from '@/lib/constants';
import { humanize } from '@/lib/format';

export function ReferencePage() {
  const { data: groups, loading: gLoading } = useApi(() => dataMgmtApi.factorGroups().catch(() => []), []);
  const { data: roles, loading: rLoading } = useApi(() => roleApi.list().catch(() => []), []);
  const { data: perms, loading: pLoading } = useApi(() => permissionApi.list().catch(() => []), []);

  const permsByCategory = (perms ?? []).reduce<Record<string, number>>((acc, p) => {
    acc[p.category] = (acc[p.category] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Reference" icon={LibraryBig} title="Reference data" subtitle="Lookups and program reference values used across CCFP." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardHeading icon={ListChecks} title="Contributing-factor groups" description="BRD-specified groups for the analyst top-three prompt." /></CardHeader>
          <CardContent>
            {gLoading ? <Skeleton className="h-32 w-full" /> : (groups ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No contributing-factor groups available.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {(groups ?? []).map((g) => (
                  <li key={g.id} className="flex items-center justify-between gap-2">
                    <span>{g.name}</span><Badge variant="neutral" size="sm">{humanize(g.applies_to)}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardHeading icon={ShieldCheck} title="Roles & permission catalog" description="12 roles · permission codes by category." /></CardHeader>
          <CardContent className="space-y-4">
            {rLoading || pLoading ? <Skeleton className="h-32 w-full" /> : (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {(roles ?? []).map((r) => <Badge key={r.id} variant="info" size="sm">{r.name}</Badge>)}
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {Object.entries(permsByCategory).map(([cat, n]) => (
                    <span key={cat} className="rounded-md border border-border bg-muted/40 px-2 py-1">{humanize(cat)}: <span className="font-medium">{n}</span></span>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardHeading icon={Map} title="U.S. States & territories" description="State codes used for crash and study scoping." /></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3 lg:grid-cols-4">
              {US_STATES.map((s) => (
                <div key={s.code} className="flex justify-between border-b border-border/50 py-1">
                  <span className="text-muted-foreground">{s.name}</span><span className="font-medium tabular-nums">{s.code}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
