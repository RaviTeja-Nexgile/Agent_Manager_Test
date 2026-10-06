import * as React from 'react';
import {
  Database, EyeOff, History, Layers, Link2, Lock, Network, Plus, Unlink,
} from 'lucide-react';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { StatTile } from '@/components/shell/StatTile';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { SensitivityBadge } from '@/components/shell/StatusBadge';
import { useApi } from '@/lib/useApi';
import { crashApi, dataAttributeApi, dataMgmtApi } from '@/lib/endpoints';
import type {
  AttributeValue,
  CrashExternalLink,
  LinkMethod,
  RepeatUnit,
  SourceRecord,
} from '@/lib/types';
import { ApiError } from '@/lib/api';
import { formatDateTime, humanize } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';
import { useCrash } from './CrashContext';

/** Display labels for the repeat units (GAP-PCR-03). */
const UNIT_LABEL: Record<RepeatUnit, string> = {
  VEHICLE: 'Vehicle',
  PERSON: 'Person',
  TRAILER: 'Trailer',
  NON_MOTORIST: 'Non-motorist',
};

type UnitKey = string;

/**
 * Split the flat attribute list into the crash-level block plus one block per
 * repeating unit (GAP-PCR-03). The new HDTS PCR form repeats whole sections —
 * Trailers 1/2/3, each Vehicle, each Person — so a single flat list would show
 * three unlabelled "Trailer GVWR" rows with no way to tell them apart.
 *
 * The API already orders crash-level first, then by unit type and position, so
 * insertion order into the Map is the display order — no re-sort needed.
 */
function groupByUnit(rows: AttributeValue[]) {
  const crashLevel: AttributeValue[] = [];
  const units = new Map<UnitKey, { type: RepeatUnit; number: number; rows: AttributeValue[] }>();
  for (const row of rows) {
    if (!row.unit_type || row.unit_number == null) {
      crashLevel.push(row);
      continue;
    }
    const key = `${row.unit_type}#${row.unit_number}`;
    let bucket = units.get(key);
    if (!bucket) {
      bucket = { type: row.unit_type, number: row.unit_number, rows: [] };
      units.set(key, bucket);
    }
    bucket.rows.push(row);
  }
  return { crashLevel, units: [...units.values()] };
}

/**
 * CCFP Aggregated Data for one crash (BRD January 2026).
 *
 * The January 2026 BRD defines "CCFP Aggregated Data" as linked CCFP crash data
 * (inspections, PCRs, investigations, reconstructions) AND data from external
 * systems related to the same crash, and makes producing it a CCFP Database
 * Administrator duty. This tab shows all three parts of that document side by
 * side: the canonical attribute values with provenance, the CCFP-collected
 * source records, and the Appendix D external-system links — with the
 * link/unlink control gated on `aggregated:link`.
 */
export function CrashAttributesTab() {
  const { crash } = useCrash();
  const { user } = useAuth();
  const canEdit = hasPermission(user, 'data_mgmt:edit');
  const canLink = hasPermission(user, 'aggregated:link');

  // One call returns the whole aggregated document; `.catch` keeps the tab
  // renderable for a caller the endpoint refuses.
  const { data: doc, loading, reload } = useApi(
    () => dataMgmtApi.aggregated(crash.id).catch(() => null),
    [crash.id],
  );
  // A complete record is locked: editing is blocked until an authorized user
  // unlocks it on the Completeness tab (DATA-1, documentation §8.8).
  const { data: completeness } = useApi(() => crashApi.completeness(crash.id).catch(() => null), [crash.id]);
  const locked = completeness?.is_locked ?? false;

  const attributes = doc?.attributes ?? [];
  const sources = doc?.source_records ?? [];
  const links = doc?.external_links ?? [];
  const summary = doc?.summary ?? null;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardHeading
            icon={Layers}
            title="CCFP Aggregated Data"
            description="Linked CCFP crash data and related external-system data for this crash (BRD Jan-2026)."
          />
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-20 w-full" />
          ) : summary ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <StatTile icon={Database} label="Canonical attributes" value={summary.current_attribute_count} />
              <StatTile
                icon={Database}
                label="Required present"
                value={summary.required_present}
                hint={`of ${summary.required_attribute_count} required`}
                tone="bg-emerald-500/10 text-emerald-600"
              />
              <StatTile
                icon={Database}
                label="Required missing"
                value={summary.required_missing}
                tone={summary.required_missing > 0 ? 'bg-destructive/10 text-destructive' : undefined}
              />
              <StatTile icon={Link2} label="CCFP source records" value={summary.source_record_count} />
              <StatTile icon={Network} label="External links" value={summary.external_link_count} />
            </div>
          ) : (
            <EmptyState
              icon={Layers}
              title="Aggregated data unavailable"
              description="The aggregated document could not be loaded for this crash."
            />
          )}
        </CardContent>
      </Card>

      <ExternalLinksCard
        crashId={crash.id}
        links={links}
        loading={loading}
        canLink={canLink}
        onChanged={reload}
      />

      <AttributesCard
        crashId={crash.id}
        attributes={attributes}
        sources={sources}
        loading={loading}
        canEdit={canEdit}
        locked={locked}
        onSaved={reload}
      />
    </div>
  );
}

