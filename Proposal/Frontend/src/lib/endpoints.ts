/**
 * Thin typed wrappers over `api()` — one function per backend route.
 * Grouped by feature; single file so the endpoint surface is greppable.
 * Mirrors Backend/app/features/* (88 routes under /api/v1).
 */
import { api } from './api';
import type {
  AggregatedData,
  AnalysisAudience,
  AnalysisCohort,
  AnalysisDataset,
  AnalysisDatasetDefinition,
  AnalysisEnvironment,
  AnalysisFields,
  AnalysisInvestigation,
  AnalysisMethod,
  AnalysisPiiLevel,
  AnalysisRefreshResult,
  AnalysisRefreshRun,
  AnalysisRows,
  AnalysisShare,
  AnalysisStatistics,
  AnalysisStatsFields,
  Assignment,
  AttributeHistoryResponse,
  AttributeRequirement,
  AttributeValue,
  AuditEntry,
  CcfpDocument,
  CohortDefinition,
  CohortMembers,
  CohortRole,
  ComparativeResult,
  Completeness,
  CompletenessEvalResult,
  CompletenessRule,
  CompletenessTokenCatalog,
  ContributingFactor,
  Crash,
  CrashExternalLink,
  CrashLifecyclePhase,
  CurrentUser,
  DataAttribute,
  DataDictionaryEntry,
  DescriptiveResult,
  DistributionResult,
  DotValidationResult,
  EldEvent,
  EldFile,
  EldIssueSeverity,
  EldParseIssue,
  EldValidation,
  ExternalSystem,
  FactorGroup,
  FactorSummary,
  FactorValue,
  GeoCrashesResponse,
  Groupings,
  IIFSubmitResult,
  IncidentPerson,
  IncidentVehicle,
  InitialIncidentForm,
  IntegrationAdapter,
  InvestigationResult,
  InvestigationWrite,
  LinkMethod,
  Notification,
  OpenDataCatalog,
  Organization,
  Page,
  PciFieldDefinition,
  PcrCoverage,
  PcrSection,
  Permission,
  PoliceCrashReport,
  PostCrashInspection,
  PostCrashInvestigation,
  PublicReport,
  QcEvalResult,
  QcResult,
  QcRule,
  QueryResult,
  ReconstructionReport,
  RefreshCadence,
  Report,
  RiskModelResult,
  Role,
  RoleDetail,
  ScopeClassification,
  SearchResults,
  ShareAudience,
  SourceRecord,
  StatExportFormat,
  Study,
  StudyParameter,
  StudyState,
  StudyStatus,
  ThematicResult,
  TimelineEntry,
  TokenResponse,
  TrendResult,
  User,
} from './types';

// ─────────────── Auth ───────────────
export const authApi = {
  login: (email: string, password: string) =>
    api<TokenResponse>('/auth/login', { method: 'POST', body: { email, password } }),
  me: () => api<CurrentUser>('/auth/me'),
  // AUTH-8: role/access groupings + PII permission codes, served from the backend
  // source of truth so the frontend stops hardcoding them.
  groupings: () => api<Groupings>('/auth/groupings'),
  logout: () => api<void>('/auth/logout', { method: 'POST' }),
};

// ─────────────── Organizations ───────────────
interface OrgWrite {
  name: string;
  org_type: string;
  state_code?: string | null;
  parent_id?: string | null;
  description?: string | null;
}
export const orgApi = {
  list: (params?: { org_type?: string; limit?: number; offset?: number }) =>
    api<Page<Organization>>('/organizations', { query: params }),
  get: (id: string) => api<Organization>(`/organizations/${id}`),
  create: (body: OrgWrite) => api<Organization>('/organizations', { method: 'POST', body }),
  update: (id: string, body: OrgWrite) =>
    api<Organization>(`/organizations/${id}`, { method: 'PATCH', body }),
};

// ─────────────── Users / roles / permissions ───────────────
export const userApi = {
  list: (params?: { q?: string; organization_id?: string; limit?: number; offset?: number }) =>
    api<Page<User>>('/users', { query: params }),
  get: (id: string) => api<User>(`/users/${id}`),
  create: (body: {
    email: string;
    full_name: string;
    organization_id?: string | null;
    title?: string | null;
    phone?: string | null;
    idp_subject?: string | null;
    piv_cac_required?: boolean;
  }) => api<User>('/users', { method: 'POST', body }),
  update: (
    id: string,
    body: Partial<{
      full_name: string;
      organization_id: string | null;
      title: string | null;
      phone: string | null;
      status: string;
      piv_cac_required: boolean;
    }>,
  ) => api<User>(`/users/${id}`, { method: 'PATCH', body }),
  deactivate: (id: string) => api<User>(`/users/${id}/deactivate`, { method: 'POST' }),
  roles: (id: string) => api<Assignment[]>(`/users/${id}/roles`),
  assignRole: (
    id: string,
    body: {
      role_code: string;
      scope_type?: string;
      state_code?: string | null;
      organization_id?: string | null;
      study_id?: string | null;
    },
  ) => api<Assignment>(`/users/${id}/roles`, { method: 'POST', body }),
  revokeRole: (id: string, assignmentId: string) =>
    api<void>(`/users/${id}/roles/${assignmentId}`, { method: 'DELETE' }),
};

