import * as React from 'react';
import type { LucideIcon } from 'lucide-react';
import { CardDescription, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface CardHeadingProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  icon: LucideIcon;
  tone?: string;
  className?: string;
  /** Optional inline actions rendered to the right of the heading. */
  actions?: React.ReactNode;
}

export function CardHeading({
  title,
  description,
  icon: Icon,
  tone = 'bg-federal-blue/10 text-federal-blue',
  className,
  actions,
}: CardHeadingProps) {
  const inner = (
    <div className={cn('flex gap-3', description ? 'items-start' : 'items-center')}>
      <span
        className={cn(
          'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md',
          description && 'mt-0.5',
          tone,
        )}
        aria-hidden
      >
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <div className="flex flex-col gap-1">
        <CardTitle className="text-base font-semibold leading-tight">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </div>
    </div>
  );

  if (!actions) {
    return <div className={className}>{inner}</div>;
  }
  return (
    <div className={cn('flex flex-wrap items-start justify-between gap-3', className)}>
      {inner}
      <div className="flex shrink-0 items-center gap-2">{actions}</div>
    </div>
  );
}