// ─────────────── External-system links ───────────────
const LINK_METHOD_LABEL: Record<LinkMethod, string> = {
  MANUAL: 'Manual',
  AUTO: 'Automatic',
  RULE: 'Rule',
};

function ExternalLinksCard({
  crashId, links, loading, canLink, onChanged,
}: {
  crashId: string;
  links: CrashExternalLink[];
  loading: boolean;
  canLink: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [removing, setRemoving] = React.useState<CrashExternalLink | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={Network}
          title="External system links"
          description="Appendix D sources linked to this crash. Linking is a CCFP Database Administrator duty."
          actions={canLink ? <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Link system</Button> : undefined}
        />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-5"><Skeleton className="h-24 w-full" /></div>
        ) : links.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Network}
              title="No external systems linked"
              description={
                canLink
                  ? 'Link records from MCMIS, DACH, SafeSpect Inspections and the other Appendix D sources to build the aggregated record.'
                  : 'A CCFP Database Administrator links external-system records to this crash.'
              }
            />
          </div>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-5">System</TableHead>
              <TableHead>External reference</TableHead>
              <TableHead>Method</TableHead>
              <TableHead>Matched on</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Linked</TableHead>
              {canLink ? <TableHead className="pr-5 text-right">Action</TableHead> : null}
            </TableRow></TableHeader>
            <TableBody>
              {links.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="pl-5">
                    <span className="font-medium">{l.source_system}</span>
                    {l.source_system_name ? (
                      <span className="block text-xs text-muted-foreground">{l.source_system_name}</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="tabular-nums">{l.external_ref}</TableCell>
                  <TableCell>
                    <Badge variant={l.link_method === 'MANUAL' ? 'neutral' : 'info'} size="sm">
                      {LINK_METHOD_LABEL[l.link_method] ?? l.link_method}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-[18rem] truncate text-muted-foreground" title={l.matched_on ? JSON.stringify(l.matched_on) : undefined}>
                    {l.matched_on ? JSON.stringify(l.matched_on) : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{l.confidence != null ? `${l.confidence}%` : '—'}</TableCell>
                  <TableCell className="text-muted-foreground">
                    <span className="block text-xs">{formatDateTime(l.linked_at)}</span>
                    {l.linked_by_name ? <span className="block text-xs">by {l.linked_by_name}</span> : null}
                  </TableCell>
                  {canLink ? (
                    <TableCell className="pr-5 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setRemoving(l)}
                        aria-label={`Unlink ${l.source_system} record ${l.external_ref}`}
                      >
                        <Unlink className="h-4 w-4" /> Unlink
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {open ? (
        <LinkSystemDialog
          crashId={crashId}
          onClose={() => setOpen(false)}
          onSaved={onChanged}
        />
      ) : null}
      {removing ? (
        <UnlinkDialog
          crashId={crashId}
          link={removing}
          onClose={() => setRemoving(null)}
          onRemoved={onChanged}
        />
      ) : null}
    </Card>
  );
}

function LinkSystemDialog({
  crashId, onClose, onSaved,
}: { crashId: string; onClose: () => void; onSaved: () => void }) {
  const { data: systems, loading: systemsLoading } = useApi(
    () => dataMgmtApi.externalSystems().catch(() => []),
    [],
  );
  const [sourceSystem, setSourceSystem] = React.useState('');
  const [externalRef, setExternalRef] = React.useState('');
  const [linkMethod, setLinkMethod] = React.useState<LinkMethod>('MANUAL');
  const [confidence, setConfidence] = React.useState('');
  const [matchedOn, setMatchedOn] = React.useState('');
  const [notes, setNotes] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const fmcsa = (systems ?? []).filter((s) => s.is_fmcsa_owned);
  const other = (systems ?? []).filter((s) => !s.is_fmcsa_owned);
  const selected = (systems ?? []).find((s) => s.code === sourceSystem) ?? null;

  async function save() {
    setBusy(true); setError(null);
    let parsedMatchedOn: Record<string, unknown> | null = null;
    if (matchedOn.trim()) {
      try {
        const parsed = JSON.parse(matchedOn);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error('not an object');
        }
        parsedMatchedOn = parsed as Record<string, unknown>;
      } catch {
        setError('“Matched on” must be a JSON object, e.g. {"dot_number": "1234567"}');
        setBusy(false);
        return;
      }
    }
    try {
      await dataMgmtApi.addExternalLink(crashId, {
        source_system: sourceSystem,
        external_ref: externalRef.trim(),
        link_method: linkMethod,
        matched_on: parsedMatchedOn,
        confidence: confidence ? Number(confidence) : null,
        notes: notes.trim() || null,
      });
      onSaved(); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Link failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0">
          <DialogTitle>Link an external system record</DialogTitle>
          <DialogDescription>
            Associate a record in an Appendix D external source with this crash to build its
            CCFP Aggregated Data. The original source data is never modified.
          </DialogDescription>
        </DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="cel-system">External system *</Label>
              <Select
                id="cel-system"
                value={sourceSystem}
                onChange={(e) => setSourceSystem(e.target.value)}
                disabled={systemsLoading}
              >
                <option value="">{systemsLoading ? 'Loading sources…' : 'Select a source…'}</option>
                {fmcsa.length ? (
                  <optgroup label="FMCSA-owned">
                    {fmcsa.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                  </optgroup>
                ) : null}
                {other.length ? (
                  <optgroup label="Owned by other entities">
                    {other.map((s) => <option key={s.code} value={s.code}>{s.name}{s.owner ? ` — ${s.owner}` : ''}</option>)}
                  </optgroup>
                ) : null}
              </Select>
              {selected?.relevant_data ? (
                <p className="text-xs text-muted-foreground">{selected.relevant_data}</p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cel-ref">External reference *</Label>
              <Input
                id="cel-ref"
                value={externalRef}
                onChange={(e) => setExternalRef(e.target.value)}
                placeholder="Identifier of the record in that system"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cel-method">Link method</Label>
              <Select id="cel-method" value={linkMethod} onChange={(e) => setLinkMethod(e.target.value as LinkMethod)}>
                <option value="MANUAL">Manual — linked by hand</option>
                <option value="AUTO">Automatic — matched by an integration adapter</option>
                <option value="RULE">Rule — produced by a matching rule</option>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cel-matched">Matched on (JSON)</Label>
              <Input
                id="cel-matched"
                value={matchedOn}
                onChange={(e) => setMatchedOn(e.target.value)}
                placeholder='{"dot_number": "1234567", "crash_date": "2026-05-04"}'
              />
              <p className="text-xs text-muted-foreground">The identifiers this match was made on, retained as evidence.</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cel-confidence">Confidence (0–100)</Label>
              <Input
                id="cel-confidence"
                type="number"
                min={0}
                max={100}
                value={confidence}
                onChange={(e) => setConfidence(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cel-notes">Notes</Label>
              <Input id="cel-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} disabled={!sourceSystem || !externalRef.trim() || busy}>Link record</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UnlinkDialog({
  crashId, link, onClose, onRemoved,
}: { crashId: string; link: CrashExternalLink; onClose: () => void; onRemoved: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function remove() {
    setBusy(true); setError(null);
    try {
      await dataMgmtApi.removeExternalLink(crashId, link.id);
      onRemoved(); onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Unlink failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0">
          <DialogTitle>Unlink external system record</DialogTitle>
          <DialogDescription>
            Remove <span className="font-medium">{link.source_system}</span> record{' '}
            <span className="font-medium">{link.external_ref}</span> from this crash&rsquo;s aggregated
            data. The linkage history is retained and the record can be linked again later.
          </DialogDescription>
        </DialogHeader>
        {error ? <p className="py-2 text-sm text-destructive">{error}</p> : null}
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="destructive" onClick={remove} disabled={busy}>Unlink</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────── Canonical attribute values ───────────────
function AttributesCard({
  crashId, attributes, sources, loading, canEdit, locked, onSaved,
}: {
  crashId: string;
  attributes: AttributeValue[];
  sources: SourceRecord[];
  loading: boolean;
  canEdit: boolean;
  locked: boolean;
  onSaved: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  // Per-attribute version history (DATA-6, §8.8): the row whose timeline is open.
  // Carries the unit (GAP-PCR-03) so the timeline is scoped to Trailer 2 rather
  // than mixing all three trailers' versions together.
  const [history, setHistory] = React.useState<
    { code: string; name: string; unit: { unit_type: string; unit_number: number } | null } | null
  >(null);
  const sourceById = React.useMemo(() => new Map(sources.map((s) => [s.id, s])), [sources]);
  // Group by repeating unit (GAP-PCR-03). Reads the aggregated document's
  // `attributes` (GAP-BRD-01) rather than a separate fetch — the two changes
  // compose: the document supplies the rows, the grouping renders them per unit.
  const grouped = React.useMemo(() => groupByUnit(attributes), [attributes]);

  return (
    <Card>
      <CardHeader>
        <CardHeading
          icon={Database}
          title="Aggregated attributes"
          description="Canonical CCFP attribute values with source provenance."
          actions={
            canEdit ? (
              locked ? (
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Lock className="h-3.5 w-3.5" /> Record locked — unlock on the Completeness tab to edit
                </span>
              ) : (
                <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Set / override</Button>
              )
            ) : undefined
          }
        />
      </CardHeader>
      <CardContent className="p-0">
        {loading ? <div className="p-5"><Skeleton className="h-32 w-full" /></div> : attributes.length === 0 ? (
          <div className="p-5"><EmptyState icon={Database} title="No aggregated attributes" description="Canonical values mapped from source data will appear here." /></div>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <TableHead className="pl-5">Code</TableHead><TableHead>Attribute</TableHead><TableHead>Section</TableHead>
              <TableHead>Value</TableHead><TableHead>Source</TableHead><TableHead className="text-right">Confidence</TableHead>
              <TableHead className="text-right pr-5">History</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {grouped.crashLevel.map((a) => (
                <AttributeRow key={a.attribute_id} a={a} sourceById={sourceById} onHistory={setHistory} />
              ))}
              {grouped.units.map((u) => (
                <React.Fragment key={`${u.type}#${u.number}`}>
                  {/* Section header for one repeating unit (GAP-PCR-03) so
                      "Trailer 2 GVWR" is distinguishable from Trailer 1's. */}
                  <TableRow className="bg-muted/50 hover:bg-muted/50">
                    <TableCell colSpan={7} className="pl-5 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {UNIT_LABEL[u.type] ?? humanize(u.type)} {u.number}
                    </TableCell>
                  </TableRow>
                  {u.rows.map((a) => (
                    <AttributeRow
                      key={`${a.attribute_id}#${u.type}#${u.number}`}
                      a={a}
                      sourceById={sourceById}
                      onHistory={setHistory}
                    />
                  ))}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {open ? <SetAttributeDialog crashId={crashId} sources={sources} onClose={() => setOpen(false)} onSaved={onSaved} /> : null}
      {history ? (
        <AttributeHistoryDialog
          crashId={crashId}
          code={history.code}
          name={history.name}
          unit={history.unit}
          onClose={() => setHistory(null)}
        />
      ) : null}
    </Card>
  );
}

/**
 * One attribute row. Extracted so the crash-level block and each per-unit block
 * (GAP-PCR-03) render identically rather than duplicating the cell markup.
 */
function AttributeRow({
  a, sourceById, onHistory,
}: {
  a: AttributeValue;
  sourceById: Map<string, SourceRecord>;
  onHistory: (h: { code: string; name: string; unit: { unit_type: string; unit_number: number } | null }) => void;
}) {
  const unit = a.unit_type && a.unit_number != null
    ? { unit_type: a.unit_type, unit_number: a.unit_number }
    : null;
  const unitSuffix = unit ? ` on ${UNIT_LABEL[a.unit_type!] ?? a.unit_type} ${a.unit_number}` : '';
  return (
    <TableRow>
      <TableCell className="pl-5 font-medium tabular-nums">{a.code}</TableCell>
      <TableCell>
        {a.name} {a.is_edited ? <Badge variant="warning" size="sm">edited</Badge> : null}
        {/* Cardinality cap from the new PCR form ("Check up to N"), surfaced so
            the analyst sees the limit alongside the value (GAP-PCR-04 seeds it). */}
        {a.max_selections != null ? (
          <Badge variant="neutral" size="sm" title={`Select up to ${a.max_selections}`}>
            up to {a.max_selections}
          </Badge>
        ) : null}
      </TableCell>
      <TableCell className="text-muted-foreground">{a.pcr_section ? humanize(a.pcr_section) : '—'}</TableCell>
      <TableCell>
        {a.redacted ? (
          <span className="inline-flex items-center gap-1 text-muted-foreground"><EyeOff className="h-3.5 w-3.5" /> Restricted <SensitivityBadge level={a.sensitivity} /></span>
        ) : (
          <span>{a.value_text ?? (a.value_json ? JSON.stringify(a.value_json) : '—')}</span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {a.source_record_id ? (
          (() => {
            // Precise source-record lineage (DATA-5, §11.3): when the value
            // carries a linked source_records id, badge the cell and name the
            // record (system · type) if it is loaded.
            const src = sourceById.get(a.source_record_id);
            const label = src ? `${src.source_system} · ${src.source_type}` : 'linked source record';
            return (
              <span
                className="inline-flex items-center gap-1"
                title={`Lineage: derived from ${label}${src?.external_id ? ` (${src.external_id})` : ''}`}
              >
                <Link2 className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                <span>{a.source_system ?? label}</span>
                <span className="sr-only">— linked to source record {label}</span>
              </span>
            );
          })()
        ) : (
          a.source_system ?? '—'
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">{a.confidence != null ? `${a.confidence}%` : '—'}</TableCell>
      <TableCell className="pr-5 text-right">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onHistory({ code: a.code, name: a.name, unit })}
          aria-label={`View change history for ${a.code} ${a.name}${unitSuffix}`}
          title="View change history"
        >
          <History className="h-4 w-4" /> History
        </Button>
      </TableCell>
    </TableRow>
  );
}

function SetAttributeDialog({
  crashId, sources, onClose, onSaved,
}: { crashId: string; sources: SourceRecord[]; onClose: () => void; onSaved: () => void }) {
  const [code, setCode] = React.useState('');
  const [value, setValue] = React.useState('');
  const [source, setSource] = React.useState('');
  const [confidence, setConfidence] = React.useState('');
  // Optional precise lineage pointer (DATA-5, §11.3): the source_records row this
  // value derives from. '' means "no linked record" -> sent as null.
  const [sourceRecordId, setSourceRecordId] = React.useState('');
  // Repeat unit (GAP-PCR-03). Left blank for a crash-level attribute; set to
  // e.g. TRAILER + 2 for a per-unit one. The server validates the pair against
  // the attribute's own `repeats_on`, so a wrong choice is a 400 rather than a
  // silently misfiled value.
  const [unitType, setUnitType] = React.useState('');
  const [unitNumber, setUnitNumber] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Selection cap for the typed code (GAP-PCR-04). Resolved from the attribute
  // catalog so the dialog can show "3 of 6 selected" and block an over-cap
  // submission before it reaches the server, which rejects it with a 400 anyway.
  const { data: catalog } = useApi(() => dataAttributeApi.list().catch(() => []), []);
  const attribute = React.useMemo(
    () => (catalog ?? []).find((a) => a.code === code.trim().toUpperCase()) ?? null,
    [catalog, code],
  );
  const cap = attribute?.max_selections ?? null;
  // A capped attribute is written as a list. Values are entered comma-separated
  // and split here, so the single-value case still works untouched.
  const selections = React.useMemo(
    () => (cap == null ? [] : value.split(',').map((s) => s.trim()).filter(Boolean)),
    [cap, value],
  );
  const overCap = cap != null && selections.length > cap;
  const duplicated = cap != null && new Set(selections).size !== selections.length;

  async function save() {
    setBusy(true); setError(null);
    try {
      await crashApi.setAttribute(crashId, {
        attribute_code: code.trim().toUpperCase(),
        // A capped attribute goes as a JSON list so its cardinality is explicit
        // on the wire; everything else keeps the plain text value.
        value_text: cap == null ? (value || null) : null,
        value_json: cap == null ? undefined : selections,
        source_system: source || null,
        source_record_id: sourceRecordId || null,
        confidence: confidence ? Number(confidence) : null,
        unit_type: unitType || null,
        unit_number: unitType && unitNumber ? Number(unitNumber) : null,
      });
      onSaved(); onClose();
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Save failed'); } finally { setBusy(false); }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0"><DialogTitle>Set / override attribute value</DialogTitle></DialogHeader>
        <div className="-mr-6 max-h-[60vh] overflow-y-auto py-4 pr-6">
          <div className="space-y-3">
            <div className="space-y-1.5"><Label>Attribute code *</Label><Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. C19, V05, P04" /></div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="attr-value">Value</Label>
                {cap != null ? (
                  <span
                    className={`text-xs tabular-nums ${overCap ? 'font-medium text-destructive' : 'text-muted-foreground'}`}
                    aria-live="polite"
                  >
                    {selections.length} of {cap} selected
                  </span>
                ) : null}
              </div>
              <Input
                id="attr-value"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={cap != null ? 'Comma-separated codes' : undefined}
                aria-invalid={overCap || duplicated}
                aria-describedby={cap != null ? 'attr-value-help' : undefined}
              />
              {cap != null ? (
                <p
                  id="attr-value-help"
                  className={`text-xs ${overCap || duplicated ? 'text-destructive' : 'text-muted-foreground'}`}
                >
                  {overCap
                    ? `The PCR form allows at most ${cap} selection${cap === 1 ? '' : 's'} for ${attribute?.code}.`
                    : duplicated
                      ? 'Remove the duplicate selection.'
                      : `${attribute?.name}: check ${cap === 1 ? 'only 1' : `up to ${cap}`}. Separate codes with commas.`}
                </p>
              ) : null}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="unit-type">Repeats on</Label>
                <select
                  id="unit-type"
                  value={unitType}
                  onChange={(e) => { setUnitType(e.target.value); if (!e.target.value) setUnitNumber(''); }}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">Crash-level (no unit)</option>
                  {(Object.keys(UNIT_LABEL) as RepeatUnit[]).map((u) => (
                    <option key={u} value={u}>{UNIT_LABEL[u]}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="unit-number">Unit number</Label>
                <Input
                  id="unit-number"
                  type="number"
                  min={1}
                  value={unitNumber}
                  onChange={(e) => setUnitNumber(e.target.value)}
                  disabled={!unitType}
                  placeholder={unitType ? '1' : '—'}
                />
              </div>
            </div>
            <p className="-mt-1 text-xs text-muted-foreground">
              The new PCR form repeats whole sections — Trailers 1–3, each Vehicle, each Person. Leave
              as crash-level unless the attribute is captured per unit.
            </p>
            <div className="space-y-1.5"><Label>Source system</Label><Input value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. MCMIS, SafeSpect, Manual" /></div>
            <div className="space-y-1.5">
              <Label>Source record (lineage)</Label>
              <Select
                value={sourceRecordId}
                onChange={(e) => setSourceRecordId(e.target.value)}
                disabled={sources.length === 0}
              >
                <option value="">
                  {sources.length === 0 ? 'No source records for this crash' : 'None — free-text source only'}
                </option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.source_system} · {s.source_type}{s.external_id ? ` (${s.external_id})` : ''}
                  </option>
                ))}
              </Select>
              <p className="text-xs text-muted-foreground">Link this value to the exact ingested source record it came from.</p>
            </div>
            <div className="space-y-1.5"><Label>Confidence (0–100)</Label><Input type="number" min={0} max={100} value={confidence} onChange={(e) => setConfidence(e.target.value)} /></div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button
            onClick={save}
            disabled={!code.trim() || (!!unitType && !unitNumber) || overCap || duplicated || busy}
          >
            Save value
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Read-only version timeline for one attribute (DATA-6, documentation §8.8).
 * Lists every value version newest-first with editor + timestamp, and diffs each
 * version against the one before it (the prior, older value) so the analyst can
 * see how the value changed and by whom. Honors the same sensitivity redaction
 * the history endpoint applies. No writes.
 */
function AttributeHistoryDialog({
  crashId,
  code,
  name,
  unit,
  onClose,
}: {
  crashId: string;
  code: string;
  name: string;
  unit: { unit_type: string; unit_number: number } | null;
  onClose: () => void;
}) {
  // Scope the timeline to this unit (GAP-PCR-03) — otherwise every trailer's
  // versions interleave and the diff-against-previous below compares values
  // from different units, which reads as a change that never happened.
  const { data, loading, error } = useApi(
    () => crashApi.attributeHistory(crashId, code, unit),
    [crashId, code, unit?.unit_type, unit?.unit_number],
  );
  const versions = data?.versions ?? [];
  const unitLabel = unit
    ? `${UNIT_LABEL[unit.unit_type as RepeatUnit] ?? humanize(unit.unit_type)} ${unit.unit_number}`
    : null;

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader className="mb-0">
          <DialogTitle className="inline-flex items-center gap-2">
            <History className="h-4 w-4" /> {code} — {name}
            {unitLabel ? <Badge variant="neutral" size="sm">{unitLabel}</Badge> : null}
          </DialogTitle>
          <DialogDescription>
            Every change to this attribute{unitLabel ? ` on ${unitLabel}` : ''}, newest first, with who
            made it and when.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-6 max-h-[60vh] space-y-3 overflow-y-auto py-4 pr-6">
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : error ? (
            <p className="text-sm text-destructive">
              {error instanceof ApiError ? error.message : 'Could not load history.'}
            </p>
          ) : versions.length === 0 ? (
            <EmptyState icon={History} title="No history" description="This attribute has no recorded versions yet." />
          ) : (
            versions.map((v, i) => {
              // The next entry (i+1) is the chronologically older value; diff
              // against it to show the "before" of this change.
              const prior = versions[i + 1];
              const display = (text: string | null, json: unknown) =>
                text ?? (json ? JSON.stringify(json) : '—');
              const current = v.redacted ? null : display(v.value_text, v.value_json);
              const before = prior && !prior.redacted ? display(prior.value_text, prior.value_json) : null;
              const changed = prior && current !== null && before !== null && current !== before;
              return (
                <div key={v.value_id} className="rounded-md border border-border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {v.is_current ? <Badge variant="success" size="sm">current</Badge> : <Badge variant="neutral" size="sm">superseded</Badge>}
                      {v.is_edited ? <Badge variant="warning" size="sm">edited</Badge> : null}
                      {v.source_system ? <span className="text-xs text-muted-foreground">via {v.source_system}</span> : null}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(v.edited_at ?? v.created_at)}
                    </span>
                  </div>
                  <div className="mt-2">
                    {v.redacted ? (
                      <span className="inline-flex items-center gap-1 text-muted-foreground">
                        <EyeOff className="h-3.5 w-3.5" /> Restricted value
                      </span>
                    ) : (
                      <div>
                        <span className="font-medium">{current}</span>
                        {changed ? (
                          <span className="ml-2 text-xs text-muted-foreground">
                            was <span className="line-through">{before}</span>
                          </span>
                        ) : null}
                      </div>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {v.edited_by_name ? `by ${v.edited_by_name}` : v.edited_by ? 'by an editor' : 'from source ingestion'}
                    {v.confidence != null ? ` · ${v.confidence}% confidence` : null}
                  </div>
                </div>
              );
            })
          )}
        </div>

        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
