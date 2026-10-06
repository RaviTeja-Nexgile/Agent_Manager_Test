-- =============================================================================
-- CCFP IT Solution - Migration 0002: user password hash (dev auth path)
-- =============================================================================
-- Adds users.password_hash for the email + password login path used by the
-- development identity provider (documentation §14 / §12.1). The column is
-- NULLABLE: production deployments authenticate via the DOT-approved OIDC
-- provider (PIV/CAC, MFA) and may leave password_hash NULL.
--
-- Hashes are bcrypt ($2b$...), verified server-side by passlib in
-- app/core/security.py. Demo passwords are seeded separately (seeds/0005).
-- =============================================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

COMMENT ON COLUMN users.password_hash IS
    'bcrypt hash for the dev email+password login path; NULL when the user '
    'authenticates only via the production OIDC identity provider.';
