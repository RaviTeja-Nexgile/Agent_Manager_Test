"""External system integration adapters (documentation §13).

Mock implementations behind stable interfaces. Each adapter is feature-flagged
in config; when a `*_live` flag is enabled a real client must be supplied,
otherwise the deterministic mock is used. Callers depend only on the interface.
"""
from app.integrations.adapters import (  # noqa: F401
    cdlis,
    clearinghouse,
    dataqs,
    driver_information,
    erods,
    mcmis,
    medical_examiners,
    registry,
    safespect,
    safety_measurement,
)
