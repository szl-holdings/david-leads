-- SPDX-License-Identifier: Apache-2.0
-- Runtime bootstrap and version lock for the David deal-desk persistence contract.
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

ALTER TABLE david_dealdesk_state
    DROP CONSTRAINT IF EXISTS david_dealdesk_state_version_check;

ALTER TABLE david_dealdesk_state
    ADD CONSTRAINT david_dealdesk_state_version_check
    CHECK (version > 0) NOT VALID;

ALTER TABLE david_dealdesk_state
    VALIDATE CONSTRAINT david_dealdesk_state_version_check;

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
VALUES ('dealdesk', 2)
ON CONFLICT (schema_name) DO UPDATE
SET schema_version = EXCLUDED.schema_version,
    applied_at = now()
WHERE david_dealdesk_schema.schema_version = 1;
