"""API tests covering auth, RBAC/scope, CRUD, the crash lifecycle, QC/completeness,
search, and public de-identification. All run inside a rolled-back transaction."""
from __future__ import annotations

from app import workers
from tests.conftest import (
    ADMIN,
    ANALYST_KS,
    ANALYST_TX,
    FEDERAL,
    INSPECTOR_KS,
    PUBLIC,
)

API = "/api/v1"


# --------------------------------------------------------------------------- health & auth
def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/db").json()["database"] == "reachable"


def test_unauthenticated_is_401(client):
    assert client.get(f"{API}/crashes").status_code == 401


def test_login_and_me(client, auth):
    me = client.get(f"{API}/auth/me", headers=auth(ANALYST_KS)).json()
    assert me["roles"] == ["STATE_CMV_ANALYST"]
    assert me["allowed_states"] == ["KS"]
    assert "crash:read" in me["permissions"]


def test_unknown_user_login_rejected(client):
    resp = client.post(f"{API}/auth/login", json={"email": "nobody@ccfp.gov", "password": "Second@123"})
    assert resp.status_code == 401


def test_wrong_password_rejected(client):
    resp = client.post(f"{API}/auth/login", json={"email": ANALYST_KS, "password": "not-the-password"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------- RBAC & scope
def test_public_user_denied_crashes(client, auth):
    assert client.get(f"{API}/crashes", headers=auth(PUBLIC)).status_code == 403


def test_state_scope_filtering(client, auth):
    ks = client.get(f"{API}/crashes", headers=auth(ANALYST_KS)).json()
    # Assert the State-isolation invariant (a KS-scoped analyst sees only KS
    # crashes), not a hardcoded identifier snapshot that drifts as seeds grow.
    assert ks["items"]
    assert all(i["state_code"] == "KS" for i in ks["items"])
    tx = client.get(f"{API}/crashes", headers=auth(ANALYST_TX)).json()
    assert all(i["state_code"] == "TX" for i in tx["items"])


def test_federal_sees_all_states(client, auth):
    # Federal user lacks crash:read, so use the project team member for cross-state read.
    me = client.get(f"{API}/auth/me", headers=auth(FEDERAL)).json()
    assert me["allowed_states"] is None  # unrestricted by state


def test_create_crash_denied_without_permission(client, auth):
    body = {"study_id": "00000000-0000-0000-0000-000000000000", "state_code": "KS"}
    assert client.post(f"{API}/crashes", headers=auth(FEDERAL), json=body).status_code == 403


# --------------------------------------------------------------------------- reference & config
def test_studies_and_attributes(client, auth):
    h = auth(ANALYST_KS)
    codes = {s["code"] for s in client.get(f"{API}/studies", headers=h).json()}
    assert "PHASE1-HDT" in codes
    # The catalog lists only attributes the CURRENT specification collects.
    # 109 originally seeded from the old KS worksheet, + 67 added by GAP-PCR-02
    # for the HDTS PCR data form, + 2 added by GAP-PCR-04 for capped elements
    # with no existing code (P44 endorsements, V37 signals) = 178 rows, of which
    # three are retired and hidden by default: DV01 (GAP-PCR-01, section
    # removed), PX2 (GAP-PCR-02, the person-address block the new form splits
    # four ways), and LV05 (GAP-PCR-08, Trailer Model(s), which the new form
    # does not carry).
    attrs = client.get(f"{API}/data-attributes", headers=h).json()
    assert len(attrs) == 175
    assert not any(a["code"] in {"DV01", "PX2", "LV05"} for a in attrs)

    all_attrs = client.get(f"{API}/data-attributes?include_inactive=true", headers=h).json()
    assert len(all_attrs) == 178
    by_code = {a["code"]: a for a in all_attrs}
    assert by_code["DV01"]["is_active"] is False
    # A retired code names its replacement so historical values stay traceable.
    assert by_code["PX2"]["is_active"] is False
    assert by_code["PX2"]["superseded_by_code"] == "P39"
    # LV05 names NO replacement: a model year (LV06) is not a model, and
    # pointing at it would misrepresent where historical values went.
    assert by_code["LV05"]["is_active"] is False
    assert by_code["LV05"]["superseded_by_code"] is None
    assert by_code["LV06"]["is_active"] is True


def test_hdts_pcr_attribute_catalog(client, auth):
    """GAP-PCR-02: new elements, sensitivity, and repeat metadata are seeded."""
    h = auth(ANALYST_KS)
    attrs = {a["code"]: a for a in client.get(f"{API}/data-attributes", headers=h).json()}

    # The public-releasable narrative must be separable from the internal one,
    # or publishing it would be a disclosure incident.
    assert attrs["C31"]["sensitivity"] == "PUBLIC"
    assert attrs["CX1"]["sensitivity"] == "SENSITIVE"

    # Personal identity detail is PII, injury/citation detail is SENSITIVE.
    for code in ("P27", "P35", "F05", "LV12", "LV18", "C35", "P39"):
        assert attrs[code]["sensitivity"] == "PII", code
    for code in ("P34", "P36", "P37", "P38"):
        assert attrs[code]["sensitivity"] == "SENSITIVE", code

    # Whole sections repeat; trailer elements repeat per trailer position.
    assert attrs["V29"]["repeats_on"] == "VEHICLE"
    assert attrs["P43"]["repeats_on"] == "PERSON"
    assert attrs["LV12"]["repeats_on"] == "TRAILER"
    assert attrs["C27"]["repeats_on"] is None      # crash-level stays crash-level

    # Conditional population + cardinality carried on the attribute itself.
    assert attrs["P30"]["applies_to"] == "ALL_DRIVERS"
    assert attrs["P33"]["max_selections"] == 4


def test_pcr_selection_caps(client, auth):
    """GAP-PCR-04: the new form's selection caps are seeded as data."""
    h = auth(ANALYST_KS)
    attrs = {a["code"]: a for a in client.get(f"{API}/data-attributes", headers=h).json()}

    # "Check only 1" is modelled as a cap of 1, not as a single-valued CODE.
    assert attrs["C12"]["max_selections"] == 1     # Light Condition
    assert attrs["C07"]["max_selections"] == 1     # First Harmful Event
    # Caps the new form widened on otherwise-unchanged elements — easy to miss.
    assert attrs["C11"]["max_selections"] == 3     # Weather, was 2
    assert attrs["C14"]["max_selections"] == 6     # Contributing circumstances, was 4
    # Every capped attribute is typed MULTI_CODE, and vice versa.
    capped = {c for c, a in attrs.items() if a["max_selections"] is not None}
    multi = {c for c, a in attrs.items() if a["data_type"] == "MULTI_CODE"}
    assert capped == multi, capped ^ multi


def test_over_cap_write_is_rejected(client, auth):
    """GAP-PCR-04: the cap is enforced at the point of entry, not only in QC."""
    h = auth(ANALYST_KS)
    # A fresh crash has no completeness row, so it is unlocked and accepts
    # attribute writes (the seeded CCFP-2026-KS-000101 is locked).
    study_id = next(
        s for s in client.get(f"{API}/studies", headers=h).json() if s["code"] == "PHASE1-HDT"
    )["id"]
    created = client.post(
        f"{API}/crashes", headers=auth(INSPECTOR_KS),
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka",
              "crash_date": "2026-05-04", "num_fatalities": 1},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]

    over = {"attribute_code": "C11", "value_json": ["RAIN", "FOG", "WIND", "SNOW"]}
    resp = client.post(f"{API}/crashes/{cid}/attributes", headers=h, json=over)
    assert resp.status_code == 400, resp.text
    assert "at most 3" in resp.text

    # Duplicates pass a naive count check but are never meaningful in a
    # check-all-that-apply group.
    dup = {"attribute_code": "C11", "value_json": ["RAIN", "RAIN"]}
    assert client.post(f"{API}/crashes/{cid}/attributes", headers=h, json=dup).status_code == 400

    # At the cap is fine, and a lone scalar counts as one selection.
    okv = {"attribute_code": "C11", "value_json": ["RAIN", "FOG", "WIND"]}
    assert client.post(f"{API}/crashes/{cid}/attributes", headers=h, json=okv).status_code == 201
    one = {"attribute_code": "C12", "value_text": "DAYLIGHT"}
    assert client.post(f"{API}/crashes/{cid}/attributes", headers=h, json=one).status_code == 201


def test_phase1_requires_gvwr(client, auth):
    """GAP-PCR-02: Phase 1 scope is Class 7/8, GVWR >= 26,001 lbs.

    Before this, no attribute carried GVWR at all, so a record could be marked
    complete without ever evidencing the rule that put it in scope.
    """
    h = auth(ANALYST_KS)
    study = next(s for s in client.get(f"{API}/studies", headers=h).json() if s["code"] == "PHASE1-HDT")
    reqs = client.get(f"{API}/studies/{study['id']}/attributes", headers=h).json()
    required = {r["code"] for r in reqs if r["is_required"]}
    assert "V29" in required


def test_pcr_sections_reflect_the_new_form(client, auth):
    """GAP-PCR-01: section set, names, and order match the HDTS PCR data form."""
    h = auth(ANALYST_KS)
    sections = client.get(f"{API}/pcr-sections", headers=h).json()
    assert [s["code"] for s in sections] == [
        "CRASH", "FATAL", "LARGE_VEH_HAZMAT", "PERSON",
        "VEHICLE", "NON_MOTORIST", "ROADWAY", "PRIMARY_CONTRIBUTING_FACTORS",
    ]
    # Names are the form's labels, not humanized codes.
    by_code = {s["code"]: s["name"] for s in sections}
    assert by_code["LARGE_VEH_HAZMAT"] == "Large Vehicle and Hazardous Material (HM) Data Elements"
    assert by_code["CRASH"] == "Crash Data Elements"
    # Dynamic Data Elements was removed by the new form: retired, not deleted.
    assert "DYNAMIC" not in by_code
    with_inactive = client.get(f"{API}/pcr-sections?include_inactive=true", headers=h).json()
    dynamic = next(s for s in with_inactive if s["code"] == "DYNAMIC")
    assert dynamic["is_active"] is False


def test_value_lists_are_versioned(client, auth):
    """GAP-PCR-09b: removed values are retired and traceable, never dropped."""
    h = auth(ANALYST_KS)
    dd = {e["code"]: e for e in client.get(f"{API}/data-dictionary", headers=h).json()}

    # C19 lost "No Apparent Injury" at crash level, but a crash recorded under
    # the old spec must still resolve it.
    c19 = {v["label"]: v for v in dd["C19"]["values"]}
    assert c19["No Apparent Injury"]["is_active"] is False
    assert c19["Fatal Injury"]["is_active"] is True

    # NMX1 narrowed to four values.
    nmx1 = {v["label"]: v["is_active"] for v in dd["NMX1"]["values"]}
    assert nmx1["Unknown Type of Non-Motorist"] is False
    assert nmx1["Other"] is False
    assert nmx1["Pedestrian"] is True

    # Collapsed values name where they went, so historical data is followable.
    p21 = {v["label"]: v for v in dd["P21"]["values"]}
    assert p21["Test given, results pending"]["is_active"] is False
    assert p21["Test given, results pending"]["superseded_by"] == "Pending"
    v08 = {v["label"]: v for v in dd["V08"]["values"]}
    assert v08["Large Limo"]["superseded_by"] == "Limousine (Large)"
    # Dropped outright, with no successor — do not invent one.
    assert nmx1_no_successor(dd)


def nmx1_no_successor(dd) -> bool:
    other = next(v for v in dd["NMX1"]["values"] if v["label"] == "Other")
    return other["superseded_by"] is None


def test_data_dictionary(client, auth):
    """GAP-PCR-09: the dictionary restores traceability the form's dropped codes lost."""
    h = auth(ANALYST_KS)
    dd = client.get(f"{API}/data-dictionary", headers=h).json()
    assert len(dd) == 175
    by_code = {e["code"]: e for e in dd}

    c19 = by_code["C19"]
    assert c19["form_section"] == "Crash Data Elements"
    assert c19["form_label"] == "CRASH SEVERITY"
    assert c19["mmucc_code"] == "C19"
    # Every row must be usable as a mapping key, so form_label falls back to the
    # attribute name rather than ever being blank.
    assert all(e["form_label"] for e in dd)

    # The ad-hoc pseudo-codes the app invented are not claimed as MMUCC.
    assert by_code["CX1"]["mmucc_code"] is None

    # Cardinality, repeat unit and conditional population all reach the dictionary.
    assert by_code["C11"]["max_selections"] == 3
    assert by_code["LV12"]["repeats_on"] == "TRAILER"
    assert by_code["P30"]["applies_to"] == "ALL_DRIVERS"

    # is_required is a per-study setting, not a property of the attribute.
    assert not any(e["is_required"] for e in dd)
    study = next(s for s in client.get(f"{API}/studies", headers=h).json() if s["code"] == "PHASE1-HDT")
    scoped = client.get(f"{API}/data-dictionary?study_id={study['id']}", headers=h).json()
    assert {e["code"] for e in scoped if e["is_required"]} >= {"V29", "C27"}


def test_coverage_realignment(client, auth):
    """GAP-PCR-05: denominators come from the current catalog, not the old worksheet."""
    h = auth(ANALYST_KS)
    study = next(s for s in client.get(f"{API}/studies", headers=h).json() if s["code"] == "PHASE1-HDT")
    cov = client.get(f"{API}/studies/{study['id']}/pcr-coverage", headers=h).json()
    assert cov

    by_section = {c["pcr_section_code"]: c for c in cov}
    # The retired Dynamic section is gone; the new one is reported.
    assert "DYNAMIC" not in by_section
    assert "PRIMARY_CONTRIBUTING_FACTORS" in by_section

    for c in cov:
        # Old-worksheet denominators counted attribute-VALUES (CRASH 202,
        # PERSON 294, VEHICLE 378). The catalog holds attributes, so every
        # section is now far below those.
        assert c["total_required"] < 100, c
        # The new form defines no optional tier, so nothing is reported against it.
        assert c["optional_collected"] == 0 and c["total_optional"] == 0, c
        assert c["spec_version"] == "HDTS-PCR-2026", c
        # A section with no required attributes is "not applicable", not 0% —
        # coercing it to zero would read as a State collecting nothing.
        if c["total_required"] == 0:
            assert c["completion_pct"] is None, c
        else:
            assert c["completion_pct"] is not None, c


def test_pcr_coverage_kansas(client, auth):
    study = next(s for s in client.get(f"{API}/studies", headers=auth(ANALYST_KS)).json() if s["code"] == "PHASE1-HDT")
    cov = client.get(f"{API}/studies/{study['id']}/pcr-coverage?state=KS", headers=auth(ANALYST_KS)).json()
    crash_section = next(c for c in cov if c["pcr_section_code"] == "CRASH")
    # completion_pct is now DERIVED from collected data (PCR-6) — assert it
    # equals round(required_collected*100/total_required, 2) rather than a
    # stored seed snapshot that drifts.
    req, tot = crash_section["required_collected"], crash_section["total_required"]
    expected = round(req * 100 / tot, 2) if tot else 0.0
    assert float(crash_section["completion_pct"]) == expected
    assert 0.0 <= float(crash_section["completion_pct"]) <= 100.0


def test_integration_dot_validation(client, auth):
    h = auth(ANALYST_KS)
    assert client.post(f"{API}/integrations/safespect/validate-dot", headers=h, json={"dot_number": "3192847"}).json()["valid"] is True
    assert client.post(f"{API}/integrations/safespect/validate-dot", headers=h, json={"dot_number": "ABC"}).json()["valid"] is False


# --------------------------------------------------------------------------- crash lifecycle (rolled back)
def _study_id(client, headers) -> str:
    return next(s for s in client.get(f"{API}/studies", headers=headers).json() if s["code"] == "PHASE1-HDT")["id"]


def test_full_crash_lifecycle(client, auth, db):
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, insp)

    # 1. create crash (inspector, KS) -> CCFP identifier assigned
    crash = client.post(
        f"{API}/crashes", headers=insp,
        json={"study_id": study_id, "state_code": "KS", "city": "Topeka", "county": "Shawnee",
              "crash_date": "2026-05-01", "num_fatalities": 1},
    ).json()
    assert crash["ccfp_identifier"].startswith("CCFP-2026-KS-")
    cid = crash["id"]

    # 2. classify scope IN_SCOPE
    scope = client.put(f"{API}/crashes/{cid}/scope", headers=analyst,
                       json={"is_qualifying": True, "scope": "IN_SCOPE"}).json()
    assert scope["scope"] == "IN_SCOPE"

    # 3. add CMV vehicle + driver
    client.post(f"{API}/crashes/{cid}/incident-vehicles", headers=insp,
                json={"vehicle_number": 1, "is_cmv": True, "us_dot_number": "3192847", "make": "Freightliner"})
    client.post(f"{API}/crashes/{cid}/incident-persons", headers=insp,
                json={"person_type": "DRIVER", "full_name": "Test Driver", "injury": "NO_INJURY"})

    # 4. save + submit Initial Incident Form -> validated + routed
    client.put(f"{API}/crashes/{cid}/initial-incident", headers=insp, json={"event_summary": "Test event"})
    submit = client.post(f"{API}/crashes/{cid}/initial-incident/submit", headers=insp).json()
    assert submit["status"] == "ROUTED"
    assert submit["dot_number_validated"] is True

    # 5. PII masking: inspector has write (PII), public would not — verify person visible to inspector
    persons = client.get(f"{API}/crashes/{cid}/incident-persons", headers=insp).json()
    assert persons[0]["full_name"] == "Test Driver"

    # 6. add inspection so completeness has a source
    client.post(f"{API}/crashes/{cid}/post-crash-inspections", headers=analyst,
                json={"inspection_number": "INS-TEST-1"})

    # 7. select top-3 contributing factors (analyst)
    factors = client.put(
        f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
        json={"factors": [
            {"factor_group_code": "DRIVER_ACTIONS", "factor_value": "Following too closely", "rank": 1},
            {"factor_group_code": "DRIVER_CONDITIONS", "factor_value": "Fatigue", "rank": 2},
            {"factor_group_code": "CC_VEHICLE", "factor_value": "Brakes", "rank": 3},
        ]},
    ).json()
    assert len(factors) == 3

    # 8. run QC + completeness via worker (uses the test session so it sees uncommitted data)
    import uuid
    qc = workers.evaluate_quality(uuid.UUID(cid), db=db)
    assert qc["summary"]["PASS"] >= 1
    comp = workers.evaluate_completeness(uuid.UUID(cid), db=db)
    assert comp["status"] in ("COMPLETE", "INCOMPLETE")

    # 9. timeline reflects audited actions
    timeline = client.get(f"{API}/crashes/{cid}/timeline", headers=insp).json()
    actions = {e["action"] for e in timeline}
    assert {"CREATE", "SUBMIT"}.issubset(actions)


