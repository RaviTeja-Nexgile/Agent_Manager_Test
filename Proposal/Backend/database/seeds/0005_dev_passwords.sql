-- =============================================================================
-- CCFP IT Solution - Seed 0005: development passwords (100% synthetic)
-- =============================================================================
-- Sets users.password_hash for every seeded demo user to a single shared
-- development password so the email + password login path can be exercised
-- end-to-end. FOR DEVELOPMENT / DEMONSTRATION ONLY — never load in production,
-- where users authenticate via the DOT-approved OIDC identity provider
-- (PIV/CAC, MFA) and password_hash stays NULL.
--
--   Shared dev password:  Second@123
--
-- The value below is a bcrypt ($2b$, cost 12) hash of that password, produced
-- by passlib (the same library that verifies it in app/core/security.py).
-- pgcrypto's crypt()/gen_salt() are not used because the pgcrypto extension is
-- not enabled on this PostgreSQL instance (and requires superuser to create).
-- =============================================================================

UPDATE users
SET password_hash = '$2b$12$iDP98tAu7ZbVeY0YZZjiouOeLsOLdTwL2vhXHsTLO8.UoIv7WCxVu'
WHERE password_hash IS NULL;
