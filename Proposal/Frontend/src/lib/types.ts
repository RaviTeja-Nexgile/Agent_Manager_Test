/**
 * TypeScript interfaces mirroring the CCFP backend Pydantic response schemas.
 * Field names match the FastAPI routes 1:1 (see Backend/app/features/*).
 */

// ─────────────── Enums (string unions matching native PG enums) ───────────────
export type CrashLifecyclePhase =
  | 'INITIAL_INCIDENT'
  | 'NOTIFICATION'
  | 'DATA_COLLECTION'
  | 'DATA_MAPPING'
  | 'QUALITY_CONTROL'
  | 'ANALYSIS'
  | 'PUBLICATION';
export type CrashScope = 'IN_SCOPE' | 'OUT_OF_SCOPE' | 'UNDETERMINED';
export type FormStatus = 'DRAFT' | 'SUBMITTED' | 'ROUTED' | 'DELETED';
export type PersonType = 'DRIVER' | 'OCCUPANT' | 'NON_MOTORIST' | 'WITNESS';
export type InjuryStatus = 'FATAL' | 'INJURY' | 'NO_INJURY' | 'UNKNOWN';
export type MappingStatus = 'PENDING' | 'MAPPED' | 'REVIEWED';
export type CodingStatus = 'PENDING' | 'IN_PROGRESS' | 'CODED';
// PARSED_WITH_ERRORS (BRD Appendix E): events WERE extracted and at least one
// ERROR-severity problem was recorded. Deliberately distinct from PARSED — see
// the file's issue list for what went wrong.
export type EldUploadStatus =
  | 'UPLOADED' | 'PARSING' | 'PARSED' | 'PARSED_WITH_ERRORS' | 'FAILED';
// PCI-7: ELD duty-status values (align with backend app.enums.DutyStatus).
export type DutyStatus = 'OFF_DUTY' | 'SLEEPER_BERTH' | 'DRIVING' | 'ON_DUTY_NOT_DRIVING';
export type QcResultStatus = 'PASS' | 'FAIL' | 'WARNING' | 'NOT_EVALUATED';
export type RuleSeverity = 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
export type CompletenessStatusValue = 'COMPLETE' | 'INCOMPLETE';
// MULTI_CODE is a capped multi-select (GAP-PCR-04); the cap itself lives in
// DataAttribute.max_selections so it stays configurable per study phase.
export type AttributeDataType = 'TEXT' | 'NUMBER' | 'DATE' | 'DATETIME' | 'BOOLEAN' | 'CODE' | 'JSON' | 'MULTI_CODE';
export type DataSensitivity = 'PUBLIC' | 'INTERNAL' | 'PII' | 'SENSITIVE' | 'CIPSEA';
export type DocumentTypeValue =
  | 'DOCUMENT' | 'IMAGE' | 'VIDEO' | 'PDF' | 'ELD_CSV' | 'SPREADSHEET' | 'REPORT' | 'OTHER';
export type ReportTypeValue = 'DASHBOARD' | 'REPORT' | 'TABLE' | 'VISUALIZATION';
// The Jan-2026 BRD separates FMCSA Federal Users from Other Federal
// Users (BTS, NHTSA, NTSB). FEDERAL is retained and means "both federal tiers",
// which is what every report created before the split already meant.
export type ReportVisibility =
  | 'PRIVATE' | 'ORGANIZATION' | 'FEDERAL' | 'FMCSA_FEDERAL' | 'OTHER_FEDERAL' | 'STATE' | 'PUBLIC';
/** Audience tier a report share releases to. Only the CCFP Database
 *  Administrator may target OTHER_FEDERAL, STATE or PUBLIC. */
export type ShareAudience = 'FMCSA_FEDERAL' | 'OTHER_FEDERAL' | 'STATE' | 'PUBLIC';
export type StudyStatus = 'PLANNING' | 'ACTIVE' | 'CLOSED' | 'PUBLISHED';
export type OrganizationType =
  // NTSB is named as an Other Federal consumer.
  | 'FMCSA' | 'BTS' | 'STATE_AGENCY' | 'VOLPE' | 'NHTSA' | 'NTSB' | 'FHWA' | 'NOAA' | 'AAMVA' | 'EXTERNAL' | 'OTHER';
export type NotificationStatusValue = 'PENDING' | 'SENT' | 'DELIVERED' | 'READ' | 'FAILED';

// ─────────────── Pagination ───────────────
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ─────────────── Auth ───────────────
export interface UserSummary {
  id: string;
  email: string;
  full_name: string;
  title?: string | null;
  organization_id?: string | null;
}
export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
  user: UserSummary;
}
export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  organization_id: string | null;
  roles: string[];
  permissions: string[];
  allowed_states: string[] | null;
  study_ids: string[];
  // AUTH-1: org scope (null == unrestricted by organization, mirrors allowed_states).
  org_ids: string[] | null;
  // AUTH-2: true when the principal is confined to study_ids (vs. unrestricted).
  study_restricted: boolean;
  // AUTH-3: sorted list of access-group codes the caller belongs to (e.g. "PII",
  // "NOPII", "CIPSEA", "PUBLIC"). The frontend derives PII visibility from
  // membership in the "PII" group instead of re-listing permission codes.
  access_groups: string[];
}

// AUTH-8: role/access groupings + PII sensitivity metadata served by
// GET /auth/groupings, so the frontend derives groupings from the API instead
// of hardcoding STATE/FEDERAL/CIPSEA/ADMIN arrays or the PII-code list.
export interface Groupings {
  role_groups: Record<string, string[]>;
  pii_permission_codes: string[];
  cipsea_permission_code: string;
}

// ─────────────── Admin ───────────────
export interface Organization {
  id: string;
  name: string;
  org_type: OrganizationType;
  state_code: string | null;
  parent_id: string | null;
  description: string | null;
  is_active: boolean;
}
export interface User {
  id: string;
  email: string;
  full_name: string;
  organization_id: string | null;
  title: string | null;
  phone: string | null;
  status: string;
  mfa_enabled: boolean;
  piv_cac_required: boolean;
}
export interface Permission {
  id: string;
  code: string;
  name: string;
  category: string;
  description: string | null;
}
export interface Role {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
}
export interface RoleDetail extends Role {
  permissions: Permission[];
}
export interface Assignment {
  id: string;
  role_id: string;
  scope_type: string;
  state_code: string | null;
  organization_id: string | null;
  study_id: string | null;
}