export const roleApi = {
  list: () => api<Role[]>('/roles'),
  get: (id: string) => api<RoleDetail>(`/roles/${id}`),
  create: (body: { code: string; name: string; description?: string | null }) =>
    api<Role>('/roles', { method: 'POST', body }),
  update: (id: string, body: { name?: string | null; description?: string | null }) =>
    api<Role>(`/roles/${id}`, { method: 'PATCH', body }),
  remove: (id: string) => api<void>(`/roles/${id}`, { method: 'DELETE' }),
  setPermissions: (id: string, body: { permission_codes: string[] }) =>
    api<RoleDetail>(`/roles/${id}/permissions`, { method: 'PUT', body }),
};
export const permissionApi = {
  list: () => api<Permission[]>('/permissions'),
  create: (body: { code: string; name: string; category: string; description?: string | null }) =>
    api<Permission>('/permissions', { method: 'POST', body }),
};

// ─────────────── Studies & config ───────────────
export const studyApi = {
  list: (params?: { status?: StudyStatus }) => api<Study[]>('/studies', { query: params }),
  get: (id: string) => api<Study>(`/studies/${id}`),
  create: (body: Record<string, unknown>) => api<Study>('/studies', { method: 'POST', body }),
  update: (id: string, body: Record<string, unknown>) =>
    api<Study>(`/studies/${id}`, { method: 'PATCH', body }),
  attributes: (id: string) => api<AttributeRequirement[]>(`/studies/${id}/attributes`),
  updateAttribute: (
    id: string,
    attributeId: string,
    body: Partial<{ is_required: boolean; is_optional: boolean; is_read_only: boolean; is_editable: boolean }>,
  ) => api<AttributeRequirement>(`/studies/${id}/attributes/${attributeId}`, { method: 'PATCH', body }),
  completenessRules: (id: string) => api<CompletenessRule[]>(`/studies/${id}/completeness-rules`),
  createCompletenessRule: (id: string, body: Record<string, unknown>) =>
    api<CompletenessRule>(`/studies/${id}/completeness-rules`, { method: 'POST', body }),
  updateCompletenessRule: (ruleId: string, body: Record<string, unknown>) =>
    api<CompletenessRule>(`/completeness-rules/${ruleId}`, { method: 'PATCH', body }),
  deleteCompletenessRule: (ruleId: string) =>
    api<void>(`/completeness-rules/${ruleId}`, { method: 'DELETE' }),
  completenessRuleTokens: () => api<CompletenessTokenCatalog>('/completeness-rule-tokens'),
  states: (id: string) => api<StudyState[]>(`/studies/${id}/states`),
  addState: (id: string, body: Record<string, unknown>) =>
    api<StudyState>(`/studies/${id}/states`, { method: 'POST', body }),
  updateState: (id: string, stateCode: string, body: Record<string, unknown>) =>
    api<StudyState>(`/studies/${id}/states/${stateCode}`, { method: 'PATCH', body }),
  parameters: (id: string) => api<StudyParameter[]>(`/studies/${id}/parameters`),
  upsertParameter: (id: string, body: { param_key: string; param_value: unknown; description?: string | null }) =>
    api<StudyParameter>(`/studies/${id}/parameters`, { method: 'POST', body }),
  deleteParameter: (id: string, paramKey: string) =>
    api<void>(`/studies/${id}/parameters/${encodeURIComponent(paramKey)}`, { method: 'DELETE' }),
  // PCI-3: per-study PCI form-field definitions (required/optional markers).
  pciFieldDefinitions: (id: string) =>
    api<PciFieldDefinition[]>(`/studies/${id}/pci-field-definitions`),
  pcrCoverage: (id: string, state?: string) =>
    api<PcrCoverage[]>(`/studies/${id}/pcr-coverage`, { query: { state } }),
  attributeCoverage: (id: string, state?: string) =>
    api<Array<{ attribute_id: string; code: string; name: string; pcr_section: string | null; is_required: boolean; is_optional: boolean; is_collected: boolean; status: 'REQUIRED_COLLECTED' | 'REQUIRED_NOT_COLLECTED' | 'OPTIONAL_NOT_COLLECTED' }>>(`/studies/${id}/attribute-coverage`, { query: { state } }),
  upsertPcrCoverage: (
    id: string,
    body: { state_code: string; pcr_section_code: string; required_collected?: number; total_required?: number; optional_collected?: number; total_optional?: number },
  ) => api<PcrCoverage>(`/studies/${id}/pcr-coverage`, { method: 'POST', body }),
  updatePcrCoverage: (
    id: string,
    state: string,
    section: string,
    body: Partial<{ required_collected: number; total_required: number; optional_collected: number; total_optional: number }>,
  ) => api<PcrCoverage>(`/studies/${id}/pcr-coverage/${encodeURIComponent(state)}/${encodeURIComponent(section)}`, { method: 'PATCH', body }),
};

