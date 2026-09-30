-- SPDX-License-Identifier: Apache-2.0
-- Expand-only evidence kernel tables for the existing Neon database.
-- Do not drop or replace david_dealdesk_state / david_dealdesk_events.
-- SQLite is test-only and must never be applied here.

INSERT INTO david_dealdesk_schema (schema_name, schema_version)
VALUES ('evidence', 1)
ON CONFLICT (schema_name) DO NOTHING;

-- A replay of this migration may preserve V1 or V2; it must never silently
-- reinterpret a database already migrated by a newer application contract.
DO $$
BEGIN
    IF (SELECT schema_version FROM david_dealdesk_schema WHERE schema_name='evidence') NOT IN (1,2) THEN
        RAISE EXCEPTION 'EVIDENCE_SCHEMA_VERSION_MISMATCH';
    END IF;
END
$$;

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
        OR (relationship = 'SAME_ORGANIZATION_ID' AND kind = 'organization')
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

-- V2 preserves every original envelope byte. New decisions bind a scoped epoch.
CREATE TABLE IF NOT EXISTS decision_scopes (
    tenant text NOT NULL,
    scope_id text NOT NULL,
    decision_epoch bigint NOT NULL DEFAULT 0 CHECK (decision_epoch >= 0),
    suppressed boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tenant, scope_id)
);
ALTER TABLE decision_scopes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_scopes_tenant ON decision_scopes;
CREATE POLICY decision_scopes_tenant ON decision_scopes FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));
ALTER TABLE evidence_nodes ADD COLUMN IF NOT EXISTS scope_id text NOT NULL DEFAULT 'legacy';
ALTER TABLE evidence_nodes ADD COLUMN IF NOT EXISTS decision_epoch bigint NOT NULL DEFAULT 0;
INSERT INTO decision_scopes (tenant, scope_id)
SELECT DISTINCT tenant, scope_id FROM evidence_nodes ON CONFLICT DO NOTHING;

ALTER TABLE source_grants ADD COLUMN IF NOT EXISTS scope_id text NOT NULL DEFAULT 'legacy';
ALTER TABLE source_grants DROP CONSTRAINT IF EXISTS source_grants_pkey;
ALTER TABLE source_grants ADD PRIMARY KEY (tenant,source_id,policy_revision,scope_id);
ALTER TABLE observations ADD COLUMN IF NOT EXISTS scope_id text NOT NULL DEFAULT 'legacy';
ALTER TABLE observations DROP CONSTRAINT IF EXISTS observations_tenant_source_id_source_record_id_revision_key;
CREATE UNIQUE INDEX IF NOT EXISTS observations_scoped_source_revision
    ON observations (tenant,source_id,source_record_id,revision,scope_id);

CREATE TABLE IF NOT EXISTS source_grant_authorities (
    tenant text NOT NULL,
    source_id text NOT NULL,
    policy_revision text NOT NULL,
    revoked boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tenant,source_id,policy_revision)
);
ALTER TABLE source_grant_authorities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS source_grant_authorities_tenant ON source_grant_authorities;
CREATE POLICY source_grant_authorities_tenant ON source_grant_authorities FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

ALTER TABLE identity_candidates DROP CONSTRAINT IF EXISTS identity_candidates_candidates_are_not_canonical;
ALTER TABLE identity_candidates ADD CONSTRAINT identity_candidates_candidates_are_not_canonical
    CHECK (canonical_organization_id IS NULL
        OR (relationship = 'SAME_ORGANIZATION_ID' AND kind = 'organization'));

ALTER TABLE identity_candidates DROP CONSTRAINT IF EXISTS identity_candidates_typed_namespace;
ALTER TABLE identity_candidates ADD CONSTRAINT identity_candidates_typed_namespace CHECK (
    (namespace <> 'PARCEL' OR kind = 'parcel') AND
    (namespace <> 'EPA_FRS' OR kind = 'facility') AND
    (namespace <> 'USDOT' OR kind = 'carrier') AND
    (namespace NOT IN ('SEC_CIK','UEI') OR kind = 'organization')
);

CREATE TABLE IF NOT EXISTS source_health (
    tenant text NOT NULL,
    source_id text NOT NULL,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant,source_id)
);
ALTER TABLE source_health ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS source_health_tenant ON source_health;
CREATE POLICY source_health_tenant ON source_health FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

CREATE TABLE IF NOT EXISTS manual_tasks (
    tenant text NOT NULL,
    id text NOT NULL,
    scope_id text NOT NULL,
    decision_epoch bigint NOT NULL,
    clearance_node text NOT NULL,
    idempotency_key text NOT NULL,
    request_digest text NOT NULL,
    body text NOT NULL,
    state text NOT NULL CHECK (state IN ('PENDING', 'REVOKED')),
    PRIMARY KEY (tenant, id),
    UNIQUE (tenant, scope_id, idempotency_key),
    FOREIGN KEY (tenant, id) REFERENCES evidence_nodes (tenant, id),
    FOREIGN KEY (tenant, clearance_node) REFERENCES evidence_nodes (tenant, id)
);
ALTER TABLE manual_tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS manual_tasks_tenant ON manual_tasks;
CREATE POLICY manual_tasks_tenant ON manual_tasks FOR ALL
    USING (tenant = current_setting('david.tenant', true))
    WITH CHECK (tenant = current_setting('david.tenant', true));

ALTER TABLE outbox ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'PENDING';
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS fencing_token bigint NOT NULL DEFAULT 0;
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS worker text;
ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_status_known;
ALTER TABLE outbox ADD CONSTRAINT outbox_status_known
    CHECK (status IN ('PENDING', 'LEASED', 'DISPATCHING', 'PUBLISHED', 'DELIVERY_UNKNOWN', 'CANCELLED'));
UPDATE david_dealdesk_schema SET schema_version=2, applied_at=now()
WHERE schema_name='evidence' AND schema_version=1;
