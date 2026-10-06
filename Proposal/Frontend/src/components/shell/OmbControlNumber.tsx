import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * OMB control number / Paperwork Reduction Act notice
 * (project_documentation §14.1; open question §17 — final approval language TBD).
 *
 * The PRA requires the OMB control number and burden statement to be displayed
 * before any public information collection and on public-facing surfaces. The
 * real control number is pending OMB approval, so the value here is a clearly
 * provisional placeholder kept in one config object (`OMB_NOTICE`) — a one-line
 * edit finalizes it once approval is granted, with no component changes.
 */
export const OMB_NOTICE = {
  controlNumber: 'OMB Control No. 2126-XXXX (pending approval)',
  expirationDate: 'Expires: TBD',
  burdenStatement:
    'A federal agency may not conduct or sponsor, and a person is not required to ' +
    'respond to, a collection of information unless it displays a currently valid ' +
    'OMB control number. The estimated time to complete this collection will be ' +
    'provided when the final OMB approval is granted.',
} as const;

export interface OmbControlNumberProps {
  className?: string;
  /** Compact variant for in-app collection forms (drops the burden statement). */
  compact?: boolean;
}

export function OmbControlNumber({ className, compact = false }: OmbControlNumberProps) {
  return (
    <aside
      aria-label="Paperwork Reduction Act notice"
      className={cn(
        'rounded-md border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground',
        className,
      )}
    >
      <p className="font-medium text-foreground">
        {OMB_NOTICE.controlNumber}
        <span className="ml-2 font-normal text-muted-foreground">{OMB_NOTICE.expirationDate}</span>
      </p>
      {compact ? null : (
        <p className="mt-1 leading-relaxed">{OMB_NOTICE.burdenStatement}</p>
      )}
    </aside>
  );
}