export const dataAttributeApi = {
  list: (params?: { pcr_section?: string; category?: string; include_inactive?: boolean }) =>
    api<DataAttribute[]>('/data-attributes', { query: params }),
  // PCR form section catalog (GAP-PCR-01): specification labels + form order.
  // Retired sections are excluded unless include_inactive is set.
  sections: (params?: { include_inactive?: boolean }) =>
    api<PcrSection[]>('/pcr-sections', { query: params }),
  // The CCFP PCR Data Dictionary (GAP-PCR-09). Pass study_id to mark which
  // attributes that study requires.
  dictionary: (params?: { study_id?: string; include_inactive?: boolean }) =>
    api<DataDictionaryEntry[]>('/data-dictionary', { query: params }),
  get: (id: string) => api<DataAttribute>(`/data-attributes/${id}`),
  create: (body: Record<string, unknown>) =>
    api<DataAttribute>('/data-attributes', { method: 'POST', body }),
  update: (id: string, body: Record<string, unknown>) =>
    api<DataAttribute>(`/data-attributes/${id}`, { method: 'PATCH', body }),
};

// ─────────────── Crashes ───────────────
export interface CrashListParams {
  study_id?: string;
  state_code?: string;
  scope?: string;
  lifecycle_phase?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
  limit?: number;
  offset?: number;
}
export const crashApi = {
  // Cached for offline use: an inspector working the Initial Incident Form at a
  // crash scene has to be able to find the record and open it. Without the list
  // and the record itself the form is unreachable offline, so caching the child
  // resources alone would not deliver a usable offline flow.
  list: (params?: CrashListParams) =>
    api<Page<Crash>>('/crashes', {
      query: params as Record<string, string | number | undefined>,
      offline: { cache: true },
    }),
  create: (body: Record<string, unknown>) => api<Crash>('/crashes', { method: 'POST', body }),
  get: (id: string) => api<Crash>(`/crashes/${id}`, { offline: { cache: true } }),
  update: (id: string, body: Record<string, unknown>) =>
    api<Crash>(`/crashes/${id}`, { method: 'PATCH', body }),
  scope: (id: string) => api<ScopeClassification>(`/crashes/${id}/scope`),
  setScope: (id: string, body: Record<string, unknown>) =>
    api<ScopeClassification>(`/crashes/${id}/scope`, { method: 'PUT', body }),
  reclassifyScope: (id: string) =>
    api<ScopeClassification>(`/crashes/${id}/scope/reclassify`, { method: 'POST' }),
  advancePhase: (id: string, target: CrashLifecyclePhase) =>
    api<Crash>(`/crashes/${id}/advance-phase`, { method: 'POST', body: { target_phase: target } }),
  attributes: (id: string) => api<AttributeValue[]>(`/crashes/${id}/attributes`),
  // Pass unit to scope the timeline to one repeating unit (GAP-PCR-03); omit it
  // for a crash-level attribute or to see every unit's versions interleaved.
  attributeHistory: (id: string, code: string, unit?: { unit_type: string; unit_number: number } | null) =>
    api<AttributeHistoryResponse>(
      `/crashes/${id}/attributes/${code}/history` +
        (unit ? `?unit_type=${encodeURIComponent(unit.unit_type)}&unit_number=${unit.unit_number}` : ''),
    ),
  setAttribute: (
    id: string,
    body: {
      attribute_code: string; value_text?: string | null; value_json?: unknown;
      source_system?: string | null; source_record_id?: string | null; confidence?: number | null;
      unit_type?: string | null; unit_number?: number | null;
    },
  ) => api<AttributeValue>(`/crashes/${id}/attributes`, { method: 'POST', body }),
  quality: (id: string) => api<QcResult[]>(`/crashes/${id}/quality`),
  evaluateQuality: (id: string) => api<QcEvalResult>(`/crashes/${id}/quality/evaluate`, { method: 'POST' }),
  completeness: (id: string) => api<Completeness>(`/crashes/${id}/completeness`),
  evaluateCompleteness: (id: string) =>
    api<CompletenessEvalResult>(`/crashes/${id}/completeness/evaluate`, { method: 'POST' }),
  unlock: (id: string) => api<Completeness>(`/crashes/${id}/unlock`, { method: 'POST' }),
  timeline: (id: string) => api<TimelineEntry[]>(`/crashes/${id}/timeline`),
  sources: (id: string) => api<SourceRecord[]>(`/crashes/${id}/sources`),
  // NOTI-5: admin/project-team on-demand scan for crashes missing an Initial
  // Incident Form. Emits MISSING_IIF notifications and returns the flagged count.
  scanMissingIif: (params?: { study_id?: string; window_hours?: number }) =>
    api<{ flagged: number; window_hours: number }>('/crashes/scan-missing-iif', {
      method: 'POST',
      query: params as Record<string, string | number | undefined>,
    }),
};

// ─────────────── Initial Incident Form ───────────────
/**
 * The Initial Incident Form is the one workflow that must work with no network:
 * the inspector completes it at the crash scene within 24-48 hours, often with
 * no signal. These calls therefore cache their reads and queue their writes.
 * Every create mints a `client_uuid` so a replayed sync returns the row the
 * first attempt created rather than inserting a duplicate.
 */
