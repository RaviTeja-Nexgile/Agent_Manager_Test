import * as React from 'react';
import { NavLink } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { hasAnyPermission, hasRole, type Role } from '@/lib/permissions';
import { useAuth } from '@/app/auth';

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  end?: boolean;
  /** Shown only if the user has at least one of these permission codes. */
  perms?: string[];
  /** Or, gate by role membership. */
  roles?: Role[];
}

export interface NavSection {
  title?: string;
  items: NavItem[];
}

export interface SideNavProps {
  sections: NavSection[];
  footer?: React.ReactNode;
  className?: string;
  onNavigate?: () => void;
}

function itemVisible(
  item: NavItem,
  user: Parameters<typeof hasAnyPermission>[0],
): boolean {
  if (item.perms && !hasAnyPermission(user, item.perms)) return false;
  if (item.roles && !hasRole(user, item.roles)) return false;
  return true;
}

export function SideNav({ sections, footer, className, onNavigate }: SideNavProps) {
  const { user } = useAuth();

  const visibleSections = sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => itemVisible(item, user)),
    }))
    .filter((section) => section.items.length > 0);

  return (
    <nav
      aria-label="Primary"
      className={cn(
        'flex h-full w-60 shrink-0 flex-col border-r border-border bg-muted/40',
        className,
      )}
    >
      <div className="flex flex-1 min-h-0 flex-col gap-2 overflow-y-auto p-3">
        {visibleSections.map((section, idx) => (
          <div key={idx} className="flex flex-col gap-1">
            {section.title ? (
              <div className="px-2 pt-1 pb-2 text-eyebrow">{section.title}</div>
            ) : null}
            {section.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-foreground hover:bg-accent/10 hover:text-accent',
                    )
                  }
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="truncate">{item.label}</span>
                </NavLink>
              );
            })}
          </div>
        ))}
      </div>
      {footer ? <div className="shrink-0 border-t border-border p-3">{footer}</div> : null}
    </nav>
  );
}
