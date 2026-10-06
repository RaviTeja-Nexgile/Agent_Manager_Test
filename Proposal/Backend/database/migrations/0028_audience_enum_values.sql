-- =============================================================================
-- CCFP IT Solution - Migration 0025: audience enum values
--
-- =============================================================================
-- The January 2026 BRD replaces the old footnoted user list with a formal
-- four-tier addressing model used consistently by every sharing requirement:
--
--   FMCSA Federal Users      CCFP Project Team, CCFP Database Administrator,
--                            FMCSA HQ, FMCSA Enforcement
--   Other Federal Users      BTS, NHTSA, NTSB
--   Participating State Users
--   Public Users
--
-- Two schema consequences:
--
--  * NTSB is named as a consumer for the first time ("Share CCFP
--    Aggregated Data and CCFP Analysis Environment data with Other Federal
--    Users (BTS, NHTSA, NTSB)"). organization_type had no NTSB value.
--
--  * report_visibility collapsed FMCSA Federal and Other Federal
--    into a single FEDERAL tier, but the BRD separates them into DIFFERENT
--    sharing actions with different authorization rows. FEDERAL is retained and
--    keeps meaning "both federal tiers", so every existing row behaves exactly
--    as before; new reports can address one tier precisely.
--
-- This migration ONLY adds enum values. PostgreSQL forbids using a value added
-- by ALTER TYPE ... ADD VALUE inside the same transaction that added it, and
-- migrate.py runs each file in its own transaction — so the columns and rows
-- that consume these values live in migration 0026 and the seeds.
--
-- Idempotent / additive: ADD VALUE IF NOT EXISTS; no table or row is touched.
-- =============================================================================

-- National Transportation Safety Board.
ALTER TYPE organization_type ADD VALUE IF NOT EXISTS 'NTSB';

-- split the collapsed federal tier. FEDERAL is deliberately NOT
-- removed — it stays valid and means "both federal tiers", which is what every
-- pre-existing FEDERAL report already meant.
ALTER TYPE report_visibility ADD VALUE IF NOT EXISTS 'FMCSA_FEDERAL';
ALTER TYPE report_visibility ADD VALUE IF NOT EXISTS 'OTHER_FEDERAL';
