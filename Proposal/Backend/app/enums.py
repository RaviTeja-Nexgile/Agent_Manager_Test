"""String enums matching the native PostgreSQL enum types in the schema.

Used by Pydantic schemas for request/response validation. Values must stay in
sync with migrations/0001_initial_schema.sql.
"""
from __future__ import annotations

from enum import Enum


class _Str(str, Enum):
    def __str__(self) -> str:  # render as the bare value
        return self.value


class OrganizationType(_Str):
    FMCSA = "FMCSA"; BTS = "BTS"; STATE_AGENCY = "STATE_AGENCY"; VOLPE = "VOLPE"
    NHTSA = "NHTSA"; FHWA = "FHWA"; NOAA = "NOAA"; AAMVA = "AAMVA"
    # The Jan-2026 BRD names NTSB as an Other Federal consumer
    # ("Share ... with Other Federal Users (BTS, NHTSA, NTSB)").
    NTSB = "NTSB"
    EXTERNAL = "EXTERNAL"; OTHER = "OTHER"


class UserStatus(_Str):
    ACTIVE = "ACTIVE"; INACTIVE = "INACTIVE"; SUSPENDED = "SUSPENDED"; PENDING = "PENDING"


class AssignmentScope(_Str):
    GLOBAL = "GLOBAL"; ORGANIZATION = "ORGANIZATION"; STATE = "STATE"; STUDY = "STUDY"


class StudyStatus(_Str):
    PLANNING = "PLANNING"; ACTIVE = "ACTIVE"; CLOSED = "CLOSED"; PUBLISHED = "PUBLISHED"


class DeidentificationPolicy(_Str):
    """Per-study de-identification policy (STUD-5, §8.1).

    The DB column stays plain ``TEXT`` (no native PG ENUM) to preserve per-study/
    phase configurability without a rebuild (§3.4/§11.1); this Python enum governs
    the vocabulary in code.
    """
    STANDARD = "STANDARD"; STRICT = "STRICT"; NONE = "NONE"


class PublicScope(_Str):
    """Scope of study data shared publicly (STUD-5, §5 Phase 7).

    Plain ``TEXT`` column; vocabulary governed here for configurability.
    """
    NONE = "NONE"; AGGREGATE_ONLY = "AGGREGATE_ONLY"; DEIDENTIFIED_RECORDS = "DEIDENTIFIED_RECORDS"


class CrashScope(_Str):
    IN_SCOPE = "IN_SCOPE"; OUT_OF_SCOPE = "OUT_OF_SCOPE"; UNDETERMINED = "UNDETERMINED"


class CrashLifecyclePhase(_Str):
    INITIAL_INCIDENT = "INITIAL_INCIDENT"; NOTIFICATION = "NOTIFICATION"
    DATA_COLLECTION = "DATA_COLLECTION"; DATA_MAPPING = "DATA_MAPPING"
    QUALITY_CONTROL = "QUALITY_CONTROL"; ANALYSIS = "ANALYSIS"; PUBLICATION = "PUBLICATION"


class FormStatus(_Str):
    DRAFT = "DRAFT"; SUBMITTED = "SUBMITTED"; ROUTED = "ROUTED"; DELETED = "DELETED"


class PersonType(_Str):
    DRIVER = "DRIVER"; OCCUPANT = "OCCUPANT"; NON_MOTORIST = "NON_MOTORIST"; WITNESS = "WITNESS"


class PhoneType(_Str):
    """Per-number phone type for an incident person (INIT-2, §19.1).

    Plain ``TEXT`` columns (``phone_primary_type`` / ``phone_secondary_type``);
    this enum governs the small fixed vocabulary in code.
    """
    HOME = "HOME"; CELL = "CELL"; WORK = "WORK"


class NonMotoristKind(_Str):
    """Occupant-vs-pedestrian discriminator for a non-motorist (INIT-3, §19.1).

    Plain ``TEXT`` column (``non_motorist_kind``); only meaningful when
    ``person_type == NON_MOTORIST``.
    """
    OCCUPANT = "OCCUPANT"; PEDESTRIAN = "PEDESTRIAN"


