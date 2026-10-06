import * as React from 'react';
import { BookMarked, Download, Search } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { SensitivityBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { dataAttributeApi } from '@/lib/endpoints';
import { humanize } from '@/lib/format';
import type { DataDictionaryEntry } from '@/lib/types';

/**
 * The CCFP PCR Data Dictionary (GAP-PCR-09; also the SOO's data-dictionary
 * deliverable).
 *
 * The new HDTS PCR data form carries no element codes — only section headers
 * and field labels — so the traceability from "field on the published form" to
 * the internal CCFP code had no written record, and a State mapping its own PCR
 * had no shared key to map against. This page is that record. It is GENERATED
 * from the catalog, so it cannot drift from what the application actually
 * collects.
 */
export function DataDictionaryPage() {
  const { data, loading } = useApi(() => dataAttributeApi.dictionary().catch(() => []), []);
  const [q, setQ] = React.useState('');
  const [section, setSection] = React.useState('');

  const sections = React.useMemo(
    () => [...new Set((data ?? []).map((e) => e.form_section).filter(Boolean))] as string[],
    [data],
  );
  // How much of the catalog is genuinely traceable to the published form. Stated
  // outright rather than left for a reader to infer row by row (GAP-PCR-09).
  const labelled = (data ?? []).filter((e) => e.form_label).length;
  const rows = (data ?? []).filter((e) => {
    if (section && e.form_section !== section) return false;
    if (!q) return true;
    const s = q.toLowerCase();
    return (
      e.code.toLowerCase().includes(s) ||
      e.name.toLowerCase().includes(s) ||
      (e.form_label ?? '').toLowerCase().includes(s) ||
      e.values.some((v) => v.label.toLowerCase().includes(s))
    );
  });

  /** CSV export — the dictionary is a deliverable, not only a screen. */
  function exportCsv() {
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = [
      'Form section', 'Form label', 'CCFP code', 'MMUCC code', 'Attribute name',
      'Data type', 'Max selections', 'Repeats on', 'Applies to', 'Sensitivity',
      'Active', 'Superseded by', 'Values',
    ];
    const lines = rows.map((e) => [
      e.form_section, e.form_label, e.code, e.mmucc_code, e.name,
      e.data_type, e.max_selections ?? '', e.repeats_on ?? '', e.applies_to ?? '',
      e.sensitivity, e.is_active ? 'Yes' : 'No', e.superseded_by_code ?? '',
      // Retired values are marked, not dropped: the dictionary has to let a
      // reader resolve historical data as well as current data.
      e.values.map((v) => (v.is_active ? v.label : `${v.label} (retired)`)).join(' | '),
    ].map(esc).join(','));
    const blob = new Blob([[header.map(esc).join(','), ...lines].join('\n')], {
      type: 'text/csv;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ccfp-pcr-data-dictionary.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Study & Data"
        icon={BookMarked}
        title="CCFP PCR Data Dictionary"
        subtitle="Form label ↔ CCFP code ↔ type ↔ cardinality ↔ value list, generated from the attribute catalog."
        actions={
          <Button size="sm" variant="outline" onClick={exportCsv} disabled={rows.length === 0}>
            <Download className="h-4 w-4" /> Export CSV
          </Button>
        }
      />
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search code, attribute, form label, or value…"
                className="pl-9"
              />
            </div>
            <Select value={section} onChange={(e) => setSection(e.target.value)} className="sm:w-72">
              <option value="">All sections</option>
              {sections.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-5"><Skeleton className="h-64 w-full" /></div>
          ) : rows.length === 0 ? (
            <div className="p-5"><EmptyState icon={BookMarked} title="No entries match" /></div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">Form label</TableHead>
                    <TableHead>CCFP code</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Cardinality</TableHead>
                    <TableHead>Repeats on</TableHead>
                    <TableHead>Sensitivity</TableHead>
                    <TableHead className="pr-5">Values</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((e) => <DictionaryRow key={e.code} entry={e} />)}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        {rows.length} of {data?.length ?? 0} entries.{' '}
        <span className="font-medium text-foreground">
          {labelled} carry a printed form label; {(data?.length ?? 0) - labelled} do not
        </span>{' '}
        and are shown under their internal name — those rows are not yet traceable to the published
        form. The published form carries no element codes, so the CCFP code is an internal
        identifier, retained because collected values, study requirements, and every State field
        mapping already reference it. MMUCC lineage is recorded separately where it exists.
      </p>
    </div>
  );
}

function DictionaryRow({ entry: e }: { entry: DataDictionaryEntry }) {
  return (
    <TableRow>
      <TableCell className="pl-5">
        {/* A row without a captured form label is marked, not filled in with the
            internal name. The dictionary's job is traceability to the published
            form; showing the internal name as though it were the printed label
            would make every row look traceable (GAP-PCR-09). */}
        {e.form_label ? (
          <div className="font-medium">{e.form_label}</div>
        ) : (
          <div className="font-medium text-muted-foreground">
            {e.name}
            <Badge variant="warning" size="sm" title="No printed form label has been captured for this attribute — the internal name is shown instead">
              label not recorded
            </Badge>
          </div>
        )}
        <div className="text-xs text-muted-foreground">{e.form_section}</div>
      </TableCell>
      <TableCell className="align-top">
        <div className="font-medium tabular-nums">{e.code}</div>
        {e.mmucc_code ? <div className="text-xs text-muted-foreground">MMUCC {e.mmucc_code}</div> : null}
      </TableCell>
      <TableCell className="align-top">
        <Badge variant="neutral" size="sm">{humanize(e.data_type)}</Badge>
      </TableCell>
      <TableCell className="align-top text-muted-foreground">
        {e.max_selections == null
          ? 'Single'
          : e.max_selections === 1
            ? 'Check only 1'
            : `Up to ${e.max_selections}`}
      </TableCell>
      <TableCell className="align-top text-muted-foreground">
        {e.repeats_on ? humanize(e.repeats_on) : 'Crash'}
        {e.applies_to ? <div className="text-xs">{humanize(e.applies_to)}</div> : null}
      </TableCell>
      <TableCell className="align-top">
        {e.sensitivity === 'INTERNAL' || e.sensitivity === 'PUBLIC'
          ? <span className="text-xs text-muted-foreground">{humanize(e.sensitivity)}</span>
          : <SensitivityBadge level={e.sensitivity} />}
      </TableCell>
      <TableCell className="pr-5 align-top">
        {e.values.length === 0 ? (
          <span className="text-xs text-muted-foreground">—</span>
        ) : (
          <ul className="flex flex-wrap gap-1">
            {e.values.map((v) => (
              <li key={v.label}>
                {/* A retired value is shown struck through rather than hidden:
                    the dictionary must let a reader resolve data collected
                    under the previous specification (GAP-PCR-09b). */}
                <span
                  className={`inline-block rounded border px-1.5 py-0.5 text-xs ${
                    v.is_active ? '' : 'text-muted-foreground line-through'
                  }`}
                  title={
                    v.is_active
                      ? undefined
                      : `Retired (${v.spec_version})${v.superseded_by ? ` — now recorded as "${v.superseded_by}"` : ' — no replacement'}`
                  }
                >
                  {v.label}
                </span>
              </li>
            ))}
          </ul>
        )}
      </TableCell>
    </TableRow>
  );
}
