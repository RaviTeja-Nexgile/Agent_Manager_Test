-- =============================================================================
-- CCFP IT Solution - Migration 0028: statistical analysis in the Analysis
-- Environment
-- =============================================================================
-- The September 2025 BRD carried one unelaborated "statistical analysis" row.
-- The January 2026 BRD replaces it with a named-methods requirement (p. 16):
--
--   "Provide tools to support descriptive, exploratory, and statistical
--    analyses (both descriptive and inferential) ... such as:
--      o Descriptive statistics and visualization-ready outputs ...
--      o Statistical summaries: central tendency and dispersion, data
--        distributions, thematic analysis, and statistical risk modeling
--        (given the availability of control such as non-fatal crashes)."
--
-- Migration 0022 built the environment and gave it dataset-level descriptive
-- statistics. Three of the four named method families still had nowhere to run:
--
--   central tendency and dispersion  ... 0022 (extended by this migration)
--   data distributions ................. 0022 histogram; categorical frequency
--                                        distributions added here
--   thematic analysis .................. NEW -- needs crash-level factor data
--   statistical risk modeling .......... NEW -- needs a CONTROL POPULATION
--
-- WHY A NEW TABLE FAMILY AND NOT MORE COLUMNS ON analysis_datasets
--
-- analysis_dataset_rows holds AGGREGATED rows: one row per (state, year, ...)
-- group with measures already summed. That is the right shape for the BRD's
-- "visualization-ready outputs", and it is deliberately not reversible.
--
-- But the three remaining method families are all CRASH-LEVEL:
--
--   * thematic analysis asks which contributing factors CO-OCCUR -- a question
--     about individual crashes that cannot be recovered once the crashes are
--     summed into groups;
--   * risk modeling needs a 2x2 table of crashes cross-classified by exposure
--     and outcome, which again is a per-crash classification;
--   * comparing two populations needs the populations to be enumerable.
--
-- So this migration adds a crash-level materialization alongside the aggregated
-- one, under the same versioning discipline. It is emphatically NOT a live view
-- onto the operational tables: analysis_cohort_members is written by a refresh
-- and read by everything else, so "as of when?" stays answerable and the BRD's
-- "will not modify original data" holds structurally, exactly as in 0022.
--
-- THE CONTROL POPULATION -- the clause that made this hard
--
-- "given the availability of control such as non-fatal crashes" is a
-- CONDITIONAL. Risk modeling is expected *when* a control is available. Phase 1
-- collects fatal Class 7/8 crashes, so the naive reading is that no control
-- exists and the requirement is unsatisfiable.
--
-- That reading is wrong, and the existing schema already shows why. Crashes are
-- recorded BEFORE they are classified, and crash_scope_classifications retains
-- the ones that did not qualify:
--
--     scope=IN_SCOPE      is_qualifying=true    -- the Phase 1 study population
--     scope=OUT_OF_SCOPE  is_qualifying=true    -- qualifying, non-participating State
--     scope=UNDETERMINED  is_qualifying=false   -- incl. crashes with 0 fatalities
--
-- The non-qualifying and non-fatal records are already in the database. They are
-- out of scope for ANALYSIS OUTPUT -- they must never appear in a published
-- count of Phase 1 crashes -- but that is not the same as being unusable as a
-- comparison denominator. A cohort therefore carries an explicit `role`
-- (CASE / CONTROL / GENERAL) so the distinction is declared by the analyst and
-- recorded, rather than inferred.
--
-- This is a modelling decision with real analytic consequences, so it is
-- deliberately made VISIBLE rather than buried: every risk-model result names
-- its control cohort, and the API refuses to compute a risk model at all when no
-- control cohort is designated. The BRD's conditional is honoured literally --
-- no control, no risk model, and an explicit reason why. If FMCSA confirms a
-- different control population in discovery (a serious-injury sample, or an
-- external non-fatal source such as MCMIS/CRSS), it becomes a new cohort row
-- and nothing here changes.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- A cohort: a named, saved, re-materializable population of crashes.
--
-- `definition` uses the same constrained-vocabulary shape as analysis_datasets
-- ({"filters":[{column,op,value}], "study_id":...}) so nothing caller-supplied
-- ever reaches SQL as text; app/workers/analysis.py resolves every name through
-- an allow-list of mapped SQLAlchemy expressions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_cohorts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id   UUID NOT NULL REFERENCES analysis_environments(id) ON DELETE CASCADE,
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT,
    -- CASE     : the population under study (Phase 1: fatal Class 7/8 crashes)
    -- CONTROL  : the comparison population that makes risk modelling possible
    -- GENERAL  : a saved population used for description only, neither arm of a
    --            comparison. Kept distinct so an analyst cannot accidentally use
    --            a descriptive slice as a denominator.
    cohort_role      TEXT NOT NULL DEFAULT 'GENERAL'
                     CHECK (cohort_role IN ('CASE','CONTROL','GENERAL')),
    definition       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','ARCHIVED')),
    current_version_id UUID,
    created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (environment_id, code)
);

