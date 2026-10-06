"""Mock external-integration adapters (SafeSpect, CDLIS, MCMIS, eRODS).

Deterministic, side-effect-free responses suitable for development and testing.
Replace each `*Adapter` with a real client and flip the corresponding
`integration_*_live` flag in config to go live; callers are unaffected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings

_DOT_RE = re.compile(r"^[0-9]{1,8}$")


@dataclass
class AdapterStatus:
    name: str
    live: bool
    description: str


class SafeSpectAdapter:
    """U.S. DOT number validation + inspection data (documentation §13.1)."""

    name = "SafeSpect"

    @property
    def live(self) -> bool:
        return settings.integration_safespect_live

    def validate_dot(self, dot_number: str | None) -> dict:
        if self.live:  # pragma: no cover - real client not configured here
            raise NotImplementedError("Live SafeSpect client not configured")
        valid = bool(dot_number and _DOT_RE.match(dot_number))
        return {
            "dot_number": dot_number,
            "valid": valid,
            "source": "SafeSpect (mock)",
            "carrier_name": f"Carrier #{dot_number}" if valid else None,
            "status": "ACTIVE" if valid else "NOT_FOUND",
        }

    def inspections(self, dot_number: str | None = None, crash_reference: str | None = None) -> dict:
        """Post-crash inspection records held in SafeSpect.

        The BRD names "SafeSpect Inspections" as a data source in its own right —
        inspection data for vehicles, drivers, carriers, cargo, and enforcement
        actions — separate from U.S. DOT number validation. It is also the worked
        example in the definition of linked/aggregated crash data, so the
        aggregation pipeline needs a retrieval call to hang off.

        Read-only by contract: the specification states that these capabilities
        "will not modify original data from CCFP (SafeSpect) or any other
        system", so this adapter exposes no mutating method.
        """
        if self.live:  # pragma: no cover - real client not configured here
            raise NotImplementedError("Live SafeSpect client not configured")
        return {
            "dot_number": dot_number,
            "crash_reference": crash_reference,
            "found": bool(dot_number or crash_reference),
            "inspections": [],
            "source": "SafeSpect Inspections (mock)",
        }


class SafeSpectIdentityAdapter:
    """Translates SafeSpect roles into CCFP roles.

    The SOO requires "role-based access aligned with the hierarchy of roles
    established in SafeSpect". CCFP's own role codes were derived from the BRD's
    prose list of users, so they are almost certainly not SafeSpect's names.

    This is an anti-corruption layer: SafeSpect's vocabulary is translated at the
    boundary and never leaks into the rest of the application. Everything inland
    keeps speaking CCFP role codes, so if SafeSpect renames or restructures its
    roles only this mapping changes.

    The mapping below is a PLACEHOLDER. FMCSA has not yet supplied the SafeSpect
    role list — that is Task 2 Discovery work in the SOO — so the entries are
    inferred from the role names both systems plainly share, and the table is
    data-driven precisely so it can be replaced wholesale without touching
    calling code. `unmapped` is returned rather than silently dropped: an
    unrecognised SafeSpect role must be visible, never quietly granted or denied.
    """

    name = "SafeSpect Identity"

    # SafeSpect role name -> CCFP role code. Replace once the real hierarchy
    # arrives; nothing outside this class depends on its contents.
    ROLE_MAP: dict[str, str] = {
        "MCSAP_INSPECTOR": "MCSAP_INSPECTOR",
        "STATE_ANALYST": "STATE_CMV_ANALYST",
        "STATE_VIEWER": "STATE_USER",
        "FMCSA_HQ": "FEDERAL_USER",
        "FMCSA_ENFORCEMENT": "FEDERAL_USER",
        "SYSTEM_ADMIN": "SYSTEM_ADMIN",
    }

    @property
    def live(self) -> bool:
        return settings.integration_safespect_live

    def map_roles(self, safespect_roles: list[str] | None) -> dict:
        """Map SafeSpect role names onto CCFP role codes.

        Returns both the resolved codes and the roles that had no mapping, so a
        caller can surface a configuration gap instead of inheriting a silent
        privilege change.
        """
        incoming = [r for r in (safespect_roles or []) if r]
        mapped: list[str] = []
        unmapped: list[str] = []
        for role in incoming:
            ccfp = self.ROLE_MAP.get(role.strip().upper())
            if ccfp:
                if ccfp not in mapped:
                    mapped.append(ccfp)
            else:
                unmapped.append(role)
        return {
            "safespect_roles": incoming,
            "ccfp_role_codes": mapped,
            "unmapped": unmapped,
            "source": "SafeSpect Identity (mock)",
        }


class CdlisAdapter:
    """Commercial Driver's License Information System (documentation §13.2)."""

    name = "CDLIS"

    @property
    def live(self) -> bool:
        return settings.integration_cdlis_live

    def verify_driver(self, license_number: str | None, jurisdiction: str | None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live CDLIS client not configured")
        valid = bool(license_number)
        return {
            "license_number": license_number,
            "jurisdiction": jurisdiction,
            "valid": valid,
            "license_status": "VALID" if valid else "UNKNOWN",
            "source": "CDLIS (mock)",
        }


class McmisAdapter:
    """Motor Carrier Management Information System crash/inspection lookup."""

    name = "MCMIS"

    @property
    def live(self) -> bool:
        return settings.integration_mcmis_live

    def lookup_crash(self, local_report_number: str | None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live MCMIS client not configured")
        return {
            "local_report_number": local_report_number,
            "found": bool(local_report_number),
            "records": [],
            "source": "MCMIS (mock)",
        }


class ErodsAdapter:
    """Electronic Record of Duty Status reference (documentation §13.1)."""

    name = "eRODS"

    @property
    def live(self) -> bool:
        return settings.integration_erods_live

    def reference(self, ccfp_code: str | None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live eRODS client not configured")
        return {"ccfp_code": ccfp_code, "available": bool(ccfp_code), "source": "eRODS (mock)"}


class ClearinghouseAdapter:
    """FMCSA Drug and Alcohol Clearinghouse (Appendix D; SOO "integrate and match").

    The BRD names this source twice — in Appendix D and, unusually, inside the
    Aggregated Data requirement itself ("linking raw CCFP crash data and data
    from external systems (e.g., SafeSpect Inspections, Drug and Alcohol
    Clearinghouse, etc.)"). It is the worked example alongside SafeSpect, so the
    aggregation pipeline needs a retrieval call to hang off.

    Read-only by contract, like every adapter here: the specification states the
    core capabilities "will not modify original data from CCFP (SafeSpect) or any
    other system".

    Returns a violation *summary*, never the underlying record. A Clearinghouse
    result is among the most sensitive facts the programme can hold about a
    driver; the aggregation layer needs to know whether a resolved violation
    exists, not to copy the substance of it into the data lake.
    """

    name = "Drug and Alcohol Clearinghouse"

    @property
    def live(self) -> bool:
        return settings.integration_clearinghouse_live

    def driver_status(self, license_number: str | None, jurisdiction: str | None = None) -> dict:
        if self.live:  # pragma: no cover - real client not configured here
            raise NotImplementedError("Live Clearinghouse client not configured")
        known = bool(license_number)
        return {
            "license_number": license_number,
            "jurisdiction": jurisdiction,
            "found": known,
            # Deterministic mock: no violations. A mock that invented a positive
            # drug-and-alcohol finding against a synthetic driver would be a
            # fabricated derogatory record, which is not a safe default.
            "prohibited_status": "NOT_PROHIBITED" if known else "UNKNOWN",
            "violation_count": 0,
            "source": "Drug and Alcohol Clearinghouse (mock)",
        }


class DriverInformationResourceAdapter:
    """FMCSA Driver Information Resource (Appendix D; named in the SOO).

    Consolidated driver history the SOO lists beside eRODS and the Clearinghouse
    as an internal source to "integrate and match".
    """

    name = "Driver Information Resource"

    @property
    def live(self) -> bool:
        return settings.integration_dir_live

    def driver_history(self, license_number: str | None, jurisdiction: str | None = None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live DIR client not configured")
        return {
            "license_number": license_number,
            "jurisdiction": jurisdiction,
            "found": bool(license_number),
            "crash_history": [],
            "inspection_history": [],
            "source": "Driver Information Resource (mock)",
        }


class SafetyMeasurementAdapter:
    """Carrier safety percentiles from SMS / the Driver Safety Measurement System.

    Appendix D lists both; they answer the same question at different subjects
    (carrier vs driver), so one adapter exposes both rather than duplicating the
    live-flag and error handling twice.
    """

    name = "Safety Measurement System"

    @property
    def live(self) -> bool:
        return settings.integration_sms_live

    def carrier_scores(self, dot_number: str | None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live SMS client not configured")
        return {
            "dot_number": dot_number,
            "found": bool(dot_number),
            "basic_percentiles": {},
            "source": "Safety Measurement System (mock)",
        }

    def driver_scores(self, license_number: str | None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live DSMS client not configured")
        return {
            "license_number": license_number,
            "found": bool(license_number),
            "percentiles": {},
            "source": "Driver Safety Measurement System (mock)",
        }


class MedicalExaminersAdapter:
    """National Registry of Certified Medical Examiners (Appendix D).

    Appendix D's relevant-data column is "driver medical certificate
    information" — the certificate's validity and expiry, not the medical
    findings behind it, which the programme has no basis to hold.
    """

    name = "National Registry of Certified Medical Examiners"

    @property
    def live(self) -> bool:
        return settings.integration_nrcme_live

    def certificate(self, license_number: str | None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live NRCME client not configured")
        known = bool(license_number)
        return {
            "license_number": license_number,
            "found": known,
            "certificate_status": "UNKNOWN" if not known else "NOT_ON_FILE",
            "expires_on": None,
            "source": "National Registry of Certified Medical Examiners (mock)",
        }


class DataQsAdapter:
    """DataQs — challenges raised against FMCSA-held records (Appendix D).

    Relevant to CCFP because an open challenge means a source record backing a
    crash may change. Surfacing that is the point: analysis built on a contested
    record should be traceable to the contest.
    """

    name = "DataQs"

    @property
    def live(self) -> bool:
        return settings.integration_dataqs_live

    def challenges(self, dot_number: str | None = None, local_report_number: str | None = None) -> dict:
        if self.live:  # pragma: no cover
            raise NotImplementedError("Live DataQs client not configured")
        return {
            "dot_number": dot_number,
            "local_report_number": local_report_number,
            "found": bool(dot_number or local_report_number),
            "open_challenges": [],
            "source": "DataQs (mock)",
        }


safespect = SafeSpectAdapter()
safespect_identity = SafeSpectIdentityAdapter()
cdlis = CdlisAdapter()
mcmis = McmisAdapter()
erods = ErodsAdapter()
clearinghouse = ClearinghouseAdapter()
driver_information = DriverInformationResourceAdapter()
safety_measurement = SafetyMeasurementAdapter()
medical_examiners = MedicalExaminersAdapter()
dataqs = DataQsAdapter()


def registry() -> list[AdapterStatus]:
    return [
        AdapterStatus(safespect.name, safespect.live, "U.S. DOT validation & inspection data"),
        AdapterStatus(
            safespect_identity.name,
            safespect_identity.live,
            "SafeSpect role -> CCFP role mapping (awaiting FMCSA role hierarchy)",
        ),
        AdapterStatus(cdlis.name, cdlis.live, "CDL driver verification"),
        AdapterStatus(mcmis.name, mcmis.live, "FMCSA crash/inspection records"),
        AdapterStatus(erods.name, erods.live, "ELD/eRODS hours-of-service reference"),
        # Appendix D sources named by the January 2026 BRD and the SOO.
        AdapterStatus(clearinghouse.name, clearinghouse.live, "Driver drug & alcohol prohibited status"),
        AdapterStatus(driver_information.name, driver_information.live, "Consolidated driver crash/inspection history"),
        AdapterStatus(safety_measurement.name, safety_measurement.live, "Carrier (SMS) and driver (DSMS) safety percentiles"),
        AdapterStatus(medical_examiners.name, medical_examiners.live, "Driver medical certificate status"),
        AdapterStatus(dataqs.name, dataqs.live, "Open challenges against FMCSA-held records"),
    ]
