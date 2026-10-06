"""SQLAlchemy ORM models mirroring the existing CCFP schema.

The database schema (Backend/database/migrations/0001_initial_schema.sql) is the
source of truth. These models map to it 1:1; no DDL is emitted from here.
Enum columns are mapped as strings (PostgreSQL casts text to the native enum on
write and returns text on read), with the valid values defined in app.enums.
Generated and server-default columns are declared so the ORM omits them on
INSERT and reads them back via RETURNING.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CHAR,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# --- common column helpers -------------------------------------------------
PK = lambda: mapped_column(  # noqa: E731
    UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
)
_now = lambda: mapped_column(DateTime(timezone=True), server_default=text("now()"))  # noqa: E731


# ===========================================================================
# Reference data
# ===========================================================================
class RefUsState(Base):
    __tablename__ = "ref_us_states"
    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    is_territory: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class RefPcrSection(Base):
    __tablename__ = "ref_pcr_sections"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # FALSE = retired by a later specification (GAP-PCR-01, e.g. DYNAMIC).
    # Retained rather than deleted so historical values and archived coverage
    # rows stay resolvable; excluded from new collection.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class RefRepeatUnit(Base):
    """Repeat-unit vocabulary for per-unit PCR values (GAP-PCR-03).

    A reference table rather than a PG enum so a future phase can add a unit
    without an ALTER TYPE, matching the configurability rule in CLAUDE.md.
    """

    __tablename__ = "ref_repeat_units"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class RefContributingFactorGroup(Base):
    __tablename__ = "ref_contributing_factor_groups"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    applies_to: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class RefContributingFactorValue(Base):
    """Per-group catalog of allowed contributing-factor values (DATA-7, §5 Phase 6)."""
    __tablename__ = "ref_contributing_factor_values"
    id: Mapped[uuid.UUID] = PK()
    factor_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ref_contributing_factor_groups.id", ondelete="CASCADE"),
    )
    code: Mapped[Optional[str]] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Vocabulary lifecycle (GAP-PCR-09b). A value retired by a later
    # specification is deactivated, never deleted, so existing
    # contributing_factor_selections stay resolvable.
    spec_version: Mapped[str] = mapped_column(Text, server_default=text("'HDTS-PCR-2026'"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ref_contributing_factor_values.id", ondelete="SET NULL")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)


class RefAttributeValue(Base):
    """Enumerated values allowed for a CODE / MULTI_CODE attribute (GAP-PCR-09b).

    Versioned by specification: the new HDTS PCR data form removes and collapses
    values inside elements it otherwise retains, and a value that disappears
    must stop being offered without orphaning the historical
    ``crash_attribute_values`` rows that already use it.
    """

    __tablename__ = "ref_attribute_values"
    id: Mapped[uuid.UUID] = PK()
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="CASCADE")
    )
    code: Mapped[Optional[str]] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    spec_version: Mapped[str] = mapped_column(Text, server_default=text("'HDTS-PCR-2026'"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ref_attribute_values.id", ondelete="SET NULL")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class RefExternalSystem(Base):
    """Appendix D external data sources available for aggregation.

    Reference data rather than a native enum so a new source (the BRD's own
    "may shift to Motus" note, or a later study phase) is an INSERT, not a
    migration. Retire with ``is_active = False``; never delete, or historical
    ``crash_external_links`` rows stop resolving.
    """
    __tablename__ = "ref_external_systems"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    owner: Mapped[Optional[str]] = mapped_column(Text)
    is_fmcsa_owned: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    relevant_data: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


# ===========================================================================
# Identity & access
# ===========================================================================
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = PK()
    name: Mapped[str] = mapped_column(Text)
    org_type: Mapped[str] = mapped_column(String)
    state_code: Mapped[Optional[str]] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = PK()
    email: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    idp_subject: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    # bcrypt hash for the dev email+password login path; NULL under the
    # production OIDC identity provider (see app/core/security.py).
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    title: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, server_default=text("'ACTIVE'"))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    piv_cac_required: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()

    organization: Mapped[Optional[Organization]] = relationship(lazy="joined")
    assignments: Mapped[list["UserRoleAssignment"]] = relationship(
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
        foreign_keys="UserRoleAssignment.user_id",
    )


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    # optional parent role. A role inherits its ancestors'
    # permissions and access groups (resolved in app/core/security.py). NULL for
    # every seeded role today, which reproduces the original flat model exactly;
    # populated once FMCSA supplies the SafeSpect role hierarchy. A DB trigger
    # (migration 0021) rejects self-parenting and cycles.
    parent_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()

    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", lazy="selectin"
    )
    # AUTH-3: access groups a role belongs to, eager-loaded like permissions so
    # core/security can derive data-sensitivity reach from group membership.
    access_groups: Mapped[list["AccessGroup"]] = relationship(
        secondary="role_access_groups", lazy="selectin"
    )
    # the parent role, eager-loaded so permission resolution can walk
    # the inheritance chain without extra round trips. `join_depth` bounds the
    # eager load; security._resolve additionally walks with a visited-set so an
    # arbitrarily deep (or cyclic) chain is still safe.
    parent: Mapped[Optional["Role"]] = relationship(
        remote_side=[id], lazy="selectin", join_depth=4
    )


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class AccessGroup(Base):
    """First-class access group layered over roles (AUTH-3, §4 l.142).

    ``data_sensitivity_max`` is the highest ``DataSensitivity`` the group may
    view (plain TEXT; vocabulary in app.enums.DataSensitivity).
    """
    __tablename__ = "access_groups"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    data_sensitivity_max: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class RoleAccessGroup(Base):
    __tablename__ = "role_access_groups"
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("access_groups.id", ondelete="CASCADE"), primary_key=True
    )


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    id: Mapped[uuid.UUID] = PK()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")
    )
    scope_type: Mapped[str] = mapped_column(String, server_default=text("'GLOBAL'"))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    state_code: Mapped[Optional[str]] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()

    user: Mapped[User] = relationship(back_populates="assignments", foreign_keys=[user_id])
    role: Mapped[Role] = relationship(lazy="joined")


# ===========================================================================
# Study configuration
# ===========================================================================
class Study(Base):
    __tablename__ = "studies"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    phase_number: Mapped[int] = mapped_column(Integer)
    vehicle_type: Mapped[str] = mapped_column(Text)
    crash_severity: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    start_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    pilot_start_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, server_default=text("'PLANNING'"))
    # Publication settings (STUD-5, §8.1 / §5 Phase 7). Plain TEXT columns;
    # vocabulary governed by app.enums.DeidentificationPolicy / PublicScope.
    deidentification_policy: Mapped[str] = mapped_column(
        Text, server_default=text("'STANDARD'")
    )
    public_scope: Mapped[str] = mapped_column(
        Text, server_default=text("'AGGREGATE_ONLY'")
    )
    publication_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    publication_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class StudyState(Base):
    __tablename__ = "study_states"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    state_code: Mapped[str] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    is_participating: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    agreement_status: Mapped[str] = mapped_column(Text, server_default=text("'PENDING'"))
    onboarded_at: Mapped[Optional[dt.date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class StudyParameter(Base):
    __tablename__ = "study_parameters"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    param_key: Mapped[str] = mapped_column(Text)
    param_value: Mapped[Any] = mapped_column(JSONB)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class DataAttribute(Base):
    __tablename__ = "data_attributes"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    pcr_section: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("ref_pcr_sections.code"))
    data_type: Mapped[str] = mapped_column(String, server_default=text("'TEXT'"))
    sensitivity: Mapped[str] = mapped_column(String, server_default=text("'INTERNAL'"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Repeat/cardinality metadata from the new HDTS PCR data form (GAP-PCR-03).
    # repeats_on NULL = crash-level; non-NULL = captured once per unit of that
    # type. max_selections caps a multi-select ("Check up to N"). applies_to
    # names the conditional Person population the field is collected for.
    repeats_on: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("ref_repeat_units.code"))
    max_selections: Mapped[Optional[int]] = mapped_column(Integer)
    applies_to: Mapped[Optional[str]] = mapped_column(Text)
    # For a retired attribute, the code that replaces it (GAP-PCR-02). Lets a
    # reader of a historical value follow the chain forward to the current
    # attribute. NULL for live attributes and for retirements with no
    # replacement (DV01, whose whole section was removed).
    superseded_by_code: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("data_attributes.code"))
    # Traceability to the published form (GAP-PCR-09). The new HDTS PCR data
    # form carries no element codes, so the header/label text is the only shared
    # key a State has when mapping its own PCR fields onto the CCFP catalog.
    form_section: Mapped[Optional[str]] = mapped_column(Text)
    form_label: Mapped[Optional[str]] = mapped_column(Text)
    mmucc_code: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class AttributeRequirement(Base):
    __tablename__ = "attribute_requirements"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="CASCADE")
    )
    is_required: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_optional: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_read_only: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_editable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


# ===========================================================================
# Crash core
# ===========================================================================
class Crash(Base):
    __tablename__ = "crashes"
    id: Mapped[uuid.UUID] = PK()
    ccfp_identifier: Mapped[str] = mapped_column(Text, unique=True)
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="RESTRICT")
    )
    local_report_number: Mapped[Optional[str]] = mapped_column(Text)
    crash_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    crash_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    city: Mapped[Optional[str]] = mapped_column(Text)
    county: Mapped[Optional[str]] = mapped_column(Text)
    state_code: Mapped[Optional[str]] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    street_highway: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    num_vehicles: Mapped[Optional[int]] = mapped_column(Integer)
    num_persons: Mapped[Optional[int]] = mapped_column(Integer)
    num_fatalities: Mapped[Optional[int]] = mapped_column(Integer)
    lifecycle_phase: Mapped[str] = mapped_column(String, server_default=text("'INITIAL_INCIDENT'"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class CrashScopeClassification(Base):
    __tablename__ = "crash_scope_classifications"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE"), unique=True
    )
    is_qualifying: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    scope: Mapped[str] = mapped_column(String, server_default=text("'UNDETERMINED'"))
    is_supplemental: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    classification_reason: Mapped[Optional[str]] = mapped_column(Text)
    # True once a human sets the scope through PUT /scope. Automatic
    # re-derivation skips these rows so a deliberate decision is never
    # overwritten; POST /scope/reclassify clears it (migration 0024).
    is_manual_override: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    classified_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    classified_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class InitialIncidentForm(Base):
    __tablename__ = "initial_incident_forms"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String, server_default=text("'DRAFT'"))
    event_summary: Mapped[Optional[str]] = mapped_column(Text)
    dot_number_validated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    dot_validation_source: Mapped[Optional[str]] = mapped_column(Text)
    submitted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    routed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class IncidentVehicle(Base):
    __tablename__ = "incident_vehicles"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    vehicle_number: Mapped[int] = mapped_column(Integer)
    # offline-sync idempotency key minted by the client. NULL when
    # the record was created online. Unique per crash (partial index, migration
    # 0020) so a replayed offline write returns the existing row.
    client_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    is_cmv: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Qualifying-criterion inputs (migration 0024). Evaluated against the study's
    # configured `vehicle_classes` / `min_gvwr_lbs` parameters — never hardcoded
    # to Phase 1. Both nullable: when neither is recorded the classifier falls
    # back to the is_cmv proxy and says so in the classification reason.
    vehicle_class: Mapped[Optional[str]] = mapped_column(Text)
    gvwr_lbs: Mapped[Optional[float]] = mapped_column(Numeric)
    us_dot_number: Mapped[Optional[str]] = mapped_column(Text)
    make: Mapped[Optional[str]] = mapped_column(Text)
    num_occupants: Mapped[Optional[int]] = mapped_column(Integer)
    num_injured_occupants: Mapped[Optional[int]] = mapped_column(Integer)
    carrier_name: Mapped[Optional[str]] = mapped_column(Text)
    carrier_phone: Mapped[Optional[str]] = mapped_column(Text)
    is_supplemental: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class IncidentPerson(Base):
    __tablename__ = "incident_persons"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    person_type: Mapped[str] = mapped_column(String)
    # offline-sync idempotency key minted by the client. NULL when
    # the record was created online. A person has no natural key, so this is the
    # ONLY thing preventing a replayed offline sync from inserting the person
    # twice — which would inflate the fatality count that drives the
    # qualifying-crash rule (documentation §3.1).
    client_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    related_vehicle_number: Mapped[Optional[int]] = mapped_column(Integer)
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    # INIT-1: structured name parts; full_name stays the derived convenience value.
    name_last: Mapped[Optional[str]] = mapped_column(Text)
    name_first: Mapped[Optional[str]] = mapped_column(Text)
    name_middle: Mapped[Optional[str]] = mapped_column(Text)
    is_minor: Mapped[Optional[bool]] = mapped_column(Boolean)
    primary_language: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    phone_primary: Mapped[Optional[str]] = mapped_column(Text)
    phone_secondary: Mapped[Optional[str]] = mapped_column(Text)
    phone_type: Mapped[Optional[str]] = mapped_column(Text)
    # INIT-2: per-number phone type (HOME | CELL | WORK).
    phone_primary_type: Mapped[Optional[str]] = mapped_column(Text)
    phone_secondary_type: Mapped[Optional[str]] = mapped_column(Text)
    # INIT-3: non-motorist occupant-vs-pedestrian discriminator.
    non_motorist_kind: Mapped[Optional[str]] = mapped_column(Text)
    injury: Mapped[Optional[str]] = mapped_column(String)
    is_supplemental: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


# ===========================================================================
# Source data
# ===========================================================================
class PostCrashInspection(Base):
    __tablename__ = "post_crash_inspections"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    source_system: Mapped[str] = mapped_column(Text, server_default=text("'SafeSpect'"))
    inspection_number: Mapped[Optional[str]] = mapped_column(Text)
    inspection_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    inspector_name: Mapped[Optional[str]] = mapped_column(Text)
    violations_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    defects_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    # The two facts the new PCR form's inspection block also reports, so the two
    # sources are comparable (GAP-PCR-07). NULL means "not reported", which is
    # deliberately distinct from FALSE — DQ_PCR_INSPECTION_XREF treats an absent
    # value as nothing to reconcile rather than as a disagreement.
    driver_oos: Mapped[Optional[bool]] = mapped_column(Boolean)
    inspection_type: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[Any]] = mapped_column(JSONB)
    linked_at: Mapped[dt.datetime] = _now()
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class PostCrashInvestigation(Base):
    __tablename__ = "post_crash_investigations"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    case_number: Mapped[Optional[str]] = mapped_column(Text)
    inspection_number: Mapped[Optional[str]] = mapped_column(Text)
    officer_name: Mapped[Optional[str]] = mapped_column(Text)
    officer_id: Mapped[Optional[str]] = mapped_column(Text)
    post_crash_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, server_default=text("'DRAFT'"))
    # DEPRECATED (PCI-1): legacy untyped JSONB blob, superseded by the typed
    # pci_* child tables below. Kept for back-compat with in-flight data.
    sections: Mapped[Optional[Any]] = mapped_column(JSONB)
    # PCI-5: presence flags for the optional conditional pages.
    has_additional_towed_units: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    has_hazmat: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()

    # PCI-1 single-valued sections (one-to-one).
    carrier_power_unit: Mapped[Optional["PciCarrierPowerUnit"]] = relationship(
        "PciCarrierPowerUnit", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    driver_load: Mapped[Optional["PciDriverLoad"]] = relationship(
        "PciDriverLoad", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    medical_certificate: Mapped[Optional["PciMedicalCertificate"]] = relationship(
        "PciMedicalCertificate", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    hours_of_service: Mapped[Optional["PciHoursOfService"]] = relationship(
        "PciHoursOfService", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    exemptions: Mapped[Optional["PciExemptions"]] = relationship(
        "PciExemptions", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    vehicle_condition: Mapped[Optional["PciVehicleCondition"]] = relationship(
        "PciVehicleCondition", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    brake_system: Mapped[Optional["PciBrakeSystem"]] = relationship(
        "PciBrakeSystem", back_populates="investigation",
        uselist=False, cascade="all, delete-orphan",
    )
    # PCI-4 repeating structures (one-to-many).
    seating_positions: Mapped[list["PciSeatingPosition"]] = relationship(
        "PciSeatingPosition", back_populates="investigation",
        cascade="all, delete-orphan",
    )
    axles: Mapped[list["PciAxle"]] = relationship(
        "PciAxle", back_populates="investigation", cascade="all, delete-orphan",
    )
    tires: Mapped[list["PciTire"]] = relationship(
        "PciTire", back_populates="investigation", cascade="all, delete-orphan",
    )
    trailers: Mapped[list["PciTrailer"]] = relationship(
        "PciTrailer", back_populates="investigation", cascade="all, delete-orphan",
    )
    # PCI-5 optional conditional sections (one-to-many).
    hazmat: Mapped[list["PciHazmat"]] = relationship(
        "PciHazmat", back_populates="investigation", cascade="all, delete-orphan",
    )
    additional_towed_units: Mapped[list["PciAdditionalTowedUnit"]] = relationship(
        "PciAdditionalTowedUnit", back_populates="investigation",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# PCI structured sections (PCI-1 single-valued child tables, migration 0014).
# Each is one-to-one with post_crash_investigations; all columns nullable.
# ---------------------------------------------------------------------------
class PciCarrierPowerUnit(Base):
    __tablename__ = "pci_carrier_power_unit"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    work_zone: Mapped[Optional[bool]] = mapped_column(Boolean)
    work_zone_type: Mapped[Optional[str]] = mapped_column(Text)
    preclearance_bypass_serial: Mapped[Optional[str]] = mapped_column(Text)
    fire: Mapped[Optional[bool]] = mapped_column(Boolean)
    fire_pre_crash: Mapped[Optional[bool]] = mapped_column(Boolean)
    fire_post_crash: Mapped[Optional[bool]] = mapped_column(Boolean)
    carrier_name_displayed: Mapped[Optional[str]] = mapped_column(Text)
    us_dot_displayed: Mapped[Optional[bool]] = mapped_column(Boolean)
    nsc_number: Mapped[Optional[str]] = mapped_column(Text)
    motor_carrier_name: Mapped[Optional[str]] = mapped_column(Text)
    motor_carrier_address: Mapped[Optional[str]] = mapped_column(Text)
    motor_carrier_phone: Mapped[Optional[str]] = mapped_column(Text)
    owner_name: Mapped[Optional[str]] = mapped_column(Text)
    owner_address: Mapped[Optional[str]] = mapped_column(Text)
    lease_indicator: Mapped[Optional[bool]] = mapped_column(Boolean)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    make: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(Text)
    company_unit_number: Mapped[Optional[str]] = mapped_column(Text)
    manufacture_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    vin: Mapped[Optional[str]] = mapped_column(Text)
    color: Mapped[Optional[str]] = mapped_column(Text)
    license_plate: Mapped[Optional[str]] = mapped_column(Text)
    license_plate_state: Mapped[Optional[str]] = mapped_column(Text)
    registered_gross_weight: Mapped[Optional[float]] = mapped_column(Numeric)
    gvwr: Mapped[Optional[float]] = mapped_column(Numeric)
    annual_inspection: Mapped[Optional[bool]] = mapped_column(Boolean)
    axles_up: Mapped[Optional[int]] = mapped_column(Integer)
    axles_down: Mapped[Optional[int]] = mapped_column(Integer)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="carrier_power_unit"
    )


class PciDriverLoad(Base):
    __tablename__ = "pci_driver_load"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    driver_name: Mapped[Optional[str]] = mapped_column(Text)
    driver_present: Mapped[Optional[bool]] = mapped_column(Boolean)
    driver_address: Mapped[Optional[str]] = mapped_column(Text)
    license_state: Mapped[Optional[str]] = mapped_column(Text)
    license_province: Mapped[Optional[str]] = mapped_column(Text)
    license_number: Mapped[Optional[str]] = mapped_column(Text)
    license_class: Mapped[Optional[str]] = mapped_column(Text)
    license_endorsements: Mapped[Optional[str]] = mapped_column(Text)
    license_restrictions: Mapped[Optional[str]] = mapped_column(Text)
    license_issue_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    license_expiration_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    lenses_required: Mapped[Optional[bool]] = mapped_column(Boolean)
    lenses_worn: Mapped[Optional[bool]] = mapped_column(Boolean)
    shipper: Mapped[Optional[str]] = mapped_column(Text)
    bill_of_lading: Mapped[Optional[str]] = mapped_column(Text)
    manifest_load_weight: Mapped[Optional[float]] = mapped_column(Numeric)
    cargo_loaded: Mapped[Optional[str]] = mapped_column(Text)
    cargo_destination: Mapped[Optional[str]] = mapped_column(Text)
    load_securement: Mapped[Optional[bool]] = mapped_column(Boolean)
    securement_contributed: Mapped[Optional[bool]] = mapped_column(Boolean)
    securement_proper_use: Mapped[Optional[bool]] = mapped_column(Boolean)
    securement_exceeded_wll: Mapped[Optional[bool]] = mapped_column(Boolean)
    securement_type: Mapped[Optional[str]] = mapped_column(Text)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="driver_load"
    )


class PciMedicalCertificate(Base):
    __tablename__ = "pci_medical_certificate"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    examination_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    expiration_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    lenses: Mapped[Optional[bool]] = mapped_column(Boolean)
    hearing_aid: Mapped[Optional[bool]] = mapped_column(Boolean)
    waiver: Mapped[Optional[bool]] = mapped_column(Boolean)
    medic_alert: Mapped[Optional[bool]] = mapped_column(Boolean)
    cert_state: Mapped[Optional[str]] = mapped_column(Text)
    cert_province: Mapped[Optional[str]] = mapped_column(Text)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="medical_certificate"
    )


class PciHoursOfService(Base):
    __tablename__ = "pci_hours_of_service"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    on_duty_not_driving_hours: Mapped[Optional[float]] = mapped_column(Numeric)
    driving_hours: Mapped[Optional[float]] = mapped_column(Numeric)
    total_on_duty_hours: Mapped[Optional[float]] = mapped_column(Numeric)
    miles_driven: Mapped[Optional[float]] = mapped_column(Numeric)
    kilometers_driven: Mapped[Optional[float]] = mapped_column(Numeric)
    record_of_duty_status: Mapped[Optional[bool]] = mapped_column(Boolean)
    timecard: Mapped[Optional[bool]] = mapped_column(Boolean)
    violations: Mapped[Optional[str]] = mapped_column(Text)
    onboard_computer_eld: Mapped[Optional[bool]] = mapped_column(Boolean)
    eld_present: Mapped[Optional[bool]] = mapped_column(Boolean)
    co_driver: Mapped[Optional[bool]] = mapped_column(Boolean)
    last_8_days_present: Mapped[Optional[bool]] = mapped_column(Boolean)
    approved_eld: Mapped[Optional[bool]] = mapped_column(Boolean)
    driver_history: Mapped[Optional[str]] = mapped_column(Text)
    road_familiarity: Mapped[Optional[str]] = mapped_column(Text)
    years_experience: Mapped[Optional[float]] = mapped_column(Numeric)
    previous_cmv_crashes: Mapped[Optional[int]] = mapped_column(Integer)
    purpose_of_trip: Mapped[Optional[str]] = mapped_column(Text)
    trip_destination: Mapped[Optional[str]] = mapped_column(Text)
    driver_condition_remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="hours_of_service"
    )


class PciExemptions(Base):
    __tablename__ = "pci_exemptions"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    exemption_14_hour: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_11_hour: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_split_sleeper: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_60_70_hour: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_34_hour_restart: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_federal: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_state: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_oilfield: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_agricultural: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_150_air_mile: Mapped[Optional[bool]] = mapped_column(Boolean)
    exemption_temporary: Mapped[Optional[bool]] = mapped_column(Boolean)
    docket_or_state_number: Mapped[Optional[str]] = mapped_column(Text)
    emergency_declaration: Mapped[Optional[bool]] = mapped_column(Boolean)
    emergency_jurisdiction: Mapped[Optional[str]] = mapped_column(Text)
    emergency_federal_number: Mapped[Optional[str]] = mapped_column(Text)
    emergency_state_number: Mapped[Optional[str]] = mapped_column(Text)
    service_center: Mapped[Optional[str]] = mapped_column(Text)
    other_description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="exemptions"
    )


class PciVehicleCondition(Base):
    __tablename__ = "pci_vehicle_condition"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    compartment_condition: Mapped[Optional[str]] = mapped_column(Text)
    drivers_view: Mapped[Optional[str]] = mapped_column(Text)
    wipers: Mapped[Optional[str]] = mapped_column(Text)
    wiper_switch_position: Mapped[Optional[str]] = mapped_column(Text)
    heater_defroster: Mapped[Optional[str]] = mapped_column(Text)
    mirrors: Mapped[Optional[str]] = mapped_column(Text)
    rearward_camera: Mapped[Optional[bool]] = mapped_column(Boolean)
    fender_mirrors: Mapped[Optional[bool]] = mapped_column(Boolean)
    odometer: Mapped[Optional[float]] = mapped_column(Numeric)
    engine_hours: Mapped[Optional[float]] = mapped_column(Numeric)
    engine_manufacturer: Mapped[Optional[str]] = mapped_column(Text)
    fuel_type: Mapped[Optional[str]] = mapped_column(Text)
    ecm_serial: Mapped[Optional[str]] = mapped_column(Text)
    adas: Mapped[Optional[str]] = mapped_column(Text)
    steering_type: Mapped[Optional[str]] = mapped_column(Text)
    steering_wheel_diameter: Mapped[Optional[float]] = mapped_column(Numeric)
    steering_lash: Mapped[Optional[str]] = mapped_column(Text)
    steering_checked_running: Mapped[Optional[bool]] = mapped_column(Boolean)
    transmission_type: Mapped[Optional[str]] = mapped_column(Text)
    transmission_model: Mapped[Optional[str]] = mapped_column(Text)
    transmission_serial: Mapped[Optional[str]] = mapped_column(Text)
    transmission_gear_position: Mapped[Optional[str]] = mapped_column(Text)
    transmission_forward_gears: Mapped[Optional[int]] = mapped_column(Integer)
    drive_line_notes: Mapped[Optional[str]] = mapped_column(Text)
    drive_axle_ratio: Mapped[Optional[str]] = mapped_column(Text)
    radio: Mapped[Optional[bool]] = mapped_column(Boolean)
    cb: Mapped[Optional[bool]] = mapped_column(Boolean)
    dash_camera: Mapped[Optional[bool]] = mapped_column(Boolean)
    audio_technology: Mapped[Optional[bool]] = mapped_column(Boolean)
    headphones: Mapped[Optional[bool]] = mapped_column(Boolean)
    bluetooth: Mapped[Optional[bool]] = mapped_column(Boolean)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="vehicle_condition"
    )


class PciBrakeSystem(Base):
    __tablename__ = "pci_brake_system"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
        unique=True,
    )
    brake_type: Mapped[Optional[str]] = mapped_column(Text)
    abs_type: Mapped[Optional[str]] = mapped_column(Text)
    engine_brake_type: Mapped[Optional[str]] = mapped_column(Text)
    engine_brake_position: Mapped[Optional[str]] = mapped_column(Text)
    air_leaks: Mapped[Optional[bool]] = mapped_column(Boolean)
    application_loss: Mapped[Optional[bool]] = mapped_column(Boolean)
    low_air_vacuum_warning: Mapped[Optional[bool]] = mapped_column(Boolean)
    low_air_vacuum_warning_psi: Mapped[Optional[float]] = mapped_column(Numeric)
    hydraulic_master_cylinder_secure: Mapped[Optional[bool]] = mapped_column(Boolean)
    hydraulic_fluid_level: Mapped[Optional[str]] = mapped_column(Text)
    hydraulic_fluid_seepage: Mapped[Optional[bool]] = mapped_column(Boolean)
    hydraulic_line_condition: Mapped[Optional[str]] = mapped_column(Text)
    electric_controller_mfr: Mapped[Optional[str]] = mapped_column(Text)
    electric_gain_setting: Mapped[Optional[str]] = mapped_column(Text)
    electric_breakaway_device: Mapped[Optional[bool]] = mapped_column(Boolean)
    electric_battery_wiring: Mapped[Optional[str]] = mapped_column(Text)
    surge_breakaway_device: Mapped[Optional[bool]] = mapped_column(Boolean)
    surge_fluid_leak: Mapped[Optional[bool]] = mapped_column(Boolean)
    power_assist: Mapped[Optional[bool]] = mapped_column(Boolean)
    parking_brake: Mapped[Optional[bool]] = mapped_column(Boolean)
    wheel_end_weight_note: Mapped[Optional[str]] = mapped_column(Text)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="brake_system"
    )


# ---------------------------------------------------------------------------
# PCI per-field definitions (PCI-3, migration 0015). Mirrors AttributeRequirement
# but keyed to PCI form fields (study + section_code + field_code), separate from
# the analytic attribute_requirements store.
# ---------------------------------------------------------------------------
class PciFieldDefinition(Base):
    __tablename__ = "pci_field_definitions"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    section_code: Mapped[str] = mapped_column(Text)
    field_code: Mapped[str] = mapped_column(Text)
    label: Mapped[Optional[str]] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_optional: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    display_order: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


# ---------------------------------------------------------------------------
# PCI repeating structures (PCI-4, migration 0016). One-to-many child tables
# keyed by an index/position column (no fixed Phase-1 column counts).
# ---------------------------------------------------------------------------
class PciSeatingPosition(Base):
    __tablename__ = "pci_seating_positions"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
    )
    position: Mapped[Optional[str]] = mapped_column(Text)
    seat_belt_equipped: Mapped[Optional[bool]] = mapped_column(Boolean)
    seat_belt_used: Mapped[Optional[bool]] = mapped_column(Boolean)
    seat_belt_condition: Mapped[Optional[str]] = mapped_column(Text)
    airbag_equipped: Mapped[Optional[bool]] = mapped_column(Boolean)
    airbag_deployed: Mapped[Optional[bool]] = mapped_column(Boolean)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="seating_positions"
    )


class PciAxle(Base):
    __tablename__ = "pci_axles"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
    )
    axle_index: Mapped[Optional[int]] = mapped_column(Integer)
    abs: Mapped[Optional[bool]] = mapped_column(Boolean)
    slack_adjuster_type: Mapped[Optional[str]] = mapped_column(Text)
    slack_adjuster_length: Mapped[Optional[float]] = mapped_column(Numeric)
    push_rod_stroke_available: Mapped[Optional[float]] = mapped_column(Numeric)
    push_rod_stroke_applied: Mapped[Optional[float]] = mapped_column(Numeric)
    air_pressure: Mapped[Optional[str]] = mapped_column(Text)
    chamber_type: Mapped[Optional[str]] = mapped_column(Text)
    drum_rotor: Mapped[Optional[str]] = mapped_column(Text)
    brake_friction_code: Mapped[Optional[str]] = mapped_column(Text)
    rolling_radius: Mapped[Optional[float]] = mapped_column(Numeric)
    wheel_end_weight: Mapped[Optional[float]] = mapped_column(Numeric)
    total_end_weight: Mapped[Optional[float]] = mapped_column(Numeric)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="axles"
    )


class PciTire(Base):
    __tablename__ = "pci_tires"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
    )
    axle_index: Mapped[Optional[int]] = mapped_column(Integer)
    side: Mapped[Optional[str]] = mapped_column(Text)
    inner_outer: Mapped[Optional[str]] = mapped_column(Text)
    size: Mapped[Optional[str]] = mapped_column(Text)
    make: Mapped[Optional[str]] = mapped_column(Text)
    model_design: Mapped[Optional[str]] = mapped_column(Text)
    tin_dot: Mapped[Optional[str]] = mapped_column(Text)
    rated_psi: Mapped[Optional[float]] = mapped_column(Numeric)
    rated_weight: Mapped[Optional[float]] = mapped_column(Numeric)
    inspection_psi: Mapped[Optional[float]] = mapped_column(Numeric)
    retread_tin_dot: Mapped[Optional[str]] = mapped_column(Text)
    repair: Mapped[Optional[bool]] = mapped_column(Boolean)
    repair_location: Mapped[Optional[str]] = mapped_column(Text)
    speed_rating: Mapped[Optional[str]] = mapped_column(Text)
    tread_depth: Mapped[Optional[float]] = mapped_column(Numeric)
    wheel_hub_remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="tires"
    )


class PciTrailer(Base):
    __tablename__ = "pci_trailers"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
    )
    trailer_index: Mapped[Optional[int]] = mapped_column(Integer)
    owner_name: Mapped[Optional[str]] = mapped_column(Text)
    owner_address: Mapped[Optional[str]] = mapped_column(Text)
    trailer_type: Mapped[Optional[str]] = mapped_column(Text)
    intermodal_indicator: Mapped[Optional[bool]] = mapped_column(Boolean)
    unit_number: Mapped[Optional[str]] = mapped_column(Text)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    make: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(Text)
    vin: Mapped[Optional[str]] = mapped_column(Text)
    color: Mapped[Optional[str]] = mapped_column(Text)
    license_plate: Mapped[Optional[str]] = mapped_column(Text)
    expiration: Mapped[Optional[dt.date]] = mapped_column(Date)
    registered_gross_weight: Mapped[Optional[float]] = mapped_column(Numeric)
    gvwr: Mapped[Optional[float]] = mapped_column(Numeric)
    axle_weight_rating: Mapped[Optional[float]] = mapped_column(Numeric)
    annual_inspection: Mapped[Optional[bool]] = mapped_column(Boolean)
    axles_up: Mapped[Optional[int]] = mapped_column(Integer)
    axles_down: Mapped[Optional[int]] = mapped_column(Integer)
    converter_dolly: Mapped[Optional[bool]] = mapped_column(Boolean)
    converter_dolly_details: Mapped[Optional[str]] = mapped_column(Text)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="trailers"
    )


# ---------------------------------------------------------------------------
# PCI optional conditional sections (PCI-5, migration 0017).
# ---------------------------------------------------------------------------
class PciHazmat(Base):
    __tablename__ = "pci_hazmat"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
    )
    unit_scope: Mapped[Optional[str]] = mapped_column(Text)
    hazmat_present: Mapped[Optional[bool]] = mapped_column(Boolean)
    hazmat_type: Mapped[Optional[str]] = mapped_column(Text)
    placards: Mapped[Optional[str]] = mapped_column(Text)
    spill: Mapped[Optional[bool]] = mapped_column(Boolean)
    leak: Mapped[Optional[bool]] = mapped_column(Boolean)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="hazmat"
    )


class PciAdditionalTowedUnit(Base):
    __tablename__ = "pci_additional_towed_units"
    id: Mapped[uuid.UUID] = PK()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("post_crash_investigations.id", ondelete="CASCADE"),
    )
    towed_index: Mapped[Optional[int]] = mapped_column(Integer)
    owner_name: Mapped[Optional[str]] = mapped_column(Text)
    owner_address: Mapped[Optional[str]] = mapped_column(Text)
    unit_type: Mapped[Optional[str]] = mapped_column(Text)
    unit_number: Mapped[Optional[str]] = mapped_column(Text)
    vin: Mapped[Optional[str]] = mapped_column(Text)
    front_clearance: Mapped[Optional[str]] = mapped_column(Text)
    rear_clearance: Mapped[Optional[str]] = mapped_column(Text)
    side_marker_left: Mapped[Optional[str]] = mapped_column(Text)
    side_marker_right: Mapped[Optional[str]] = mapped_column(Text)
    turn_signals: Mapped[Optional[str]] = mapped_column(Text)
    stop_lamps: Mapped[Optional[str]] = mapped_column(Text)
    id_lamps: Mapped[Optional[str]] = mapped_column(Text)
    tail_lamps: Mapped[Optional[str]] = mapped_column(Text)
    reflectors: Mapped[Optional[str]] = mapped_column(Text)
    conspicuity_tape: Mapped[Optional[str]] = mapped_column(Text)
    distance_from_rear: Mapped[Optional[float]] = mapped_column(Numeric)
    rear_protection_from_rear: Mapped[Optional[float]] = mapped_column(Numeric)
    rear_protection_from_ground: Mapped[Optional[float]] = mapped_column(Numeric)
    rear_protection_from_side: Mapped[Optional[float]] = mapped_column(Numeric)
    rear_protection_width: Mapped[Optional[float]] = mapped_column(Numeric)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    investigation: Mapped["PostCrashInvestigation"] = relationship(
        "PostCrashInvestigation", back_populates="additional_towed_units"
    )


class PoliceCrashReport(Base):
    __tablename__ = "police_crash_reports"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    state_code: Mapped[Optional[str]] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    source_repository: Mapped[Optional[str]] = mapped_column(Text)
    # PCR-4: structured ingestion path (MCMIS_ROUNDTRIP | DIRECT_STATE).
    ingestion_path: Mapped[str] = mapped_column(
        String, server_default=text("'MCMIS_ROUNDTRIP'")
    )
    pcr_number: Mapped[Optional[str]] = mapped_column(Text)
    report_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    mapping_status: Mapped[str] = mapped_column(String, server_default=text("'PENDING'"))
    mapped_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class PcrColumnMapping(Base):
    """A State export column -> CCFP attribute ingest rule (GAP-SOO-05, §8.5).

    The SOO's goal is "minimizing data sharing burden to the States", so CCFP
    does not define a file format for States to conform to — it adapts to the
    export each State's existing system already produces. That adaptation is
    this table: configuration, not code. Onboarding a State is inserting rows.

    NULL ``study_id``/``state_code`` = a default applying more broadly; a
    study+state rule wins, with ``priority`` breaking ties. Mirrors
    ``EldFieldMapping`` deliberately, so there is one mental model for
    "map an external source's columns onto CCFP attributes".
    """
    __tablename__ = "pcr_column_mappings"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    state_code: Mapped[Optional[str]] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    source_header: Mapped[str] = mapped_column(Text)
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="RESTRICT")
    )
    priority: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()


class PcrFieldMapping(Base):
    """One State-PCR-field -> CCFP-attribute mapping (PCR-1, §8.5/§19.4).

    Records that a field on a State's existing police crash report (named/located
    by `state_field_name` + `state_field_position`) corresponds to a CCFP
    `data_attributes` row, without altering the State form. UNIQUE(pcr_id,
    attribute_id) keeps one mapping per attribute per PCR (migration 0019)."""
    __tablename__ = "pcr_field_mapping"
    id: Mapped[uuid.UUID] = PK()
    pcr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("police_crash_reports.id", ondelete="CASCADE")
    )
    state_field_name: Mapped[str] = mapped_column(Text)
    state_field_position: Mapped[Optional[str]] = mapped_column(Text)
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="RESTRICT")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    mapped_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class ReconstructionReport(Base):
    __tablename__ = "reconstruction_reports"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    title: Mapped[Optional[str]] = mapped_column(Text)
    received_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    coding_status: Mapped[str] = mapped_column(String, server_default=text("'PENDING'"))
    coded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    coded_findings: Mapped[Optional[Any]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class EldFile(Base):
    __tablename__ = "eld_files"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    file_name: Mapped[str] = mapped_column(Text)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    ccfp_code_in_file: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[Optional[str]] = mapped_column(Text)
    upload_status: Mapped[str] = mapped_column(String, server_default=text("'UPLOADED'"))
    event_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"))
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    parsed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    # PCI-7 (§19.2 l.844): ELD summary / download-status detail (migration 0018).
    eld_downloaded: Mapped[Optional[bool]] = mapped_column(Boolean)
    last_entry_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    last_duty_status: Mapped[Optional[str]] = mapped_column(Text)
    last_stop_arrived_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    last_stop_departed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    # --- Parse diagnostics (BRD Appendix E, migration 0031) -----------------
    # error_code is stable and machine-readable; error_message is written for
    # the uploader and names the fix. Both are cleared at the start of every
    # (re)parse so a stale failure never shadows a later success.
    error_code: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    file_format: Mapped[Optional[str]] = mapped_column(Text)
    encoding: Mapped[Optional[str]] = mapped_column(Text)
    delimiter: Mapped[Optional[str]] = mapped_column(Text)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    content_sha256: Mapped[Optional[str]] = mapped_column(Text)
    line_count: Mapped[Optional[int]] = mapped_column(Integer)
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    warning_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    parse_started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    parse_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    parse_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    # --- Extracted ELD file header segment (49 CFR 395 App. A §4.8.2.1) -----
    driver_name: Mapped[Optional[str]] = mapped_column(Text)
    driver_license_number: Mapped[Optional[str]] = mapped_column(Text)
    driver_license_state: Mapped[Optional[str]] = mapped_column(Text)
    co_driver_name: Mapped[Optional[str]] = mapped_column(Text)
    carrier_name: Mapped[Optional[str]] = mapped_column(Text)
    carrier_usdot: Mapped[Optional[str]] = mapped_column(Text)
    vin: Mapped[Optional[str]] = mapped_column(Text)
    power_unit_number: Mapped[Optional[str]] = mapped_column(Text)
    trailer_numbers: Mapped[Optional[str]] = mapped_column(Text)
    time_zone_offset: Mapped[Optional[str]] = mapped_column(Text)
    eld_registration_id: Mapped[Optional[str]] = mapped_column(Text)
    eld_identifier: Mapped[Optional[str]] = mapped_column(Text)
    output_file_comment: Mapped[Optional[str]] = mapped_column(Text)
    file_data_check_value: Mapped[Optional[str]] = mapped_column(Text)
    sections: Mapped[Optional[Any]] = mapped_column(JSONB)
    header_metadata: Mapped[Optional[Any]] = mapped_column(JSONB)
    hos_summary: Mapped[Optional[Any]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class EldEvent(Base):
    __tablename__ = "eld_events"
    id: Mapped[uuid.UUID] = PK()
    eld_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eld_files.id", ondelete="CASCADE")
    )
    event_sequence: Mapped[int] = mapped_column(Integer)
    event_timestamp: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    duty: Mapped[Optional[str]] = mapped_column(String)
    event_type: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    miles_driven: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    engine_hours: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    ignition_status: Mapped[Optional[str]] = mapped_column(Text)
    raw: Mapped[Optional[Any]] = mapped_column(JSONB)
    # --- ELD-standard event columns (migration 0031) ------------------------
    # 49 CFR 395 App. A records more than a duty status per event, and an HOS
    # analysis needs all of it: an INACTIVE_CHANGED record must not be counted
    # like an active one, and a driver-entered record carries different weight
    # from an automatically captured one.
    section: Mapped[Optional[str]] = mapped_column(Text)
    line_number: Mapped[Optional[int]] = mapped_column(Integer)
    event_type_code: Mapped[Optional[int]] = mapped_column(Integer)
    event_code: Mapped[Optional[int]] = mapped_column(Integer)
    record_status: Mapped[Optional[str]] = mapped_column(Text)
    record_origin: Mapped[Optional[str]] = mapped_column(Text)
    distance_since_last_coords: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    malfunction_indicator: Mapped[Optional[str]] = mapped_column(Text)
    diagnostic_indicator: Mapped[Optional[str]] = mapped_column(Text)
    annotation: Mapped[Optional[str]] = mapped_column(Text)
    driver_identifier: Mapped[Optional[str]] = mapped_column(Text)
    cmv_identifier: Mapped[Optional[str]] = mapped_column(Text)
    data_check_value: Mapped[Optional[str]] = mapped_column(Text)
    is_duplicate: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )


class EldParseIssue(Base):
    """One aggregated ELD parse/validation problem (BRD Appendix E, §8.7).

    Aggregated, not per-occurrence: a file whose timestamp column is
    systematically unreadable produces ONE row with ``occurrences`` set and up
    to 20 sample line numbers in ``details``. Rewritten from scratch on every
    (re)parse of the file, so the set always describes the current extraction.
    """

    __tablename__ = "eld_parse_issues"
    id: Mapped[uuid.UUID] = PK()
    eld_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eld_files.id", ondelete="CASCADE")
    )
    severity: Mapped[str] = mapped_column(Text)  # app.enums.EldIssueSeverity
    code: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    section: Mapped[Optional[str]] = mapped_column(Text)
    line_number: Mapped[Optional[int]] = mapped_column(Integer)
    column_name: Mapped[Optional[str]] = mapped_column(Text)
    raw_value: Mapped[Optional[str]] = mapped_column(Text)
    occurrences: Mapped[int] = mapped_column(Integer, server_default=text("1"), default=1)
    details: Mapped[Optional[Any]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = _now()


class EldFieldMapping(Base):
    """ELD CSV header -> canonical-field mapping (RECO-5, §8.7).

    NULL ``study_id``/``provider`` = global default; a study+provider-specific
    row wins via higher ``priority``.
    """
    __tablename__ = "eld_field_mappings"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    provider: Mapped[Optional[str]] = mapped_column(Text)
    canonical_field: Mapped[str] = mapped_column(Text)
    source_header: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EldDutyCodeMapping(Base):
    """ELD source duty-code -> canonical DutyStatus mapping (RECO-5, §8.7).

    NULL ``study_id``/``provider`` = global default.
    """
    __tablename__ = "eld_duty_code_mappings"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    provider: Mapped[Optional[str]] = mapped_column(Text)
    source_code: Mapped[str] = mapped_column(Text)
    canonical_duty: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class SourceRecord(Base):
    __tablename__ = "source_records"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    source_system: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)
    external_id: Mapped[Optional[str]] = mapped_column(Text)
    raw_zone_uri: Mapped[Optional[str]] = mapped_column(Text)
    provenance_note: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[dt.datetime] = _now()
    created_at: Mapped[dt.datetime] = _now()


class CrashExternalLink(Base):
    """One crash -> external-system-record correspondence.

    The half of "CCFP Aggregated Data" that ``source_records`` does not cover:
    the BRD's "data from external systems (e.g., SafeSpect Inspections, Drug and
    Alcohol Clearinghouse, etc.) that are related to a specific crash".

    Append-only, mirroring ``CrashAttributeValue``: unlinking flips
    ``is_current`` to False rather than deleting, so the linkage history is
    retained and ``uq_cel_current`` still permits a later re-link of the same
    reference.
    """
    __tablename__ = "crash_external_links"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    source_system: Mapped[str] = mapped_column(
        Text, ForeignKey("ref_external_systems.code", ondelete="RESTRICT")
    )
    external_ref: Mapped[str] = mapped_column(Text)
    link_method: Mapped[str] = mapped_column(String, server_default=text("'MANUAL'"))
    matched_on: Mapped[Optional[Any]] = mapped_column(JSONB)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    linked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    linked_at: Mapped[dt.datetime] = _now()
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    unlinked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    unlinked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


# ===========================================================================
# Mapping / QC / completeness
# ===========================================================================
class CrashAttributeValue(Base):
    __tablename__ = "crash_attribute_values"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="RESTRICT")
    )
    # Repeat discriminator (GAP-PCR-03). Both NULL = a crash-level value; both
    # set = "this attribute, for unit #N of that type" (Trailer 2, Vehicle 3).
    # A DB CHECK enforces that they are set or unset together.
    unit_type: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("ref_repeat_units.code"))
    unit_number: Mapped[Optional[int]] = mapped_column(Integer)
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_json: Mapped[Optional[Any]] = mapped_column(JSONB)
    source_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_records.id", ondelete="SET NULL")
    )
    source_system: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_edited: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    edited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    edited_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class DataQualityRule(Base):
    __tablename__ = "data_quality_rules"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(Text)
    attribute_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="SET NULL")
    )
    severity: Mapped[str] = mapped_column(String, server_default=text("'WARNING'"))
    definition: Mapped[Optional[Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_quality_rules.id", ondelete="CASCADE")
    )
    attribute_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String, server_default=text("'NOT_EVALUATED'"))
    message: Mapped[Optional[str]] = mapped_column(Text)
    evaluated_at: Mapped[dt.datetime] = _now()


class CompletenessRule(Base):
    __tablename__ = "completeness_rules"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    definition: Mapped[Optional[Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class CrashCompletenessStatus(Base):
    __tablename__ = "crash_completeness_status"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String, server_default=text("'INCOMPLETE'"))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_locked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    missing_summary: Mapped[Optional[Any]] = mapped_column(JSONB)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    changed_at: Mapped[dt.datetime] = _now()


class ContributingFactorSelection(Base):
    __tablename__ = "contributing_factor_selections"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    factor_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ref_contributing_factor_groups.id", ondelete="SET NULL")
    )
    factor_value: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    selected_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    selected_at: Mapped[dt.datetime] = _now()


class StatePcrCoverage(Base):
    __tablename__ = "state_pcr_coverage"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    state_code: Mapped[str] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    pcr_section_code: Mapped[str] = mapped_column(Text, ForeignKey("ref_pcr_sections.code"))
    required_collected: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_required: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    optional_collected: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_optional: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Which PCR specification these reported counts belong to (GAP-PCR-05).
    # Percentages are not comparable across versions: the HDTS PCR data form
    # changed the denominators and dropped the optional tier entirely.
    spec_version: Mapped[str] = mapped_column(Text, server_default=text("'HDTS-PCR-2026'"))
    completion_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        Computed(
            "CASE WHEN total_required > 0 THEN round(required_collected * 100.0 / total_required, 2) ELSE 0 END",
            persisted=True,
        ),
    )
    updated_at: Mapped[dt.datetime] = _now()


class StateAttributeCoverage(Base):
    """Per-State, per-attribute collection flag (PCR-3, §8.5).

    Mirrors StatePcrCoverage but at attribute grain, driving the three-way
    per-attribute colour status (required-collected / required-not-collected /
    optional-not-collected).
    """
    __tablename__ = "state_attribute_coverage"
    id: Mapped[uuid.UUID] = PK()
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    state_code: Mapped[str] = mapped_column(CHAR(2), ForeignKey("ref_us_states.code"))
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_attributes.id", ondelete="CASCADE")
    )
    is_collected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[dt.datetime] = _now()


# ===========================================================================
# Documents / reports / audit / notifications
# ===========================================================================
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = PK()
    crash_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    # The police crash report this document belongs to (GAP-PCR-06). NULL for a
    # document attached to the crash generally. Without it a crash carrying two
    # State reports could not say which diagram belonged to which.
    pcr_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("police_crash_reports.id", ondelete="SET NULL")
    )
    doc_type: Mapped[str] = mapped_column(String, server_default=text("'DOCUMENT'"))
    file_name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[Optional[str]] = mapped_column(Text)
    # SEAR-2: extracted/plain text for full-text document content search. NULL for
    # binary docs (still findable by file_name); no OCR pipeline.
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    storage_uri: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    sensitivity: Mapped[str] = mapped_column(String, server_default=text("'INTERNAL'"))
    malware_scan: Mapped[str] = mapped_column(String, server_default=text("'PENDING'"))
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_at: Mapped[dt.datetime] = _now()
    created_at: Mapped[dt.datetime] = _now()


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = PK()
    name: Mapped[str] = mapped_column(Text)
    report_type: Mapped[str] = mapped_column(String, server_default=text("'REPORT'"))
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="SET NULL")
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    definition: Mapped[Optional[Any]] = mapped_column(JSONB)
    visibility: Mapped[str] = mapped_column(String, server_default=text("'PRIVATE'"))
    # The State a STATE-visibility report belongs to. NULL = not
    # State-bound (visible to every State user, preserving pre-existing rows);
    # when set, only principals scoped to this State may read or download it.
    state_code: Mapped[Optional[str]] = mapped_column(
        CHAR(2), ForeignKey("ref_us_states.code")
    )
    is_published: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_deidentified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    # Open-data catalog metadata for published outputs (ANAL-9, §14.1). All
    # nullable/additive; surfaced on the public endpoints + /public/data.json.
    license: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    publisher: Mapped[Optional[str]] = mapped_column(Text)
    contact_name: Mapped[Optional[str]] = mapped_column(Text)
    contact_email: Mapped[Optional[str]] = mapped_column(Text)
    update_cadence: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class ReportShare(Base):
    __tablename__ = "report_shares"
    id: Mapped[uuid.UUID] = PK()
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE")
    )
    shared_with_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    shared_with_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")
    )
    shared_with_org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    can_download: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # The audience tier this share releases to. NULL = a directed
    # user/role/org share, the only kind that existed before. Only the CCFP
    # Database Administrator may create OTHER_FEDERAL / STATE / PUBLIC shares.
    audience: Mapped[Optional[str]] = mapped_column(String)
    audience_state_code: Mapped[Optional[str]] = mapped_column(
        CHAR(2), ForeignKey("ref_us_states.code")
    )
    shared_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = PK()
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    crash_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="SET NULL")
    )
    before_state: Mapped[Optional[Any]] = mapped_column(JSONB)
    after_state: Mapped[Optional[Any]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[dt.datetime] = _now()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = PK()
    recipient_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    notification_type: Mapped[str] = mapped_column(Text)
    crash_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[Optional[str]] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text, server_default=text("'IN_APP'"))
    status: Mapped[str] = mapped_column(String, server_default=text("'PENDING'"))
    created_at: Mapped[dt.datetime] = _now()
    read_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))


# ===========================================================================
# CCFP Analysis Environment (migration 0022, BRD Jan-2026 pp. 13-16)
#
# A tier distinct from the operational crash tables: Aggregated Data is
# *materialized* into versioned dataset rows on a refresh cadence, derived views
# are built on top of it, and outward shares carry the audience/PII rules. See
# the migration header for the requirement mapping.
# ===========================================================================
class AnalysisEnvironment(Base):
    __tablename__ = "analysis_environments"
    id: Mapped[uuid.UUID] = PK()
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("studies.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String, server_default=text("'ACTIVE'"))
    refresh_cadence: Mapped[str] = mapped_column(String, server_default=text("'DAILY'"))
    last_refreshed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    next_refresh_due: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class AnalysisDataset(Base):
    __tablename__ = "analysis_datasets"
    id: Mapped[uuid.UUID] = PK()
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_environments.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String, server_default=text("'DERIVED_VIEW'"))
    definition: Mapped[Any] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    pii_level: Mapped[str] = mapped_column(String, server_default=text("'NO_PII'"))
    # True when every materialized row carries a state_code, which is the
    # precondition for a PARTICIPATING_STATE share (see the DB trigger).
    is_state_partitioned: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    status: Mapped[str] = mapped_column(String, server_default=text("'ACTIVE'"))
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_dataset_versions.id", ondelete="SET NULL")
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class AnalysisDatasetVersion(Base):
    __tablename__ = "analysis_dataset_versions"
    id: Mapped[uuid.UUID] = PK()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_datasets.id", ondelete="CASCADE")
    )
    version_no: Mapped[int] = mapped_column(Integer)
    materialized_at: Mapped[dt.datetime] = _now()
    row_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    columns: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    refresh_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))


class AnalysisDatasetRow(Base):
    __tablename__ = "analysis_dataset_rows"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_dataset_versions.id", ondelete="CASCADE")
    )
    row_index: Mapped[int] = mapped_column(Integer)
    # Lifted out of `data` so a State-scoped share filters on an index.
    state_code: Mapped[Optional[str]] = mapped_column(
        CHAR(2), ForeignKey("ref_us_states.code")
    )
    data: Mapped[Any] = mapped_column(JSONB)


class AnalysisRefreshRun(Base):
    __tablename__ = "analysis_refresh_runs"
    id: Mapped[uuid.UUID] = PK()
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_environments.id", ondelete="CASCADE")
    )
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_datasets.id", ondelete="CASCADE")
    )
    trigger: Mapped[str] = mapped_column(String, server_default=text("'MANUAL'"))
    status: Mapped[str] = mapped_column(String, server_default=text("'RUNNING'"))
    started_at: Mapped[dt.datetime] = _now()
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    datasets_refreshed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rows_written: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # The same refresh materializes crash-level cohorts, so the run
    # log records both halves of the work rather than only the aggregated one.
    cohorts_refreshed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    members_written: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    message: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class AnalysisShare(Base):
    __tablename__ = "analysis_shares"
    id: Mapped[uuid.UUID] = PK()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_datasets.id", ondelete="CASCADE")
    )
    audience: Mapped[str] = mapped_column(String)
    state_code: Mapped[Optional[str]] = mapped_column(
        CHAR(2), ForeignKey("ref_us_states.code")
    )
    refresh_cadence: Mapped[str] = mapped_column(String, server_default=text("'DAILY'"))
    status: Mapped[str] = mapped_column(String, server_default=text("'ACTIVE'"))
    note: Mapped[Optional[str]] = mapped_column(Text)
    shared_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    shared_at: Mapped[dt.datetime] = _now()
    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))


# ===========================================================================
# Statistical analysis over the Analysis Environment
#
# Crash-level counterpart to the aggregated dataset tables above. The BRD's
# thematic-analysis and risk-modelling methods ask questions about individual
# crashes ("which factors co-occur?", "how do exposed cases compare to
# controls?") that aggregation destroys, so cohorts materialize one row per
# crash under the same versioning discipline. See migration 0028.
# ===========================================================================
class AnalysisCohort(Base):
    __tablename__ = "analysis_cohorts"
    id: Mapped[uuid.UUID] = PK()
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_environments.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # CASE / CONTROL / GENERAL. The control designation is what makes the BRD's
    # "given the availability of control" clause satisfiable, so it is declared
    # by the analyst and recorded rather than inferred from the definition.
    cohort_role: Mapped[str] = mapped_column(String, server_default=text("'GENERAL'"))
    definition: Mapped[Any] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String, server_default=text("'ACTIVE'"))
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_cohort_versions.id", ondelete="SET NULL")
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class AnalysisCohortVersion(Base):
    __tablename__ = "analysis_cohort_versions"
    id: Mapped[uuid.UUID] = PK()
    cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_cohorts.id", ondelete="CASCADE")
    )
    version_no: Mapped[int] = mapped_column(Integer)
    member_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    definition_snapshot: Mapped[Any] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    materialized_at: Mapped[dt.datetime] = _now()
    refresh_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_refresh_runs.id", ondelete="SET NULL")
    )


class AnalysisCohortMember(Base):
    """One crash in one version of one cohort.

    The analysis variables are copied onto the row rather than joined from
    ``crashes``: a statistic must describe the population as it was when the
    cohort was materialized, and joining live would let an operational edit
    silently change an already-reported result.
    """

    __tablename__ = "analysis_cohort_members"
    id: Mapped[uuid.UUID] = PK()
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_cohort_versions.id", ondelete="CASCADE")
    )
    crash_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crashes.id", ondelete="SET NULL")
    )
    ccfp_identifier: Mapped[Optional[str]] = mapped_column(Text)
    state_code: Mapped[Optional[str]] = mapped_column(CHAR(2))
    county: Mapped[Optional[str]] = mapped_column(Text)
    crash_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    crash_year: Mapped[Optional[int]] = mapped_column(Integer)
    crash_month: Mapped[Optional[int]] = mapped_column(Integer)
    lifecycle_phase: Mapped[Optional[str]] = mapped_column(Text)
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    num_fatalities: Mapped[Optional[int]] = mapped_column(Integer)
    num_vehicles: Mapped[Optional[int]] = mapped_column(Integer)
    num_persons: Mapped[Optional[int]] = mapped_column(Integer)
    is_fatal: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    scope: Mapped[Optional[str]] = mapped_column(Text)
    is_qualifying: Mapped[Optional[bool]] = mapped_column(Boolean)
    factors: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    factor_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))


class AnalysisInvestigation(Base):
    """A saved, re-runnable analytical investigation.

    Stores the METHOD and its PARAMETERS, never a captured result: re-running a
    saved investigation against a newer cohort version is the point, and a frozen
    result would go stale the moment the environment refreshed. Reproducibility
    comes from the cohort version stamped on each result.
    """

    __tablename__ = "analysis_investigations"
    id: Mapped[uuid.UUID] = PK()
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_environments.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String)
    parameters: Mapped[Any] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    visibility: Mapped[str] = mapped_column(String, server_default=text("'TEAM'"))
    status: Mapped[str] = mapped_column(String, server_default=text("'ACTIVE'"))
    last_run_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
