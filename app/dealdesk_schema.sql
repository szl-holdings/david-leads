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
