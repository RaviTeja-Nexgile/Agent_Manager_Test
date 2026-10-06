import * as React from 'react';
import { PlugZap, ShieldCheck, IdCard, FileSearch } from 'lucide-react';

import { PageHeader } from '@/components/shell/PageHeader';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { CardHeading } from '@/components/shell/CardHeading';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import { useApi } from '@/lib/useApi';
import { integrationApi } from '@/lib/endpoints';
import type { DotValidationResult } from '@/lib/types';
import { hasPermission } from '@/lib/permissions';
import { useAuth } from '@/app/auth';

type CdlisVerifyResult = {
  license_number?: string | null;
  jurisdiction?: string | null;
  valid?: boolean;
  license_status?: string | null;
  source?: string | null;
};
type McmisLookupResult = {
  local_report_number?: string | null;
  found?: boolean;
  records?: unknown[];
  source?: string | null;
};

export function IntegrationsPage() {
  const { user } = useAuth();
  const canValidate = hasPermission(user, 'source_data:ingest') || hasPermission(user, 'crash:read');
  const canVerifyCdlis = hasPermission(user, 'data_mgmt:qc') || hasPermission(user, 'source_data:ingest');
  const canLookupMcmis = hasPermission(user, 'source_data:ingest') || hasPermission(user, 'crash:read');
  const { data, loading } = useApi(() => integrationApi.list().catch(() => ({ adapters: [] })), []);

  const [dot, setDot] = React.useState('');
  const [result, setResult] = React.useState<DotValidationResult | null>(null);
  const [busy, setBusy] = React.useState(false);

  const [cdlisLicense, setCdlisLicense] = React.useState('');
  const [cdlisJurisdiction, setCdlisJurisdiction] = React.useState(
    user?.allowed_states?.length === 1 ? user.allowed_states[0] : '',
  );
  const [cdlisResult, setCdlisResult] = React.useState<CdlisVerifyResult | null>(null);
  const [cdlisBusy, setCdlisBusy] = React.useState(false);

  const [mcmisLrn, setMcmisLrn] = React.useState('');
  const [mcmisResult, setMcmisResult] = React.useState<McmisLookupResult | null>(null);
  const [mcmisBusy, setMcmisBusy] = React.useState(false);

  async function validate() {
    setBusy(true); setResult(null);
    try { setResult(await integrationApi.validateDot(dot.trim())); } catch { /* ignore */ } finally { setBusy(false); }
  }

  async function verifyCdlis() {
    setCdlisBusy(true); setCdlisResult(null);
    try {
      setCdlisResult(await integrationApi.verifyCdlis(cdlisLicense.trim(), cdlisJurisdiction.trim() || undefined) as CdlisVerifyResult);
    } catch { /* ignore */ } finally { setCdlisBusy(false); }
  }

  async function lookupMcmis() {
    setMcmisBusy(true); setMcmisResult(null);
    try {
      setMcmisResult(await integrationApi.lookupMcmis(mcmisLrn.trim()) as McmisLookupResult);
    } catch { /* ignore */ } finally { setMcmisBusy(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" icon={PlugZap} title="External integrations" subtitle="SafeSpect, CDLIS, MCMIS, and eRODS adapters." />

      <Card>
        <CardHeader><CardHeading icon={PlugZap} title="Configured adapters" description="Live vs. mock status per external system." /></CardHeader>
        <CardContent>
          {loading ? <Skeleton className="h-28 w-full" /> : (
            <ul className="space-y-2">
              {(data?.adapters ?? []).map((a) => (
                <li key={a.name} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <div><div className="text-sm font-medium">{a.name}</div><div className="text-xs text-muted-foreground">{a.description}</div></div>
                  <Badge variant={a.live ? 'success' : 'warning'}>{a.live ? 'Live' : 'Mock'}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {canValidate ? (
        <Card>
          <CardHeader><CardHeading icon={ShieldCheck} title="SafeSpect U.S. DOT validation" description="Validate a U.S. DOT number via the SafeSpect adapter." /></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1.5"><Label>U.S. DOT number</Label><Input value={dot} onChange={(e) => setDot(e.target.value)} placeholder="e.g. 3192847" /></div>
              <Button onClick={validate} disabled={!dot.trim() || busy}>{busy ? <Spinner className="h-4 w-4" /> : null} Validate</Button>
            </div>
            {result ? (
              <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={result.valid ? 'success' : 'danger'}>{result.valid ? 'Valid' : 'Not found'}</Badge>
                  <span className="text-muted-foreground">{result.source}</span>
                </div>
                {result.carrier_name ? <p className="mt-1">Carrier: <span className="font-medium">{result.carrier_name}</span></p> : null}
                <p className="text-xs text-muted-foreground">Status: {result.status}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {canVerifyCdlis ? (
        <Card>
          <CardHeader><CardHeading icon={IdCard} title="CDLIS driver verification" description="Verify a driver license via the CDLIS adapter." /></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1.5"><Label>License number</Label><Input value={cdlisLicense} onChange={(e) => setCdlisLicense(e.target.value)} placeholder="e.g. D1234567" /></div>
              <div className="w-28 space-y-1.5"><Label>Jurisdiction</Label><Input value={cdlisJurisdiction} onChange={(e) => setCdlisJurisdiction(e.target.value)} placeholder="e.g. KS" /></div>
              <Button onClick={verifyCdlis} disabled={!cdlisLicense.trim() || cdlisBusy}>{cdlisBusy ? <Spinner className="h-4 w-4" /> : null} Verify</Button>
            </div>
            {cdlisResult ? (
              <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={cdlisResult.valid ? 'success' : 'danger'}>{cdlisResult.valid ? 'Valid' : 'Not found'}</Badge>
                  <span className="text-muted-foreground">{cdlisResult.source}</span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Status: {cdlisResult.license_status ?? '—'}</p>
                {cdlisResult.jurisdiction ? <p className="text-xs text-muted-foreground">Jurisdiction: {cdlisResult.jurisdiction}</p> : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {canLookupMcmis ? (
        <Card>
          <CardHeader><CardHeading icon={FileSearch} title="MCMIS crash lookup" description="Look up a crash by local report number via the MCMIS adapter." /></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1.5"><Label>Local report number</Label><Input value={mcmisLrn} onChange={(e) => setMcmisLrn(e.target.value)} placeholder="e.g. LRN-1" /></div>
              <Button onClick={lookupMcmis} disabled={!mcmisLrn.trim() || mcmisBusy}>{mcmisBusy ? <Spinner className="h-4 w-4" /> : null} Look up</Button>
            </div>
            {mcmisResult ? (
              <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={mcmisResult.found ? 'success' : 'danger'}>{mcmisResult.found ? 'Found' : 'Not found'}</Badge>
                  <span className="text-muted-foreground">{mcmisResult.source}</span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Records: {mcmisResult.records?.length ?? 0}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
