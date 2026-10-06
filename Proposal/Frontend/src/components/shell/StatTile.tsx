import * as React from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface StatTileProps {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon: LucideIcon;
  tone?: string;
  className?: string;
}

export function StatTile({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'bg-federal-blue/10 text-federal-blue',
  className,
}: StatTileProps) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-md border border-border bg-card px-4 py-3 shadow-xs',
        className,
      )}
    >
      <span
        className={cn(
          'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md',
          tone,
        )}
        aria-hidden
      >
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-eyebrow">{label}</span>
        <span className="truncate text-lg font-semibold leading-tight tabular-nums text-foreground">
          {value}
        </span>
        {hint ? <span className="truncate text-xs text-muted-foreground">{hint}</span> : null}
      </div>
    </div>
  );
}
