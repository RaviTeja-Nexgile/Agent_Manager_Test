"""External integration endpoints (documentation §13) — mock adapters."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import require
from app.core.security import CurrentUser, get_current_user
from app.integrations import (
    cdlis,
    clearinghouse,
    dataqs,
    driver_information,
    mcmis,
    medical_examiners,
    registry,
    safespect,
    safety_measurement,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


class DotValidateRequest(BaseModel):
    dot_number: str


class CdlisVerifyRequest(BaseModel):
    license_number: str
    jurisdiction: str | None = None


class McmisLookupRequest(BaseModel):
    local_report_number: str


@router.get("")
def list_integrations(current: CurrentUser = Depends(get_current_user)):
    return {
        "adapters": [
            {"name": a.name, "live": a.live, "mode": "live" if a.live else "mock", "description": a.description}
            for a in registry()
        ]
    }


@router.post("/safespect/validate-dot")
def validate_dot(body: DotValidateRequest, current: CurrentUser = Depends(require("source_data:ingest", "crash:read"))):
    return safespect.validate_dot(body.dot_number)


@router.post("/cdlis/verify")
def verify_cdlis(body: CdlisVerifyRequest, current: CurrentUser = Depends(require("data_mgmt:qc", "source_data:ingest"))):
    return cdlis.verify_driver(body.license_number, body.jurisdiction)


@router.post("/mcmis/lookup")
def lookup_mcmis(body: McmisLookupRequest, current: CurrentUser = Depends(require("source_data:ingest", "crash:read"))):
    return mcmis.lookup_crash(body.local_report_number)


# ---------------------------------------------------------------------------
# Appendix D sources the January 2026 BRD and the SOO name for aggregation.
# All read-only: the specification is explicit that these capabilities "will not
# modify original data from CCFP (SafeSpect) or any other system".
# ---------------------------------------------------------------------------
class DriverLookupRequest(BaseModel):
    license_number: str
    jurisdiction: str | None = None


class CarrierLookupRequest(BaseModel):
    dot_number: str


class DataQsRequest(BaseModel):
    dot_number: str | None = None
    local_report_number: str | None = None


@router.post("/clearinghouse/driver-status")
def clearinghouse_status(
    body: DriverLookupRequest,
    # Drug-and-alcohol prohibited status is among the most sensitive facts the
    # programme can hold about a person, so this is gated on the PII-capable
    # ingest/QC permissions rather than plain crash:read.
    current: CurrentUser = Depends(require("data_mgmt:qc", "source_data:ingest")),
):
    return clearinghouse.driver_status(body.license_number, body.jurisdiction)


@router.post("/driver-information/history")
def driver_information_history(
    body: DriverLookupRequest,
    current: CurrentUser = Depends(require("data_mgmt:qc", "source_data:ingest")),
):
    return driver_information.driver_history(body.license_number, body.jurisdiction)


@router.post("/sms/carrier-scores")
def sms_carrier_scores(
    body: CarrierLookupRequest,
    current: CurrentUser = Depends(require("source_data:ingest", "crash:read")),
):
    return safety_measurement.carrier_scores(body.dot_number)


@router.post("/dsms/driver-scores")
def dsms_driver_scores(
    body: DriverLookupRequest,
    current: CurrentUser = Depends(require("data_mgmt:qc", "source_data:ingest")),
):
    return safety_measurement.driver_scores(body.license_number)


@router.post("/nrcme/certificate")
def nrcme_certificate(
    body: DriverLookupRequest,
    current: CurrentUser = Depends(require("data_mgmt:qc", "source_data:ingest")),
):
    return medical_examiners.certificate(body.license_number)


@router.post("/dataqs/challenges")
def dataqs_challenges(
    body: DataQsRequest,
    current: CurrentUser = Depends(require("source_data:ingest", "crash:read")),
):
    return dataqs.challenges(body.dot_number, body.local_report_number)
