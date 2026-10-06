"""PCR-6: per-State PCR coverage is *derived* from collected per-attribute facts.

§8.5 / §19.3 — section coverage counts (required_collected / total_required /
optional_collected / total_optional) and completion_pct must reflect the actual
collected data (study-scoped ``attribute_requirements`` for the denominators and
live ``crash_attribute_values`` for the numerators), not the static seed values
that were inserted verbatim into ``state_pcr_coverage``.

Every test runs inside the rolled-back transaction provided by the ``db``/``client``
fixtures, so any rows added here are discarded on teardown.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import (
    AttributeRequirement,
    Crash,
    CrashAttributeValue,
    DataAttribute,
    Study,
)
from tests.conftest import ANALYST_KS, ANALYST_TX

API = "/api/v1"


def _study_id(client, headers) -> str:
    return next(
        s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT"
    )["id"]


def _crash_section(client, headers, study_id, *, state="KS"):
    cov = client.get(
        f"{API}/studies/{study_id}/pcr-coverage?state={state}", headers=headers
    ).json()
    return next(c for c in cov if c["pcr_section_code"] == "CRASH")


def _derive_crash_counts(db, study_id):
    """Compute expected CRASH (total_required, required_collected) for KS from raw data."""
    total_required = len(
        db.scalars(
            select(DataAttribute.id)
            .join(
                AttributeRequirement,
                (AttributeRequirement.attribute_id == DataAttribute.id)
                & (AttributeRequirement.study_id == study_id)
                & (AttributeRequirement.is_required.is_(True)),
            )
            .where(DataAttribute.pcr_section == "CRASH")
        ).all()
    )
    required_collected = len(
        set(
            db.scalars(
                select(DataAttribute.id)
                .join(CrashAttributeValue, CrashAttributeValue.attribute_id == DataAttribute.id)
                .join(Crash, Crash.id == CrashAttributeValue.crash_id)
                .join(
                    AttributeRequirement,
                    (AttributeRequirement.attribute_id == DataAttribute.id)
                    & (AttributeRequirement.study_id == study_id)
                    & (AttributeRequirement.is_required.is_(True)),
                )
                .where(
                    Crash.study_id == study_id,
                    Crash.state_code == "KS",
                    CrashAttributeValue.is_current.is_(True),
                    DataAttribute.pcr_section == "CRASH",
                )
            ).all()
        )
    )
    return total_required, required_collected


# --------------------------------------------------------------------------- derivation
def test_coverage_counts_are_derived_not_seeded(client, auth, db):
    """CRASH counts/percentage come from real collected data, not the seed VALUES list."""
    h = auth(ANALYST_KS)
    study_id = _study_id(client, h)
    total_required, required_collected = _derive_crash_counts(db, study_id)

    crash = _crash_section(client, h, study_id)
    # Denominator equals the study-scoped required-attribute count for the section,
    # NOT the inflated static seed total (202).
    assert crash["total_required"] == total_required
    assert crash["total_required"] != 202
    # Numerator equals distinct required attributes that are actually collected for KS,
    # NOT the static seed value (129).
    assert crash["required_collected"] == required_collected
    assert crash["required_collected"] != 129
    # completion_pct follows the derived counts (generated-column formula), not 63.86.
    expected = round(required_collected * 100.0 / total_required, 2)
    assert float(crash["completion_pct"]) == expected
    assert float(crash["completion_pct"]) != 63.86
    # Collected can never exceed the (now truthful) total.
    assert crash["required_collected"] <= crash["total_required"]


def test_collecting_a_required_attribute_raises_completion(client, auth, db):
    """Adding a current value for a not-yet-collected required CRASH attribute must
    increase required_collected and therefore completion_pct on the next GET."""
    h = auth(ANALYST_KS)
    study_id = _study_id(client, h)

    before = _crash_section(client, h, study_id)

    # Find a KS crash and a required CRASH attribute that is NOT yet collected for it.
    crash = db.scalar(
        select(Crash).where(Crash.study_id == study_id, Crash.state_code == "KS").limit(1)
    )
    assert crash is not None
    collected_ids = set(
        db.scalars(
            select(CrashAttributeValue.attribute_id).where(
                CrashAttributeValue.crash_id == crash.id,
                CrashAttributeValue.is_current.is_(True),
            )
        ).all()
    )
    target = db.scalar(
        select(DataAttribute)
        .join(
            AttributeRequirement,
            (AttributeRequirement.attribute_id == DataAttribute.id)
            & (AttributeRequirement.study_id == study_id)
            & (AttributeRequirement.is_required.is_(True)),
        )
        .where(DataAttribute.pcr_section == "CRASH", DataAttribute.id.not_in(collected_ids or [crash.id]))
        .limit(1)
    )
    assert target is not None, "expected an uncollected required CRASH attribute to exist"

    db.add(
        CrashAttributeValue(
            crash_id=crash.id, attribute_id=target.id, value_text="x", is_current=True
        )
    )
    db.flush()

    after = _crash_section(client, h, study_id)
    assert after["required_collected"] == before["required_collected"] + 1
    assert after["total_required"] == before["total_required"]  # denominator unchanged
    assert float(after["completion_pct"]) > float(before["completion_pct"])


# --------------------------------------------------------------------------- scope / authz
def test_state_scope_isolation_tx_sees_no_ks_rows(client, auth):
    """A TX-scoped analyst is scoped to its own State and must not see KS coverage
    rows when no explicit ?state filter is supplied (server-side allowed_states
    guard at studies.py:395-398, preserved by this change)."""
    htx = auth(ANALYST_TX)
    study_id = _study_id(client, htx)
    cov = client.get(f"{API}/studies/{study_id}/pcr-coverage", headers=htx).json()
    assert all(c["state_code"] == "TX" for c in cov)
    assert not any(c["state_code"] == "KS" for c in cov)

    # This previously asserted `cov == []`, which held only because the seed
    # carried coverage rows for KS alone. That is an incidental property of the
    # fixture data, not the security property under test: it would pass just as
    # happily if the endpoint returned nothing at all, and it fails the moment
    # any other State is onboarded — as happened when TX gained coverage rows.
    #
    # Assert the isolation itself instead. A KS analyst must see KS rows and no
    # TX rows, mirroring the TX case above, so the test proves each analyst sees
    # their OWN State rather than proving one of them sees nothing.
    hks = auth(ANALYST_KS)
    cov_ks = client.get(f"{API}/studies/{study_id}/pcr-coverage", headers=hks).json()
    assert all(c["state_code"] == "KS" for c in cov_ks)
    assert not any(c["state_code"] == "TX" for c in cov_ks)
    # Neither analyst's rows may leak into the other's result set.
    assert {c["pcr_section_code"] for c in cov} and {c["pcr_section_code"] for c in cov_ks}


def test_unauthenticated_request_rejected(client):
    """PCR coverage requires authentication (no anonymous access)."""
    study_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"{API}/studies/{study_id}/pcr-coverage")
    assert resp.status_code == 401
