-- SPDX-License-Identifier: Apache-2.0
-- Owner-executed bootstrap and version lock for the David deal-desk persistence contract.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'david_dealdesk_runtime') THEN
        CREATE ROLE david_dealdesk_runtime
            NOLOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION;
    END IF;
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO david_dealdesk_runtime',
        current_database()
    );
END
$$;

CREATE TABLE IF NOT EXISTS david_dealdesk_schema (
    schema_name text PRIMARY KEY,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS david_dealdesk_state (
    opportunity_id text PRIMARY KEY,
    payload jsonb NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS david_dealdesk_events (
    event_id text PRIMARY KEY,
    opportunity_id text NOT NULL,
    event_type text NOT NULL,
    actor text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS david_dealdesk_events_opportunity_created_idx
    ON david_dealdesk_events (opportunity_id, created_at);

INSERT INTO david_dealdesk_schema (schema_name, schema_version)
VALUES ('dealdesk', 1)
ON CONFLICT (schema_name) DO NOTHING;

GRANT USAGE ON SCHEMA public TO david_dealdesk_runtime;
GRANT SELECT ON david_dealdesk_schema TO david_dealdesk_runtime;
GRANT SELECT, INSERT, UPDATE ON david_dealdesk_state TO david_dealdesk_runtime;
GRANT SELECT, INSERT ON david_dealdesk_events TO david_dealdesk_runtime;
