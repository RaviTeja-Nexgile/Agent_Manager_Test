import {
  BarChart3,
  Calendar,
  CheckCircle2,
  Download,
  FileBarChart2,
  FileJson,
  FileText,
  Globe,
  LayoutDashboard,
  Mail,
  Scale,
  Table2,
  Tag,
  type LucideIcon,
} from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { GovBanner } from '@/components/shell/GovBanner';
import { OmbControlNumber } from '@/components/shell/OmbControlNumber';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { useApi } from '@/lib/useApi';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { publicApi } from '@/lib/endpoints';
import { API_BASE } from '@/lib/api';
import { formatDate, humanize } from '@/lib/format';
import type { PublicReport } from '@/lib/types';

/** Icon + color tint per report type, drawn from the federal palette. */
const TYPE_META: Record<string, { icon: LucideIcon; tone: string }> = {
  DASHBOARD: { icon: LayoutDashboard, tone: 'bg-federal-blue/10 text-federal-blue' },
  REPORT: { icon: FileText, tone: 'bg-dot-navy/10 text-dot-navy' },
  TABLE: { icon: Table2, tone: 'bg-success-green/15 text-success-green-700' },
  VISUALIZATION: { icon: BarChart3, tone: 'bg-alert-amber/15 text-alert-amber-700' },
};

// The machine-readable Project Open Data catalog lives at the public route and
// needs no auth; link directly so the browser opens/downloads the JSON document.
const CATALOG_URL = `${API_BASE}/public/data.json`;

/** Trim a long license URL/identifier to a compact display label. */
function licenseLabel(license: string): string {
  if (/creativecommons\.org\/publicdomain\/zero/i.test(license)) return 'CC0 1.0 (Public Domain)';
  try {
    const u = new URL(license);
    return u.hostname.replace(/^www\./, '') + u.pathname.replace(/\/$/, '');
  } catch {
    return license;
  }
}

export function PublicOutputsPage() {
  useDocumentTitle('Published Outputs');
  // The public outputs endpoint requires no auth and lists all published,
  // de-identified outputs across studies — available to every role.
  const { data, loading } = useApi(() => publicApi.allOutputs().catch(() => []), []);
  const count = data?.length ?? 0;

  return (
    <div className="space-y-6">
      <GovBanner className="rounded-md border" />
      <PageHeader eyebrow="Public" icon={Globe} title="Published outputs" subtitle="Summarized, de-identified study outputs released to the public." />

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-44 w-full rounded-lg" />)}
        </div>
      ) : count === 0 ? (
        <Card><CardContent className="p-5"><EmptyState icon={Globe} title="No published outputs yet" description="De-identified study summaries appear here after a study is published." /></CardContent></Card>
      ) : (
        <>
          {/* Open-data intro band + machine-readable catalog link */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-federal-blue-50 px-4 py-3">
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-federal-blue/10 text-federal-blue">
              <Globe className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">Open data — de-identified study outputs</p>
              <p className="text-xs text-muted-foreground">Released to the public under federal open-data requirements. Free to view and download.</p>
            </div>
            <Badge variant="info" size="sm" className="shrink-0">{count} published</Badge>
            <Button asChild variant="outline" size="xs" className="shrink-0">
              <a href={CATALOG_URL} target="_blank" rel="noopener noreferrer">
                <FileJson className="h-3.5 w-3.5" /> Download catalog (data.json)
              </a>
            </Button>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {data!.map((r) => <PublicOutputCard key={r.id} report={r} />)}
          </div>
        </>
      )}

      <OmbControlNumber />
    </div>
  );
}

function PublicOutputCard({ report: r }: { report: PublicReport }) {
  const meta = TYPE_META[r.report_type] ?? { icon: FileBarChart2, tone: 'bg-muted text-muted-foreground' };
  const Icon = meta.icon;
  const keywords = (r.keywords ?? []).filter(Boolean);

  async function downloadCsv() {
    try {
      const csv = await publicApi.downloadCsv(r.id);
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${r.name.replace(/\s+/g, '_')}.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  }

  return (
    <Card className="relative flex flex-col transition-shadow hover:shadow-pop">
      <CardContent className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <span className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${meta.tone}`}>
            <Icon className="h-5 w-5" />
          </span>
          <Badge variant="success" size="sm" className="shrink-0"><CheckCircle2 className="h-3 w-3" /> Published</Badge>
        </div>

        <div className="min-w-0">
          <h3 className="text-base font-semibold leading-snug text-foreground">{r.name}</h3>
          <p className="mt-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">{humanize(r.report_type)} · Open data</p>
        </div>

        {r.description ? <p className="line-clamp-3 text-sm text-muted-foreground">{r.description}</p> : null}

        {/* Open-data (Project Open Data) metadata: license / publisher / contact / keywords */}
        <dl className="space-y-1.5 text-xs text-muted-foreground">
          {r.license ? (
            <div className="flex items-start gap-1.5">
              <Scale className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">License</dt>
              <dd className="min-w-0 truncate" title={r.license}>{licenseLabel(r.license)}</dd>
            </div>
          ) : null}
          {r.publisher ? (
            <div className="flex items-start gap-1.5">
              <Globe className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">Publisher</dt>
              <dd className="min-w-0 truncate" title={r.publisher}>{r.publisher}</dd>
            </div>
          ) : null}
          {r.contact_email ? (
            <div className="flex items-start gap-1.5">
              <Mail className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">Contact</dt>
              <dd className="min-w-0 truncate">
                <a className="underline-offset-2 hover:underline" href={`mailto:${r.contact_email}`} title={r.contact_name ?? r.contact_email}>
                  {r.contact_name ? `${r.contact_name} (${r.contact_email})` : r.contact_email}
                </a>
              </dd>
            </div>
          ) : null}
        </dl>

        {keywords.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <Tag className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            {keywords.slice(0, 4).map((k) => (
              <Badge key={k} variant="neutral" size="sm" className="font-normal">{k}</Badge>
            ))}
            {keywords.length > 4 ? <span className="text-xs text-muted-foreground">+{keywords.length - 4} more</span> : null}
          </div>
        ) : null}

        <div className="flex-1" />

        <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5"><Calendar className="h-3.5 w-3.5" /> Released {formatDate(r.published_at)}</span>
          <Button variant="outline" size="xs" onClick={downloadCsv}><Download className="h-3.5 w-3.5" /> CSV</Button>
        </div>
      </CardContent>
    </Card>
  );
}
