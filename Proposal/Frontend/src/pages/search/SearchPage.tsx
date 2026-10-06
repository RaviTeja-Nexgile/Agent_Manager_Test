import * as React from 'react';
import { Link } from 'react-router-dom';
import { CarFront, FileText, Search, Truck, User as UserIcon, FileBarChart2 } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { searchApi } from '@/lib/endpoints';
import { humanize } from '@/lib/format';
import type { SearchHit } from '@/lib/types';

const ICONS: Record<string, LucideIcon> = {
  crash: CarFront, person: UserIcon, carrier: Truck, report: FileBarChart2, document: FileText,
};

export function SearchPage() {
  const [q, setQ] = React.useState('');
  const [hits, setHits] = React.useState<SearchHit[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setLoading(true); setError(null);
    try { const res = await searchApi.search(q.trim()); setHits(res.hits); }
    catch (err) { setError((err as Error).message); } finally { setLoading(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Crash Records" icon={Search} title="Search" subtitle="Full-text search across crashes, persons, motor carriers, reports, and documents — including report and document content." />

      <Card>
        <CardContent className="p-4">
          <form onSubmit={run} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search CCFP ID, name, carrier, report or document content…" className="pl-9" autoFocus />
            </div>
            <Button type="submit" disabled={q.trim().length < 2 || loading}>{loading ? <Spinner className="h-4 w-4" /> : <Search className="h-4 w-4" />} Search</Button>
          </form>
        </CardContent>
      </Card>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {hits === null ? null : hits.length === 0 ? (
        <EmptyState icon={Search} title="No results" description="Try a different query. Results respect your State scope and PII clearance." />
      ) : (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y divide-border">
              {hits.map((h) => {
                const Icon = ICONS[h.type] ?? Search;
                const body = (
                  <>
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-federal-blue/10 text-federal-blue"><Icon className="h-4 w-4" /></span>
                    <div className="min-w-0"><div className="truncate text-sm font-medium">{h.label}</div><div className="text-xs text-muted-foreground"><Badge variant="neutral" size="sm">{humanize(h.type)}</Badge></div></div>
                  </>
                );
                return (
                  <li key={`${h.type}-${h.id}`}>
                    {h.crash_id ? (
                      <Link to={`/crashes/${h.crash_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/40">{body}</Link>
                    ) : (
                      <div className="flex items-center gap-3 px-5 py-3">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