class InjuryStatus(_Str):
    FATAL = "FATAL"; INJURY = "INJURY"; NO_INJURY = "NO_INJURY"; UNKNOWN = "UNKNOWN"


class IngestionPath(_Str):
    """Structured PCR ingestion path (PCR-4, §8.5).

    Matches the native PG enum ``ingestion_path`` declared in
    migrations/0011_pcr_ingestion_path.sql.
    """
    MCMIS_ROUNDTRIP = "MCMIS_ROUNDTRIP"; DIRECT_STATE = "DIRECT_STATE"


class LinkMethod(_Str):
    """How a crash was linked to a record in an Appendix D external system
    (BRD Jan-2026 "CCFP Aggregated Data").

    Matches the native PG enum ``external_link_method`` declared in
    migrations/0023_crash_external_links.sql. MANUAL = a CCFP Database
    Administrator linked it by hand; AUTO = an integration adapter matched it;
    RULE = a deterministic matching rule produced it.
    """
    MANUAL = "MANUAL"; AUTO = "AUTO"; RULE = "RULE"


class MappingStatus(_Str):
    PENDING = "PENDING"; MAPPED = "MAPPED"; REVIEWED = "REVIEWED"


class CodingStatus(_Str):
    PENDING = "PENDING"; IN_PROGRESS = "IN_PROGRESS"; CODED = "CODED"


class EldUploadStatus(_Str):
    """Lifecycle of an uploaded ELD/eRODS output file (BRD Appendix E, §8.7).

    ``PARSED_WITH_ERRORS`` (migration 0030) is the honest middle state: events
    WERE extracted and are usable, and at least one ERROR-severity problem was
    recorded against the file (truncation at the row cap, a section that could
    not be interpreted, a time-budget overrun). Collapsing that into ``PARSED``
    is exactly the silent failure this status exists to prevent; the per-problem
    detail lives in ``eld_parse_issues``.
    """

    UPLOADED = "UPLOADED"; PARSING = "PARSING"; PARSED = "PARSED"
    PARSED_WITH_ERRORS = "PARSED_WITH_ERRORS"; FAILED = "FAILED"


class EldIssueSeverity(_Str):
    """Severity of one ``eld_parse_issues`` row.

    ERROR   — extraction was blocked or incomplete; the file needs attention.
    WARNING — a value or row could not be interpreted; the rest still extracted.
    INFO    — an interpretation worth recording (encoding fallback, positional
              header reading, positions the ELD itself could not capture).
    """

    ERROR = "ERROR"; WARNING = "WARNING"; INFO = "INFO"


class EldFileFormat(_Str):
    """How an uploaded ELD file was interpreted.

    ``FMCSA_ELD_OUTPUT`` is the sectioned output file defined by 49 CFR 395
    Appendix A to Subpart B — what a driver actually transfers to eRODS.
    ``FLAT_CSV`` is a single-header tabular export mapped through the
    configurable ``eld_field_mappings`` rows.
    """

    FMCSA_ELD_OUTPUT = "FMCSA_ELD_OUTPUT"; FLAT_CSV = "FLAT_CSV"; UNKNOWN = "UNKNOWN"


class DutyStatus(_Str):
    OFF_DUTY = "OFF_DUTY"; SLEEPER_BERTH = "SLEEPER_BERTH"
    DRIVING = "DRIVING"; ON_DUTY_NOT_DRIVING = "ON_DUTY_NOT_DRIVING"


class QcResultStatus(_Str):
    PASS = "PASS"; FAIL = "FAIL"; WARNING = "WARNING"; NOT_EVALUATED = "NOT_EVALUATED"


class RuleSeverity(_Str):
    INFO = "INFO"; WARNING = "WARNING"; ERROR = "ERROR"; CRITICAL = "CRITICAL"


class CompletenessStatus(_Str):
    COMPLETE = "COMPLETE"; INCOMPLETE = "INCOMPLETE"


