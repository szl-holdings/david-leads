-- SPDX-License-Identifier: Apache-2.0
-- Expand-only evidence kernel tables for the existing Neon database.
-- Do not drop or replace david_dealdesk_state / david_dealdesk_events.
-- SQLite is test-only and must never be applied here.

INSERT INTO david_dealdesk_schema (schema_name, schema_version)
VALUES ('evidence', 1)
ON CONFLICT (schema_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS source_grants (
    tenant text NOT NULL,
    source_id text NOT NULL,
    policy_revision text NOT NULL,
    review_reference text NOT NULL,
    expires_at text NOT NULL,
    rights text NOT NULL,
    allowed_fields text NOT NULL,
    envelope text NOT NULL,
    node_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, source_id, policy_revision)
);

CREATE TABLE IF NOT EXISTS observations (
    tenant text NOT NULL,
    id text NOT NULL,
    source_id text NOT NULL,
    source_record_id text NOT NULL,
    revision text NOT NULL,
    published_at text NOT NULL,
    observed_at text NOT NULL,
    expires_at text NOT NULL,
    fields text NOT NULL,
    envelope text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, id),
    UNIQUE (tenant, source_id, source_record_id, revision)
);

CREATE TABLE IF NOT EXISTS identity_candidates (
    tenant text NOT NULL,
    id text NOT NULL,
    kind text NOT NULL,
    namespace text NOT NULL,
    jurisdiction text NOT NULL,
    value_normalized text NOT NULL,
    name_key text,
    state_code text,
    postal text,
    relationship text NOT NULL,
    canonical_organization_id text,
    observation_id text,
    envelope text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, id),
    CONSTRAINT identity_candidates_relationship_known CHECK (
        relationship IN (
            'CANDIDATE_REVIEW',
            'UNRESOLVED',
            'CONFLICT_REVIEW',
            'SAME_ORGANIZATION_ID',
            'SAME_NON_ORGANIZATION_RECORD'
        )
    ),
    CONSTRAINT identity_candidates_candidates_are_not_canonical CHECK (
        canonical_organization_id IS NULL
        OR relationship IN ('SAME_ORGANIZATION_ID', 'SAME_NON_ORGANIZATION_RECORD')
    )
);

CREATE TABLE IF NOT EXISTS evidence_nodes (
    tenant text NOT NULL,
    id text NOT NULL,
    kind text NOT NULL,
    envelope text NOT NULL,
    expires_at text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, id)
);

CREATE TABLE IF NOT EXISTS evidence_edges (
    tenant text NOT NULL,
    parent text NOT NULL,
    child text NOT NULL,
    PRIMARY KEY (tenant, parent, child),
    FOREIGN KEY (tenant, parent) REFERENCES evidence_nodes (tenant, id),
    FOREIGN KEY (tenant, child) REFERENCES evidence_nodes (tenant, id)
);

CREATE INDEX IF NOT EXISTS evidence_edges_child
    ON evidence_edges (tenant, child);

CREATE TABLE IF NOT EXISTS derivations (
    tenant text NOT NULL,
    id text NOT NULL,
    kind text NOT NULL,
    node_id text NOT NULL,
    body text NOT NULL,
    expires_at text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, node_id) REFERENCES evidence_nodes (tenant, id)
);

CREATE TABLE IF NOT EXISTS clearances (
    tenant text NOT NULL,
    id text NOT NULL,
    node_id text NOT NULL,
    named_operator text NOT NULL,
    facts text NOT NULL,
    expires_at text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, node_id) REFERENCES evidence_nodes (tenant, id)
);

CREATE TABLE IF NOT EXISTS suppressions (
    tenant text NOT NULL,
    id text NOT NULL,
    subject_key text NOT NULL,
    reason text NOT NULL,
    recorded_at text NOT NULL,
    node_id text,
    active boolean NOT NULL DEFAULT true,
    envelope text NOT NULL,
    PRIMARY KEY (tenant, id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    tenant text NOT NULL,
    id text NOT NULL,
    kind text NOT NULL,
    node_id text NOT NULL,
    body text NOT NULL,
    expires_at text NOT NULL,
    state text NOT NULL CHECK (state IN ('VALID', 'REVOKED')),
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, node_id) REFERENCES evidence_nodes (tenant, id)
);

CREATE TABLE IF NOT EXISTS outbox (
    tenant text NOT NULL,
    id text NOT NULL,
    node_id text NOT NULL,
    event_type text NOT NULL,
    payload text NOT NULL,
    created_at text NOT NULL,
    published_at text,
    PRIMARY KEY (tenant, id)
);

CREATE INDEX IF NOT EXISTS outbox_unpublished
    ON outbox (tenant, created_at)
    WHERE published_at IS NULL;

ALTER TABLE source_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE derivations ENABLE ROW LEVEL SECURITY;
ALTER TABLE clearances ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS source_grants_tenant ON source_grants;
CREATE POLICY source_grants_tenant ON source_grants
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS observations_tenant ON observations;
CREATE POLICY observations_tenant ON observations
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS identity_candidates_tenant ON identity_candidates;
CREATE POLICY identity_candidates_tenant ON identity_candidates
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS evidence_nodes_tenant ON evidence_nodes;
CREATE POLICY evidence_nodes_tenant ON evidence_nodes
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS evidence_edges_tenant ON evidence_edges;
CREATE POLICY evidence_edges_tenant ON evidence_edges
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS derivations_tenant ON derivations;
CREATE POLICY derivations_tenant ON derivations
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS clearances_tenant ON clearances;
CREATE POLICY clearances_tenant ON clearances
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS suppressions_tenant ON suppressions;
CREATE POLICY suppressions_tenant ON suppressions
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS outcomes_tenant ON outcomes;
CREATE POLICY outcomes_tenant ON outcomes
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

DROP POLICY IF EXISTS outbox_tenant ON outbox;
CREATE POLICY outbox_tenant ON outbox
    FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));