// ─────────────── Studies & config ───────────────
export interface Study {
  id: string;
  code: string;
  name: string;
  phase_number: number;
  vehicle_type: string;
  crash_severity: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  pilot_start_date: string | null;
  status: StudyStatus;
  // Publication settings (STUD-5, §8.1 / §5 Phase 7)
  deidentification_policy: 'STANDARD' | 'STRICT' | 'NONE';
  public_scope: 'NONE' | 'AGGREGATE_ONLY' | 'DEIDENTIFIED_RECORDS';
  publication_enabled: boolean;
  publication_notes: string | null;
}
export interface StudyState {
  id: string;
  study_id: string;
  state_code: string;
  is_participating: boolean;
  agreement_status: string;
  onboarded_at: string | null;
  notes: string | null;
}
export interface StudyParameter {
  id: string;
  study_id: string;
  param_key: string;
  param_value: unknown;
  description: string | null;
}
export interface DataAttribute {
  id: string;
  code: string;
  name: string;
  category: string;
  pcr_section: string | null;
  data_type: AttributeDataType;
  sensitivity: DataSensitivity;
  description: string | null;
  is_active: boolean;
  /**
   * Repeat / cardinality / supersession metadata (GAP-PCR-02, -03, -04).
   * `max_selections` is the cap the HDTS PCR form states ("Check up to 3");
   * `superseded_by_code` names the replacement for a retired attribute.
   */
  repeats_on: RepeatUnit | null;
  max_selections: number | null;
  applies_to: string | null;
  superseded_by_code: string | null;
}
/**
 * One PCR form section (GAP-PCR-01). `name` is the label as written on the HDTS
 * PCR data form; `code` is the stable internal join key used by
 * `DataAttribute.pcr_section` and coverage rows. `is_active` is false for a
 * section retired by a later specification (e.g. DYNAMIC).
 */
export interface PcrSection {
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
}
/**
 * One enumerated value for an attribute (GAP-PCR-09b). A value retired by a
 * later specification is kept and flagged rather than dropped, so data
 * collected under the previous form still resolves to a label.
 */
/** One plottable crash position (GAP-BRD-11). */
export interface GeoCrashPoint {
  id: string;
  ccfp_identifier: string;
  latitude: number;
  longitude: number;
  state_code: string | null;
  num_fatalities: number | null;
  lifecycle_phase: CrashLifecyclePhase;
}
export interface GeoCrashesResponse {
  points: GeoCrashPoint[];
  /** Crashes in scope, so the UI can say when the map shows a subset. */
  total_in_scope: number;
  plotted: number;
  missing_coordinates: number;
}
export interface AttributeValueOption {
  code: string | null;
  label: string;
  sort_order: number;
  is_active: boolean;
  spec_version: string;
  superseded_by: string | null;
  notes: string | null;
}
/** One row of the CCFP PCR Data Dictionary (GAP-PCR-09, also GAP-SOO-10). */
export interface DataDictionaryEntry {
  code: string;
  form_section: string | null;
  form_label: string | null;
  mmucc_code: string | null;
  name: string;
  pcr_section: string | null;
  data_type: AttributeDataType;
  sensitivity: DataSensitivity;
  max_selections: number | null;
  repeats_on: RepeatUnit | null;
  applies_to: string | null;
  is_required: boolean;
  is_active: boolean;
  superseded_by_code: string | null;
  description: string | null;
  values: AttributeValueOption[];
}
export interface AttributeRequirement {
  attribute_id: string;
  code: string;
  name: string;
  category: string;
  pcr_section: string | null;
  data_type: AttributeDataType;
  sensitivity: DataSensitivity;
  is_required: boolean;
  is_optional: boolean;
  is_read_only: boolean;
  is_editable: boolean;
}
export interface CompletenessRule {
  id: string;
  study_id: string;
  name: string;
  description: string | null;
  definition: Record<string, unknown> | null;
  is_active: boolean;
}
export interface CompletenessTokenParam {
  name: string;
  default: number;
}
export interface CompletenessTokenSpec {
  token: string;
  params: CompletenessTokenParam[];
}
export interface CompletenessTokenCatalog {
  tokens: CompletenessTokenSpec[];
}
export interface PcrCoverage {
  pcr_section_code: string;
  state_code: string;
  required_collected: number;
  total_required: number;
  /**
   * The optional tier is not reported (GAP-PCR-05): the HDTS PCR data form
   * defines no optional attributes, so these always come back as 0. Retained
   * because a future study phase may reintroduce the tier.
   */
  optional_collected: number;
  total_optional: number;
  completion_pct: number | null;
  /** Which PCR specification the reported counts belong to. Percentages are not
   * comparable across versions — the denominators changed. */
  spec_version: string | null;
}

// ─────────────── Crash ───────────────
export interface Crash {
  id: string;
  ccfp_identifier: string;
  study_id: string;
  local_report_number: string | null;
  crash_date: string | null;
  crash_time: string | null;
  city: string | null;
  county: string | null;
  state_code: string | null;
  street_highway: string | null;
  latitude: number | null;
  longitude: number | null;
  num_vehicles: number | null;
  num_persons: number | null;
  num_fatalities: number | null;
  lifecycle_phase: CrashLifecyclePhase;
  created_by: string | null;
  created_at: string;
}
export interface ScopeClassification {
  id: string;
  crash_id: string;
  is_qualifying: boolean;
  scope: CrashScope;
  is_supplemental: boolean;
  classification_reason: string | null;
  /** True when a person set this value; the system then stops re-deriving it
   *  automatically until someone explicitly re-runs the classification. */
  is_manual_override: boolean;
}
export interface AttributeValue {
  attribute_id: string;
  code: string;
  name: string;
  pcr_section: string | null;
  sensitivity: DataSensitivity;
  value_text: string | null;
  value_json: unknown;
  source_system: string | null;
  confidence: number | null;
  is_edited: boolean;
  source_record_id: string | null;
  redacted: boolean;
  /**
   * Repeat discriminator (GAP-PCR-03). Null on a crash-level attribute; set to
   * the unit this value belongs to (TRAILER 2, VEHICLE 3) when the attribute
   * repeats. `repeats_on`/`max_selections`/`applies_to` describe the attribute
   * itself so the table can group and label without a second request.
   */
  unit_type: RepeatUnit | null;
  unit_number: number | null;
  repeats_on: RepeatUnit | null;
  max_selections: number | null;
  applies_to: string | null;
}
export type RepeatUnit = 'VEHICLE' | 'PERSON' | 'TRAILER' | 'NON_MOTORIST';
export interface AttributeHistoryEntry {
  value_id: string;
  value_text: string | null;
  value_json: unknown;
  source_system: string | null;
  confidence: number | null;
  is_current: boolean;
  is_edited: boolean;
  edited_by: string | null;
  edited_by_name: string | null;
  edited_at: string | null;
  created_at: string;
  redacted: boolean;
  unit_type: RepeatUnit | null;
  unit_number: number | null;
}
export interface AttributeHistoryResponse {
  attribute_id: string;
  code: string;
  name: string;
  pcr_section: string | null;
  sensitivity: DataSensitivity;
  versions: AttributeHistoryEntry[];
  repeats_on: RepeatUnit | null;
}

