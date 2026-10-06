import * as React from 'react';
import { History } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useApi } from '@/lib/useApi';
import { auditApi } from '@/lib/endpoints';
import { formatDateTime, humanize, shortId } from '@/lib/format';

const PAGE_SIZE = 50;

export function AuditLogPage() {
  const [entityType, setEntityType] = React.useState('');
  const [action, setAction] = React.useState('');
  const [page, setPage] = React.useState(0);
  const { data, loading } = useApi(
    () => auditApi.list({ entity_type: entityType || undefined, action: action || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [entityType, action, page],
  );
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" icon={History} title="Audit log" subtitle="Immutable record of state-changing actions." />

      <Card>
        <CardContent className="p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input value={entityType} onChange={(e) => { setEntityType(e.target.value); setPage(0); }} placeholder="Filter by entity type (e.g. crash, report)" />
            <Input value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} placeholder="Filter by action (e.g. CREATE, SUBMIT)" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? <div className="p-5"><Skeleton className="h-64 w-full" /></div> : items.length === 0 ? (
            <div className="p-5"><EmptyState icon={History} title="No audit entries" /></div>
          ) : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">When</TableHead><TableHead>Action</TableHead><TableHead>Entity</TableHead><TableHead>Actor</TableHead><TableHead className="pr-5">Detail</TableHead></TableRow></TableHeader>
              <TableBody>
                {items.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="pl-5 text-xs text-muted-foreground">{formatDateTime(e.occurred_at)}</TableCell>
                    <TableCell><Badge variant="info" size="sm">{humanize(e.action)}</Badge></TableCell>
                    <TableCell>{humanize(e.entity_type)}</TableCell>
                    <TableCell className="text-muted-foreground">{e.actor_user_id ? shortId(e.actor_user_id) : 'system'}</TableCell>
                    <TableCell className="pr-5"><code className="text-xs text-muted-foreground">{e.after_state ? JSON.stringify(e.after_state).slice(0, 80) : '—'}</code></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {total > PAGE_SIZE ? (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-sm text-muted-foreground">Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
          <Button variant="outline" size="sm" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      ) : null}
    </div>
  );
}
