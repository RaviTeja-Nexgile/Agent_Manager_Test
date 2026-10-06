import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { humanize } from '@/lib/format';
import {
  COMPLETENESS_TONE,
  INJURY_TONE,
  MAPPING_TONE,
  PHASE_LABEL,
  PHASE_TONE,
  QC_STATUS_TONE,
  SCOPE_TONE,
  SENSITIVITY_TONE,
  SEVERITY_TONE,
} from '@/lib/constants';
import type {
  CompletenessStatusValue,
  CrashLifecyclePhase,
  CrashScope,
  InjuryStatus,
  MappingStatus,
  QcResultStatus,
  RuleSeverity,
} from '@/lib/types';

type Variant = 'success' | 'warning' | 'danger' | 'progress' | 'neutral' | 'info';

export function PhaseBadge({ phase, className }: { phase: CrashLifecyclePhase; className?: string }) {
  return (
    <Badge variant={PHASE_TONE[phase] as Variant} className={cn('font-medium', className)}>
      {PHASE_LABEL[phase] ?? humanize(phase)}
    </Badge>
  );
}

export function ScopeBadge({ scope, className }: { scope: CrashScope; className?: string }) {
  return (
    <Badge variant={SCOPE_TONE[scope] as Variant} className={className}>
      {humanize(scope)}
    </Badge>
  );
}

export function CompletenessBadge({
  status,
  locked,
  className,
}: {
  status: CompletenessStatusValue;
  locked?: boolean;
  className?: string;
}) {
  return (
    <Badge variant={COMPLETENESS_TONE[status] as Variant} className={className}>
      {humanize(status)}
      {locked ? ' · Locked' : ''}
    </Badge>
  );
}

export function QcStatusBadge({ status, className }: { status: QcResultStatus; className?: string }) {
  return (
    <Badge variant={QC_STATUS_TONE[status] as Variant} className={className}>
      {humanize(status)}
    </Badge>
  );
}

export function SeverityBadge({ severity, className }: { severity: RuleSeverity; className?: string }) {
  return (
    <Badge variant={SEVERITY_TONE[severity] as Variant} size="sm" className={className}>
      {humanize(severity)}
    </Badge>
  );
}

export function MappingBadge({ status, className }: { status: MappingStatus; className?: string }) {
  return (
    <Badge variant={MAPPING_TONE[status] as Variant} className={className}>
      {humanize(status)}
    </Badge>
  );
}

export function InjuryBadge({ injury, className }: { injury: InjuryStatus | null; className?: string }) {
  if (!injury) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <Badge variant={INJURY_TONE[injury] as Variant} size="sm" className={className}>
      {humanize(injury)}
    </Badge>
  );
}

export function SensitivityBadge({ level, className }: { level: string; className?: string }) {
  if (level === 'INTERNAL' || level === 'PUBLIC') return null;
  return (
    <Badge variant={(SENSITIVITY_TONE[level] ?? 'neutral') as Variant} size="sm" className={className}>
      {humanize(level)}
    </Badge>
  );
}

export function StatusChip({ status, className }: { status: string; className?: string }) {
  const tone: Variant =
    status === 'ROUTED' || status === 'SUBMITTED' || status === 'CODED' || status === 'PARSED'
      ? 'success'
      : status === 'DRAFT' || status === 'PENDING' || status === 'UPLOADED'
        ? 'neutral'
        : status === 'FAILED'
          ? 'danger'
          : // PARSED_WITH_ERRORS (BRD Appendix E): data WAS extracted but at least
            // one error was recorded. It must not read as a clean success, and it
            // is not a failure either — warning is the honest middle.
            status === 'PARSED_WITH_ERRORS'
            ? 'warning'
            : 'progress';
  return (
    <Badge variant={tone} className={className}>
      {humanize(status)}
    </Badge>
  );
}