export const iifApi = {
  get: (crashId: string) =>
    api<InitialIncidentForm>(`/crashes/${crashId}/initial-incident`, { offline: { cache: true } }),
  // INIT-4: the form also carries the crash's general-information/location fields
  // (documentation §8.2). Sending them here applies them to the crash under
  // `initial_incident:write`, so the MCSAP Inspector who owns the form can correct
  // what the form collects without holding `crash:update`.
  save: (
    crashId: string,
    body: {
      event_summary?: string | null;
      dot_validation_source?: string | null;
      local_report_number?: string | null;
      crash_date?: string | null;
      crash_time?: string | null;
      state_code?: string | null;
      city?: string | null;
      county?: string | null;
      street_highway?: string | null;
      num_vehicles?: number | null;
      num_persons?: number | null;
      num_fatalities?: number | null;
    },
  ) =>
    api<InitialIncidentForm>(`/crashes/${crashId}/initial-incident`, {
      method: 'PUT',
      body,
      // The PUT is a server-side upsert keyed on the crash, so it is already
      // safe to replay as-is and needs no client key.
      offline: { queue: true, crashId, label: 'Initial Incident Form', optimistic: null },
    }),
  // Submit deliberately stays online-only: it validates U.S. DOT numbers against
  // SafeSpect and fans out routing notifications, neither of which can be
  // decided on the device. The form is captured offline; routing happens on sync.
  submit: (crashId: string) =>
    api<IIFSubmitResult>(`/crashes/${crashId}/initial-incident/submit`, { method: 'POST' }),
  remove: (crashId: string) =>
    api<void>(`/crashes/${crashId}/initial-incident`, { method: 'DELETE' }),
  vehicles: (crashId: string) =>
    api<IncidentVehicle[]>(`/crashes/${crashId}/incident-vehicles`, { offline: { cache: true } }),
  addVehicle: (crashId: string, body: Record<string, unknown>) => {
    const client_uuid = (body.client_uuid as string) ?? crypto.randomUUID();
    const payload = { ...body, client_uuid };
    return api<IncidentVehicle>(`/crashes/${crashId}/incident-vehicles`, {
      method: 'POST',
      body: payload,
      offline: {
        queue: true,
        crashId,
        label: `Vehicle ${body.vehicle_number ?? ''}`.trim(),
        optimistic: { ...payload, id: client_uuid, crash_id: crashId },
      },
    });
  },
  updateVehicle: (crashId: string, vehId: string, body: Record<string, unknown>) =>
    api<IncidentVehicle>(`/crashes/${crashId}/incident-vehicles/${vehId}`, {
      method: 'PATCH',
      body,
      offline: { queue: true, crashId, label: `Vehicle ${body.vehicle_number ?? ''}`.trim(), optimistic: null },
    }),
  deleteVehicle: (crashId: string, vehId: string) =>
    api<void>(`/crashes/${crashId}/incident-vehicles/${vehId}`, { method: 'DELETE' }),
  persons: (crashId: string) =>
    api<IncidentPerson[]>(`/crashes/${crashId}/incident-persons`, { offline: { cache: true } }),
  addPerson: (crashId: string, body: Record<string, unknown>) => {
    // A person has no natural key, so without this the server cannot tell a
    // replay from a genuinely new person — and a duplicated fatality changes
    // whether the crash qualifies for the study.
    const client_uuid = (body.client_uuid as string) ?? crypto.randomUUID();
    const payload = { ...body, client_uuid };
    // The server derives full_name from the name parts. Mirror that locally so a
    // queued record shows a name in the table instead of a dash while it waits.
    const parts = [body.name_first, body.name_middle, body.name_last].filter(Boolean);
    const displayName = (body.full_name as string) ?? (parts.length ? parts.join(' ') : undefined);
    return api<IncidentPerson>(`/crashes/${crashId}/incident-persons`, {
      method: 'POST',
      body: payload,
      offline: {
        queue: true,
        crashId,
        label: `Person: ${displayName ?? body.person_type ?? 'unnamed'}`,
        optimistic: {
          ...payload,
          full_name: displayName,
          id: client_uuid,
          crash_id: crashId,
          pii_redacted: false,
        },
      },
    });
  },
  updatePerson: (crashId: string, personId: string, body: Record<string, unknown>) =>
    api<IncidentPerson>(`/crashes/${crashId}/incident-persons/${personId}`, {
      method: 'PATCH',
      body,
      offline: { queue: true, crashId, label: `Person: ${body.full_name ?? 'edit'}`, optimistic: null },
    }),
  deletePerson: (crashId: string, personId: string) =>
    api<void>(`/crashes/${crashId}/incident-persons/${personId}`, { method: 'DELETE' }),
};

// PCR-1 (§8.5/§19.4): one State-PCR-field -> CCFP-attribute mapping row.
// `attribute_code`/`attribute_name` are resolved server-side for display.
export interface PcrFieldMapping {
  id: string;
  pcr_id: string;
  state_field_name: string;
  state_field_position: string | null;
  attribute_id: string;
  attribute_code: string | null;
  attribute_name: string | null;
  notes: string | null;
  mapped_by: string | null;
}

