-- =============================================================================
-- CCFP IT Solution - Migration 0022: CCFP Analysis Environment (GAP-BRD-02)
-- =============================================================================
-- The September 2025 BRD mentioned "an analysis environment" in a single clause
-- with no requirements attached, so the implementation treated it as a synonym
-- for the Data Lake and pointed analytics straight at the operational tables.
--
-- The January 2026 BRD makes it a DISTINCT, ADDRESSABLE TIER. Requirements are
-- now written against "CCFP Aggregated Data and CCFP Analysis Environment data"
-- as two separately-shared things (BRD pp. 13-16):
--
--   * Share CCFP Aggregated Data (and summary BTS data) INTO the Analysis
--     Environment  ................................................ analysis_shares
--   * Create new data/VIEWS DERIVED FROM Aggregated Data, held in the
--     Analysis Environment  ...................................... analysis_datasets
--   * Perform REGULAR REFRESHES (daily or hourly) of Aggregated Data to the
--     Analysis Environment  ................ analysis_environments.refresh_cadence
--                                            + analysis_refresh_runs
--   * Share Aggregated Data AND Analysis Environment data outward with four
--     audiences carrying different PII rules  ..................... analysis_shares
--   * "Manage the Analysis Environment"  .................... analysis_environments
--
-- The architectural point of the tier is SEPARATION: analysis reads MATERIALIZED
-- rows (analysis_dataset_rows) captured at a known point in time, not the live
-- operational tables. That is what makes "refreshed daily or hourly" a
-- meaningful statement, and it is what the BRD's note demands -- "the core
-- capabilities listed above will not modify original data from CCFP (SafeSpect)
-- or any other system." Nothing in this tier writes to an operational table.
--
-- SCOPE NOTE: the BRD names Tableau / ArcGIS / Python / SAS / R as example
-- supporting tools "to be determined in discovery." This migration deliberately
-- builds the TIER (datasets, versioned refresh, audience-scoped shares, export)
-- rather than an opinion about the tool. If FMCSA procures an external BI
-- platform in discovery, these same tables are the refresh/export contract that
-- platform consumes; nothing here is wasted by that outcome.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- The environment itself. The BRD lists "Manage the Analysis Environment" as a
-- capability with its own access rule, so the environment is a row, not an
-- implicit concept.
--
-- study_id NULL means "spans all studies". Phase 1 runs one environment over the
-- Heavy-Duty Truck Study, but a future phase can stand up a second environment
-- without a schema change (§3.4 configurability).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_environments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    description      TEXT,
    study_id         UUID REFERENCES studies(id) ON DELETE SET NULL,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','PAUSED','ARCHIVED')),
    -- "Provide ability to perform regular refreshes (daily or hourly) of the
    -- aggregated CCFP Aggregated Data ... to the CCFP Analysis Environment."
    refresh_cadence  TEXT NOT NULL DEFAULT 'DAILY'
                     CHECK (refresh_cadence IN ('HOURLY','DAILY','MANUAL')),
    last_refreshed_at TIMESTAMPTZ,
    next_refresh_due  TIMESTAMPTZ,
    created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_analysis_env_study ON analysis_environments(study_id);
CREATE INDEX IF NOT EXISTS idx_analysis_env_due
    ON analysis_environments(next_refresh_due)
    WHERE status = 'ACTIVE' AND refresh_cadence <> 'MANUAL';

COMMENT ON TABLE analysis_environments IS
    'CCFP Analysis Environment (BRD Jan-2026, Data Analysis and Sharing). A '
    'managed tier holding data shared in from the CCFP Aggregated Data, '
    'refreshed on a cadence, separate from the operational crash tables.';