// ─────────────── CCFP Aggregated Data ───────────────
// The Jan-2026 BRD defines "CCFP Aggregated Data" as linked CCFP crash data
// PLUS data from external systems related to a specific crash. The linkage is a
// CCFP Database Administrator duty, gated on `aggregated:link`.
export type LinkMethod = 'MANUAL' | 'AUTO' | 'RULE';

/** One Appendix D external data source. */
export interface ExternalSystem {
  code: string;
  name: string;
  owner: string | null;
  is_fmcsa_owned: boolean;
  relevant_data: string | null;
  is_active: boolean;
}

export interface CrashExternalLink {
  id: string;
  crash_id: string;
  source_system: string;
  source_system_name: string | null;
  external_ref: string;
  link_method: LinkMethod;
  matched_on: Record<string, unknown> | null;
  confidence: number | null;
  notes: string | null;
  linked_by: string | null;
  linked_by_name: string | null;
  linked_at: string;
  is_current: boolean;
}

export interface AggregatedSummary {
  current_attribute_count: number;
  required_attribute_count: number;
  required_present: number;
  required_missing: number;
  source_record_count: number;
  external_link_count: number;
}

export interface AggregatedData {
  crash_id: string;
  ccfp_identifier: string | null;
  study_id: string | null;
  summary: AggregatedSummary;
  // Retained at the top level for callers written against the counts-only
  // counts-only response this endpoint used to return.
  current_attribute_count: number;
  required_attribute_count: number;
  required_present: number;
  required_missing: number;
  attributes: AttributeValue[];
  source_records: SourceRecord[];
  external_links: CrashExternalLink[];
}
export interface QcResult {
  rule_code: string;
  rule_name: string;
  severity: RuleSeverity;
  status: QcResultStatus;
  message: string | null;
  evaluated_at: string;
}
export interface Completeness {
  status: CompletenessStatusValue;
  is_locked: boolean;
  missing_summary: { missing?: Array<{ rule?: string; unmet?: string } | string> } | null;
  changed_at: string;
}
/** QC & Completeness gate for a lifecycle transition (DL5, DL6).
 *  `blocked` means the advance will be refused with 409; `blockers` names each
 *  unmet completeness rule so the UI can say why rather than just disabling. */
export interface PhaseGate {
  target_phase: CrashLifecyclePhase | null;
  is_gated: boolean;
  blocked: boolean;
  blockers: string[];
}
export interface TimelineEntry {
  action: string;
  entity_type: string;
  actor_user_id: string | null;
  occurred_at: string;
  after_state: Record<string, unknown> | null;
  phase?: string | null;
  is_milestone?: boolean;
}
export interface SourceRecord {
  id: string;
  source_system: string;
  source_type: string;
  external_id: string | null;
  raw_zone_uri: string | null;
  provenance_note: string | null;
  received_at: string;
}

// ─────────────── Initial Incident Form ───────────────
export interface InitialIncidentForm {
  id: string;
  crash_id: string;
  status: FormStatus;
  event_summary: string | null;
  dot_number_validated: boolean;
  dot_validation_source: string | null;
  submitted_at: string | null;
  routed_at: string | null;
}
export interface IncidentVehicle {
  id: string;
  crash_id: string;
  vehicle_number: number;
  is_cmv: boolean;
  /** FHWA vehicle class, e.g. '7' or '8'. Evaluated against the study's
   *  configured `vehicle_classes` when deciding whether the crash qualifies. */
  vehicle_class: string | null;
  /** Gross vehicle weight rating in pounds; checked against `min_gvwr_lbs`. */
  gvwr_lbs: number | null;
  us_dot_number: string | null;
  make: string | null;
  num_occupants: number | null;
  num_injured_occupants: number | null;
  carrier_name: string | null;
  carrier_phone: string | null;
  is_supplemental: boolean;
  /** Client-side only: entered offline and still queued in the outbox. */
  _pendingSync?: boolean;
  client_uuid?: string | null;
}
export interface IncidentPerson {
  id: string;
  crash_id: string;
  person_type: PersonType;
  related_vehicle_number: number | null;
  full_name: string | null;
  name_last: string | null;
  name_first: string | null;
  name_middle: string | null;
  is_minor: boolean | null;
  primary_language: string | null;
  address: string | null;
  phone_primary: string | null;
  phone_secondary: string | null;
  phone_type: string | null;
  phone_primary_type: string | null;
  phone_secondary_type: string | null;
  non_motorist_kind: string | null;
  injury: InjuryStatus | null;
  is_supplemental: boolean;
  pii_redacted: boolean;
  /** Client-side only: entered offline and still queued in the outbox. Never
   *  returned by the API — set when a queued record is merged into a list. */
  _pendingSync?: boolean;
  /** Offline-sync idempotency key. Present on records created by the offline
   *  client; null for records created online. */
  client_uuid?: string | null;
}
export interface IIFSubmitResult {
  status: FormStatus;
  dot_number_validated: boolean;
  notified_users: number;
  routed_to_bts: boolean;
  /** An out-of-scope or supplemental crash: retained by the CCFP Project Team,
   *  not routed for a CIPSEA interview. */
  routed_out_of_scope?: boolean;
  /** The crash could not be classified (a required fact is still missing), so
   *  neither routing branch applied and the Project Team was asked to complete
   *  it. Surfaced so "reached nobody" never reads as "routed correctly". */
  routed_unclassified?: boolean;
}

