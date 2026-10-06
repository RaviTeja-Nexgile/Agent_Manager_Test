import * as React from 'react';
import { Database, Search } from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { SensitivityBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { studyApi } from '@/lib/endpoints';
import { humanize } from '@/lib/format';
import { hasAnyPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useStudy } from './StudyDetailPage';

export function StudyAttributesTab() {
  const { study } = useStudy();
  const { user } = useAuth();
  const canConfig = hasAnyPermission(user, ['study:configure', 'admin:attributes']);
  const { data, loading, reload } = useApi(() => studyApi.attributes(study.id).catch(() => []), [study.id]);
  const [q, setQ] = React.useState('');
  const [section, setSection] = React.useState('');

  const sections = React.useMemo(() => [...new Set((data ?? []).map((a) => a.pcr_section).filter(Boolean))] as string[], [data]);
  const filtered = (data ?? []).filter((a) => {
    if (section && a.pcr_section !== section) return false;
    if (q) { const s = q.toLowerCase(); return a.code.toLowerCase().includes(s) || a.name.toLowerCase().includes(s); }
    return true;
  });

  async function toggleRequired(attributeId: string, current: boolean) {
    await studyApi.updateAttribute(study.id, attributeId, { is_required: !current, is_optional: current });
    reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardHeading icon={Database} title="Attribute requirements" description="Per-study required / optional / editable settings for CCFP attributes." />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search code or name…" className="pl-9" />
          </div>
          <Select value={section} onChange={(e) => setSection(e.target.value)} className="sm:w-56">
            <option value="">All sections</option>
            {sections.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </div>
        {loading ? <Skeleton className="h-64 w-full" /> : filtered.length === 0 ? (
          <EmptyState icon={Database} title="No attributes match" />
        ) : (
          <div className="max-h-[28rem] overflow-y-auto rounded-md border border-border">
            <Table>
              <TableHeader><TableRow>
                <TableHead className="pl-5">Code</TableHead><TableHead>Name</TableHead><TableHead>Section</TableHead>
                <TableHead>Sensitivity</TableHead><TableHead className="text-center">Required</TableHead><TableHead className="text-center">Editable</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {filtered.map((a) => (
                  <TableRow key={a.attribute_id}>
                    <TableCell className="pl-5 font-medium tabular-nums">{a.code}</TableCell>
                    <TableCell>{a.name}</TableCell>
                    <TableCell className="text-muted-foreground">{a.pcr_section ? humanize(a.pcr_section) : '—'}</TableCell>
                    <TableCell>{a.sensitivity === 'INTERNAL' || a.sensitivity === 'PUBLIC' ? <span className="text-xs text-muted-foreground">{humanize(a.sensitivity)}</span> : <SensitivityBadge level={a.sensitivity} />}</TableCell>
                    <TableCell className="text-center">
                      {canConfig ? (
                        <Button size="xs" variant={a.is_required ? 'default' : 'outline'} onClick={() => toggleRequired(a.attribute_id, a.is_required)}>{a.is_required ? 'Required' : 'Optional'}</Button>
                      ) : a.is_required ? <Badge variant="info" size="sm">Required</Badge> : <Badge variant="neutral" size="sm">Optional</Badge>}
                    </TableCell>
                    <TableCell className="text-center">{a.is_editable ? <Badge variant="success" size="sm">Yes</Badge> : <Badge variant="neutral" size="sm">Read-only</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{filtered.length} attribute(s){canConfig ? ' · click Required/Optional to toggle' : ''}.</p>
      </CardContent>
    </Card>
  );
}