-- ---------------------------------------------------------------------------
-- Datasets: the "new data/views of data derived from CCFP Aggregated Data in
-- the CCFP Analysis Environment" that the CCFP Project Team creates.
--
-- `definition` is a CONSTRAINED spec -- {dimensions, measures, filters} chosen
-- from server-side allow-lists (app/workers/analysis.py), never free-form SQL.
-- The same discipline the ad-hoc query builder already uses (§14): a stored
-- definition must not be able to widen its own reach when it is replayed by the
-- scheduled refresh under no user's eye.
--
-- `pii_level` is the control that makes the BRD's four audience tiers real
-- rather than labelled -- see the share guard below.
--
-- `is_state_partitioned` records whether every materialized row carries a
-- state_code. A dataset that does not partition by State cannot be shared to a
-- participating State without leaking other States' aggregates, so the share
-- guard refuses it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_datasets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id UUID NOT NULL REFERENCES analysis_environments(id) ON DELETE CASCADE,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT,
    -- AGGREGATED_SNAPSHOT: data shared in from CCFP Aggregated Data as-is.
    -- DERIVED_VIEW:        a new view derived from it by the CCFP Project Team.
    kind           TEXT NOT NULL DEFAULT 'DERIVED_VIEW'
                   CHECK (kind IN ('AGGREGATED_SNAPSHOT','DERIVED_VIEW')),
    definition     JSONB NOT NULL DEFAULT '{}'::jsonb,
    pii_level      TEXT NOT NULL DEFAULT 'NO_PII'
                   CHECK (pii_level IN ('PII','NO_PII','DEIDENTIFIED_SUMMARY')),
    is_state_partitioned BOOLEAN NOT NULL DEFAULT FALSE,
    status         TEXT NOT NULL DEFAULT 'ACTIVE'
                   CHECK (status IN ('ACTIVE','ARCHIVED')),
    -- Set to the newest successfully materialized version. NULL until the first
    -- refresh, which is why the API reports a dataset as "never refreshed"
    -- rather than silently serving an empty result as if it were the answer.
    current_version_id UUID,
    created_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (environment_id, code)
);
CREATE INDEX IF NOT EXISTS idx_analysis_dataset_env ON analysis_datasets(environment_id);

