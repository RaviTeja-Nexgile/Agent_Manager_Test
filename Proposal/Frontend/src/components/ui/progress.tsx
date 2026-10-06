import * as React from 'react';
import { cn } from '@/lib/utils';

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number; // 0..100
  tone?: 'default' | 'success' | 'warning' | 'danger';
}

const TONES: Record<NonNullable<ProgressProps['tone']>, string> = {
  default: 'bg-federal-blue',
  success: 'bg-success-green',
  warning: 'bg-alert-amber',
  danger: 'bg-alert-red',
};

export function Progress({ value, tone = 'default', className, ...props }: ProgressProps) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn('relative h-2 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      <div className={cn('h-full rounded-full transition-all', TONES[tone])} style={{ width: `${v}%` }} />
    </div>
  );
}
