"""STUD-1 — administrable roles, permissions, and role->permission mappings.

Covers the new role-definition CRUD and the set-permissions primitive that the
Roles & permissions admin page calls. Each test runs inside a single rolled-back
transaction (see conftest), so created roles/permissions never leak to the real
DB. ADMIN (avery.thornton) holds `admin:roles`; ANALYST_KS and PUBLIC do not."""
from __future__ import annotations

from tests.conftest import ADMIN, ANALYST_KS, PUBLIC

API = "/api/v1"


def test_admin_creates_role_then_it_lists(client, auth):
    """ADMIN holds admin:roles: POST a unique code -> 201 with is_system False,
    and the new role then appears in GET /roles."""
    h = auth(ADMIN)
    body = {"code": "STUD1_DEMO_ROLE", "name": "STUD-1 Demo Role", "description": "temp"}
    resp = client.post(f"{API}/roles", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["code"] == "STUD1_DEMO_ROLE"
    assert created["name"] == "STUD-1 Demo Role"
    assert created["is_system"] is False
    assert "id" in created

    listing = client.get(f"{API}/roles", headers=h)
    assert listing.status_code == 200, listing.text
    assert any(r["code"] == "STUD1_DEMO_ROLE" for r in listing.json())


def test_set_role_permissions_replaces_mappings(client, auth):
    """PUT /roles/{id}/permissions replaces the role's permission set; the
    role detail then returns exactly the requested codes."""
    h = auth(ADMIN)
    create = client.post(
        f"{API}/roles",
        headers=h,
        json={"code": "STUD1_PERM_ROLE", "name": "STUD-1 Perm Role"},
    )
    assert create.status_code == 201, create.text
    role_id = create.json()["id"]

    resp = client.put(
        f"{API}/roles/{role_id}/permissions",
        headers=h,
        json={"permission_codes": ["crash:read", "report:read"]},
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert {p["code"] for p in detail["permissions"]} == {"crash:read", "report:read"}

    # And the dedicated GET reflects the same two codes (no second round-trip needed).
    fetched = client.get(f"{API}/roles/{role_id}", headers=h)
    assert fetched.status_code == 200, fetched.text
    assert {p["code"] for p in fetched.json()["permissions"]} == {"crash:read", "report:read"}


def test_update_role_changes_name_only(client, auth):
    """PATCH updates name/description (the edit path); code/is_system unchanged."""
    h = auth(ADMIN)
    create = client.post(
        f"{API}/roles", headers=h, json={"code": "STUD1_EDIT_ROLE", "name": "Original"}
    )
    assert create.status_code == 201, create.text
    role_id = create.json()["id"]

    resp = client.patch(f"{API}/roles/{role_id}", headers=h, json={"name": "Renamed"})
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "Renamed"
    assert updated["code"] == "STUD1_EDIT_ROLE"
    assert updated["is_system"] is False


def test_delete_non_system_role(client, auth):
    """A freshly-created (non-system, unassigned) role can be deleted -> 204,
    and afterwards it is gone (404)."""
    h = auth(ADMIN)
    create = client.post(
        f"{API}/roles", headers=h, json={"code": "STUD1_DEL_ROLE", "name": "Disposable"}
    )
    assert create.status_code == 201, create.text
    role_id = create.json()["id"]

    resp = client.delete(f"{API}/roles/{role_id}", headers=h)
    assert resp.status_code == 204, resp.text
    assert client.get(f"{API}/roles/{role_id}", headers=h).status_code == 404


def test_create_permission_then_it_lists(client, auth):
    """POST /permissions creates a catalog entry -> 201; it then lists."""
    h = auth(ADMIN)
    body = {
        "code": "stud1:demo",
        "name": "STUD-1 Demo Permission",
        "category": "admin",
        "description": "temp",
    }
    resp = client.post(f"{API}/permissions", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["code"] == "stud1:demo"

    listing = client.get(f"{API}/permissions", headers=h)
    assert listing.status_code == 200, listing.text
    assert any(p["code"] == "stud1:demo" for p in listing.json())


# --------------------------------------------------------------------------- negatives


def test_non_admin_cannot_create_role(client, auth):
    """Authorization: a State CMV Analyst lacks admin:roles -> 403; so does a
    public user. This is what gates the New role / edit controls server-side."""
    body = {"code": "STUD1_DENIED", "name": "Denied"}
    assert client.post(f"{API}/roles", headers=auth(ANALYST_KS), json=body).status_code == 403
    assert client.post(f"{API}/roles", headers=auth(PUBLIC), json=body).status_code == 403


def test_duplicate_role_code_conflicts(client, auth):
    """Validation: reusing an existing role code -> 409 Conflict."""
    h = auth(ADMIN)
    existing = client.get(f"{API}/roles", headers=h).json()
    assert existing, "expected seeded roles"
    dup_code = existing[0]["code"]
    resp = client.post(f"{API}/roles", headers=h, json={"code": dup_code, "name": "Dup"})
    assert resp.status_code == 409, resp.text


def test_set_permissions_rejects_unknown_code(client, auth):
    """Validation: an unknown permission code -> 400 BadRequest."""
    h = auth(ADMIN)
    create = client.post(
        f"{API}/roles", headers=h, json={"code": "STUD1_BAD_PERM_ROLE", "name": "Bad"}
    )
    assert create.status_code == 201, create.text
    role_id = create.json()["id"]
    resp = client.put(
        f"{API}/roles/{role_id}/permissions",
        headers=h,
        json={"permission_codes": ["nope:nope"]},
    )
    assert resp.status_code == 400, resp.text


def test_cannot_delete_system_role(client, auth):
    """Protection: a seeded is_system role cannot be deleted -> rejected (400/409)."""
    h = auth(ADMIN)
    roles = client.get(f"{API}/roles", headers=h).json()
    system_role = next((r for r in roles if r["is_system"]), None)
    assert system_role is not None, "expected at least one seeded system role"
    resp = client.delete(f"{API}/roles/{system_role['id']}", headers=h)
    assert resp.status_code in (400, 409), resp.text
    # And it is still present afterwards.
    still = client.get(f"{API}/roles/{system_role['id']}", headers=h)
    assert still.status_code == 200