def test_contributing_factor_rank_validation(client, auth):
    insp = auth(INSPECTOR_KS)
    analyst = auth(ANALYST_KS)
    study_id = _study_id(client, insp)
    cid = client.post(f"{API}/crashes", headers=insp, json={"study_id": study_id, "state_code": "KS"}).json()["id"]
    bad = client.put(f"{API}/crashes/{cid}/contributing-factors", headers=analyst,
                     json={"factors": [{"factor_value": "x", "rank": 5}]})
    assert bad.status_code == 400


# --------------------------------------------------------------------------- search & public
def test_search(client, auth):
    res = client.get(f"{API}/search?q=CCFP-2026-KS", headers=auth(ANALYST_KS)).json()
    assert any(h["type"] == "crash" for h in res["hits"])


def test_public_outputs_no_auth(client):
    # Public endpoints require no authentication and only expose published, de-identified reports.
    studies = client.get(f"{API}/studies", headers={})  # no auth -> 401
    assert studies.status_code == 401
    study_any = "00000000-0000-0000-0000-000000000000"
    pub = client.get(f"{API}/public/studies/{study_any}/outputs")
    assert pub.status_code == 200
    assert isinstance(pub.json(), list)


def test_admin_can_list_users(client, auth):
    users = client.get(f"{API}/users", headers=auth(ADMIN)).json()
    assert users["total"] >= 15
    # analyst lacks admin:users
    assert client.get(f"{API}/users", headers=auth(ANALYST_KS)).status_code == 403