// ─────────────── Source data ───────────────
export interface PostCrashInspection {
  id: string;
  crash_id: string;
  source_system: string;
  inspection_number: string | null;
  inspection_date: string | null;
  inspector_name: string | null;
  violations_count: number | null;
  defects_count: number | null;
  details: Record<string, unknown> | null;
  // PCI-6: derived §8.3 7-day upload-window SLA (visibility only)
  days_to_upload: number | null;
  is_overdue: boolean;
}
// PCI-1/4/5 (§8.4, §19.2 Appendix B): the post-crash investigation is the full
// field inventory, modeled as typed child sections/arrays. Every section/array
// item field is optional (the form marks most fields optional and per-field
// required/optional is study-configured via PCI-3). Numeric/Decimal columns
// serialize as JSON numbers; dates as 'YYYY-MM-DD'; datetimes as ISO strings.
export interface CarrierPowerUnitData {
  work_zone: boolean | null; work_zone_type: string | null; preclearance_bypass_serial: string | null;
  fire: boolean | null; fire_pre_crash: boolean | null; fire_post_crash: boolean | null;
  carrier_name_displayed: string | null; us_dot_displayed: boolean | null; nsc_number: string | null;
  motor_carrier_name: string | null; motor_carrier_address: string | null; motor_carrier_phone: string | null;
  owner_name: string | null; owner_address: string | null; lease_indicator: boolean | null;
  year: number | null; make: string | null; model: string | null; company_unit_number: string | null;
  manufacture_date: string | null; vin: string | null; color: string | null;
  license_plate: string | null; license_plate_state: string | null;
  registered_gross_weight: number | null; gvwr: number | null; annual_inspection: boolean | null;
  axles_up: number | null; axles_down: number | null; remarks: string | null;
}
export interface DriverLoadData {
  driver_name: string | null; driver_present: boolean | null; driver_address: string | null;
  license_state: string | null; license_province: string | null; license_number: string | null;
  license_class: string | null; license_endorsements: string | null; license_restrictions: string | null;
  license_issue_date: string | null; license_expiration_date: string | null;
  lenses_required: boolean | null; lenses_worn: boolean | null;
  shipper: string | null; bill_of_lading: string | null; manifest_load_weight: number | null;
  cargo_loaded: string | null; cargo_destination: string | null; load_securement: boolean | null;
  securement_contributed: boolean | null; securement_proper_use: boolean | null;
  securement_exceeded_wll: boolean | null; securement_type: string | null; remarks: string | null;
}
export interface MedicalCertificateData {
  examination_date: string | null; expiration_date: string | null; lenses: boolean | null;
  hearing_aid: boolean | null; waiver: boolean | null; medic_alert: boolean | null;
  cert_state: string | null; cert_province: string | null; remarks: string | null;
}
export interface HoursOfServiceData {
  on_duty_not_driving_hours: number | null; driving_hours: number | null; total_on_duty_hours: number | null;
  miles_driven: number | null; kilometers_driven: number | null; record_of_duty_status: boolean | null;
  timecard: boolean | null; violations: string | null; onboard_computer_eld: boolean | null;
  eld_present: boolean | null; co_driver: boolean | null; last_8_days_present: boolean | null;
  approved_eld: boolean | null; driver_history: string | null; road_familiarity: string | null;
  years_experience: number | null; previous_cmv_crashes: number | null; purpose_of_trip: string | null;
  trip_destination: string | null; driver_condition_remarks: string | null;
}
export interface ExemptionsData {
  exemption_14_hour: boolean | null; exemption_11_hour: boolean | null; exemption_split_sleeper: boolean | null;
  exemption_60_70_hour: boolean | null; exemption_34_hour_restart: boolean | null; exemption_federal: boolean | null;
  exemption_state: boolean | null; exemption_oilfield: boolean | null; exemption_agricultural: boolean | null;
  exemption_150_air_mile: boolean | null; exemption_temporary: boolean | null; docket_or_state_number: string | null;
  emergency_declaration: boolean | null; emergency_jurisdiction: string | null; emergency_federal_number: string | null;
  emergency_state_number: string | null; service_center: string | null; other_description: string | null;
}
export interface VehicleConditionData {
  compartment_condition: string | null; drivers_view: string | null; wipers: string | null;
  wiper_switch_position: string | null; heater_defroster: string | null; mirrors: string | null;
  rearward_camera: boolean | null; fender_mirrors: boolean | null; odometer: number | null;
  engine_hours: number | null; engine_manufacturer: string | null; fuel_type: string | null;
  ecm_serial: string | null; adas: string | null; steering_type: string | null;
  steering_wheel_diameter: number | null; steering_lash: string | null; steering_checked_running: boolean | null;
  transmission_type: string | null; transmission_model: string | null; transmission_serial: string | null;
  transmission_gear_position: string | null; transmission_forward_gears: number | null;
  drive_line_notes: string | null; drive_axle_ratio: string | null; radio: boolean | null; cb: boolean | null;
  dash_camera: boolean | null; audio_technology: boolean | null; headphones: boolean | null;
  bluetooth: boolean | null; remarks: string | null;
}
export interface BrakeSystemData {
  brake_type: string | null; abs_type: string | null; engine_brake_type: string | null;
  engine_brake_position: string | null; air_leaks: boolean | null; application_loss: boolean | null;
  low_air_vacuum_warning: boolean | null; low_air_vacuum_warning_psi: number | null;
  hydraulic_master_cylinder_secure: boolean | null; hydraulic_fluid_level: string | null;
  hydraulic_fluid_seepage: boolean | null; hydraulic_line_condition: string | null;
  electric_controller_mfr: string | null; electric_gain_setting: string | null;
  electric_breakaway_device: boolean | null; electric_battery_wiring: string | null;
  surge_breakaway_device: boolean | null; surge_fluid_leak: boolean | null; power_assist: boolean | null;
  parking_brake: boolean | null; wheel_end_weight_note: string | null; remarks: string | null;
}
export interface SeatingPositionData {
  // Index signature lets these section rows flow through the form's generic
  // Record<string, unknown> row helpers without per-call casts (PCI-2).
  [key: string]: unknown;
  position: string | null; seat_belt_equipped: boolean | null; seat_belt_used: boolean | null;
  seat_belt_condition: string | null; airbag_equipped: boolean | null; airbag_deployed: boolean | null;
  remarks: string | null;
}
export interface AxleData {
  [key: string]: unknown;
  axle_index: number | null; abs: boolean | null; slack_adjuster_type: string | null;
  slack_adjuster_length: number | null; push_rod_stroke_available: number | null;
  push_rod_stroke_applied: number | null; air_pressure: string | null; chamber_type: string | null;
  drum_rotor: string | null; brake_friction_code: string | null; rolling_radius: number | null;
  wheel_end_weight: number | null; total_end_weight: number | null; remarks: string | null;
}
export interface TireData {
  [key: string]: unknown;
  axle_index: number | null; side: string | null; inner_outer: string | null; size: string | null;
  make: string | null; model_design: string | null; tin_dot: string | null; rated_psi: number | null;
  rated_weight: number | null; inspection_psi: number | null; retread_tin_dot: string | null;
  repair: boolean | null; repair_location: string | null; speed_rating: string | null;
  tread_depth: number | null; wheel_hub_remarks: string | null;
}
export interface TrailerData {
  [key: string]: unknown;
  trailer_index: number | null; owner_name: string | null; owner_address: string | null;
  trailer_type: string | null; intermodal_indicator: boolean | null; unit_number: string | null;
  year: number | null; make: string | null; model: string | null; vin: string | null; color: string | null;
  license_plate: string | null; expiration: string | null; registered_gross_weight: number | null;
  gvwr: number | null; axle_weight_rating: number | null; annual_inspection: boolean | null;
  axles_up: number | null; axles_down: number | null; converter_dolly: boolean | null;
  converter_dolly_details: string | null; remarks: string | null;
}
export interface HazmatData {
  [key: string]: unknown;
  unit_scope: string | null; hazmat_present: boolean | null; hazmat_type: string | null;
  placards: string | null; spill: boolean | null; leak: boolean | null; remarks: string | null;
}
export interface AdditionalTowedUnitData {
  [key: string]: unknown;
  towed_index: number | null; owner_name: string | null; owner_address: string | null; unit_type: string | null;
  unit_number: string | null; vin: string | null; front_clearance: string | null; rear_clearance: string | null;
  side_marker_left: string | null; side_marker_right: string | null; turn_signals: string | null;
  stop_lamps: string | null; id_lamps: string | null; tail_lamps: string | null; reflectors: string | null;
  conspicuity_tape: string | null; distance_from_rear: number | null; rear_protection_from_rear: number | null;
  rear_protection_from_ground: number | null; rear_protection_from_side: number | null;
  rear_protection_width: number | null; remarks: string | null;
}
export interface PostCrashInvestigation {
  id: string;
  crash_id: string;
  case_number: string | null;
  inspection_number: string | null;
  officer_name: string | null;
  officer_id: string | null;
  post_crash_date: string | null;
  status: FormStatus;
  // DEPRECATED legacy untyped blob, still echoed for back-compat (PCI-1).
  sections: Record<string, unknown> | null;
  has_hazmat: boolean;
  has_additional_towed_units: boolean;
  carrier_power_unit: CarrierPowerUnitData | null;
  driver_load: DriverLoadData | null;
  medical_certificate: MedicalCertificateData | null;
  hours_of_service: HoursOfServiceData | null;
  exemptions: ExemptionsData | null;
  vehicle_condition: VehicleConditionData | null;
  brake_system: BrakeSystemData | null;
  seating_positions: SeatingPositionData[];
  axles: AxleData[];
  tires: TireData[];
  trailers: TrailerData[];
  hazmat: HazmatData[];
  additional_towed_units: AdditionalTowedUnitData[];
}
// PATCH/POST request body (InvestigationIn). All section/header fields optional;
// repeating + conditional arrays are replace-on-write (send the full list).
// Conditional arrays persist only when their presence flag is true.
export interface InvestigationWrite {
  case_number?: string | null;
  inspection_number?: string | null;
  officer_name?: string | null;
  officer_id?: string | null;
  post_crash_date?: string | null;
  sections?: Record<string, unknown> | null;
  has_hazmat?: boolean;
  has_additional_towed_units?: boolean;
  carrier_power_unit?: Partial<CarrierPowerUnitData> | null;
  driver_load?: Partial<DriverLoadData> | null;
  medical_certificate?: Partial<MedicalCertificateData> | null;
  hours_of_service?: Partial<HoursOfServiceData> | null;
  exemptions?: Partial<ExemptionsData> | null;
  vehicle_condition?: Partial<VehicleConditionData> | null;
  brake_system?: Partial<BrakeSystemData> | null;
  seating_positions?: Partial<SeatingPositionData>[];
  axles?: Partial<AxleData>[];
  tires?: Partial<TireData>[];
  trailers?: Partial<TrailerData>[];
  hazmat?: Partial<HazmatData>[];
  additional_towed_units?: Partial<AdditionalTowedUnitData>[];
}
// PCI-3: one per-study PCI form-field definition (§19.2). `field_code` matches a
// structured field key on the sections above; `is_required` drives the required
// marker the form renders and submit-validation enforces server-side.
export interface PciFieldDefinition {
  id: string;
  study_id: string;
  section_code: string;
  field_code: string;
  label: string | null;
  is_required: boolean;
  is_optional: boolean;
  display_order: number | null;
}
export interface PoliceCrashReport {
  id: string;
  crash_id: string;
  state_code: string | null;
  source_repository: string | null;
  ingestion_path: string;
  pcr_number: string | null;
  report_date: string | null;
  mapping_status: MappingStatus;
}
export interface ReconstructionReport {
  id: string;
  crash_id: string;
  title: string | null;
  received_date: string | null;
  document_id: string | null;
  coding_status: CodingStatus;
  coded_findings: Record<string, unknown> | null;
}
export interface EldFile {
  id: string;
  crash_id: string;
  file_name: string;
  document_id: string | null;
  ccfp_code_in_file: string | null;
  provider: string | null;
  model: string | null;
  version: string | null;
  upload_status: EldUploadStatus;
  event_count: number | null;
  parsed_at: string | null;
  // PCI-7 (§19.2): editable ELD summary / download-status detail.
  eld_downloaded: boolean | null;
  last_entry_at: string | null;
  last_duty_status: DutyStatus | string | null;
  last_stop_arrived_at: string | null;
  last_stop_departed_at: string | null;
  // BRD Appendix E: parse outcome. error_code is stable and machine-readable;
  // error_message is written for the uploader and names the fix.
  error_code: string | null;
  error_message: string | null;
  file_format: string | null;
  encoding: string | null;
  delimiter: string | null;
  file_size_bytes: number | null;
  line_count: number | null;
  row_count: number | null;
  error_count: number;
  warning_count: number;
  parse_duration_ms: number | null;
  parse_attempts: number;
  // Extracted ELD file header segment (49 CFR 395 Appendix A).
  driver_name: string | null;
  driver_license_number: string | null;
  driver_license_state: string | null;
  co_driver_name: string | null;
  carrier_name: string | null;
  carrier_usdot: string | null;
  vin: string | null;
  power_unit_number: string | null;
  trailer_numbers: string | null;
  time_zone_offset: string | null;
  eld_registration_id: string | null;
  eld_identifier: string | null;
  output_file_comment: string | null;
  file_data_check_value: string | null;
  sections: Record<string, number> | null;
  hos_summary: EldHosSummary | null;
}