CREATE TABLE IF NOT EXISTS analysis_cohort_versions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cohort_id        UUID NOT NULL REFERENCES analysis_cohorts(id) ON DELETE CASCADE,
    version_no       INTEGER NOT NULL,
    member_count     INTEGER NOT NULL DEFAULT 0,
    definition_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    materialized_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    refresh_run_id   UUID REFERENCES analysis_refresh_runs(id) ON DELETE SET NULL,
    UNIQUE (cohort_id, version_no)
);

ALTER TABLE analysis_cohorts
    DROP CONSTRAINT IF EXISTS analysis_cohorts_current_version_fk;
ALTER TABLE analysis_cohorts
    ADD CONSTRAINT analysis_cohorts_current_version_fk
    FOREIGN KEY (current_version_id)
    REFERENCES analysis_cohort_versions(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- Cohort membership, one row per crash per version.
--
-- The analysis variables are DENORMALIZED onto the member row on purpose. Two
-- reasons, both required by the tier's contract:
--
--   1. A statistic must describe the population AS IT WAS when the cohort was
--      materialized. If statistics joined back to `crashes` for the fatality
--      count, an operational edit would silently change a result that was
--      already reported, and the version number would be a lie.
--   2. It keeps every statistical query a single-table scan with no joins to
--      operational data, which is what lets the environment stay separate.
--
-- crash_id is retained (nullable FK, ON DELETE SET NULL) for drill-down from a
-- result back to the record, without making the snapshot depend on the record
-- continuing to exist.
--
-- `factors` is the crash's contributing-factor values as a text array -- the raw
-- material for thematic analysis. Arrays rather than a child table because every
-- question asked of them ("which appear together?", "how often?") is answered by
-- unnest/intersection over the array, and a child table would need its own
-- versioning to stay consistent with the snapshot.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_cohort_members (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id       UUID NOT NULL REFERENCES analysis_cohort_versions(id) ON DELETE CASCADE,
    crash_id         UUID REFERENCES crashes(id) ON DELETE SET NULL,
    ccfp_identifier  TEXT,
    state_code       CHAR(2),
    county           TEXT,
    crash_date       DATE,
    crash_year       INTEGER,
    crash_month      INTEGER,
    lifecycle_phase  TEXT,
    study_id         UUID,
    num_fatalities   INTEGER,
    num_vehicles     INTEGER,
    num_persons      INTEGER,
    -- Outcome variable for risk modelling. Stored rather than derived so the
    -- 2x2 table is built from a column the snapshot actually recorded.
    is_fatal         BOOLEAN NOT NULL DEFAULT false,
    scope            TEXT,
    is_qualifying    BOOLEAN,
    factors          TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    factor_groups    TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_analysis_cohort_members_version
    ON analysis_cohort_members(version_id);
-- Statistics are almost always State-scoped for State principals and grouped by
-- State for everyone else, so this composite carries the common access path.
CREATE INDEX IF NOT EXISTS idx_analysis_cohort_members_version_state
    ON analysis_cohort_members(version_id, state_code);
CREATE INDEX IF NOT EXISTS idx_analysis_cohort_members_factors
    ON analysis_cohort_members USING GIN (factors);
CREATE INDEX IF NOT EXISTS idx_analysis_cohort_versions_cohort
    ON analysis_cohort_versions(cohort_id);
CREATE INDEX IF NOT EXISTS idx_analysis_cohorts_environment
    ON analysis_cohorts(environment_id);

-- ---------------------------------------------------------------------------
-- Saved analytical investigations.
--
-- "Save/share reusable analytical investigations within the CCFP Analysis
-- Environment." An investigation is a METHOD plus its PARAMETERS -- not a
-- captured result. It is stored that way deliberately: re-running a saved
-- investigation against a newer cohort version is the point, and a frozen result
-- would make the saved object go stale the moment the environment refreshed.
-- The result carries its cohort version, so reproducibility is preserved by
-- naming the version, not by pickling numbers.
--
-- `visibility` is PRIVATE or TEAM rather than the four-audience model used by
-- analysis_shares. The BRD scopes investigation sharing to "within the CCFP
-- Analysis Environment" -- i.e. among CCFP analysts -- whereas analysis_shares
-- governs data leaving the environment for States and the public. Conflating
-- them would let an investigation become an undocumented export path.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_investigations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id   UUID NOT NULL REFERENCES analysis_environments(id) ON DELETE CASCADE,
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT,
    method           TEXT NOT NULL
                     CHECK (method IN ('DESCRIPTIVE','DISTRIBUTION','THEMATIC',
                                       'RISK_MODEL','COMPARATIVE','TREND')),
    parameters       JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility       TEXT NOT NULL DEFAULT 'TEAM'
                     CHECK (visibility IN ('PRIVATE','TEAM')),
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','ARCHIVED')),
    last_run_at      TIMESTAMPTZ,
    created_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (environment_id, code)
);

CREATE INDEX IF NOT EXISTS idx_analysis_investigations_environment
    ON analysis_investigations(environment_id);

-- ---------------------------------------------------------------------------
-- Cohorts are materialized by the SAME refresh that materializes datasets, so
-- the aggregated and crash-level views of the environment can never drift to
-- different points in time. The existing run log counted only datasets; give it
-- somewhere to record the other half of the work rather than burying it in the
-- free-text message, so "the refresh succeeded" stays a checkable claim.
-- ---------------------------------------------------------------------------
ALTER TABLE analysis_refresh_runs
    ADD COLUMN IF NOT EXISTS cohorts_refreshed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE analysis_refresh_runs
    ADD COLUMN IF NOT EXISTS members_written   INTEGER NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------------------
-- Database-level guard: a CONTROL cohort must not be the same population as the
-- CASE cohort it is compared against.
--
-- Enforced here rather than only in the API for the same reason 0022 put the
-- PII/audience rules in triggers: a seed, a migration, or a future writer that
-- bypasses the API must not be able to create a self-comparing risk model. A
-- risk model whose exposed and unexposed arms are the same crashes yields an
-- odds ratio of exactly 1 with a tight confidence interval -- a confident,
-- meaningless answer, which is worse than an error.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION analysis_cohorts_role_change_guard() RETURNS TRIGGER AS $$
DECLARE
    ref_count INTEGER;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.cohort_role <> OLD.cohort_role THEN
        -- An investigation that named this cohort as a control must not be left
        -- pointing at something that is no longer a control population.
        SELECT count(*) INTO ref_count
          FROM analysis_investigations
         WHERE method = 'RISK_MODEL'
           AND parameters ->> 'control_cohort_id' = OLD.id::text;
        IF ref_count > 0 AND NEW.cohort_role <> 'CONTROL' THEN
            RAISE EXCEPTION
                'cohort % is the control population of % saved risk model(s); archive them before changing its role',
                OLD.code, ref_count;
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_analysis_cohorts_role_guard ON analysis_cohorts;
CREATE TRIGGER trg_analysis_cohorts_role_guard
    BEFORE UPDATE ON analysis_cohorts
    FOR EACH ROW EXECUTE FUNCTION analysis_cohorts_role_change_guard();

-- ---------------------------------------------------------------------------
-- Permissions.
--
-- The BRD's "Analyze CCFP Data" access table (p. 16) lists ONE user for all
-- three statistical rows -- the CCFP Project Team -- with Create, Read, Update,
-- Delete. Note what it does NOT do: unlike the Visualize table on the next page,
-- it grants no read to State, Federal or public users. Those users receive
-- analysis OUTPUTS through dashboards, reports and tables, which the environment
-- already delivers via analysis_shares. So the statistical tooling is internal,
-- and this migration keeps it that way.
--
-- Split in two because "run an analysis" and "save a reusable investigation /
-- define the study populations" are different acts with different blast radii:
-- a badly-chosen cohort definition silently changes every result computed from
-- it afterwards, which is a stronger power than running a method once.
-- ---------------------------------------------------------------------------
INSERT INTO permissions (code, name, category, description) VALUES
 ('analysis_stats:run','Run statistical analyses in the Analysis Environment','analysis_environment',
  'Conduct descriptive, distributional, thematic, comparative, trend and risk analyses over Analysis Environment cohorts.'),
 ('analysis_stats:manage','Define cohorts and saved investigations','analysis_environment',
  'Create, update and delete analysis cohorts (including control populations) and saved analytical investigations.')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.code = 'SYSTEM_ADMIN'
  AND p.code LIKE 'analysis_stats:%'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
 -- "Run queries and analyze CCFP data", "Conduct descriptive statistics
 -- analysis", "Create statistical summaries" -- all three rows, CRUD.
 ('CCFP_PROJECT_TEAM',   ARRAY['analysis_stats:run','analysis_stats:manage']),
 ('CCFP_PROJECT_ADMIN',  ARRAY['analysis_stats:run','analysis_stats:manage']),
 -- Descriptive and inferential analysis of environment data is precisely this
 -- role's job; it already holds analysis_env:dataset from 0022.
 ('CCFP_DATA_SCIENTIST', ARRAY['analysis_stats:run','analysis_stats:manage']),
 -- Manages the environment and its refreshes, so must be able to run a method
 -- to verify a refresh produced usable data -- but does not define the study
 -- populations, which is an analytic judgement, not an operational one.
 ('CCFP_DB_ADMIN',       ARRAY['analysis_stats:run']),
 -- CIPSEA agents analyse the interview data they steward. Run only; the BRD
 -- notes "further coordination with BTS is needed to determine access
 -- requirements for BTS data", so nothing broader is assumed here.
 ('BTS_CIPSEA_AGENT',    ARRAY['analysis_stats:run']),
 ('FMCSA_CIPSEA_AGENT',  ARRAY['analysis_stats:run'])
) AS m(role_code, perms)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = ANY(m.perms)
ON CONFLICT DO NOTHING;