// ─────────────── Source data ───────────────
export const sourceApi = {
  inspections: (crashId: string) =>
    api<PostCrashInspection[]>(`/crashes/${crashId}/post-crash-inspections`),
  addInspection: (crashId: string, body: Record<string, unknown>) =>
    api<PostCrashInspection>(`/crashes/${crashId}/post-crash-inspections`, { method: 'POST', body }),
  updateInspection: (crashId: string, recId: string, body: Record<string, unknown>) =>
    api<PostCrashInspection>(`/crashes/${crashId}/post-crash-inspections/${recId}`, { method: 'PATCH', body }),

  investigations: (crashId: string) =>
    api<PostCrashInvestigation[]>(`/crashes/${crashId}/post-crash-investigations`),
  addInvestigation: (crashId: string, body: Record<string, unknown>) =>
    api<PostCrashInvestigation>(`/crashes/${crashId}/post-crash-investigations`, { method: 'POST', body }),
  // PCI-2: the full structured §19.2 payload (sections + repeating/conditional arrays + flags).
  updateInvestigation: (crashId: string, recId: string, body: InvestigationWrite) =>
    api<PostCrashInvestigation>(`/crashes/${crashId}/post-crash-investigations/${recId}`, { method: 'PATCH', body }),
  submitInvestigation: (crashId: string, recId: string) =>
    api<PostCrashInvestigation>(`/crashes/${crashId}/post-crash-investigations/${recId}/submit`, { method: 'POST' }),

  pcrs: (crashId: string) => api<PoliceCrashReport[]>(`/crashes/${crashId}/police-crash-reports`),
  addPcr: (crashId: string, body: Record<string, unknown>) =>
    api<PoliceCrashReport>(`/crashes/${crashId}/police-crash-reports`, { method: 'POST', body }),
  updatePcr: (crashId: string, recId: string, body: Record<string, unknown>) =>
    api<PoliceCrashReport>(`/crashes/${crashId}/police-crash-reports/${recId}`, { method: 'PATCH', body }),
  mapPcr: (crashId: string, recId: string) =>
    api<PoliceCrashReport>(`/crashes/${crashId}/police-crash-reports/${recId}/map`, { method: 'POST' }),
  // PCR-1 (§8.5/§19.4): State PCR field -> CCFP attribute mappings, scoped under the PCR.
  pcrFieldMappings: (crashId: string, recId: string) =>
    api<PcrFieldMapping[]>(`/crashes/${crashId}/police-crash-reports/${recId}/field-mappings`),
  addPcrFieldMapping: (
    crashId: string,
    recId: string,
    body: { state_field_name: string; state_field_position?: string | null; attribute_code: string; notes?: string | null },
  ) => api<PcrFieldMapping>(`/crashes/${crashId}/police-crash-reports/${recId}/field-mappings`, { method: 'POST', body }),
  deletePcrFieldMapping: (crashId: string, recId: string, mappingId: string) =>
    api<void>(`/crashes/${crashId}/police-crash-reports/${recId}/field-mappings/${mappingId}`, { method: 'DELETE' }),

  reconstructions: (crashId: string) =>
    api<ReconstructionReport[]>(`/crashes/${crashId}/reconstruction-reports`),
  addReconstruction: (
    crashId: string,
    body: { title?: string | null; received_date?: string | null },
    file?: File,
  ) => {
    // RECO-3: the recon endpoint is multipart with an OPTIONAL file (mirrors sourceApi.uploadEld).
    // Always send FormData; append the binary only when one is attached. The no-file path
    // (metadata-only stub) still works because add_recon's Form fields are all optional.
    const fd = new FormData();
    if (file) fd.append('file', file);
    if (body.title) fd.append('title', String(body.title));
    if (body.received_date) fd.append('received_date', String(body.received_date));
    return api<ReconstructionReport>(`/crashes/${crashId}/reconstruction-reports`, { method: 'POST', body: fd });
  },
  codeReconstruction: (
    crashId: string,
    recId: string,
    body: {
      coding_status: string;
      coded_attributes?: { attribute_code: string; value_text?: string | null; value_json?: unknown; confidence?: number | null }[];
      coded_findings?: Record<string, unknown> | null;
    },
  ) => api<ReconstructionReport>(`/crashes/${crashId}/reconstruction-reports/${recId}`, { method: 'PATCH', body }),

  // PCI-7: edit an ELD file's summary fields (download status / last entry / last
  // duty status / last stop). Partial update — only the keys sent are touched.
  updateEldFile: (
    crashId: string,
    fileId: string,
    body: {
      eld_downloaded?: boolean | null;
      last_entry_at?: string | null;
      last_duty_status?: string | null;
      last_stop_arrived_at?: string | null;
      last_stop_departed_at?: string | null;
    },
  ) => api<EldFile>(`/crashes/${crashId}/eld-files/${fileId}`, { method: 'PATCH', body }),
  eldFiles: (crashId: string) => api<EldFile[]>(`/crashes/${crashId}/eld-files`),
  eldFile: (crashId: string, fileId: string) => api<EldFile>(`/crashes/${crashId}/eld-files/${fileId}`),
  uploadEld: (crashId: string, file: File, meta?: { provider?: string; model?: string; version?: string }) => {
    const fd = new FormData();
    fd.append('file', file);
    if (meta?.provider) fd.append('provider', meta.provider);
    if (meta?.model) fd.append('model', meta.model);
    if (meta?.version) fd.append('version', meta.version);
    return api<EldFile>(`/crashes/${crashId}/eld-files`, { method: 'POST', body: fd });
  },
  // BRD Appendix E: every problem the extraction recorded for one file —
  // ERROR (why it stopped or was incomplete), WARNING (a value that could not
  // be read, with its line) and INFO (an interpretation the parser made).
  eldFileIssues: (crashId: string, fileId: string, severity?: EldIssueSeverity) =>
    api<EldParseIssue[]>(
      `/crashes/${crashId}/eld-files/${fileId}/issues${severity ? `?severity=${severity}` : ''}`,
    ),
  // Re-run extraction on a stored file — the recovery path after an
  // administrator configures a provider's column names or duty codes.
  reparseEldFile: (crashId: string, fileId: string) =>
    api<EldFile>(`/crashes/${crashId}/eld-files/${fileId}/reparse`, { method: 'POST' }),
  // Dry run: report what WOULD be extracted, store nothing.
  validateEld: (crashId: string, file: File, provider?: string) => {
    const fd = new FormData();
    fd.append('file', file);
    if (provider) fd.append('provider', provider);
    return api<EldValidation>(`/crashes/${crashId}/eld-files/validate`, { method: 'POST', body: fd });
  },
  eldEvents: (crashId: string) => api<EldEvent[]>(`/crashes/${crashId}/eld-events`),
};

