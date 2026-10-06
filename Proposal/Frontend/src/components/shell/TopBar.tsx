import * as React from 'react';
import { Menu, Truck, User as UserIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/app/auth';
import { getPrimaryRoleLabel } from '@/lib/permissions';
import { NotificationsBell } from './NotificationsBell';
import { OfflineIndicator } from './OfflineIndicator';

export interface TopBarProps {
  className?: string;
  onMenuClick?: () => void;
}

/**
 * Sticky top bar — dark `dot-navy` surface, white type.
 * Left:  mobile menu toggle + CCFP wordmark + program subtitle.
 * Right: environment chip, notifications, current user + role.
 */
export function TopBar({ className, onMenuClick }: TopBarProps) {
  const { user } = useAuth();
  const primaryRoleLabel = getPrimaryRoleLabel(user);
  return (
    <header
      className={cn(
        'sticky top-0 z-40 flex h-14 w-full items-center justify-between border-b border-dot-navy-700 bg-dot-navy px-4 text-white shadow-sm sm:px-6',
        className,
      )}
    >
      <div className="flex items-center gap-3">
        {onMenuClick ? (
          <button
            type="button"
            onClick={onMenuClick}
            aria-label="Open navigation"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-white hover:bg-dot-navy-700 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
        ) : null}
        <Truck className="h-5 w-5 text-alert-amber" aria-hidden />
        <span className="font-sans text-base font-bold tracking-tight">
          CC<span className="text-white">FP</span>
        </span>
        <span className="hidden text-xs text-dot-navy-100 md:inline">
          FMCSA · Crash Causal Factors Program · Heavy-Duty Truck Study
        </span>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {/* Renders only when offline or work is queued, so the bar is unchanged
            in the normal connected case. */}
        <OfflineIndicator />
        <span
          role="status"
          aria-label="Environment"
          className="hidden items-center rounded-sm bg-alert-amber px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-white shadow-sm sm:inline-flex"
        >
          Dev / Synthetic
        </span>
        {user ? (
          <div className="flex items-center gap-3 border-l border-dot-navy-700 pl-3">
            <NotificationsBell />
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-federal-blue text-xs font-bold text-white">
                {(user.full_name?.[0] ?? user.email?.[0] ?? '?').toUpperCase()}
              </span>
              <div className="hidden text-left text-xs leading-tight md:block">
                <div className="font-medium text-white">{user.full_name}</div>
                <div className="text-dot-navy-100">{primaryRoleLabel}</div>
              </div>
            </div>
          </div>
        ) : (
          <span className="inline-flex items-center gap-1 text-dot-navy-100">
            <UserIcon className="h-4 w-4" /> Not signed in
          </span>
        )}
      </div>
    </header>
  );
}