// Derived hours-of-service roll-up (BRD Appendix E "so the data can be analyzed").
export interface EldHosSummary {
  event_count?: number;
  timed_event_count?: number;
  events_by_type?: Record<string, number>;
  events_by_section?: Record<string, number>;
  duty_hours?: Record<string, number>;
  total_driving_hours?: number;
  total_on_duty_hours?: number;
  duty_status_changes?: number;
  inactive_records?: number;
  malfunction_events?: number;
  unidentified_driver_records?: number;
  personal_conveyance_events?: number;
  yard_move_events?: number;
  distinct_days?: number;
  first_event_at?: string | null;
  last_event_at?: string | null;
  last_duty_status?: string;
  accumulated_miles_span?: number;
  engine_hours_span?: number;
  parse_duration_ms?: number;
}

export type EldIssueSeverity = 'ERROR' | 'WARNING' | 'INFO';

// One aggregated parse problem. `occurrences` + details.sample_lines mean a file
// with a systematically bad column yields ONE issue, not one per row.
export interface EldParseIssue {
  id: string;
  severity: EldIssueSeverity;
  code: string;
  message: string;
  section: string | null;
  line_number: number | null;
  column_name: string | null;
  raw_value: string | null;
  occurrences: number;
  details: { sample_lines?: number[]; sample_values?: string[] } | null;
}

