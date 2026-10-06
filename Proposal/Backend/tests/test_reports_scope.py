"""Tests for report access scoping (ANAL-5) and CSV download rendering (ANAL-10).

All requests run through the shared ``client`` fixture, which is bound to a single
rolled-back transaction (see conftest.py), so the live database is never mutated.

Role/permission notes (from seeds/0002_rbac_orgs_users.sql):
  * PROJECT (dana.whitfield, CCFP_PROJECT_TEAM) holds report:create + report:read
    + report:download — used as the report owner/creator.
  * ANALYST_KS (elliot.fontaine, STATE_CMV_ANALYST) holds report:read only — used
    as the non-owner who may hit the endpoint but must not see a PRIVATE report.
"""
from __future__ import annotations

import csv
import io

from tests.conftest import ANALYST_KS, PROJECT

API = "/api/v1"


def _create_private_report(client, headers, name="Scope Test Private Report"):
    resp = client.post(
        f"{API}/reports",
        headers=headers,
        json={
            "name": name,
            "report_type": "TABLE",
            "visibility": "PRIVATE",
            "definition": {"columns": ["a", "b"], "rows": [{"a": 1, "b": 2}]},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- ANAL-5


def test_get_private_report_hidden_from_non_owner_returns_404(client, auth):
    """A report:read user who is not the owner (and has no share) gets 404 — the
    single GET enforces the same visibility scoping as the list endpoint."""
    owner = auth(PROJECT)
    report = _create_private_report(client, owner)

    other = auth(ANALYST_KS)
    resp = client.get(f"{API}/reports/{report['id']}", headers=other)
    assert resp.status_code == 404, resp.text


def test_owner_can_get_own_private_report(client, auth):
    """The owner can still fetch their own PRIVATE report (200)."""
    owner = auth(PROJECT)
    report = _create_private_report(client, owner)

    resp = client.get(f"{API}/reports/{report['id']}", headers=owner)
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == report["id"]


def test_published_report_visible_to_any_reader(client, auth):
    """Published reports remain visible to any report:read user via _visible_filter."""
    reader = auth(ANALYST_KS)
    # Pull a published report id from the public open-data feed (no auth needed).
    outputs = client.get(f"{API}/public/outputs").json()
    assert outputs, "expected at least one published, de-identified public output in seeds"
    published_id = outputs[0]["id"]

    resp = client.get(f"{API}/reports/{published_id}", headers=reader)
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == published_id


def test_get_unknown_report_returns_404(client, auth):
    """An id that does not exist is also a 404 (no existence disclosure)."""
    resp = client.get(
        f"{API}/reports/00000000-0000-0000-0000-000000000000", headers=auth(PROJECT)
    )
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------- ANAL-10


def test_download_returns_csv_attachment(client, auth):
    """Downloading a report yields a text/csv attachment whose body parses as CSV."""
    owner = auth(PROJECT)
    report = _create_private_report(client, owner, name="CSV Download Report")

    resp = client.get(f"{API}/reports/{report['id']}/download", headers=owner)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv"), resp.headers
    assert "attachment" in resp.headers.get("content-disposition", "").lower()

    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) >= 1
    # The leading header block names the report.
    assert any("CSV Download Report" in cell for row in rows for cell in row)
    # The tabular rows carry the column header derived from the definition.
    flat = [cell for row in rows for cell in row]
    assert "a" in flat and "b" in flat


def test_download_table_rows_rendered(client, auth):
    """The {columns, rows} definition shape is rendered as a header row + data rows."""
    owner = auth(PROJECT)
    resp = client.post(
        f"{API}/reports",
        headers=owner,
        json={
            "name": "Tabular Report",
            "report_type": "TABLE",
            "visibility": "PRIVATE",
            "definition": {
                "columns": ["state", "count"],
                "rows": [{"state": "KS", "count": 3}, {"state": "TX", "count": 5}],
            },
        },
    )
    assert resp.status_code == 201, resp.text
    report_id = resp.json()["id"]

    dl = client.get(f"{API}/reports/{report_id}/download", headers=owner)
    assert dl.status_code == 200, dl.text
    text = dl.text
    assert "state,count" in text.replace(" ", "")
    assert "KS" in text and "TX" in text


# ----------------------------------------------------------------- ANAL-10 public download


def test_public_report_download_returns_csv(client):
    """A published, de-identified, PUBLIC report downloads as CSV with no auth."""
    outputs = client.get(f"{API}/public/outputs").json()
    assert outputs, "expected at least one published public output in seeds"
    published_id = outputs[0]["id"]

    resp = client.get(f"{API}/public/reports/{published_id}/download")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv"), resp.headers
    assert "attachment" in resp.headers.get("content-disposition", "").lower()
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) >= 1


def test_public_report_download_unpublished_returns_404(client, auth):
    """A non-published (PRIVATE) report is not downloadable via the public route."""
    private = _create_private_report(client, auth(PROJECT), name="Not Public")
    resp = client.get(f"{API}/public/reports/{private['id']}/download")
    assert resp.status_code == 404, resp.text
