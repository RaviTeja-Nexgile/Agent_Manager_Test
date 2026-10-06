import * as React from 'react';
import { Navigate, Outlet, useLocation, useMatches } from 'react-router-dom';
import {
  Bell,
  BookMarked,
  Boxes,
  Building2,
  CarFront,
  Database,
  FileBarChart2,
  FlaskConical,
  Globe,
  History,
  Layers,
  LayoutDashboard,
  LibraryBig,
  LogOut,
  PlugZap,
  Settings,
  ShieldCheck,
  Sigma,
  Users as UsersIcon,
} from 'lucide-react';

import { TopBar } from '@/components/shell/TopBar';
import { SideNav, type NavSection } from '@/components/shell/SideNav';
import { useAuth } from './auth';
import { ADMIN_ROLES } from '@/lib/permissions';
import { TITLE_SUFFIX } from '@/lib/useDocumentTitle';

/** Shape of the `handle` we attach to routes for descriptive page titles. */
interface RouteTitleHandle {
  title?: string;
}

/**
 * Side-nav with per-item permission gating against the backend permission codes.
 * The count is deliberately not stated here — it has drifted twice already, and
 * a number in a comment is a claim nobody re-checks.
 * Items without `perms`/`roles` are visible to every authenticated user.
 */
const NAV: NavSection[] = [
  { items: [{ label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard, end: true }] },
  {
    title: 'Crash Records',
    items: [
      { label: 'Crashes', to: '/crashes', icon: CarFront, perms: ['crash:read'] },
    ],
  },
  {
    title: 'Study & Data',
    items: [
      { label: 'Studies', to: '/studies', icon: Boxes, perms: ['study:read', 'crash:read'] },
      { label: 'Data Attributes', to: '/data-attributes', icon: Database, perms: ['study:read', 'crash:read'] },
      { label: 'Data Dictionary', to: '/data-dictionary', icon: BookMarked, perms: ['study:read', 'crash:read'] },
      { label: 'Reference Data', to: '/reference', icon: LibraryBig },
    ],
  },
  {
    title: 'Analysis & Reporting',
    items: [
      { label: 'Analytics', to: '/analytics', icon: FlaskConical, perms: ['analytics:query', 'analytics:dashboard'] },
      { label: 'Analysis Environment', to: '/analysis-environment', icon: Layers, perms: ['analysis_env:read'] },
      { label: 'Statistical Analysis', to: '/statistical-analysis', icon: Sigma, perms: ['analysis_stats:run'] },
      { label: 'Reports', to: '/reports', icon: FileBarChart2, perms: ['report:read'] },
      { label: 'Public Outputs', to: '/public-outputs', icon: Globe, perms: ['public:read'] },
    ],
  },
  {
    title: 'Inbox',
    items: [{ label: 'Notifications', to: '/notifications', icon: Bell }],
  },
  {
    title: 'Administration',
    items: [
      { label: 'Users', to: '/admin/users', icon: UsersIcon, perms: ['admin:users'] },
      { label: 'Organizations', to: '/admin/organizations', icon: Building2, perms: ['admin:users', 'admin:system'] },
      { label: 'Roles & Permissions', to: '/admin/roles', icon: ShieldCheck, perms: ['admin:roles'] },
      { label: 'Integrations', to: '/integrations', icon: PlugZap, perms: ['source_data:ingest', 'admin:system'] },
      { label: 'Audit Log', to: '/admin/audit', icon: History, perms: ['audit:read'] },
      { label: 'Administration', to: '/admin', icon: Settings, end: true, roles: ADMIN_ROLES },
    ],
  },
];

function RouteFallback() {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="text-sm text-muted-foreground">Loading…</div>
    </div>
  );
}

export function AppShell() {
  const { user, loading, logout } = useAuth();
  const location = useLocation();
  const matches = useMatches();
  const mainRef = React.useRef<HTMLElement>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  React.useEffect(() => {
    mainRef.current?.scrollTo({ top: 0, left: 0 });
    setDrawerOpen(false);
  }, [location.pathname]);

  // Descriptive per-page titles (federal website standard §14.1): take the
  // deepest matched route that declares a `handle.title` and set document.title.
  React.useEffect(() => {
    const titled = [...matches]
      .reverse()
      .find((m) => (m.handle as RouteTitleHandle | undefined)?.title);
    const title = (titled?.handle as RouteTitleHandle | undefined)?.title;
    document.title = title ? `${title} · ${TITLE_SUFFIX}` : TITLE_SUFFIX;
  }, [matches]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/30">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  const signOut = (
    <button
      type="button"
      onClick={logout}
      className="flex w-full items-center gap-2.5 rounded-md bg-alert-red-50 px-3 py-2 text-sm font-medium text-alert-red transition-colors hover:bg-alert-red-100"
    >
      <LogOut className="h-4 w-4 shrink-0" aria-hidden />
      <span className="truncate">Sign out</span>
    </button>
  );

  return (
    <div className="flex h-full min-h-screen flex-col bg-background">
      <TopBar onMenuClick={() => setDrawerOpen(true)} />
      <div className="flex flex-1 min-h-0">
        {/* Desktop sidebar */}
        <div className="hidden lg:flex">
          <SideNav sections={NAV} footer={signOut} />
        </div>

        {/* Mobile drawer */}
        {drawerOpen ? (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-black/50" onClick={() => setDrawerOpen(false)} aria-hidden />
            <div className="absolute left-0 top-0 h-full animate-slide-up">
              <SideNav sections={NAV} footer={signOut} onNavigate={() => setDrawerOpen(false)} />
            </div>
          </div>
        ) : null}

        <main ref={mainRef} className="flex-1 min-w-0 overflow-y-auto bg-muted/20">
          <div className="px-4 py-6 sm:px-6">
            <React.Suspense fallback={<RouteFallback />}>
              <Outlet />
            </React.Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}