// Dry-run validation result (POST /crashes/{id}/eld-files/validate).
export interface EldValidation {
  ok: boolean;
  file_name: string | null;
  file_format: string | null;
  encoding: string | null;
  delimiter: string | null;
  file_size_bytes: number;
  line_count: number;
  row_count: number;
  event_count: number;
  ccfp_code_in_file: string | null;
  ccfp_code_matches_crash: boolean;
  error_code: string | null;
  error_message: string | null;
  error_count: number;
  warning_count: number;
  sections: Record<string, number> | null;
  header: Record<string, unknown> | null;
  hos_summary: EldHosSummary | null;
  issues: Omit<EldParseIssue, 'id'>[];
}
export interface EldEvent {
  id: string;
  event_sequence: number;
  event_timestamp: string | null;
  duty: string | null;
  event_type: string | null;
  location: string | null;
  miles_driven: number | null;
  engine_hours: number | null;
  ignition_status: string | null;
  // ELD-standard event detail (49 CFR 395 Appendix A). record_status matters for
  // reading the log: an INACTIVE_* record was edited out by the driver and is
  // excluded from the duty totals, so the UI dims it rather than showing it as
  // a live duty period.
  section: string | null;
  line_number: number | null;
  event_type_code: number | null;
  event_code: number | null;
  record_status: string | null;
  record_origin: string | null;
  latitude: number | null;
  longitude: number | null;
  distance_since_last_coords: number | null;
  malfunction_indicator: string | null;
  diagnostic_indicator: string | null;
  annotation: string | null;
  driver_identifier: string | null;
  cmv_identifier: string | null;
  data_check_value: string | null;
  is_duplicate: boolean;
}

// ─────────────── QC / completeness / factors ───────────────
export interface QcRule {
  id: string;
  code: string;
  name: string;
  rule_type: string;
  severity: RuleSeverity;
  attribute_id: string | null;
  definition: Record<string, unknown> | null;
  is_active: boolean;
}
export interface ContributingFactor {
  id: string;
  crash_id: string;
  factor_group_id: string | null;
  factor_value: string;
  rank: number;
}
export interface FactorGroup {
  id: string;
  code: string;
  name: string;
  applies_to: string;
}
export interface FactorValue {
  id: string;
  factor_group_id: string;
  code: string | null;
  label: string;
}

/**
 * BRD DL4: the summary of data attributes collected in the PCR sections that
 * inform the top-three contributing-factor ranking. `redacted` mirrors the
 * Attributes tab — the value is nulled when the caller may not see that
 * sensitivity level.
 */
export interface FactorSummaryValue {
  attribute_id: string;
  code: string;
  name: string;
  value_text: string | null;
  value_json: unknown | null;
  sensitivity: DataSensitivity;
  redacted: boolean;
  unit_type: string | null;
  unit_number: number | null;
}
export interface FactorSummarySection {
  code: string;
  name: string;
  /** Attributes carrying a current value, out of the section's active catalogue. */
  collected: number;
  total: number;
  values: FactorSummaryValue[];
}
export interface FactorSummary {
  crash_id: string;
  sections: FactorSummarySection[];
  collected: number;
}
export interface QcEvalResult {
  crash_id: string;
  summary: Record<string, number>;
  results: { rule: string; status: string; message: string }[];
}
/** One unmet completeness requirement: the rule that failed and its token. */
export interface CompletenessMissingItem {
  rule: string;
  unmet: string;
  /** Set when the rule names a token the evaluator cannot resolve (a rule
   *  misconfiguration, not a genuine data gap). */
  unknown_token?: boolean;
}

export interface CompletenessEvalResult {
  crash_id: string;
  status: CompletenessStatusValue;
  checks: Record<string, boolean>;
  missing: CompletenessMissingItem[];
}

// ─────────────── Documents / reports / notifications / audit ───────────────
export interface CcfpDocument {
  id: string;
  crash_id: string | null;
  doc_type: DocumentTypeValue;
  file_name: string;
  mime_type: string | null;
  storage_uri: string;
  size_bytes: number | null;
  sensitivity: DataSensitivity;
  malware_scan: string;
  uploaded_at: string;
}
export interface Report {
  id: string;
  name: string;
  report_type: ReportTypeValue;
  study_id: string | null;
  description: string | null;
  definition: Record<string, unknown> | null;
  visibility: ReportVisibility;
  /** State a STATE-visibility report is bound to. null = not
   *  State-bound (visible to every State user). */
  state_code: string | null;
  is_published: boolean;
  is_deidentified: boolean;
  owner_id: string | null;
  published_at: string | null;
}
export interface PublicReport {
  id: string;
  name: string;
  report_type: ReportTypeValue;
  study_id: string | null;
  description: string | null;
  definition: Record<string, unknown> | null;
  published_at: string | null;
  // ANAL-9 open-data (Project Open Data) metadata; per-report value or program default.
  license: string | null;
  keywords: string[] | null;
  publisher: string | null;
  contact_name: string | null;
  contact_email: string | null;
  update_cadence: string | null;
}
export interface OpenDataDistribution {
  '@type'?: string;
  title?: string;
  downloadURL: string;
  mediaType?: string;
  format?: string;
}
export interface OpenDataDataset {
  '@type'?: string;
  identifier: string;
  title: string;
  description: string;
  keyword: string[];
  accessLevel: string;
  license: string;
  publisher: { '@type'?: string; name: string };
  contactPoint: { '@type'?: string; fn: string; hasEmail: string };
  accrualPeriodicity: string;
  modified?: string;
  distribution: OpenDataDistribution[];
}
export interface OpenDataCatalog {
  '@context'?: string;
  '@type'?: string;
  conformsTo: string;
  describedBy?: string;
  dataset: OpenDataDataset[];
}
export interface Notification {
  id: string;
  notification_type: string;
  crash_id: string | null;
  title: string;
  message: string | null;
  channel: string;
  status: NotificationStatusValue;
  created_at: string;
  read_at: string | null;
}
export interface AuditEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  crash_id: string | null;
  after_state: Record<string, unknown> | null;
  occurred_at: string;
}