// ─────────────── Data management & QC ───────────────
export const dataMgmtApi = {
  qcRules: () => api<QcRule[]>('/data-quality-rules'),
  createQcRule: (body: Record<string, unknown>) =>
    api<QcRule>('/data-quality-rules', { method: 'POST', body }),
  updateQcRule: (id: string, body: Record<string, unknown>) =>
    api<QcRule>(`/data-quality-rules/${id}`, { method: 'PATCH', body }),
  rawData: (crashId: string) =>
    api<{ crash_id: string; counts: Record<string, number>; source_records: Record<string, unknown>[] }>(
      `/crashes/${crashId}/raw-data`,
    ),
  // The full CCFP Aggregated Data document — canonical attributes
  // with provenance, CCFP source records, and Appendix D external links. The
  // four legacy counts remain at the top level for existing callers.
  aggregated: (crashId: string) => api<AggregatedData>(`/crashes/${crashId}/aggregated`),
  externalSystems: (includeInactive = false) =>
    api<ExternalSystem[]>('/external-systems', { query: { include_inactive: includeInactive } }),
  externalLinks: (crashId: string, includeHistorical = false) =>
    api<CrashExternalLink[]>(`/crashes/${crashId}/external-links`, {
      query: { include_historical: includeHistorical },
    }),
  addExternalLink: (
    crashId: string,
    body: {
      source_system: string;
      external_ref: string;
      link_method?: LinkMethod;
      matched_on?: Record<string, unknown> | null;
      confidence?: number | null;
      notes?: string | null;
    },
  ) => api<CrashExternalLink>(`/crashes/${crashId}/external-links`, { method: 'POST', body }),
  removeExternalLink: (crashId: string, linkId: string) =>
    api<void>(`/crashes/${crashId}/external-links/${linkId}`, { method: 'DELETE' }),
  factorGroups: () => api<FactorGroup[]>('/contributing-factor-groups'),
  factorValues: (groupCode?: string) =>
    api<FactorValue[]>('/contributing-factor-values', { query: { group_code: groupCode } }),
  contributingFactors: (crashId: string) =>
    api<ContributingFactor[]>(`/crashes/${crashId}/contributing-factors`),
  /** BRD DL4: PCR-section summary the analyst ranks the top three factors from. */
  contributingFactorSummary: (crashId: string) =>
    api<FactorSummary>(`/crashes/${crashId}/contributing-factor-summary`),
  setContributingFactors: (
    crashId: string,
    factors: { factor_group_code?: string | null; factor_value: string; rank: number }[],
  ) => api<ContributingFactor[]>(`/crashes/${crashId}/contributing-factors`, { method: 'PUT', body: { factors } }),
};

// ─────────────── Analytics ───────────────
export const analyticsApi = {
  dashboards: () => api<Report[]>('/analytics/dashboards'),
  dashboard: (reportId: string) => api<Report>(`/analytics/dashboards/${reportId}`),
  queries: () => api<{ available_queries: Record<string, string> }>('/analytics/queries'),
  runQuery: (query_name: string, study_id?: string) =>
    api<QueryResult>('/analytics/queries', { method: 'POST', body: { query_name, study_id } }),
  queryBuilderFields: () =>
    api<{ group_by: string[]; aggregations: string[]; filter_columns: string[]; operators: string[] }>(
      '/analytics/query-builder/fields',
    ),
  runQueryBuilder: (body: {
    group_by: string;
    aggregation?: string;
    filters?: { column: string; op: string; value: string | number }[];
    study_id?: string;
  }) => api<QueryResult>('/analytics/query-builder', { method: 'POST', body }),
  // Crash positions for the map (GAP-BRD-11). State-scoped server-side like
  // every other analytics read.
  geoCrashes: (params?: { study_id?: string; limit?: number }) =>
    api<GeoCrashesResponse>('/analytics/geo/crashes', { query: params }),
};

// ─────────────── Reports ───────────────
export const reportApi = {
  list: (report_type?: string) => api<Report[]>('/reports', { query: { report_type } }),
  create: (body: Record<string, unknown>) => api<Report>('/reports', { method: 'POST', body }),
  get: (id: string) => api<Report>(`/reports/${id}`),
  update: (id: string, body: Record<string, unknown>) =>
    api<Report>(`/reports/${id}`, { method: 'PATCH', body }),
  remove: (id: string) => api<void>(`/reports/${id}`, { method: 'DELETE' }),
  // `audience` releases to a tier rather than a named target. Only
  // the CCFP Database Administrator may use OTHER_FEDERAL / STATE / PUBLIC; the
  // backend 403s otherwise, so the UI gates the options to match.
  share: (id: string, body: { shared_with_user_id?: string | null; shared_with_role_code?: string | null; shared_with_org_id?: string | null; audience?: ShareAudience | null; audience_state_code?: string | null; can_download?: boolean }) =>
    api<{ share_id: string; report_id: string }>(`/reports/${id}/share`, { method: 'POST', body }),
  publish: (id: string) => api<Report>(`/reports/${id}/publish`, { method: 'POST' }),
  download: (id: string) => api<string>(`/reports/${id}/download`),
};

