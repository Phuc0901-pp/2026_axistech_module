-- ISO/IEC 27001 Identity, RBAC & Session Persistence (Zero Plaintext Passwords)
CREATE TABLE IF NOT EXISTS core.users (
    id              text PRIMARY KEY,
    email           text NOT NULL UNIQUE,
    display_name    text NOT NULL,
    role            text NOT NULL DEFAULT 'ADMIN' CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER')),
    password_hash   text NOT NULL,
    active          boolean NOT NULL DEFAULT true,
    failed_attempts integer NOT NULL DEFAULT 0,
    locked_until_utc timestamptz,
    last_login_utc  timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.user_sessions (
    session_id      text PRIMARY KEY,
    user_id         text NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    expires_at_utc  timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    revoked_at      timestamptz
);

CREATE INDEX IF NOT EXISTS idx_core_users_email ON core.users (lower(email));
CREATE INDEX IF NOT EXISTS idx_core_sessions_user ON core.user_sessions (user_id, expires_at_utc DESC);

-- Seeded Administrator Account (Salted PBKDF2-HMAC-SHA256, 100000 iterations)
INSERT INTO core.users (id, email, display_name, role, password_hash, active)
VALUES (
    'usr-tbsg-admin-01',
    'admin@tanbaocorp.vn',
    'TBSG Administrator',
    'ADMIN',
    'pbkdf2_sha256$100000$3d372b5efd2b3ee2fa4a8df323f1fe4e$9d9a3de495edab4c4107df6f1d081b276e8b227fb49ef47b5bd170bdfb9ebeec',
    true
)
ON CONFLICT (email) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    role = EXCLUDED.role,
    password_hash = EXCLUDED.password_hash,
    active = true,
    updated_at = now();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agtech_erp_app') THEN
        GRANT SELECT, INSERT, UPDATE ON core.users, core.user_sessions TO agtech_erp_app;
    END IF;
END;
$$;