// ─────────────── Analytics / integrations / search ───────────────
export interface QueryResult {
  query_name: string;
  columns: string[];
  rows: Record<string, unknown>[];
}
export interface IntegrationAdapter {
  name: string;
  live: boolean;
  mode: string;
  description: string;
}
export interface SearchHit {
  type: string;
  id: string;
  label: string;
  crash_id: string | null;
}
export interface SearchResults {
  query: string;
  hits: SearchHit[];
}
export interface DotValidationResult {
  dot_number: string | null;
  valid: boolean;
  source: string;
  carrier_name: string | null;
  status: string;
}

// ─────────────── CCFP Analysis Environment ───────────────
// Mirrors Backend/app/features/analysis_environment.py. The tier the Jan-2026
// BRD introduces: Aggregated Data is materialized into versioned datasets on a
// refresh cadence, then shared outward to four audiences with different PII
// rules.

export type RefreshCadence = 'HOURLY' | 'DAILY' | 'MANUAL';
export type AnalysisAudience =
  | 'FMCSA_FEDERAL'
  | 'OTHER_FEDERAL'
  | 'PARTICIPATING_STATE'
  | 'PUBLIC';
export type AnalysisPiiLevel = 'PII' | 'NO_PII' | 'DEIDENTIFIED_SUMMARY';

export interface AnalysisEnvironment {
  id: string;
  code: string;
  name: string;
  description: string | null;
  study_id: string | null;
  status: 'ACTIVE' | 'PAUSED' | 'ARCHIVED';
  refresh_cadence: RefreshCadence;
  last_refreshed_at: string | null;
  /** When the snapshot goes stale and the next page-open triggers a refresh. */
  next_refresh_due: string | null;
  created_at: string;
  updated_at: string;
  /** Derived server-side: the snapshot has aged past its cadence. */
  is_stale: boolean;
  /** Derived server-side from the refresh advisory lock: one is running now. */
  refresh_in_progress: boolean;
}

export interface AnalysisDatasetDefinition {
  dimensions: string[];
  measures: string[];
  filters: { column: string; op: string; value: string | number }[];
  study_id?: string;
}

export interface AnalysisDataset {
  id: string;
  environment_id: string;
  code: string;
  name: string;
  description: string | null;
  kind: 'AGGREGATED_SNAPSHOT' | 'DERIVED_VIEW';
  definition: AnalysisDatasetDefinition;
  pii_level: AnalysisPiiLevel;
  is_state_partitioned: boolean;
  status: 'ACTIVE' | 'ARCHIVED';
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  /** Version facts, so "is this stale?" needs no second request. */
  version_no: number | null;
  row_count: number | null;
  materialized_at: string | null;
  columns: string[];
}

export interface AnalysisRows {
  dataset_id: string;
  version_no: number | null;
  materialized_at: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
  /** True when the caller is seeing a State-filtered slice, not the whole set. */
  state_scoped: boolean;
}

export interface AnalysisHistogramBin {
  bin: number;
  lower: number;
  upper: number;
  count: number;
}

export interface AnalysisStatistics {
  dataset_id: string;
  column: string;
  version_no: number | null;
  materialized_at: string | null;
  n: number;
  mean: number | null;
  median: number | null;
  stddev: number | null;
  variance: number | null;
  minimum: number | null;
  maximum: number | null;
  p25: number | null;
  p75: number | null;
  iqr: number | null;
  total: number | null;
  histogram: AnalysisHistogramBin[];
}

export interface AnalysisShare {
  id: string;
  dataset_id: string;
  audience: AnalysisAudience;
  state_code: string | null;
  refresh_cadence: RefreshCadence;
  status: 'ACTIVE' | 'REVOKED';
  note: string | null;
  shared_at: string;
  revoked_at: string | null;
}

export interface AnalysisRefreshRun {
  id: string;
  environment_id: string;
  dataset_id: string | null;
  trigger: 'SCHEDULED' | 'MANUAL';
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  started_at: string;
  finished_at: string | null;
  datasets_refreshed: number;
  rows_written: number;
  message: string | null;
}

export interface AnalysisFields {
  dimensions: string[];
  measures: string[];
  filter_columns: string[];
  operators: string[];
  pii_levels: AnalysisPiiLevel[];
  audiences: AnalysisAudience[];
  cadences: RefreshCadence[];
}

export interface AnalysisRefreshResult {
  environment_id: string;
  run_id: string;
  status: string;
  datasets_refreshed: number;
  rows_written: number;
  message: string;
}

// ─────────────── Statistical analysis ───────────────
// Crash-level cohorts and the four BRD-named method families that run over
// them. Every result carries the cohort version it describes, so "as of when?"
// is answerable for a statistic exactly as it is for a dataset row.

export type CohortRole = 'CASE' | 'CONTROL' | 'GENERAL';
export type AnalysisMethod =
  | 'DESCRIPTIVE'
  | 'DISTRIBUTION'
  | 'THEMATIC'
  | 'RISK_MODEL'
  | 'COMPARATIVE'
  | 'TREND';
export type StatExportFormat = 'CSV' | 'PYTHON' | 'R' | 'SAS';

export interface CohortFilter {
  column: string;
  op: string;
  value: string | number | boolean | (string | number)[];
}

export interface CohortDefinition {
  filters: CohortFilter[];
  study_id?: string;
}

export interface AnalysisCohort {
  id: string;
  environment_id: string;
  code: string;
  name: string;
  description: string | null;
  cohort_role: CohortRole;
  definition: CohortDefinition;
  status: 'ACTIVE' | 'ARCHIVED';
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  /** Version facts, so a cohort card answers "how many, as of when?" directly. */
  version_no: number | null;
  member_count: number | null;
  materialized_at: string | null;
}

