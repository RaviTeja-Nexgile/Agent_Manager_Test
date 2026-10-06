"""Tests for the open-data catalog endpoint (ANAL-9).

`GET /api/v1/public/data.json` emits a Project Open Data ``data.json`` catalog of
every published, de-identified, PUBLIC report — no authentication. All requests
run through the shared ``client`` fixture (one rolled-back transaction; see
conftest.py), so the live database is never mutated.
"""
from __future__ import annotations

from tests.conftest import PROJECT

API = "/api/v1"


def _create_private_report(client, headers, name="Open Data Private Report"):
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


# --------------------------------------------------------------------------- shape / no auth


def test_catalog_no_auth_returns_pod_shape(client):
    """The catalog is reachable without auth and conforms to the POD schema shape."""
    resp = client.get(f"{API}/public/data.json")  # no Authorization header
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["conformsTo"] == "https://project-open-data.cio.gov/v1.1/schema"
    assert isinstance(body["dataset"], list)

    for dataset in body["dataset"]:
        assert dataset["title"]
        assert dataset["identifier"]
        assert dataset["accessLevel"] == "public"
        # license / publisher / contactPoint / cadence metadata present
        assert dataset["license"]
        assert dataset["publisher"]["name"]
        assert dataset["contactPoint"]["fn"]
        assert dataset["contactPoint"]["hasEmail"].startswith("mailto:")
        assert dataset["accrualPeriodicity"]
        assert isinstance(dataset["keyword"], list) and dataset["keyword"]
        # distribution entries point at the existing public detail + download URLs
        download_urls = [d["downloadURL"] for d in dataset["distribution"]]
        assert any(
            url == f"{API}/public/reports/{dataset['identifier']}" for url in download_urls
        ), download_urls
        assert any(url.endswith("/download") for url in download_urls), download_urls


def test_catalog_lists_all_published_outputs(client):
    """Every published, de-identified, PUBLIC report appears exactly once in the catalog."""
    outputs = client.get(f"{API}/public/outputs").json()
    assert outputs, "expected at least one published public output in seeds"
    published_ids = {o["id"] for o in outputs}

    catalog = client.get(f"{API}/public/data.json").json()
    catalog_ids = {d["identifier"] for d in catalog["dataset"]}

    assert catalog_ids == published_ids
    assert len(catalog["dataset"]) == len(outputs)


# --------------------------------------------------------------------------- exclusion / leakage


def test_catalog_excludes_private_report(client, auth):
    """A PRIVATE (non-published) report must never surface in the public catalog."""
    private = _create_private_report(client, auth(PROJECT), name="Not In Catalog")

    catalog = client.get(f"{API}/public/data.json").json()
    catalog_ids = {d["identifier"] for d in catalog["dataset"]}
    assert private["id"] not in catalog_ids


# --------------------------------------------------------------------------- metadata on /outputs


def test_public_outputs_carry_open_data_metadata(client):
    """The public outputs DTO now advertises license / keywords / publisher / contact."""
    outputs = client.get(f"{API}/public/outputs").json()
    assert outputs, "expected at least one published public output in seeds"
    first = outputs[0]
    assert first["license"]
    assert first["publisher"]
    assert first["contact_email"]
    assert first["update_cadence"]
    assert isinstance(first["keywords"], list) and first["keywords"]