-- ---------------------------------------------------------------------------
-- Versions: one row per successful materialization. Keeping the previous
-- version means a refresh is not a destructive overwrite -- an analyst mid-way
-- through reading a dataset is not pulled out from under, and "as of" is a real
-- answerable question rather than "whenever you happened to look".
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_dataset_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID NOT NULL REFERENCES analysis_datasets(id) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    materialized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_count       INTEGER NOT NULL DEFAULT 0,
    columns         JSONB NOT NULL DEFAULT '[]'::jsonb,
    refresh_run_id  UUID,
    UNIQUE (dataset_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_analysis_version_dataset
    ON analysis_dataset_versions(dataset_id, version_no DESC);

-- current_version_id is added as a deferred FK because the two tables reference
-- each other: a dataset points at its newest version, a version belongs to a
-- dataset.
ALTER TABLE analysis_datasets
    DROP CONSTRAINT IF EXISTS fk_analysis_dataset_current_version;
ALTER TABLE analysis_datasets
    ADD CONSTRAINT fk_analysis_dataset_current_version
    FOREIGN KEY (current_version_id)
    REFERENCES analysis_dataset_versions(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- The materialized rows -- the actual Analysis Environment data.
--
-- `state_code` is lifted OUT of the JSONB payload into a real column so a
-- State-scoped share can be filtered in the index rather than by unpacking
-- every row's JSON. NULL means the row is not attributable to one State (a
-- national aggregate), which is exactly the case a State share must not expose.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_dataset_rows (
    id         BIGSERIAL PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES analysis_dataset_versions(id) ON DELETE CASCADE,
    row_index  INTEGER NOT NULL,
    state_code CHAR(2) REFERENCES ref_us_states(code),
    data       JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analysis_rows_version
    ON analysis_dataset_rows(version_id, row_index);
CREATE INDEX IF NOT EXISTS idx_analysis_rows_version_state
    ON analysis_dataset_rows(version_id, state_code);

-- ---------------------------------------------------------------------------
-- Refresh runs. "Provide ability to perform regular refreshes" is only credible
-- if a failed refresh is visible: an analyst looking at a dataset needs to be
-- able to tell stale-because-nothing-changed from stale-because-the-refresh-
-- has-been-failing-for-two-days.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_refresh_runs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id     UUID NOT NULL REFERENCES analysis_environments(id) ON DELETE CASCADE,
    dataset_id         UUID REFERENCES analysis_datasets(id) ON DELETE CASCADE,
    trigger            TEXT NOT NULL DEFAULT 'MANUAL'
                       CHECK (trigger IN ('SCHEDULED','MANUAL')),
    status             TEXT NOT NULL DEFAULT 'RUNNING'
                       CHECK (status IN ('RUNNING','SUCCEEDED','FAILED')),
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,
    datasets_refreshed INTEGER NOT NULL DEFAULT 0,
    rows_written       INTEGER NOT NULL DEFAULT 0,
    message            TEXT,
    triggered_by       UUID REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_env
    ON analysis_refresh_runs(environment_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- Shares. The BRD's outward-sharing requirement names four audiences with
-- materially different rules:
--
--   FMCSA_FEDERAL       FMCSA users and the CCFP Project Team -- PII permitted
--   OTHER_FEDERAL       BTS, NHTSA, NTSB
--   PARTICIPATING_STATE "data will be State-specific, have no PII"
--   PUBLIC              "no PII, summary de-identified data only"
--
-- `refresh_cadence` here is the second, separate refresh requirement: "regular
-- refreshes (AS DETERMINED BY THE CCFP PROJECT TEAM) of CCFP Aggregated Data and
-- CCFP Analysis Environment data for other Federal users, participating State
-- users, and public users" -- i.e. an outward share may be refreshed on its own
-- schedule, distinct from the inbound environment refresh.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID NOT NULL REFERENCES analysis_datasets(id) ON DELETE CASCADE,
    audience        TEXT NOT NULL
                    CHECK (audience IN ('FMCSA_FEDERAL','OTHER_FEDERAL',
                                        'PARTICIPATING_STATE','PUBLIC')),
    state_code      CHAR(2) REFERENCES ref_us_states(code),
    refresh_cadence TEXT NOT NULL DEFAULT 'DAILY'
                    CHECK (refresh_cadence IN ('HOURLY','DAILY','MANUAL')),
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','REVOKED')),
    note            TEXT,
    shared_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    shared_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    -- A State share is meaningless without naming the State; the other three
    -- audiences are not State-specific, so a stray state_code there would be a
    -- silently ignored restriction -- reject it instead.
    CONSTRAINT chk_analysis_share_state CHECK (
        (audience = 'PARTICIPATING_STATE' AND state_code IS NOT NULL)
        OR (audience <> 'PARTICIPATING_STATE' AND state_code IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_share_active
    ON analysis_shares(dataset_id, audience, COALESCE(state_code, '--'))
    WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_analysis_share_dataset ON analysis_shares(dataset_id);

-- ---------------------------------------------------------------------------
-- PII guard.
--
-- The BRD's PII rules for the State and Public audiences are the sort of
-- requirement that decays into a label if it only lives in a request handler:
-- one seed file, one migration, one background job that inserts a share row
-- directly, and the rule is gone. Enforcing it in the database means the rule
-- holds for every writer, including the ones written later by someone who never
-- read the BRD.
--
-- Two conditions, both cross-table (hence a trigger rather than a CHECK):
--   1. A dataset carrying PII may not be shared to PARTICIPATING_STATE or
--      PUBLIC at all.
--   2. PUBLIC additionally requires DEIDENTIFIED_SUMMARY -- the BRD says
--      "summary de-identified data only", which NO_PII does not satisfy on its
--      own (a row-level extract with no direct identifiers is still re-
--      identifiable and is not a summary).
--   3. A PARTICIPATING_STATE share requires a State-partitioned dataset, or the
--      State would receive every other State's rows along with its own.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION analysis_shares_enforce_pii() RETURNS TRIGGER AS $$
DECLARE
    ds_pii   TEXT;
    ds_state BOOLEAN;
BEGIN
    IF NEW.status <> 'ACTIVE' THEN
        RETURN NEW;  -- a revoked share exposes nothing
    END IF;

    SELECT pii_level, is_state_partitioned
      INTO ds_pii, ds_state
      FROM analysis_datasets
     WHERE id = NEW.dataset_id;

    IF ds_pii IS NULL THEN
        RAISE EXCEPTION 'analysis dataset % not found', NEW.dataset_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF NEW.audience IN ('PARTICIPATING_STATE','PUBLIC') AND ds_pii = 'PII' THEN
        RAISE EXCEPTION
            'dataset % carries PII and cannot be shared to audience %',
            NEW.dataset_id, NEW.audience
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.audience = 'PUBLIC' AND ds_pii <> 'DEIDENTIFIED_SUMMARY' THEN
        RAISE EXCEPTION
            'public shares require a DEIDENTIFIED_SUMMARY dataset (dataset % is %)',
            NEW.dataset_id, ds_pii
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.audience = 'PARTICIPATING_STATE' AND NOT ds_state THEN
        RAISE EXCEPTION
            'dataset % is not State-partitioned and cannot be shared to a single State',
            NEW.dataset_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_analysis_shares_pii ON analysis_shares;
CREATE TRIGGER trg_analysis_shares_pii
    BEFORE INSERT OR UPDATE ON analysis_shares
    FOR EACH ROW EXECUTE FUNCTION analysis_shares_enforce_pii();

-- A dataset's sensitivity can also be raised AFTER it was shared, which would
-- quietly widen exposure past what the share was approved for. Re-check the
-- dataset's live shares whenever pii_level or partitioning changes.
CREATE OR REPLACE FUNCTION analysis_datasets_recheck_shares() RETURNS TRIGGER AS $$
DECLARE
    offending TEXT;
BEGIN
    IF NEW.pii_level IS NOT DISTINCT FROM OLD.pii_level
       AND NEW.is_state_partitioned IS NOT DISTINCT FROM OLD.is_state_partitioned THEN
        RETURN NEW;
    END IF;

    SELECT string_agg(DISTINCT audience, ', ')
      INTO offending
      FROM analysis_shares
     WHERE dataset_id = NEW.id
       AND status = 'ACTIVE'
       AND (
            (audience IN ('PARTICIPATING_STATE','PUBLIC') AND NEW.pii_level = 'PII')
         OR (audience = 'PUBLIC' AND NEW.pii_level <> 'DEIDENTIFIED_SUMMARY')
         OR (audience = 'PARTICIPATING_STATE' AND NOT NEW.is_state_partitioned)
       );

    IF offending IS NOT NULL THEN
        RAISE EXCEPTION
            'cannot change dataset % sensitivity: active share(s) to % would be invalidated; revoke them first',
            NEW.id, offending
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_analysis_datasets_recheck ON analysis_datasets;
CREATE TRIGGER trg_analysis_datasets_recheck
    BEFORE UPDATE ON analysis_datasets
    FOR EACH ROW EXECUTE FUNCTION analysis_datasets_recheck_shares();

-- ---------------------------------------------------------------------------
-- Permissions. Split four ways because the BRD gives the two roles genuinely
-- different verbs: the CCFP Database Administrator SHARES data into and out of
-- the environment and MANAGES it, while the CCFP Project Team CREATES derived
-- views and RUNS analyses in it (BRD pp. 15-16 access tables).
-- ---------------------------------------------------------------------------
INSERT INTO permissions (code, name, category, description) VALUES
 ('analysis_env:read','View the Analysis Environment and its datasets','analysis_environment',
  'Read Analysis Environment datasets, materialized rows, and statistics.'),
 ('analysis_env:manage','Manage the Analysis Environment','analysis_environment',
  'Create/configure environments and trigger refreshes of Aggregated Data into the environment.'),
 ('analysis_env:dataset','Create derived data/views in the Analysis Environment','analysis_environment',
  'Create, update and delete datasets derived from CCFP Aggregated Data.'),
 ('analysis_env:share','Share Analysis Environment data','analysis_environment',
  'Share Aggregated Data and Analysis Environment data with Federal, State and public audiences.')
ON CONFLICT (code) DO NOTHING;

-- SYSTEM_ADMIN holds every permission (seeds/0002 grants by CROSS JOIN, which
-- only covered permissions existing at that time) -- re-apply for the new codes.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.code = 'SYSTEM_ADMIN'
  AND p.code LIKE 'analysis_env:%'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 -- "Share ... via the CCFP Analysis Environment" + "Manage the Analysis
 -- Environment" + all four outward-share rows: CRUD / Create,Read.
 ('CCFP_DB_ADMIN',       ARRAY['analysis_env:read','analysis_env:manage','analysis_env:dataset','analysis_env:share']),
 -- "Create new derived data/views ... in the CCFP Analysis Environment" and
 -- "Run queries and analyze CCFP data stored in the designated Analysis
 -- Environment": CRUD.
 ('CCFP_PROJECT_TEAM',   ARRAY['analysis_env:read','analysis_env:dataset']),
 ('CCFP_PROJECT_ADMIN',  ARRAY['analysis_env:read','analysis_env:manage','analysis_env:dataset']),
 -- Descriptive/inferential analysis over environment data is this role's job.
 ('CCFP_DATA_SCIENTIST', ARRAY['analysis_env:read','analysis_env:dataset']),
 -- Read-only consumers of shared environment data.
 ('FMCSA_CIPSEA_AGENT',  ARRAY['analysis_env:read']),
 ('BTS_CIPSEA_AGENT',    ARRAY['analysis_env:read']),
 ('FEDERAL_USER',        ARRAY['analysis_env:read']),
 -- State users read only what has been shared to their State, enforced by
 -- audience + State scope at query time (features/analysis_environment.py).
 ('STATE_CMV_ANALYST',   ARRAY['analysis_env:read']),
 ('STATE_USER',          ARRAY['analysis_env:read'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;
