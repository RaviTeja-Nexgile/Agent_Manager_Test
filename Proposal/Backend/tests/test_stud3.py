"""STUD-3 — data-attribute catalog create/edit (the endpoints the new
DataAttributesPage create/edit dialog calls). Each test runs inside a single
rolled-back transaction, so created attributes never leak to the real DB."""
from __future__ import annotations

from tests.conftest import ADMIN, ANALYST_KS, PUBLIC

API = "/api/v1"


def test_admin_creates_attribute_then_it_lists(client, auth):
    """ADMIN holds admin:attributes: POST a unique code -> 201, and the new
    attribute then shows up in the catalog (count increases by exactly one)."""
    h = auth(ADMIN)
    before = client.get(f"{API}/data-attributes", headers=h).json()
    body = {
        "code": "STUD3_DEMO_ATTR",
        "name": "STUD-3 Demo Attribute",
        "category": "crash",
        "pcr_section": "CRASH",
        "data_type": "TEXT",
        "sensitivity": "INTERNAL",
        "description": "Created by the STUD-3 test.",
    }
    resp = client.post(f"{API}/data-attributes", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["code"] == "STUD3_DEMO_ATTR"
    assert created["is_active"] is True
    assert created["data_type"] == "TEXT"
    assert created["sensitivity"] == "INTERNAL"
    assert "id" in created

    after = client.get(f"{API}/data-attributes", headers=h).json()
    assert len(after) == len(before) + 1
    assert any(a["code"] == "STUD3_DEMO_ATTR" for a in after)


def test_admin_edits_attribute(client, auth):
    """PATCH updates the attribute (the dialog's edit path); the full
    DataAttributeIn body overwrites fields including a changed name."""
    h = auth(ADMIN)
    create = client.post(
        f"{API}/data-attributes",
        headers=h,
        json={"code": "STUD3_EDIT_ATTR", "name": "Original", "category": "crash"},
    )
    assert create.status_code == 201, create.text
    attr_id = create.json()["id"]

    resp = client.patch(
        f"{API}/data-attributes/{attr_id}",
        headers=h,
        json={
            "code": "STUD3_EDIT_ATTR",
            "name": "Renamed",
            "category": "crash",
            "data_type": "NUMBER",
            "sensitivity": "PII",
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "Renamed"
    assert updated["data_type"] == "NUMBER"
    assert updated["sensitivity"] == "PII"


def test_non_admin_cannot_create_attribute(client, auth):
    """Authorization: a State CMV Analyst lacks admin:attributes -> 403.
    This is what gates the Add/Edit controls server-side."""
    body = {"code": "STUD3_DENIED", "name": "Denied", "category": "crash"}
    assert client.post(f"{API}/data-attributes", headers=auth(ANALYST_KS), json=body).status_code == 403
    # A public user is likewise denied.
    assert client.post(f"{API}/data-attributes", headers=auth(PUBLIC), json=body).status_code == 403


def test_duplicate_code_conflicts(client, auth):
    """Validation: reusing an existing catalog code -> 409 Conflict, the error
    the dialog surfaces via ApiError.message."""
    h = auth(ADMIN)
    existing = client.get(f"{API}/data-attributes", headers=h).json()
    assert existing, "expected seeded attributes"
    dup_code = existing[0]["code"]
    resp = client.post(
        f"{API}/data-attributes",
        headers=h,
        json={"code": dup_code, "name": "Dup", "category": "crash"},
    )
    assert resp.status_code == 409, resp.text