class AttributeDataType(_Str):
    TEXT = "TEXT"; NUMBER = "NUMBER"; DATE = "DATE"; DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"; CODE = "CODE"; JSON = "JSON"
    # A capped multi-select (GAP-PCR-04): the new HDTS PCR form states caps on
    # 28 elements ("Check up to 3", "Check only 1"). The cap itself lives in
    # data_attributes.max_selections so it stays configurable per study phase;
    # the values are stored as a JSON list in crash_attribute_values.value_json.
    MULTI_CODE = "MULTI_CODE"


class DataSensitivity(_Str):
    PUBLIC = "PUBLIC"; INTERNAL = "INTERNAL"; PII = "PII"
    SENSITIVE = "SENSITIVE"; CIPSEA = "CIPSEA"


class RepeatUnit(_Str):
    """Units a PCR attribute may repeat on (GAP-PCR-03).

    Mirrors the ``ref_repeat_units`` reference table, which is the authority —
    this enum exists for readable call sites and request validation. Because the
    vocabulary is a table (not a PG enum), a future phase can add a unit in a
    seed; validation resolves against the table, so an added unit works without
    editing this class.
    """

    VEHICLE = "VEHICLE"; PERSON = "PERSON"
    TRAILER = "TRAILER"; NON_MOTORIST = "NON_MOTORIST"


class PersonPopulation(_Str):
    """Conditional Person populations on the new HDTS PCR form (GAP-PCR-03).

    The form scopes Person fields to different populations — a field collected
    for "All Drivers" is not collected for a passenger. Stored on
    ``data_attributes.applies_to``; NULL there means "every row of the unit".
    """

    ALL_PERSONS = "ALL_PERSONS"; ALL_OCCUPANTS = "ALL_OCCUPANTS"
    ALL_DRIVERS = "ALL_DRIVERS"; CMV_DRIVERS = "CMV_DRIVERS"
    DRIVERS_AND_NON_MOTORISTS = "DRIVERS_AND_NON_MOTORISTS"
    ALL_INJURED = "ALL_INJURED"


class DocumentType(_Str):
    DOCUMENT = "DOCUMENT"; IMAGE = "IMAGE"; VIDEO = "VIDEO"; PDF = "PDF"
    ELD_CSV = "ELD_CSV"; SPREADSHEET = "SPREADSHEET"; REPORT = "REPORT"; OTHER = "OTHER"
    # The new HDTS PCR data form names the crash diagram as an explicit upload
    # ("UPLOAD DIAGRAM DESIGN FILE", GAP-PCR-06). Its own type rather than a
    # generic IMAGE, so the PCR view can find "the diagram" for a report without
    # guessing from the filename.
    CRASH_DIAGRAM = "CRASH_DIAGRAM"


class MalwareScanStatus(_Str):
    PENDING = "PENDING"; CLEAN = "CLEAN"; INFECTED = "INFECTED"; ERROR = "ERROR"


class ReportType(_Str):
    DASHBOARD = "DASHBOARD"; REPORT = "REPORT"; TABLE = "TABLE"; VISUALIZATION = "VISUALIZATION"


class ReportVisibility(_Str):
    """Report audience.

    The Jan-2026 BRD separates FMCSA Federal Users from Other Federal Users
    (BTS, NHTSA, NTSB) — they receive data through *different* sharing actions
    with different authorization rows. ``FEDERAL`` is retained and still means
    "both federal tiers", which is what every report created before the split
    already meant; it is not deprecated so much as deliberately broad.
    """
    PRIVATE = "PRIVATE"; ORGANIZATION = "ORGANIZATION"; FEDERAL = "FEDERAL"
    FMCSA_FEDERAL = "FMCSA_FEDERAL"; OTHER_FEDERAL = "OTHER_FEDERAL"
    STATE = "STATE"; PUBLIC = "PUBLIC"


class ShareAudience(_Str):
    """Audience tier a report share releases to.

    Matches the native PG enum ``share_audience`` in
    migrations/0029_report_share_audience.sql. Only the CCFP Database
    Administrator may create OTHER_FEDERAL, STATE or PUBLIC shares; the CCFP
    Project Team is confined to FMCSA_FEDERAL.
    """
    FMCSA_FEDERAL = "FMCSA_FEDERAL"; OTHER_FEDERAL = "OTHER_FEDERAL"
    STATE = "STATE"; PUBLIC = "PUBLIC"