// ─────────────── Public (no auth) ───────────────
export const publicApi = {
  allOutputs: () => api<PublicReport[]>('/public/outputs'),
  studyOutputs: (studyId: string) => api<PublicReport[]>(`/public/studies/${studyId}/outputs`),
  report: (id: string) => api<PublicReport>(`/public/reports/${id}`),
  downloadCsv: (id: string) => api<string>(`/public/reports/${id}/download`),
  // ANAL-9: machine-readable Project Open Data catalog of published outputs (no auth).
  catalog: () => api<OpenDataCatalog>('/public/data.json'),
};

// ─────────────── Documents ───────────────
export const documentApi = {
  upload: (file: File, body: { crash_id: string; doc_type?: string; sensitivity?: string }) => {
    const fd = new FormData();
    fd.append('crash_id', body.crash_id);
    fd.append('file', file);
    if (body.doc_type) fd.append('doc_type', body.doc_type);
    if (body.sensitivity) fd.append('sensitivity', body.sensitivity);
    return api<CcfpDocument>('/documents', { method: 'POST', body: fd });
  },
  forCrash: (crashId: string) => api<CcfpDocument[]>(`/crashes/${crashId}/documents`),
  get: (id: string) => api<CcfpDocument>(`/documents/${id}`),
  downloadLink: (id: string) =>
    api<{ signed_url: string; expires_in_minutes: number }>(`/documents/${id}/download`),
};

// ─────────────── Notifications ───────────────
export const notificationApi = {
  list: (unreadOnly = false) => api<Notification[]>('/notifications', { query: { unread_only: unreadOnly } }),
  markRead: (id: string) => api<Notification>(`/notifications/${id}/read`, { method: 'PATCH' }),
  markAllRead: () => api<{ marked_read: number }>('/notifications/read-all', { method: 'POST' }),
};

// ─────────────── Search ───────────────
export const searchApi = {
  search: (q: string, types?: string, limit = 25) =>
    api<SearchResults>('/search', { query: { q, types, limit } }),
};

