"""ANAL-9: per-report open-data metadata on the public outputs + ``data.json`` catalog.

Each published, de-identified, PUBLIC report may now carry its own open-data
metadata in dedicated columns (``license``, ``keywords`` (TEXT[]), ``publisher``,
``contact_name``, ``contact_email``, ``update_cadence``). The public DTO and the
Project Open Data ``data.json`` catalog surface those per-report values, falling
back to program-level defaults when a column is NULL. The catalog stays scoped to
published + de-identified + PUBLIC reports (no internal/FEDERAL/STATE leakage).

All requests run through the shared ``client`` fixture, which is bound to a single
rolled-back transaction (see conftest.py); reports inserted via the ``db`` fixture
share that connection and are visible to ``client`` requests but never persist, so
the live database is never mutated and assertions are robust to seed drift.
"""
from __future__ import annotations

import datetime as dt
import uuid

from app.models import Report
from tests.conftest import PROJECT

API = "/api/v1"

# Program-level open-data defaults (mirror app/features/public.py). Used to assert
# the NULL-column fallback without coupling the test to the exact constant values
# beyond the markers that must be present.
_DEFAULT_LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"
_DEFAULT_PUBLISHER = "FMCSA Crash Causal Factors Program"


def _add_published_report(db, **overrides) -> Report:
    """Insert a published + de-identified + PUBLIC report inside the test txn.

    Any open-data column may be overridden; unset columns stay NULL so the
    program-level fallback path is exercised.
    """
    fields: dict = {
        "name": "ANAL-9 Probe Output",
        "report_type": "TABLE",
        "description": "Probe output for open-data metadata.",
        "definition": {"columns": ["a", "b"], "rows": [{"a": 1, "b": 2}]},
        "visibility": "PUBLIC",
        "is_published": True,
        "is_deidentified": True,
        "published_at": dt.datetime.now(dt.timezone.utc),
    }
    fields.update(overrides)
    report = Report(**fields)
    db.add(report)
    db.flush()
    return report


def _catalog_entry(catalog: dict, identifier: str) -> dict:
    match = [d for d in catalog["dataset"] if d["identifier"] == identifier]
    assert match, f"{identifier} not found in catalog"
    return match[0]


# --------------------------------------------------------------------------- no auth / shape
def test_catalog_no_auth_pod_shape(client):
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
        assert dataset["license"]
        assert dataset["publisher"]["name"]
        assert dataset["contactPoint"]["fn"]
        assert dataset["contactPoint"]["hasEmail"].startswith("mailto:")
        assert dataset["accrualPeriodicity"]
        assert isinstance(dataset["keyword"], list) and dataset["keyword"]
        download_urls = [d["downloadURL"] for d in dataset["distribution"]]
        assert any(u == f"{API}/public/reports/{dataset['identifier']}" for u in download_urls)
        assert any(u.endswith("/download") for u in download_urls)


def test_outputs_carry_open_data_metadata(client):
    """Every public output DTO advertises license / publisher / contact / cadence / keywords."""
    outputs = client.get(f"{API}/public/outputs").json()
    assert outputs, "expected at least one published public output in seeds"
    first = outputs[0]
    assert first["license"]
    assert first["publisher"]
    assert first["contact_email"]
    assert first["update_cadence"]
    assert isinstance(first["keywords"], list) and first["keywords"]


# --------------------------------------------------------------------------- per-report override
def test_per_report_metadata_surfaces_on_outputs(client, db):
    """A report's own open-data columns win over the program defaults on /outputs."""
    report = _add_published_report(
        db,
        name="State-Provided Open Dataset",
        license="https://opendatacommons.org/licenses/odbl/1-0/",
        keywords=["kansas", "fatal", "class 8"],
        publisher="Kansas Department of Transportation",
        contact_name="KDOT Data Office",
        contact_email="data@kdot.example.gov",
        update_cadence="R/P1M",
    )

    outputs = client.get(f"{API}/public/outputs").json()
    entry = next(o for o in outputs if o["id"] == str(report.id))
    assert entry["license"] == "https://opendatacommons.org/licenses/odbl/1-0/"
    assert entry["keywords"] == ["kansas", "fatal", "class 8"]
    assert entry["publisher"] == "Kansas Department of Transportation"
    assert entry["contact_name"] == "KDOT Data Office"
    assert entry["contact_email"] == "data@kdot.example.gov"
    assert entry["update_cadence"] == "R/P1M"