class NotificationStatus(_Str):
    PENDING = "PENDING"; SENT = "SENT"; DELIVERED = "DELIVERED"; READ = "READ"; FAILED = "FAILED"


class NotificationType(_Str):
    """Single source of truth for the notification-type vocabulary (§8.11, NOTI-9).

    The DB column stays plain ``TEXT`` (no native PG ENUM) to preserve per-study/
    phase configurability without a rebuild (§3.4, §11.1); this Python enum governs
    the vocabulary in code. Members cover the §8.11 catalogue plus the operational
    types already present in seed 0005, and ``IIF_DRAFT_SAVED`` emitted on first
    IIF save (INIT-6). ``create_notification`` accepts either a member or a bare
    str for backward compatibility, storing the bare string value either way.
    """
    NEW_IIF = "NEW_IIF"; IN_SCOPE_ROUTING = "IN_SCOPE_ROUTING"
    OUT_OF_SCOPE_ROUTING = "OUT_OF_SCOPE_ROUTING"; MISSING_DATA = "MISSING_DATA"
    MISSING_IIF = "MISSING_IIF"; QC_FAILURE = "QC_FAILURE"
    COMPLETENESS_CHANGE = "COMPLETENESS_CHANGE"; REPORT_PUBLISHED = "REPORT_PUBLISHED"
    REPORT_SHARED = "REPORT_SHARED"; SYSTEM_ALERT = "SYSTEM_ALERT"
    INTEGRATION_STATUS = "INTEGRATION_STATUS"; DATA_MAPPING = "DATA_MAPPING"
    DATASET_READY = "DATASET_READY"; ELD_UPLOAD_REQUEST = "ELD_UPLOAD_REQUEST"
    IIF_DRAFT_SAVED = "IIF_DRAFT_SAVED"
    # Emitted when an IIF is submitted while the crash still cannot be classified
    # (a required fact — fatality count or incident vehicles — is absent). Without
    # it such a crash matches neither routing branch and reaches nobody, which is
    # exactly how the BTS-routing defect stayed invisible (DL1, §5 Phase 2).
    SCOPE_UNDETERMINED = "SCOPE_UNDETERMINED"
    # BRD Appendix E: an ELD upload is parsed AFTER the response returns, so a
    # failed or partial extraction has no request to report on. This notifies the
    # uploader (and the crash's State analysts) instead of leaving the file in a
    # failed state nobody is told about.
    ELD_PARSE_FAILED = "ELD_PARSE_FAILED"


# Catalog list of the documented notification-type codes — the single source of
# truth exposed for admin/config consumers and tests (NOTI-9). Order follows the
# §8.11 catalogue then the operational types.
NOTIFICATION_TYPES: list[str] = [t.value for t in NotificationType]


# ===========================================================================
# CCFP Analysis Environment (BRD Jan-2026 "Data Analysis and Sharing")
# ===========================================================================
class AnalysisEnvironmentStatus(_Str):
    ACTIVE = "ACTIVE"; PAUSED = "PAUSED"; ARCHIVED = "ARCHIVED"


class RefreshCadence(_Str):
    """How often Aggregated Data is refreshed into the environment, and how
    often an outward share is refreshed for its audience. The BRD names "daily
    or hourly" for the inbound refresh and leaves the outbound cadence to the
    CCFP Project Team, so both are drawn from this one vocabulary."""
    HOURLY = "HOURLY"; DAILY = "DAILY"; MANUAL = "MANUAL"


class AnalysisDatasetKind(_Str):
    """AGGREGATED_SNAPSHOT is CCFP Aggregated Data shared *into* the environment;
    DERIVED_VIEW is a "new data/view of data derived from CCFP Aggregated Data"
    created by the CCFP Project Team once it is there."""
    AGGREGATED_SNAPSHOT = "AGGREGATED_SNAPSHOT"; DERIVED_VIEW = "DERIVED_VIEW"