// ─────────────── Audit ───────────────
export const auditApi = {
  list: (params?: {
    crash_id?: string;
    entity_type?: string;
    actor_user_id?: string;
    action?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => api<Page<AuditEntry>>('/audit-logs', { query: params }),
};

// ─────────────── Integrations ───────────────
export const integrationApi = {
  list: () => api<{ adapters: IntegrationAdapter[] }>('/integrations'),
  validateDot: (dot_number: string) =>
    api<DotValidationResult>('/integrations/safespect/validate-dot', { method: 'POST', body: { dot_number } }),
  verifyCdlis: (license_number: string, jurisdiction?: string) =>
    api<Record<string, unknown>>('/integrations/cdlis/verify', { method: 'POST', body: { license_number, jurisdiction } }),
  lookupMcmis: (local_report_number: string) =>
    api<Record<string, unknown>>('/integrations/mcmis/lookup', { method: 'POST', body: { local_report_number } }),
};

// ─────────────── CCFP Analysis Environment ───────────────
export const analysisEnvApi = {
  environments: () => api<AnalysisEnvironment[]>('/analysis-environments'),
  environment: (id: string) => api<AnalysisEnvironment>(`/analysis-environments/${id}`),
  updateEnvironment: (id: string, body: { status?: string; refresh_cadence?: RefreshCadence; name?: string; description?: string }) =>
    api<AnalysisEnvironment>(`/analysis-environments/${id}`, { method: 'PATCH', body }),
  refreshEnvironment: (id: string) =>
    api<AnalysisRefreshResult>(`/analysis-environments/${id}/refresh`, { method: 'POST' }),
  refreshRuns: (id: string, limit = 10) =>
    api<AnalysisRefreshRun[]>(`/analysis-environments/${id}/refresh-runs`, { query: { limit } }),

  fields: () => api<AnalysisFields>('/analysis-datasets/fields'),
  datasets: (environment_id?: string) =>
    api<AnalysisDataset[]>('/analysis-datasets', { query: { environment_id } }),
  dataset: (id: string) => api<AnalysisDataset>(`/analysis-datasets/${id}`),
  createDataset: (body: {
    environment_id: string;
    code: string;
    name: string;
    description?: string;
    kind?: string;
    pii_level?: AnalysisPiiLevel;
    definition: AnalysisDatasetDefinition;
  }) => api<AnalysisDataset>('/analysis-datasets', { method: 'POST', body }),
  deleteDataset: (id: string) => api<void>(`/analysis-datasets/${id}`, { method: 'DELETE' }),
  refreshDataset: (id: string) =>
    api<AnalysisDataset>(`/analysis-datasets/${id}/refresh`, { method: 'POST' }),

  rows: (id: string, limit = 100, offset = 0) =>
    api<AnalysisRows>(`/analysis-datasets/${id}/rows`, { query: { limit, offset } }),
  statistics: (id: string, column: string) =>
    api<AnalysisStatistics>(`/analysis-datasets/${id}/statistics`, { query: { column } }),
  // Export returns a file body. CSV arrives as raw text; JSON is parsed by
  // `api()` because the response is application/json — so the caller re-
  // serialises it before saving. Typed as unknown to keep that explicit rather
  // than lying about the CSV/JSON split.
  exportData: (id: string, format: 'csv' | 'json') =>
    api<unknown>(`/analysis-datasets/${id}/export`, { query: { format } }),

  shares: (id: string) => api<AnalysisShare[]>(`/analysis-datasets/${id}/shares`),
  createShare: (id: string, body: { audience: AnalysisAudience; state_code?: string | null; refresh_cadence?: RefreshCadence; note?: string }) =>
    api<AnalysisShare>(`/analysis-datasets/${id}/shares`, { method: 'POST', body }),
  revokeShare: (shareId: string) =>
    api<AnalysisShare>(`/analysis-shares/${shareId}`, { method: 'DELETE' }),
};

// ─────────────── Statistical analysis ───────────────
// Cohorts, the four BRD-named statistical method families, saved investigations
// and export to the statistical tools the BRD names (Python, SAS, R).
export const analysisStatsApi = {
  fields: () => api<AnalysisStatsFields>('/analysis-cohorts/fields'),
  /** Contributing factors present in materialized cohorts — the exposures that
   *  can actually be modelled, as opposed to everything in the catalog. */
  factors: (cohort_id?: string) =>
    api<{ factor: string; crashes: number }[]>('/analysis-cohorts/factors', { query: { cohort_id } }),

  cohorts: (environment_id?: string) =>
    api<AnalysisCohort[]>('/analysis-cohorts', { query: { environment_id } }),
  cohort: (id: string) => api<AnalysisCohort>(`/analysis-cohorts/${id}`),
  createCohort: (body: {
    environment_id: string;
    code: string;
    name: string;
    description?: string;
    cohort_role?: CohortRole;
    definition: CohortDefinition;
  }) => api<AnalysisCohort>('/analysis-cohorts', { method: 'POST', body }),
  updateCohort: (
    id: string,
    body: { name?: string; description?: string; cohort_role?: CohortRole; definition?: CohortDefinition; status?: string },
  ) => api<AnalysisCohort>(`/analysis-cohorts/${id}`, { method: 'PATCH', body }),
  deleteCohort: (id: string) => api<void>(`/analysis-cohorts/${id}`, { method: 'DELETE' }),
  refreshCohort: (id: string) =>
    api<AnalysisCohort>(`/analysis-cohorts/${id}/refresh`, { method: 'POST' }),
  members: (id: string, limit = 100, offset = 0) =>
    api<CohortMembers>(`/analysis-cohorts/${id}/members`, { query: { limit, offset } }),

  // Methods. Each returns its cohort version alongside the numbers.
  describe: (id: string, variable: string, confidence = 0.95) =>
    api<DescriptiveResult>(`/analysis-cohorts/${id}/describe`, { query: { variable, confidence } }),
  distribution: (id: string, variable: string, bins = 10) =>
    api<DistributionResult>(`/analysis-cohorts/${id}/distribution`, { query: { variable, bins } }),
  thematic: (id: string, min_support = 1, top_n = 25) =>
    api<ThematicResult>(`/analysis-cohorts/${id}/thematic`, { query: { min_support, top_n } }),
  trend: (id: string, period = 'YEAR', measure = 'crash_count') =>
    api<TrendResult>(`/analysis-cohorts/${id}/trend`, { query: { period, measure } }),
  riskModel: (body: {
    case_cohort_id: string;
    control_cohort_id: string;
    exposure_factor: string;
    confidence?: number;
  }) => api<RiskModelResult>('/analysis-statistics/risk-model', { method: 'POST', body }),
  compare: (body: {
    cohort_a_id: string;
    cohort_b_id: string;
    variable?: string;
    factor?: string;
    confidence?: number;
  }) => api<ComparativeResult>('/analysis-statistics/compare', { method: 'POST', body }),

  investigations: (environment_id?: string) =>
    api<AnalysisInvestigation[]>('/analysis-investigations', { query: { environment_id } }),
  createInvestigation: (body: {
    environment_id: string;
    code: string;
    name: string;
    description?: string;
    method: AnalysisMethod;
    parameters: Record<string, unknown>;
    visibility?: 'PRIVATE' | 'TEAM';
  }) => api<AnalysisInvestigation>('/analysis-investigations', { method: 'POST', body }),
  deleteInvestigation: (id: string) =>
    api<void>(`/analysis-investigations/${id}`, { method: 'DELETE' }),
  runInvestigation: (id: string) =>
    api<InvestigationResult>(`/analysis-investigations/${id}/run`, { method: 'POST' }),

  /** Cohort export. CSV and the three loader scripts all come back as text —
   *  `api()` returns the raw string for non-JSON content types, so the caller
   *  gets script source rather than a parse error. */
  exportData: (id: string, format: StatExportFormat) =>
    api<string>(`/analysis-cohorts/${id}/export`, { query: { format } }),
};
