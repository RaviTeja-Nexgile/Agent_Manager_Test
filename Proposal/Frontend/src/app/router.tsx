import { lazy } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './AppShell';
import { RequirePermission } from '@/components/auth/RequirePermission';
import { ADMIN_ROLES } from '@/lib/permissions';

/** Every page is code-split via React.lazy (named exports → { default }). */
const lz = (loader: () => Promise<Record<string, unknown>>, name: string) =>
  lazy(async () => ({ default: (await loader())[name] as React.ComponentType<unknown> }));

const LoginPage = lz(() => import('@/pages/auth/LoginPage'), 'LoginPage');
const DashboardPage = lz(() => import('@/pages/DashboardPage'), 'DashboardPage');
const NotFoundPage = lz(() => import('@/pages/NotFoundPage'), 'NotFoundPage');

const CrashesListPage = lz(() => import('@/pages/crashes/CrashesListPage'), 'CrashesListPage');
const CrashDetailPage = lz(() => import('@/pages/crashes/CrashDetailPage'), 'CrashDetailPage');
const CrashOverviewTab = lz(() => import('@/pages/crashes/CrashOverviewTab'), 'CrashOverviewTab');
const CrashInitialIncidentTab = lz(() => import('@/pages/crashes/CrashInitialIncidentTab'), 'CrashInitialIncidentTab');
const CrashSourceDataTab = lz(() => import('@/pages/crashes/CrashSourceDataTab'), 'CrashSourceDataTab');
const CrashAttributesTab = lz(() => import('@/pages/crashes/CrashAttributesTab'), 'CrashAttributesTab');
const CrashQualityTab = lz(() => import('@/pages/crashes/CrashQualityTab'), 'CrashQualityTab');
const CrashCompletenessTab = lz(() => import('@/pages/crashes/CrashCompletenessTab'), 'CrashCompletenessTab');
const CrashFactorsTab = lz(() => import('@/pages/crashes/CrashFactorsTab'), 'CrashFactorsTab');
const CrashDocumentsTab = lz(() => import('@/pages/crashes/CrashDocumentsTab'), 'CrashDocumentsTab');
const CrashTimelineTab = lz(() => import('@/pages/crashes/CrashTimelineTab'), 'CrashTimelineTab');

const StudiesListPage = lz(() => import('@/pages/studies/StudiesListPage'), 'StudiesListPage');
const StudyDetailPage = lz(() => import('@/pages/studies/StudyDetailPage'), 'StudyDetailPage');
const StudyOverviewTab = lz(() => import('@/pages/studies/StudyOverviewTab'), 'StudyOverviewTab');
const StudyStatesTab = lz(() => import('@/pages/studies/StudyStatesTab'), 'StudyStatesTab');
const StudyParametersTab = lz(() => import('@/pages/studies/StudyParametersTab'), 'StudyParametersTab');
const StudyAttributesTab = lz(() => import('@/pages/studies/StudyAttributesTab'), 'StudyAttributesTab');
const StudyCompletenessTab = lz(() => import('@/pages/studies/StudyCompletenessTab'), 'StudyCompletenessTab');
const StudyCoverageTab = lz(() => import('@/pages/studies/StudyCoverageTab'), 'StudyCoverageTab');
const StudyPublicationTab = lz(() => import('@/pages/studies/StudyPublicationTab'), 'StudyPublicationTab');

const DataAttributesPage = lz(() => import('@/pages/reference/DataAttributesPage'), 'DataAttributesPage');
const DataDictionaryPage = lz(() => import('@/pages/reference/DataDictionaryPage'), 'DataDictionaryPage');
const ReferencePage = lz(() => import('@/pages/reference/ReferencePage'), 'ReferencePage');
const AnalyticsPage = lz(() => import('@/pages/analytics/AnalyticsPage'), 'AnalyticsPage');
const AnalysisEnvironmentPage = lz(() => import('@/pages/analysis/AnalysisEnvironmentPage'), 'AnalysisEnvironmentPage');
const StatisticalAnalysisPage = lz(() => import('@/pages/analysis/StatisticalAnalysisPage'), 'StatisticalAnalysisPage');
const ReportsPage = lz(() => import('@/pages/reports/ReportsPage'), 'ReportsPage');
const PublicOutputsPage = lz(() => import('@/pages/public/PublicOutputsPage'), 'PublicOutputsPage');
const NotificationsPage = lz(() => import('@/pages/notifications/NotificationsPage'), 'NotificationsPage');
const SearchPage = lz(() => import('@/pages/search/SearchPage'), 'SearchPage');
const IntegrationsPage = lz(() => import('@/pages/integrations/IntegrationsPage'), 'IntegrationsPage');

const UsersPage = lz(() => import('@/pages/admin/UsersPage'), 'UsersPage');
const OrganizationsPage = lz(() => import('@/pages/admin/OrganizationsPage'), 'OrganizationsPage');
const RolesPage = lz(() => import('@/pages/admin/RolesPage'), 'RolesPage');
const AuditLogPage = lz(() => import('@/pages/admin/AuditLogPage'), 'AuditLogPage');
const AdminPage = lz(() => import('@/pages/admin/AdminPage'), 'AdminPage');

