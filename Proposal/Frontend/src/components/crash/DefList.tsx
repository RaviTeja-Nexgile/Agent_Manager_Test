import * as React from 'react';
import { cn } from '@/lib/utils';

export interface DefItem {
  label: React.ReactNode;
  value: React.ReactNode;
}

/** Compact definition list (label / value rows) used across crash detail tabs. */
export function DefList({ items, className }: { items: DefItem[]; className?: string }) {
  return (
    <dl className={cn('grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2', className)}>
      {items.map((it, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          <dt className="text-eyebrow">{it.label}</dt>
          <dd className="text-sm text-foreground">{it.value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  );
}
