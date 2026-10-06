import * as React from 'react';
import { useAuth } from '@/app/auth';
import { hasAnyPermission, hasRole, type Role } from '@/lib/permissions';
import { NoAccessPage } from '@/pages/NoAccessPage';

export interface RequirePermissionProps {
  /** Allowed if the user has ANY of these permission codes. */
  perms?: string[];
  /** Or allowed by role membership. */
  roles?: Role[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Renders children only when the current user satisfies the permission/role
 * requirement; otherwise shows the no-access page (explicit, not a blank
 * screen or a silent backend 403).
 */
export function RequirePermission({ perms, roles, children, fallback }: RequirePermissionProps) {
  const { user } = useAuth();
  const okPerms = perms ? hasAnyPermission(user, perms) : true;
  const okRoles = roles ? hasRole(user, roles) : true;
  if (okPerms && okRoles) return <>{children}</>;
  return <>{fallback ?? <NoAccessPage perms={perms} roles={roles} />}</>;
}