export interface CohortMember {
  crash_id: string | null;
  ccfp_identifier: string | null;
  state_code: string | null;
  county: string | null;
  crash_date: string | null;
  crash_year: number | null;
  crash_month: number | null;
  lifecycle_phase: string | null;
  num_fatalities: number | null;
  num_vehicles: number | null;
  num_persons: number | null;
  is_fatal: boolean;
  scope: string | null;
  is_qualifying: boolean | null;
  factors: string[];
}

export interface CohortMembers {
  cohort_id: string;
  version_no: number | null;
  materialized_at: string | null;
  member_count: number;
  returned: number;
  members: CohortMember[];
}

export interface AnalysisStatsFields {
  filter_columns: string[];
  filter_operators: string[];
  list_operators: string[];
  factor_columns: string[];
  boolean_columns: string[];
  numeric_variables: Record<string, string>;
  categorical_variables: Record<string, string>;
  trend_periods: string[];
  trend_measures: string[];
  cohort_roles: CohortRole[];
  methods: AnalysisMethod[];
  export_formats: StatExportFormat[];
}

/** Provenance stamped onto every statistical result. */
export interface ResultStamp {
  cohort_id?: string;
  cohort_code?: string;
  cohort_name?: string;
  cohort_role?: CohortRole;
  version_no?: number;
  materialized_at?: string;
  member_count?: number;
  /** Statistical-validity warnings. Part of the result, never decoration. */
  caveats: string[];
}

export interface DescriptiveResult extends ResultStamp {
  variable: string;
  label: string;
  n: number;
  n_missing: number;
  mean: number | null;
  median: number | null;
  mode: number | null;
  stddev: number | null;
  stddev_population: number | null;
  variance: number | null;
  minimum: number | null;
  maximum: number | null;
  range?: number;
  total: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  iqr?: number;
  coefficient_of_variation?: number;
  standard_error?: number;
  ci_lower?: number;
  ci_upper?: number;
  skewness?: number;
  kurtosis_excess?: number;
  confidence: number;
}

export interface DistributionEntry {
  category: string;
  frequency: number;
  percent: number;
  cumulative_percent: number;
}

export interface HistogramBin {
  bin: number;
  lower: number;
  upper: number;
  count: number;
}

export interface DistributionResult extends ResultStamp {
  variable: string;
  label: string;
  kind: 'CATEGORICAL' | 'NUMERIC';
  n: number;
  distinct_categories: number;
  entries: DistributionEntry[];
  histogram: HistogramBin[];
}

export interface ThemeEntry {
  factor: string;
  crashes: number;
  percent_of_cohort: number;
  percent_of_coded: number;
}

export interface CoOccurrenceEntry {
  factor_a: string;
  factor_b: string;
  crashes: number;
  percent_of_cohort: number;
  lift?: number | null;
  support_a?: number;
  support_b?: number;
}

export interface ThematicResult extends ResultStamp {
  n: number;
  n_with_factors: number;
  coded_percent: number;
  themes: ThemeEntry[];
  groups: { group: string; crashes: number; percent_of_cohort: number }[];
  co_occurrence: CoOccurrenceEntry[];
}

export interface CohortRef {
  id: string;
  code: string;
  name: string;
  version_no: number;
  materialized_at: string;
}

export interface RiskModelResult {
  exposure: string;
  confidence: number;
  table: {
    case_exposed: number;
    case_unexposed: number;
    control_exposed: number;
    control_unexposed: number;
    case_total: number;
    control_total: number;
  };
  case_exposure_rate?: number;
  control_exposure_rate?: number;
  /** False when the exposure is absent from (or universal in) both cohorts —
   *  no risk measure is reported in that case. */
  exposure_varies?: boolean;
  odds_ratio?: number;
  odds_ratio_ci_lower?: number;
  odds_ratio_ci_upper?: number;
  relative_risk?: number;
  relative_risk_ci_lower?: number;
  relative_risk_ci_upper?: number;
  risk_difference?: number;
  risk_difference_ci_lower?: number;
  risk_difference_ci_upper?: number;
  attributable_fraction_exposed?: number;
  min_expected_cell?: number;
  chi_square?: number;
  chi_square_p?: number;
  fisher_exact_p?: number | null;
  p_value?: number | null;
  test_used?: 'CHI_SQUARE_YATES' | 'FISHER_EXACT';
  significant?: boolean;
  case_cohort?: CohortRef;
  control_cohort?: CohortRef;
  caveats: string[];
  investigation?: { id: string; code: string; name: string; method: AnalysisMethod };
}

export interface ComparativeSide {
  id?: string;
  code?: string;
  name?: string;
  version_no?: number;
  materialized_at?: string;
  n: number;
  mean?: number | null;
  stddev?: number | null;
  median?: number | null;
  count?: number;
  proportion?: number | null;
}

export interface ComparativeResult {
  variable?: string;
  factor?: string;
  label?: string;
  confidence: number;
  cohort_a: ComparativeSide;
  cohort_b: ComparativeSide;
  mean_difference?: number;
  difference?: number;
  t_statistic?: number;
  z_statistic?: number;
  degrees_of_freedom?: number;
  p_value?: number;
  test_used?: 'WELCH_T' | 'TWO_PROPORTION_Z';
  significant?: boolean;
  difference_ci_lower?: number;
  difference_ci_upper?: number;
  cohens_d?: number;
  effect_size_magnitude?: string;
  caveats: string[];
  investigation?: { id: string; code: string; name: string; method: AnalysisMethod };
}

export interface TrendResult extends ResultStamp {
  period: string;
  measure: string;
  series: { period: number; value: number }[];
  n_periods: number;
  slope?: number;
  intercept?: number;
  direction?: 'increasing' | 'decreasing' | 'flat';
  change_per_period?: number;
  pearson_r?: number;
  r_squared?: number;
  t_statistic?: number;
  degrees_of_freedom?: number;
  p_value?: number;
  significant?: boolean;
}

export interface AnalysisInvestigation {
  id: string;
  environment_id: string;
  code: string;
  name: string;
  description: string | null;
  method: AnalysisMethod;
  parameters: Record<string, unknown>;
  visibility: 'PRIVATE' | 'TEAM';
  status: 'ACTIVE' | 'ARCHIVED';
  last_run_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Union of everything POST /analysis-investigations/{id}/run can return. */
export type InvestigationResult =
  | DescriptiveResult
  | DistributionResult
  | ThematicResult
  | RiskModelResult
  | ComparativeResult
  | TrendResult;