def test_per_report_metadata_surfaces_in_catalog(client, db):
    """Per-report columns map into the POD dataset fields (keywords->keyword,
    update_cadence->accrualPeriodicity, contact->contactPoint, etc.)."""
    report = _add_published_report(
        db,
        name="State-Provided Catalog Dataset",
        license="https://opendatacommons.org/licenses/odbl/1-0/",
        keywords=["kansas", "fatal"],
        publisher="Kansas Department of Transportation",
        contact_name="KDOT Data Office",
        contact_email="data@kdot.example.gov",
        update_cadence="R/P1M",
    )

    catalog = client.get(f"{API}/public/data.json").json()
    entry = _catalog_entry(catalog, str(report.id))
    assert entry["title"] == "State-Provided Catalog Dataset"
    assert entry["license"] == "https://opendatacommons.org/licenses/odbl/1-0/"
    assert entry["keyword"] == ["kansas", "fatal"]
    assert entry["publisher"]["name"] == "Kansas Department of Transportation"
    assert entry["contactPoint"]["fn"] == "KDOT Data Office"
    assert entry["contactPoint"]["hasEmail"] == "mailto:data@kdot.example.gov"
    assert entry["accrualPeriodicity"] == "R/P1M"
    # published_at maps to ``modified``.
    assert entry.get("modified")


# --------------------------------------------------------------------------- NULL-column fallback
def test_null_columns_fall_back_to_program_defaults(client, db):
    """A published report with NULL metadata columns advertises the program defaults."""
    report = _add_published_report(db, name="Bare Output (no metadata columns)")

    outputs = client.get(f"{API}/public/outputs").json()
    entry = next(o for o in outputs if o["id"] == str(report.id))
    assert entry["license"] == _DEFAULT_LICENSE
    assert entry["publisher"] == _DEFAULT_PUBLISHER
    assert entry["contact_email"]  # default contact present
    assert entry["update_cadence"]  # default cadence present
    assert isinstance(entry["keywords"], list) and entry["keywords"]  # derived defaults

    catalog = client.get(f"{API}/public/data.json").json()
    cat_entry = _catalog_entry(catalog, str(report.id))
    assert cat_entry["license"] == _DEFAULT_LICENSE
    assert cat_entry["publisher"]["name"] == _DEFAULT_PUBLISHER
    assert isinstance(cat_entry["keyword"], list) and cat_entry["keyword"]


# --------------------------------------------------------------------------- exclusion / leakage
def test_catalog_lists_only_published_public_reports(client, db):
    """Catalog ids exactly equal the published-public outputs set (no leakage)."""
    # Add one of each kind that must NOT appear, plus one that must.
    included = _add_published_report(db, name="Included Public Output")
    private = _add_published_report(
        db, name="Excluded Private", visibility="PRIVATE", is_published=False
    )
    federal = _add_published_report(
        db, name="Excluded Federal", visibility="FEDERAL"
    )
    not_deid = _add_published_report(
        db, name="Excluded Not De-identified", is_deidentified=False
    )

    outputs = client.get(f"{API}/public/outputs").json()
    output_ids = {o["id"] for o in outputs}

    catalog = client.get(f"{API}/public/data.json").json()
    catalog_ids = {d["identifier"] for d in catalog["dataset"]}

    assert catalog_ids == output_ids
    assert len(catalog["dataset"]) == len(outputs)
    assert str(included.id) in catalog_ids
    for hidden in (private, federal, not_deid):
        assert str(hidden.id) not in catalog_ids


def test_create_private_report_via_api_is_not_catalogued(client, auth):
    """A PRIVATE report created through the API never surfaces in the public catalog."""
    resp = client.post(
        f"{API}/reports",
        headers=auth(PROJECT),
        json={
            "name": "API Private Report",
            "report_type": "TABLE",
            "visibility": "PRIVATE",
            "definition": {"columns": ["a"], "rows": [{"a": 1}]},
        },
    )
    assert resp.status_code == 201, resp.text
    private_id = resp.json()["id"]

    catalog = client.get(f"{API}/public/data.json").json()
    catalog_ids = {d["identifier"] for d in catalog["dataset"]}
    assert private_id not in catalog_ids


# --------------------------------------------------------------------------- distribution URLs
def test_distribution_points_at_public_detail_and_download(client, db):
    """Each dataset's distribution links the existing public JSON detail + CSV download."""
    report = _add_published_report(db, name="Distribution Probe")
    catalog = client.get(f"{API}/public/data.json").json()
    entry = _catalog_entry(catalog, str(report.id))
    urls = [d["downloadURL"] for d in entry["distribution"]]
    assert f"{API}/public/reports/{report.id}" in urls
    assert f"{API}/public/reports/{report.id}/download" in urls