class AnalysisDatasetStatus(_Str):
    ACTIVE = "ACTIVE"; ARCHIVED = "ARCHIVED"


class AnalysisPiiLevel(_Str):
    """Sensitivity of a dataset's materialized rows. Drives which audiences it
    may be shared with (enforced in the database by
    ``analysis_shares_enforce_pii``): States and the public may never receive
    PII, and the public additionally requires DEIDENTIFIED_SUMMARY because the
    BRD says "summary de-identified data only"."""
    PII = "PII"; NO_PII = "NO_PII"; DEIDENTIFIED_SUMMARY = "DEIDENTIFIED_SUMMARY"


class AnalysisAudience(_Str):
    """The four sharing audiences the BRD enumerates, each with its own rule."""
    FMCSA_FEDERAL = "FMCSA_FEDERAL"; OTHER_FEDERAL = "OTHER_FEDERAL"
    PARTICIPATING_STATE = "PARTICIPATING_STATE"; PUBLIC = "PUBLIC"


class AnalysisShareStatus(_Str):
    ACTIVE = "ACTIVE"; REVOKED = "REVOKED"


class RefreshTrigger(_Str):
    """What caused a refresh run.

    ``MANUAL`` means a person pressed "Refresh now". ``SCHEDULED`` means the
    cadence policy decided the snapshot was stale — today that decision is made
    when an analyst opens the Analysis Environment, and later it could be made by
    a scheduler; either way it is the cadence, not a person, that asked. Keeping
    the distinction at *who decided* rather than *what woke it up* is what lets a
    scheduler be added later without a new trigger value or a migration.
    """
    SCHEDULED = "SCHEDULED"; MANUAL = "MANUAL"


class RefreshRunStatus(_Str):
    RUNNING = "RUNNING"; SUCCEEDED = "SUCCEEDED"; FAILED = "FAILED"


class CohortRole(_Str):
    """What a cohort is *for*, declared by the analyst rather than inferred.

    ``CONTROL`` is the load-bearing one: the BRD makes risk modelling conditional
    on "the availability of control such as non-fatal crashes", so a population
    only serves as a comparison denominator when someone has said it should.
    ``GENERAL`` exists so a descriptive slice cannot be picked up and used as a
    denominator by accident.
    """
    CASE = "CASE"; CONTROL = "CONTROL"; GENERAL = "GENERAL"


class CohortStatus(_Str):
    ACTIVE = "ACTIVE"; ARCHIVED = "ARCHIVED"


class AnalysisMethod(_Str):
    """The statistical method families the January 2026 BRD names (p. 16),
    plus the comparative and trend analyses it expects of analysts."""
    DESCRIPTIVE = "DESCRIPTIVE"      # central tendency and dispersion
    DISTRIBUTION = "DISTRIBUTION"    # data distributions
    THEMATIC = "THEMATIC"            # thematic analysis
    RISK_MODEL = "RISK_MODEL"        # statistical risk modeling
    COMPARATIVE = "COMPARATIVE"      # compare crash populations
    TREND = "TREND"                  # trend analysis


class InvestigationVisibility(_Str):
    """Who can see a saved investigation.

    Deliberately *not* the four-audience model used by analysis_shares: the BRD
    scopes investigation sharing to "within the CCFP Analysis Environment", while
    analysis_shares governs data leaving the environment for States and the
    public. Conflating them would make an investigation an undocumented export
    path.
    """
    PRIVATE = "PRIVATE"; TEAM = "TEAM"


class InvestigationStatus(_Str):
    ACTIVE = "ACTIVE"; ARCHIVED = "ARCHIVED"


class StatisticalExportFormat(_Str):
    """Formats for "data should be exportable to any statistical summary or
    visualization/report builder tools ... e.g. Python, SAS, R" (BRD p. 17).

    CSV is the data; the other three are ready-to-run loader scripts that carry
    the column types and value labels with them, so the export is reproducible
    rather than a file someone has to guess the schema of.
    """
    CSV = "CSV"; PYTHON = "PYTHON"; R = "R"; SAS = "SAS"