const guard = (perms: string[], el: React.ReactNode) => (
  <RequirePermission perms={perms}>{el}</RequirePermission>
);

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage />, handle: { title: 'Dashboard' } },

      // Crashes
      { path: 'crashes', element: guard(['crash:read'], <CrashesListPage />), handle: { title: 'Crash Records' } },
      {
        path: 'crashes/:id',
        element: guard(['crash:read'], <CrashDetailPage />),
        handle: { title: 'Crash Record' },
        children: [
          { index: true, element: <Navigate to="overview" replace /> },
          { path: 'overview', element: <CrashOverviewTab /> },
          { path: 'initial-incident', element: guard(['crash:read', 'initial_incident:read'], <CrashInitialIncidentTab />) },
          { path: 'source-data', element: guard(['crash:read', 'source_data:read'], <CrashSourceDataTab />) },
          { path: 'attributes', element: guard(['crash:read', 'data_mgmt:read_aggregated'], <CrashAttributesTab />) },
          { path: 'quality', element: guard(['crash:read', 'data_mgmt:qc'], <CrashQualityTab />) },
          { path: 'completeness', element: guard(['crash:read', 'data_mgmt:complete'], <CrashCompletenessTab />) },
          { path: 'contributing-factors', element: <CrashFactorsTab /> },
          { path: 'documents', element: <CrashDocumentsTab /> },
          { path: 'timeline', element: <CrashTimelineTab /> },
        ],
      },

      // Studies & data (backend allows any authenticated user to read studies;
      // gate on study:read OR crash:read so State analysts/inspectors aren't blocked)
      { path: 'studies', element: guard(['study:read', 'crash:read'], <StudiesListPage />), handle: { title: 'Studies' } },
      {
        path: 'studies/:id',
        element: guard(['study:read', 'crash:read'], <StudyDetailPage />),
        handle: { title: 'Study' },
        children: [
          { index: true, element: <Navigate to="overview" replace /> },
          { path: 'overview', element: <StudyOverviewTab /> },
          { path: 'states', element: <StudyStatesTab /> },
          { path: 'parameters', element: <StudyParametersTab /> },
          { path: 'attributes', element: <StudyAttributesTab /> },
          { path: 'completeness-rules', element: <StudyCompletenessTab /> },
          { path: 'coverage', element: <StudyCoverageTab /> },
          { path: 'publication', element: <StudyPublicationTab /> },
        ],
      },
      { path: 'data-attributes', element: guard(['study:read', 'crash:read'], <DataAttributesPage />), handle: { title: 'Data Attributes' } },
      { path: 'data-dictionary', element: guard(['study:read', 'crash:read'], <DataDictionaryPage />), handle: { title: 'Data Dictionary' } },
      { path: 'reference', element: <ReferencePage />, handle: { title: 'Reference Data' } },

      // Analysis & reporting
      { path: 'analytics', element: guard(['analytics:query', 'analytics:dashboard'], <AnalyticsPage />), handle: { title: 'Analytics' } },
      { path: 'analysis-environment', element: guard(['analysis_env:read'], <AnalysisEnvironmentPage />), handle: { title: 'Analysis Environment' } },
      { path: 'statistical-analysis', element: guard(['analysis_stats:run'], <StatisticalAnalysisPage />), handle: { title: 'Statistical Analysis' } },
      { path: 'reports', element: guard(['report:read'], <ReportsPage />), handle: { title: 'Reports' } },
      { path: 'public-outputs', element: guard(['public:read'], <PublicOutputsPage />), handle: { title: 'Published Outputs' } },

      // Inbox / search
      { path: 'notifications', element: <NotificationsPage />, handle: { title: 'Notifications' } },
      { path: 'search', element: guard(['crash:read', 'report:read'], <SearchPage />), handle: { title: 'Search' } },

      // Administration
      { path: 'admin/users', element: guard(['admin:users'], <UsersPage />), handle: { title: 'Users' } },
      { path: 'admin/organizations', element: guard(['admin:users', 'admin:system'], <OrganizationsPage />), handle: { title: 'Organizations' } },
      { path: 'admin/roles', element: guard(['admin:roles'], <RolesPage />), handle: { title: 'Roles & Permissions' } },
      { path: 'integrations', element: guard(['source_data:ingest', 'admin:system'], <IntegrationsPage />), handle: { title: 'Integrations' } },
      { path: 'admin/audit', element: guard(['audit:read'], <AuditLogPage />), handle: { title: 'Audit Log' } },
      { path: 'admin', element: <RequirePermission roles={ADMIN_ROLES}><AdminPage /></RequirePermission>, handle: { title: 'Administration' } },

      { path: '*', element: <NotFoundPage />, handle: { title: 'Not Found' } },
    ],
  },
]);
