BEGIN;

-- Running upgrade 20260925_0013 -> 20261001_0014

ALTER TABLE chat_interaction DROP CONSTRAINT ck_chat_interaction_abstention_reason;

ALTER TABLE chat_interaction ADD CONSTRAINT ck_chat_interaction_abstention_reason CHECK (abstention_reason IS NULL OR abstention_reason IN ('no_matching_evidence','empty_analysis_cohort','publication_pending','aggregate_scope_required','aggregate_unavailable','no_sources_selected','source_disabled','freshness_unavailable'));

UPDATE alembic_version SET version_num='20261001_0014' WHERE alembic_version.version_num = '20260925_0013';

-- Running upgrade 20261001_0014 -> 20261004_0015

CREATE TABLE research_registry_review (
    id UUID NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    registry_key VARCHAR(255) NOT NULL, 
    definition_json JSON NOT NULL, 
    content_sha256 VARCHAR(64) NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by_user_id UUID NOT NULL, 
    decided_by_user_id UUID, 
    applied_by_user_id UUID, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_research_registry_review_kind CHECK (kind IN ('sampling', 'sst_product')), 
    CONSTRAINT ck_research_registry_review_state CHECK (state IN ('draft', 'approved', 'rejected', 'applied')), 
    CONSTRAINT ck_research_registry_review_version CHECK (version >= 1), 
    CONSTRAINT ck_research_registry_review_decided CHECK (state = 'draft' OR decided_by_user_id IS NOT NULL), 
    CONSTRAINT ck_research_registry_review_applied CHECK (state <> 'applied' OR applied_by_user_id IS NOT NULL), 
    FOREIGN KEY(created_by_user_id) REFERENCES app_user (id) ON DELETE RESTRICT, 
    FOREIGN KEY(decided_by_user_id) REFERENCES app_user (id) ON DELETE RESTRICT, 
    FOREIGN KEY(applied_by_user_id) REFERENCES app_user (id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_registry_review_registry_key ON research_registry_review (registry_key);

CREATE TABLE research_registry_event (
    review_id UUID NOT NULL, 
    sequence INTEGER NOT NULL, 
    event_sha256 VARCHAR(64) NOT NULL, 
    payload_json JSON NOT NULL, 
    PRIMARY KEY (review_id, sequence), 
    CONSTRAINT ck_research_registry_event_sequence CHECK (sequence >= 1), 
    FOREIGN KEY(review_id) REFERENCES research_registry_review (id) ON DELETE RESTRICT, 
    UNIQUE (event_sha256)
);

CREATE TABLE research_registry_version (
    registry_id VARCHAR(64) NOT NULL, 
    review_id UUID NOT NULL, 
    registry_key VARCHAR(255) NOT NULL, 
    payload_json JSON NOT NULL, 
    PRIMARY KEY (registry_id), 
    UNIQUE (review_id), 
    FOREIGN KEY(review_id) REFERENCES research_registry_review (id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_registry_version_registry_key ON research_registry_version (registry_key);

CREATE TABLE research_registry_head (
    registry_key VARCHAR(255) NOT NULL, 
    registry_id VARCHAR(64) NOT NULL, 
    PRIMARY KEY (registry_key), 
    FOREIGN KEY(registry_id) REFERENCES research_registry_version (registry_id) ON DELETE RESTRICT
);

CREATE TABLE research_physical_membership (
    registry_id VARCHAR(64) NOT NULL, 
    sample_id VARCHAR(64) NOT NULL, 
    physical_sample_id VARCHAR(64) NOT NULL, 
    scientific_content_sha256 VARCHAR(64) NOT NULL, 
    representative_assay_id VARCHAR(64) NOT NULL, 
    representative_assay_sha256 VARCHAR(64) NOT NULL, 
    area_id VARCHAR(255) NOT NULL, 
    area_version VARCHAR(64) NOT NULL, 
    PRIMARY KEY (registry_id, sample_id), 
    FOREIGN KEY(registry_id) REFERENCES research_registry_version (registry_id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_physical_membership_physical_sample_id ON research_physical_membership (physical_sample_id);

CREATE TABLE research_area_definition (
    registry_id VARCHAR(64) NOT NULL, 
    area_id VARCHAR(255) NOT NULL, 
    area_version VARCHAR(64) NOT NULL, 
    definition_json JSON NOT NULL, 
    PRIMARY KEY (registry_id, area_id), 
    FOREIGN KEY(registry_id) REFERENCES research_registry_version (registry_id) ON DELETE RESTRICT
);

CREATE FUNCTION ocean_research_immutable_record() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Research evidence records are immutable';
        END $$;

CREATE TRIGGER research_registry_event_immutable BEFORE UPDATE OR DELETE ON research_registry_event FOR EACH ROW EXECUTE FUNCTION ocean_research_immutable_record();

CREATE TRIGGER research_registry_version_immutable BEFORE UPDATE OR DELETE ON research_registry_version FOR EACH ROW EXECUTE FUNCTION ocean_research_immutable_record();

CREATE TRIGGER research_physical_membership_immutable BEFORE UPDATE OR DELETE ON research_physical_membership FOR EACH ROW EXECUTE FUNCTION ocean_research_immutable_record();

CREATE TRIGGER research_area_definition_immutable BEFORE UPDATE OR DELETE ON research_area_definition FOR EACH ROW EXECUTE FUNCTION ocean_research_immutable_record();

UPDATE alembic_version SET version_num='20261004_0015' WHERE alembic_version.version_num = '20261001_0014';

-- Running upgrade 20261004_0015 -> 20261005_0016

ALTER TABLE chat_interaction DROP CONSTRAINT ck_chat_interaction_abstention_reason;

ALTER TABLE chat_interaction ADD CONSTRAINT ck_chat_interaction_abstention_reason CHECK (abstention_reason IS NULL OR abstention_reason IN ('no_matching_evidence','empty_analysis_cohort','publication_pending','aggregate_scope_required','aggregate_unavailable','no_sources_selected','source_disabled','freshness_unavailable','incomplete_source_coverage','overlap_unverified'));

UPDATE alembic_version SET version_num='20261005_0016' WHERE alembic_version.version_num = '20261004_0015';

-- Running upgrade 20261005_0016 -> 20261018_0017

CREATE TABLE research_investigation (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    metadata_version INTEGER NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    head_revision_id UUID, 
    predecessor_investigation_id UUID, 
    predecessor_revision_id UUID, 
    legal_hold BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    retired_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_investigation_owner UNIQUE (id, user_id), 
    CONSTRAINT ck_research_investigation_name CHECK (length(name) BETWEEN 1 AND 255 AND length(trim(name)) >= 1), 
    CONSTRAINT ck_research_investigation_version CHECK (metadata_version >= 1), 
    CONSTRAINT ck_research_investigation_status CHECK (status IN ('preparing', 'active', 'archived', 'retired')), 
    CONSTRAINT ck_research_investigation_predecessor_pair CHECK ((predecessor_investigation_id IS NULL AND predecessor_revision_id IS NULL) OR (predecessor_investigation_id IS NOT NULL AND predecessor_revision_id IS NOT NULL)), 
    CONSTRAINT ck_research_investigation_predecessor_other CHECK (predecessor_investigation_id IS NULL OR predecessor_investigation_id <> id), 
    CONSTRAINT fk_research_investigation_predecessor_owner FOREIGN KEY(predecessor_investigation_id, user_id) REFERENCES research_investigation (id, user_id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_investigation_user_id ON research_investigation (user_id);

CREATE INDEX ix_research_investigation_retention ON research_investigation (updated_at, legal_hold, status);

CREATE TABLE research_conversation (
    id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    metadata_version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_research_conversation_name CHECK (length(name) BETWEEN 1 AND 255 AND length(trim(name)) >= 1), 
    CONSTRAINT ck_research_conversation_version CHECK (metadata_version >= 1), 
    FOREIGN KEY(investigation_id) REFERENCES research_investigation (id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_conversation_investigation_id ON research_conversation (investigation_id);

CREATE TABLE research_context_revision (
    id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    sequence INTEGER NOT NULL, 
    predecessor_revision_id UUID, 
    snapshot_id VARCHAR(64) NOT NULL, 
    payload_json TEXT NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    created_by_user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_context_revision_sequence UNIQUE (investigation_id, sequence), 
    CONSTRAINT uq_research_context_revision_identity UNIQUE (investigation_id, id), 
    CONSTRAINT ck_research_context_revision_sequence CHECK (sequence >= 1), 
    CONSTRAINT ck_research_context_revision_snapshot CHECK (length(snapshot_id) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(snapshot_id, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_context_revision_payload_hash CHECK (length(payload_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(payload_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_context_revision_predecessor_other CHECK (predecessor_revision_id IS NULL OR predecessor_revision_id <> id), 
    CONSTRAINT fk_research_context_revision_owner FOREIGN KEY(investigation_id, created_by_user_id) REFERENCES research_investigation (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_context_revision_predecessor FOREIGN KEY(investigation_id, predecessor_revision_id) REFERENCES research_context_revision (investigation_id, id) ON DELETE RESTRICT, 
    FOREIGN KEY(investigation_id) REFERENCES research_investigation (id) ON DELETE RESTRICT, 
    FOREIGN KEY(created_by_user_id) REFERENCES app_user (id) ON DELETE RESTRICT
);

ALTER TABLE research_investigation ADD CONSTRAINT fk_research_investigation_head FOREIGN KEY(id, head_revision_id) REFERENCES research_context_revision (investigation_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE research_investigation ADD CONSTRAINT fk_research_investigation_predecessor_revision FOREIGN KEY(predecessor_investigation_id, predecessor_revision_id) REFERENCES research_context_revision (investigation_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE research_context_operation (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    expected_head_id UUID, 
    candidate_revision_id UUID, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    candidate_json TEXT NOT NULL, 
    references_json TEXT NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    error_code VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_context_operation_idempotency UNIQUE (user_id, idempotency_key), 
    CONSTRAINT ck_research_context_operation_key CHECK (length(idempotency_key) BETWEEN 1 AND 128), 
    CONSTRAINT ck_research_context_operation_kind CHECK (length(kind) BETWEEN 1 AND 32), 
    CONSTRAINT ck_research_context_operation_request_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_context_operation_state CHECK (state IN ('prepared', 'committed', 'conflict', 'unavailable', 'uncertain')), 
    CONSTRAINT ck_research_context_operation_error CHECK (error_code IS NULL OR length(error_code) BETWEEN 1 AND 64), 
    CONSTRAINT fk_research_context_operation_owner FOREIGN KEY(investigation_id, user_id) REFERENCES research_investigation (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_context_operation_expected_head FOREIGN KEY(investigation_id, expected_head_id) REFERENCES research_context_revision (investigation_id, id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE RESTRICT, 
    FOREIGN KEY(investigation_id) REFERENCES research_investigation (id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_context_operation_investigation_id ON research_context_operation (investigation_id);

CREATE FUNCTION ocean_context_revision_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Research context revisions are append-only';
        END $$;

CREATE TRIGGER research_context_revision_immutable
        BEFORE UPDATE OR DELETE ON research_context_revision
        FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_investigation_no_truncate BEFORE TRUNCATE ON research_investigation FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_conversation_no_truncate BEFORE TRUNCATE ON research_conversation FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_context_revision_no_truncate BEFORE TRUNCATE ON research_context_revision FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_context_operation_no_truncate BEFORE TRUNCATE ON research_context_operation FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_investigation_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Research context records are retained';
              END IF;
              IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.predecessor_investigation_id IS DISTINCT FROM OLD.predecessor_investigation_id OR NEW.predecessor_revision_id IS DISTINCT FROM OLD.predecessor_revision_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Research context identity and prepared inputs are immutable';
              END IF;
              RETURN NEW;
            END $$;

CREATE TRIGGER research_investigation_guard BEFORE UPDATE OR DELETE ON research_investigation FOR EACH ROW EXECUTE FUNCTION ocean_research_investigation_guard();

CREATE FUNCTION ocean_research_conversation_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Research context records are retained';
              END IF;
              IF NEW.id IS DISTINCT FROM OLD.id OR NEW.investigation_id IS DISTINCT FROM OLD.investigation_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Research context identity and prepared inputs are immutable';
              END IF;
              RETURN NEW;
            END $$;

CREATE TRIGGER research_conversation_guard BEFORE UPDATE OR DELETE ON research_conversation FOR EACH ROW EXECUTE FUNCTION ocean_research_conversation_guard();

CREATE FUNCTION ocean_research_context_operation_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Research context records are retained';
              END IF;
              IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.investigation_id IS DISTINCT FROM OLD.investigation_id OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.expected_head_id IS DISTINCT FROM OLD.expected_head_id OR NEW.candidate_revision_id IS DISTINCT FROM OLD.candidate_revision_id OR NEW.request_json IS DISTINCT FROM OLD.request_json OR NEW.request_sha256 IS DISTINCT FROM OLD.request_sha256 OR NEW.candidate_json IS DISTINCT FROM OLD.candidate_json OR NEW.references_json IS DISTINCT FROM OLD.references_json OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'Research context identity and prepared inputs are immutable';
              END IF;
              RETURN NEW;
            END $$;

CREATE TRIGGER research_context_operation_guard BEFORE UPDATE OR DELETE ON research_context_operation FOR EACH ROW EXECUTE FUNCTION ocean_research_context_operation_guard();

UPDATE alembic_version SET version_num='20261018_0017' WHERE alembic_version.version_num = '20261005_0016';

-- Running upgrade 20261018_0017 -> 20261019_0018

ALTER TABLE research_conversation ADD CONSTRAINT uq_research_conversation_identity UNIQUE (investigation_id, id);

ALTER TABLE research_context_revision ADD CONSTRAINT uq_research_context_revision_binding UNIQUE (investigation_id, id, snapshot_id, payload_sha256);

CREATE TABLE research_run (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    snapshot_id VARCHAR(64) NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    context_json TEXT NOT NULL, 
    original_question TEXT NOT NULL, 
    effective_question TEXT NOT NULL, 
    continuation_of UUID, 
    status VARCHAR(32) NOT NULL, 
    version INTEGER NOT NULL, 
    input_version INTEGER NOT NULL, 
    clarification_id UUID, 
    event_cursor INTEGER NOT NULL, 
    active_elapsed_ms INTEGER NOT NULL, 
    tool_actions INTEGER NOT NULL, 
    model_calls INTEGER NOT NULL, 
    malformed_repairs INTEGER NOT NULL, 
    lease_epoch INTEGER NOT NULL, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    active_started_at TIMESTAMP WITH TIME ZONE, 
    cancellation_requested BOOLEAN NOT NULL, 
    checkpoint_json TEXT NOT NULL, 
    manifest_json TEXT, 
    controller_result_json TEXT, 
    reason_code VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_run_owner UNIQUE (id, user_id), 
    CONSTRAINT uq_research_run_binding UNIQUE (id, investigation_id, conversation_id, revision_id), 
    CONSTRAINT fk_research_run_owner FOREIGN KEY(investigation_id, user_id) REFERENCES research_investigation (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_run_conversation FOREIGN KEY(investigation_id, conversation_id) REFERENCES research_conversation (investigation_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_run_revision FOREIGN KEY(investigation_id, revision_id, snapshot_id, payload_sha256) REFERENCES research_context_revision (investigation_id, id, snapshot_id, payload_sha256) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_run_continuation_owner FOREIGN KEY(continuation_of, user_id) REFERENCES research_run (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_run_continuation_binding FOREIGN KEY(continuation_of, investigation_id, conversation_id, revision_id) REFERENCES research_run (id, investigation_id, conversation_id, revision_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_run_status CHECK (status IN ('queued','running','awaiting_clarification','awaiting_approval','completed','partial','cancelled','failed')), 
    CONSTRAINT ck_research_run_versions CHECK (version >= 1 AND input_version >= 1 AND event_cursor >= 0 AND lease_epoch >= 0), 
    CONSTRAINT ck_research_run_budget CHECK (active_elapsed_ms >= 0 AND tool_actions BETWEEN 0 AND 12 AND model_calls BETWEEN 0 AND 14 AND malformed_repairs BETWEEN 0 AND 1), 
    CONSTRAINT ck_research_run_question CHECK (length(original_question) BETWEEN 1 AND 8000 AND length(effective_question) BETWEEN 1 AND 8000), 
    CONSTRAINT ck_research_run_snapshot CHECK (length(snapshot_id) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(snapshot_id, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_run_payload_hash CHECK (length(payload_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(payload_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_run_continuation_other CHECK (continuation_of IS NULL OR continuation_of <> id)
);

CREATE INDEX ix_research_run_conversation ON research_run (user_id, investigation_id, conversation_id, created_at, id);

CREATE TABLE research_run_input_history (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    sequence INTEGER NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    effective_question TEXT NOT NULL, 
    result_run_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_run_input_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT uq_research_run_input_sequence UNIQUE (run_id, sequence), 
    CONSTRAINT fk_research_run_input_owner FOREIGN KEY(run_id, user_id) REFERENCES research_run (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_run_input_result_owner FOREIGN KEY(result_run_id, user_id) REFERENCES research_run (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_run_input_kind CHECK (sequence >= 1 AND kind IN ('submit','clarify','continue','cancel')), 
    CONSTRAINT ck_research_run_input_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE TABLE research_run_event (
    run_id UUID NOT NULL, 
    cursor INTEGER NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    elapsed_ms INTEGER NOT NULL, 
    summary_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (run_id, cursor), 
    CONSTRAINT ck_research_run_event_cursor CHECK (cursor >= 1 AND elapsed_ms >= 0), 
    FOREIGN KEY(run_id) REFERENCES research_run (id) ON DELETE RESTRICT
);

CREATE TABLE research_run_payload (
    run_id UUID NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    payload_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (run_id, sha256), 
    CONSTRAINT ck_research_run_retained_hash CHECK (length(sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    FOREIGN KEY(run_id) REFERENCES research_run (id) ON DELETE RESTRICT
);

CREATE TABLE research_run_step (
    run_id UUID NOT NULL, 
    step_id VARCHAR(255) NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    request_json TEXT NOT NULL, 
    outcome_sha256 VARCHAR(64), 
    state VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (run_id, step_id), 
    CONSTRAINT fk_research_run_step_payload FOREIGN KEY(run_id, outcome_sha256) REFERENCES research_run_payload (run_id, sha256) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_run_step_kind CHECK (kind IN ('tool','model','repair')), 
    CONSTRAINT ck_research_run_step_state CHECK ((state = 'prepared' AND outcome_sha256 IS NULL) OR (state = 'committed' AND outcome_sha256 IS NOT NULL)), 
    CONSTRAINT ck_research_run_step_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    FOREIGN KEY(run_id) REFERENCES research_run (id) ON DELETE RESTRICT
);

CREATE TABLE research_run_attempt (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    step_id VARCHAR(255) NOT NULL, 
    ordinal INTEGER NOT NULL, 
    lease_epoch INTEGER NOT NULL, 
    budget_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_run_attempt_ordinal UNIQUE (run_id, step_id, ordinal), 
    CONSTRAINT fk_research_run_attempt_step FOREIGN KEY(run_id, step_id) REFERENCES research_run_step (run_id, step_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_run_attempt_version CHECK (ordinal >= 1 AND lease_epoch >= 1)
);

CREATE TABLE research_run_manifest (
    run_id UUID NOT NULL, 
    input_version INTEGER NOT NULL, 
    manifest_json TEXT NOT NULL, 
    manifest_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (run_id, input_version), 
    CONSTRAINT ck_research_run_manifest_version CHECK (input_version >= 1), 
    CONSTRAINT ck_research_run_manifest_hash CHECK (length(manifest_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(manifest_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    FOREIGN KEY(run_id) REFERENCES research_run (id) ON DELETE RESTRICT
);

CREATE TABLE research_run_outbox (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    input_version INTEGER NOT NULL, 
    delivery_id UUID NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    attempts INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_run_outbox_input UNIQUE (run_id, input_version), 
    CONSTRAINT ck_research_run_outbox_state CHECK (input_version >= 1 AND attempts >= 0 AND state IN ('pending','sent')), 
    FOREIGN KEY(run_id) REFERENCES research_run (id) ON DELETE RESTRICT, 
    UNIQUE (delivery_id)
);

CREATE TRIGGER research_run_input_history_immutable BEFORE UPDATE OR DELETE ON research_run_input_history FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_event_immutable BEFORE UPDATE OR DELETE ON research_run_event FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_payload_immutable BEFORE UPDATE OR DELETE ON research_run_payload FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_attempt_immutable BEFORE UPDATE OR DELETE ON research_run_attempt FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_manifest_immutable BEFORE UPDATE OR DELETE ON research_run_manifest FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_no_truncate BEFORE TRUNCATE ON research_run FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_input_history_no_truncate BEFORE TRUNCATE ON research_run_input_history FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_event_no_truncate BEFORE TRUNCATE ON research_run_event FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_payload_no_truncate BEFORE TRUNCATE ON research_run_payload FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_step_no_truncate BEFORE TRUNCATE ON research_run_step FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_attempt_no_truncate BEFORE TRUNCATE ON research_run_attempt FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_manifest_no_truncate BEFORE TRUNCATE ON research_run_manifest FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_run_outbox_no_truncate BEFORE TRUNCATE ON research_run_outbox FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_run_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Research execution history is retained'; END IF;
IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.investigation_id IS DISTINCT FROM OLD.investigation_id OR NEW.conversation_id IS DISTINCT FROM OLD.conversation_id OR NEW.revision_id IS DISTINCT FROM OLD.revision_id OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256 OR NEW.context_json IS DISTINCT FROM OLD.context_json OR NEW.original_question IS DISTINCT FROM OLD.original_question OR NEW.continuation_of IS DISTINCT FROM OLD.continuation_of OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.version < OLD.version OR NEW.input_version < OLD.input_version OR NEW.event_cursor < OLD.event_cursor OR NEW.active_elapsed_ms < OLD.active_elapsed_ms OR NEW.tool_actions < OLD.tool_actions OR NEW.model_calls < OLD.model_calls OR NEW.malformed_repairs < OLD.malformed_repairs OR NEW.lease_epoch < OLD.lease_epoch OR (OLD.status IN ('completed','partial','cancelled','failed') AND NEW IS DISTINCT FROM OLD) THEN RAISE EXCEPTION 'Research execution identity and committed outcomes are immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_run_guard BEFORE UPDATE OR DELETE ON research_run FOR EACH ROW EXECUTE FUNCTION ocean_research_run_guard();

CREATE FUNCTION ocean_research_run_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Research execution history is retained'; END IF;
IF NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.step_id IS DISTINCT FROM OLD.step_id OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.request_sha256 IS DISTINCT FROM OLD.request_sha256 OR NEW.request_json IS DISTINCT FROM OLD.request_json OR NEW.created_at IS DISTINCT FROM OLD.created_at OR OLD.state = 'committed' THEN RAISE EXCEPTION 'Research execution identity and committed outcomes are immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_run_step_guard BEFORE UPDATE OR DELETE ON research_run_step FOR EACH ROW EXECUTE FUNCTION ocean_research_run_step_guard();

CREATE FUNCTION ocean_research_run_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Research execution history is retained'; END IF;
IF NEW.id IS DISTINCT FROM OLD.id OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.input_version IS DISTINCT FROM OLD.input_version OR NEW.delivery_id IS DISTINCT FROM OLD.delivery_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'Research execution identity and committed outcomes are immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_run_outbox_guard BEFORE UPDATE OR DELETE ON research_run_outbox FOR EACH ROW EXECUTE FUNCTION ocean_research_run_outbox_guard();

UPDATE alembic_version SET version_num='20261019_0018' WHERE alembic_version.version_num = '20261018_0017';

-- Running upgrade 20261019_0018 -> 20261019_0019

ALTER TABLE research_context_operation ADD CONSTRAINT uq_research_context_operation_owner_identity UNIQUE (id, investigation_id, user_id);

CREATE TABLE research_evidence_blob (
    user_id UUID NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    payload_json TEXT NOT NULL, 
    inputs_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id, sha256), 
    CONSTRAINT ck_research_evidence_blob_hash CHECK (length(sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE RESTRICT
);

CREATE TABLE research_answer_job (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    snapshot_id VARCHAR(64) NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    input_version INTEGER NOT NULL, 
    locale VARCHAR(2) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    budget_floor_json TEXT NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    version INTEGER NOT NULL, 
    event_cursor INTEGER NOT NULL, 
    cancellation_requested BOOLEAN NOT NULL, 
    active_elapsed_ms INTEGER NOT NULL, 
    tool_actions INTEGER NOT NULL, 
    model_calls INTEGER NOT NULL, 
    malformed_repairs INTEGER NOT NULL, 
    active_started_at TIMESTAMP WITH TIME ZONE, 
    lease_epoch INTEGER NOT NULL, 
    lease_until TIMESTAMP WITH TIME ZONE, 
    manifest_json TEXT, 
    pack_sha256 VARCHAR(64), 
    reason_code VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_answer_job_owner UNIQUE (id, user_id), 
    CONSTRAINT uq_research_answer_job_run_owner UNIQUE (id, user_id, run_id), 
    CONSTRAINT uq_research_answer_job_input UNIQUE (run_id, input_version), 
    CONSTRAINT uq_research_answer_job_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_research_answer_job_owner FOREIGN KEY(run_id, user_id) REFERENCES research_run (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_answer_job_run_binding FOREIGN KEY(run_id, investigation_id, conversation_id, revision_id) REFERENCES research_run (id, investigation_id, conversation_id, revision_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_answer_job_input FOREIGN KEY(run_id, input_version) REFERENCES research_run_manifest (run_id, input_version) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_answer_job_revision FOREIGN KEY(investigation_id, revision_id, snapshot_id, payload_sha256) REFERENCES research_context_revision (investigation_id, id, snapshot_id, payload_sha256) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_answer_job_status CHECK (status IN ('queued','running','completed','partial','cancelled','failed','unavailable')), 
    CONSTRAINT ck_research_answer_job_versions CHECK (version >= 1 AND input_version >= 1 AND event_cursor >= 0 AND lease_epoch >= 0), 
    CONSTRAINT ck_research_answer_job_budget CHECK (active_elapsed_ms BETWEEN 0 AND 180000 AND tool_actions BETWEEN 0 AND 12 AND model_calls BETWEEN 0 AND 14 AND malformed_repairs BETWEEN 0 AND 1), 
    CONSTRAINT ck_research_answer_job_locale_key CHECK (locale IN ('en','ja') AND length(idempotency_key) BETWEEN 1 AND 128), 
    CONSTRAINT ck_research_answer_job_request_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE TABLE research_evidence_receipt (
    id VARCHAR(76) NOT NULL, 
    user_id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    input_version INTEGER NOT NULL, 
    investigation_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    snapshot_id VARCHAR(64) NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    blob_sha256 VARCHAR(64) NOT NULL, 
    receipt_json TEXT NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_evidence_receipt_owner UNIQUE (id, user_id), 
    CONSTRAINT fk_research_evidence_receipt_owner FOREIGN KEY(run_id, user_id) REFERENCES research_run (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_evidence_receipt_run_binding FOREIGN KEY(run_id, investigation_id, conversation_id, revision_id) REFERENCES research_run (id, investigation_id, conversation_id, revision_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_evidence_receipt_input FOREIGN KEY(run_id, input_version) REFERENCES research_run_manifest (run_id, input_version) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_evidence_receipt_revision FOREIGN KEY(investigation_id, revision_id, snapshot_id, payload_sha256) REFERENCES research_context_revision (investigation_id, id, snapshot_id, payload_sha256) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_evidence_receipt_blob FOREIGN KEY(user_id, blob_sha256) REFERENCES research_evidence_blob (user_id, sha256) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_evidence_receipt_identity CHECK (id = 'c21:receipt:' || sha256), 
    CONSTRAINT ck_research_evidence_receipt_state CHECK (state IN ('prepared','ready')), 
    CONSTRAINT ck_research_evidence_receipt_hash CHECK (length(sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE INDEX ix_research_evidence_run_input ON research_evidence_receipt (user_id, run_id, input_version, id);

CREATE TABLE research_answer (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    answer_json TEXT NOT NULL, 
    answer_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_research_answer_owner_run FOREIGN KEY(job_id, user_id, run_id) REFERENCES research_answer_job (id, user_id, run_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_answer_hash CHECK (length(answer_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(answer_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    UNIQUE (job_id)
);

CREATE TABLE research_answer_event (
    job_id UUID NOT NULL, 
    cursor INTEGER NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    elapsed_ms INTEGER NOT NULL, 
    summary_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (job_id, cursor), 
    CONSTRAINT ck_research_answer_event_cursor CHECK (cursor >= 1 AND elapsed_ms BETWEEN 0 AND 180000), 
    FOREIGN KEY(job_id) REFERENCES research_answer_job (id) ON DELETE RESTRICT
);

CREATE TABLE research_answer_input_history (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_answer_input_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_research_answer_input_owner FOREIGN KEY(job_id, user_id) REFERENCES research_answer_job (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_answer_input_kind CHECK (kind IN ('submit','cancel') AND length(idempotency_key) BETWEEN 1 AND 128), 
    CONSTRAINT ck_research_answer_input_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE TABLE research_answer_outbox (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    delivery_id UUID NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    attempts INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_research_answer_outbox_state CHECK (attempts >= 0 AND state IN ('pending','sent')), 
    UNIQUE (job_id), 
    FOREIGN KEY(job_id) REFERENCES research_answer_job (id) ON DELETE RESTRICT, 
    UNIQUE (delivery_id)
);

CREATE TABLE research_answer_payload (
    job_id UUID NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    payload_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (job_id, sha256), 
    CONSTRAINT ck_research_answer_payload_hash CHECK (length(sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    FOREIGN KEY(job_id) REFERENCES research_answer_job (id) ON DELETE RESTRICT
);

CREATE TABLE research_evidence_context_dependency (
    operation_id UUID NOT NULL, 
    receipt_id VARCHAR(76) NOT NULL, 
    user_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (operation_id, receipt_id), 
    CONSTRAINT fk_research_evidence_context_operation FOREIGN KEY(operation_id, investigation_id, user_id) REFERENCES research_context_operation (id, investigation_id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_evidence_context_receipt FOREIGN KEY(receipt_id, user_id) REFERENCES research_evidence_receipt (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_evidence_context_state CHECK (state IN ('prepared','committed'))
);

CREATE TABLE research_evidence_dependency (
    receipt_id VARCHAR(76) NOT NULL, 
    origin_receipt_id VARCHAR(76) NOT NULL, 
    user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (receipt_id, origin_receipt_id), 
    CONSTRAINT fk_research_evidence_dependency_owner FOREIGN KEY(receipt_id, user_id) REFERENCES research_evidence_receipt (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_evidence_dependency_origin FOREIGN KEY(origin_receipt_id, user_id) REFERENCES research_evidence_receipt (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_evidence_dependency_other CHECK (receipt_id <> origin_receipt_id)
);

CREATE TABLE research_evidence_protection (
    receipt_id VARCHAR(76) NOT NULL, 
    user_id UUID NOT NULL, 
    references_json TEXT NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (receipt_id), 
    CONSTRAINT fk_research_evidence_protection_owner FOREIGN KEY(receipt_id, user_id) REFERENCES research_evidence_receipt (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_evidence_protection_state CHECK (state IN ('prepared','uncertain','ready'))
);

CREATE TABLE research_answer_step (
    job_id UUID NOT NULL, 
    step_id VARCHAR(255) NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    outcome_sha256 VARCHAR(64), 
    state VARCHAR(16) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (job_id, step_id), 
    CONSTRAINT fk_research_answer_step_payload FOREIGN KEY(job_id, outcome_sha256) REFERENCES research_answer_payload (job_id, sha256) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_answer_step_kind CHECK (kind IN ('tool','model','repair')), 
    CONSTRAINT ck_research_answer_step_state CHECK ((state = 'prepared' AND outcome_sha256 IS NULL) OR (state = 'committed' AND outcome_sha256 IS NOT NULL)), 
    CONSTRAINT ck_research_answer_step_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    FOREIGN KEY(job_id) REFERENCES research_answer_job (id) ON DELETE RESTRICT
);

CREATE TABLE research_answer_attempt (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    step_id VARCHAR(255) NOT NULL, 
    ordinal INTEGER NOT NULL, 
    lease_epoch INTEGER NOT NULL, 
    budget_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_answer_attempt_ordinal UNIQUE (job_id, step_id, ordinal), 
    CONSTRAINT fk_research_answer_attempt_step FOREIGN KEY(job_id, step_id) REFERENCES research_answer_step (job_id, step_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_answer_attempt_version CHECK (ordinal >= 1 AND lease_epoch >= 1)
);

CREATE TRIGGER research_evidence_blob_immutable BEFORE UPDATE OR DELETE ON research_evidence_blob FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_answer_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Private evidence cannot be deleted'; END IF;
IF (to_jsonb(NEW) - ARRAY['status','version','event_cursor','cancellation_requested','active_elapsed_ms','tool_actions','model_calls','malformed_repairs','active_started_at','lease_epoch','lease_until','manifest_json','pack_sha256','reason_code','updated_at']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','version','event_cursor','cancellation_requested','active_elapsed_ms','tool_actions','model_calls','malformed_repairs','active_started_at','lease_epoch','lease_until','manifest_json','pack_sha256','reason_code','updated_at']) THEN RAISE EXCEPTION 'Private evidence identity is immutable'; END IF;
IF OLD.status IN ('completed','partial','cancelled','failed','unavailable') THEN RAISE EXCEPTION 'Terminal answer is immutable'; END IF;
IF NEW.version < OLD.version OR NEW.event_cursor < OLD.event_cursor OR NEW.lease_epoch < OLD.lease_epoch OR NEW.active_elapsed_ms < OLD.active_elapsed_ms OR NEW.tool_actions < OLD.tool_actions OR NEW.model_calls < OLD.model_calls OR NEW.malformed_repairs < OLD.malformed_repairs THEN RAISE EXCEPTION 'Answer counters cannot decrease'; END IF;
IF (OLD.manifest_json IS NOT NULL AND NEW.manifest_json IS DISTINCT FROM OLD.manifest_json) OR (OLD.pack_sha256 IS NOT NULL AND NEW.pack_sha256 IS DISTINCT FROM OLD.pack_sha256) THEN RAISE EXCEPTION 'Answer execution is immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_answer_job_guard BEFORE UPDATE OR DELETE ON research_answer_job FOR EACH ROW EXECUTE FUNCTION ocean_research_answer_job_guard();

CREATE FUNCTION ocean_research_evidence_receipt_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Private evidence cannot be deleted'; END IF;
IF (to_jsonb(NEW) - ARRAY['state']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state']) THEN RAISE EXCEPTION 'Private evidence identity is immutable'; END IF;
IF OLD.state = 'ready' THEN RAISE EXCEPTION 'Ready evidence is immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_evidence_receipt_guard BEFORE UPDATE OR DELETE ON research_evidence_receipt FOR EACH ROW EXECUTE FUNCTION ocean_research_evidence_receipt_guard();

CREATE TRIGGER research_answer_immutable BEFORE UPDATE OR DELETE ON research_answer FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_event_immutable BEFORE UPDATE OR DELETE ON research_answer_event FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_input_history_immutable BEFORE UPDATE OR DELETE ON research_answer_input_history FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_answer_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Private evidence cannot be deleted'; END IF;
IF (to_jsonb(NEW) - ARRAY['state','attempts','sent_at']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state','attempts','sent_at']) THEN RAISE EXCEPTION 'Private evidence identity is immutable'; END IF;
IF NEW.attempts < OLD.attempts OR (OLD.state = 'sent' AND NEW.state <> 'sent') THEN RAISE EXCEPTION 'Outbox rollback'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_answer_outbox_guard BEFORE UPDATE OR DELETE ON research_answer_outbox FOR EACH ROW EXECUTE FUNCTION ocean_research_answer_outbox_guard();

CREATE TRIGGER research_answer_payload_immutable BEFORE UPDATE OR DELETE ON research_answer_payload FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_evidence_context_dependency_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Private evidence cannot be deleted'; END IF;
IF (to_jsonb(NEW) - ARRAY['state']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state']) THEN RAISE EXCEPTION 'Private evidence identity is immutable'; END IF;
IF OLD.state = 'committed' THEN RAISE EXCEPTION 'Committed context protection is immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_evidence_context_dependency_guard BEFORE UPDATE OR DELETE ON research_evidence_context_dependency FOR EACH ROW EXECUTE FUNCTION ocean_research_evidence_context_dependency_guard();

CREATE TRIGGER research_evidence_dependency_immutable BEFORE UPDATE OR DELETE ON research_evidence_dependency FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_evidence_protection_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Private evidence cannot be deleted'; END IF;
IF (to_jsonb(NEW) - ARRAY['state']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state']) THEN RAISE EXCEPTION 'Private evidence identity is immutable'; END IF;
IF OLD.state = 'ready' THEN RAISE EXCEPTION 'Ready evidence is immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_evidence_protection_guard BEFORE UPDATE OR DELETE ON research_evidence_protection FOR EACH ROW EXECUTE FUNCTION ocean_research_evidence_protection_guard();

CREATE FUNCTION ocean_research_answer_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Private evidence cannot be deleted'; END IF;
IF (to_jsonb(NEW) - ARRAY['state','outcome_sha256']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state','outcome_sha256']) THEN RAISE EXCEPTION 'Private evidence identity is immutable'; END IF;
IF OLD.state = 'committed' THEN RAISE EXCEPTION 'Committed answer step is immutable'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_answer_step_guard BEFORE UPDATE OR DELETE ON research_answer_step FOR EACH ROW EXECUTE FUNCTION ocean_research_answer_step_guard();

CREATE TRIGGER research_answer_attempt_immutable BEFORE UPDATE OR DELETE ON research_answer_attempt FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_evidence_retirement_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF NEW.status = 'retired' AND OLD.status <> 'retired' AND (
EXISTS (SELECT 1 FROM research_evidence_receipt r WHERE r.investigation_id=OLD.id) OR
EXISTS (SELECT 1 FROM research_answer_job j WHERE j.investigation_id=OLD.id) OR
EXISTS (SELECT 1 FROM research_evidence_context_dependency d WHERE d.investigation_id=OLD.id)) THEN
RAISE EXCEPTION 'Retained evidence dependency prevents retirement'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_evidence_retirement_guard BEFORE UPDATE ON research_investigation FOR EACH ROW EXECUTE FUNCTION ocean_evidence_retirement_guard();

CREATE FUNCTION ocean_evidence_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE current_status text; BEGIN
SELECT status INTO current_status FROM research_investigation WHERE id=NEW.investigation_id FOR UPDATE;
IF current_status IS NULL OR current_status = 'retired' THEN RAISE EXCEPTION 'Evidence source is unavailable'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_evidence_receipt_source_guard BEFORE INSERT ON research_evidence_receipt FOR EACH ROW EXECUTE FUNCTION ocean_evidence_insert_guard();

CREATE TRIGGER research_answer_job_source_guard BEFORE INSERT ON research_answer_job FOR EACH ROW EXECUTE FUNCTION ocean_evidence_insert_guard();

CREATE TRIGGER research_evidence_context_dependency_source_guard BEFORE INSERT ON research_evidence_context_dependency FOR EACH ROW EXECUTE FUNCTION ocean_evidence_insert_guard();

CREATE FUNCTION ocean_evidence_dependency_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE producer_state text; consumer_state text; closure_size integer; cycle_found boolean;
BEGIN
SELECT state INTO consumer_state FROM research_evidence_receipt WHERE id=NEW.receipt_id AND user_id=NEW.user_id FOR UPDATE;
SELECT state INTO producer_state FROM research_evidence_receipt WHERE id=NEW.origin_receipt_id AND user_id=NEW.user_id;
IF consumer_state <> 'prepared' OR producer_state <> 'ready' THEN RAISE EXCEPTION 'Only a prepared receipt may retain an older ready receipt'; END IF;
-- UNION on node identity visits a shared DAG once, rather than enumerating paths.
-- Include the prepared consumer in the 1024 distinct-node budget.
WITH RECURSIVE origins(id) AS (
  SELECT NEW.origin_receipt_id
  UNION
  SELECT d.origin_receipt_id FROM research_evidence_dependency d JOIN origins o ON d.receipt_id=o.id
)
SELECT count(*), coalesce(bool_or(id=NEW.receipt_id),false) INTO closure_size,cycle_found
FROM (SELECT id FROM origins LIMIT 1024) bounded;
IF cycle_found OR closure_size >= 1024 THEN RAISE EXCEPTION 'Evidence dependency cycle or unbounded closure'; END IF;
-- Existing origins and the proposed origin can be individually small but have
-- a combined closure larger than the same read-side distinct-node allowance.
WITH RECURSIVE combined(id) AS (
  SELECT NEW.receipt_id UNION SELECT NEW.origin_receipt_id
  UNION
  SELECT d.origin_receipt_id FROM research_evidence_dependency d JOIN combined c ON d.receipt_id=c.id
)
SELECT count(*) INTO closure_size FROM (SELECT id FROM combined LIMIT 1025) bounded;
IF closure_size > 1024 THEN RAISE EXCEPTION 'Evidence dependency cycle or unbounded closure'; END IF;
RETURN NEW; END $$;

CREATE TRIGGER research_evidence_dependency_guard BEFORE INSERT ON research_evidence_dependency FOR EACH ROW EXECUTE FUNCTION ocean_evidence_dependency_guard();

CREATE TRIGGER research_answer_no_truncate BEFORE TRUNCATE ON research_answer FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_attempt_no_truncate BEFORE TRUNCATE ON research_answer_attempt FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_event_no_truncate BEFORE TRUNCATE ON research_answer_event FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_input_history_no_truncate BEFORE TRUNCATE ON research_answer_input_history FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_job_no_truncate BEFORE TRUNCATE ON research_answer_job FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_outbox_no_truncate BEFORE TRUNCATE ON research_answer_outbox FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_payload_no_truncate BEFORE TRUNCATE ON research_answer_payload FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_answer_step_no_truncate BEFORE TRUNCATE ON research_answer_step FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_evidence_blob_no_truncate BEFORE TRUNCATE ON research_evidence_blob FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_evidence_context_dependency_no_truncate BEFORE TRUNCATE ON research_evidence_context_dependency FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_evidence_dependency_no_truncate BEFORE TRUNCATE ON research_evidence_dependency FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_evidence_protection_no_truncate BEFORE TRUNCATE ON research_evidence_protection FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_evidence_receipt_no_truncate BEFORE TRUNCATE ON research_evidence_receipt FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

UPDATE alembic_version SET version_num='20261019_0019' WHERE alembic_version.version_num = '20261019_0018';

-- Running upgrade 20261019_0019 -> 20261020_0020

CREATE TABLE research_experiment_capacity (
    id SERIAL NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_research_experiment_capacity_singleton CHECK (id = 1)
);

CREATE TABLE research_experiment_input_blob (
    user_id UUID NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    content BYTEA NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id, sha256), 
    CONSTRAINT ck_research_experiment_blob_hash CHECK (length(sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_blob_bytes CHECK (size_bytes BETWEEN 0 AND 268435456 AND length(content) = size_bytes), 
    FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE RESTRICT
);

CREATE TABLE research_experiment (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    head_revision_id UUID, 
    version INTEGER NOT NULL, 
    event_cursor INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_experiment_owner UNIQUE (id, user_id), 
    CONSTRAINT uq_research_experiment_context UNIQUE (id, investigation_id, conversation_id), 
    CONSTRAINT fk_research_experiment_owner FOREIGN KEY(investigation_id, user_id) REFERENCES research_investigation (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_experiment_conversation FOREIGN KEY(investigation_id, conversation_id) REFERENCES research_conversation (investigation_id, id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_experiment_version CHECK (version >= 1 AND event_cursor >= 0)
);

CREATE TABLE research_experiment_event (
    experiment_id UUID NOT NULL, 
    cursor INTEGER NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    summary_json TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (experiment_id, cursor), 
    CONSTRAINT ck_research_experiment_event_cursor CHECK (cursor >= 1), 
    FOREIGN KEY(experiment_id) REFERENCES research_experiment (id) ON DELETE RESTRICT
);

CREATE TABLE research_experiment_operation (
    id UUID NOT NULL, 
    experiment_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    expected_version INTEGER NOT NULL, 
    candidate_revision_id UUID, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    frozen_json TEXT NOT NULL, 
    references_json TEXT NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    result_json TEXT, 
    error_code VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_experiment_operation_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_research_experiment_operation_owner FOREIGN KEY(experiment_id, user_id) REFERENCES research_experiment (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_experiment_operation_origin FOREIGN KEY(investigation_id, user_id) REFERENCES research_investigation (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_experiment_operation_request CHECK (kind IN ('create','revise','approve','dispatch') AND length(idempotency_key) BETWEEN 1 AND 128 AND expected_version >= 1), 
    CONSTRAINT ck_research_experiment_operation_state CHECK (state IN ('prepared','committed','conflict','uncertain','unavailable')), 
    CONSTRAINT ck_research_experiment_operation_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE TABLE research_experiment_revision (
    id UUID NOT NULL, 
    experiment_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    investigation_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    context_revision_id UUID NOT NULL, 
    snapshot_id VARCHAR(64) NOT NULL, 
    payload_sha256 VARCHAR(64) NOT NULL, 
    sequence INTEGER NOT NULL, 
    context_json TEXT NOT NULL, 
    proposal_json TEXT NOT NULL, 
    environment_json TEXT NOT NULL, 
    manifest_json TEXT NOT NULL, 
    proposal_sha256 VARCHAR(64) NOT NULL, 
    code_sha256 VARCHAR(64) NOT NULL, 
    input_manifest_sha256 VARCHAR(64) NOT NULL, 
    environment_sha256 VARCHAR(64) NOT NULL, 
    resources_sha256 VARCHAR(64) NOT NULL, 
    source_sha256 VARCHAR(64) NOT NULL, 
    total_bytes INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_experiment_revision_identity UNIQUE (experiment_id, id), 
    CONSTRAINT uq_research_experiment_revision_owner UNIQUE (id, experiment_id, user_id), 
    CONSTRAINT uq_research_experiment_revision_sequence UNIQUE (experiment_id, sequence), 
    CONSTRAINT fk_research_experiment_revision_owner FOREIGN KEY(experiment_id, user_id) REFERENCES research_experiment (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_experiment_revision_context FOREIGN KEY(experiment_id, investigation_id, conversation_id) REFERENCES research_experiment (id, investigation_id, conversation_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_experiment_revision_frozen FOREIGN KEY(investigation_id, context_revision_id, snapshot_id, payload_sha256) REFERENCES research_context_revision (investigation_id, id, snapshot_id, payload_sha256) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_experiment_revision_bounds CHECK (sequence >= 1 AND total_bytes BETWEEN 1 AND 268435456), 
    CONSTRAINT ck_research_experiment_revision_snapshot_id CHECK (length(snapshot_id) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(snapshot_id, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_payload_sha256 CHECK (length(payload_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(payload_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_proposal_sha256 CHECK (length(proposal_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(proposal_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_code_sha256 CHECK (length(code_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(code_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_input_manifest_sha256 CHECK (length(input_manifest_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(input_manifest_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_environment_sha256 CHECK (length(environment_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(environment_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_resources_sha256 CHECK (length(resources_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(resources_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_research_experiment_revision_source_sha256 CHECK (length(source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE TABLE research_experiment_approval (
    id UUID NOT NULL, 
    experiment_id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    request_json TEXT NOT NULL, 
    request_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_experiment_approval_binding UNIQUE (id, experiment_id, revision_id, user_id), 
    CONSTRAINT uq_research_experiment_approval_revision UNIQUE (revision_id), 
    CONSTRAINT fk_research_experiment_approval_owner FOREIGN KEY(revision_id, experiment_id, user_id) REFERENCES research_experiment_revision (id, experiment_id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_experiment_approval_hash CHECK (length(request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE TABLE research_experiment_revision_file (
    revision_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    experiment_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    PRIMARY KEY (revision_id, name), 
    CONSTRAINT fk_research_experiment_file_revision FOREIGN KEY(revision_id, experiment_id, user_id) REFERENCES research_experiment_revision (id, experiment_id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_research_experiment_file_blob FOREIGN KEY(user_id, sha256) REFERENCES research_experiment_input_blob (user_id, sha256) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_experiment_file_bounds CHECK (length(name) BETWEEN 1 AND 255 AND size_bytes BETWEEN 0 AND 268435456)
);

CREATE TABLE research_experiment_reservation (
    id UUID NOT NULL, 
    experiment_id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    approval_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    slot INTEGER NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    envelope_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_research_experiment_reservation_owner UNIQUE (id, user_id), 
    CONSTRAINT uq_research_experiment_reservation_revision UNIQUE (revision_id), 
    CONSTRAINT fk_research_experiment_reservation_approval FOREIGN KEY(approval_id, experiment_id, revision_id, user_id) REFERENCES research_experiment_approval (id, experiment_id, revision_id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_research_experiment_reservation_state CHECK (slot IN (0,1) AND state IN ('reserved','accepted','uncertain','released')), 
    CONSTRAINT ck_research_experiment_reservation_hash CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
);

CREATE UNIQUE INDEX uq_research_experiment_active_slot ON research_experiment_reservation (slot) WHERE state <> 'released';

CREATE UNIQUE INDEX uq_research_experiment_active_owner ON research_experiment_reservation (user_id) WHERE state <> 'released';

CREATE TABLE research_experiment_outbox (
    id UUID NOT NULL, 
    reservation_id UUID NOT NULL, 
    delivery_id UUID NOT NULL, 
    state VARCHAR(16) NOT NULL, 
    attempts INTEGER NOT NULL, 
    receipt_json TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_research_experiment_outbox_state CHECK (state IN ('pending','sent','uncertain') AND attempts >= 0), 
    UNIQUE (reservation_id), 
    FOREIGN KEY(reservation_id) REFERENCES research_experiment_reservation (id) ON DELETE RESTRICT, 
    UNIQUE (delivery_id)
);

ALTER TABLE research_experiment ADD CONSTRAINT fk_research_experiment_head FOREIGN KEY(id, head_revision_id) REFERENCES research_experiment_revision (experiment_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

INSERT INTO research_experiment_capacity(id) VALUES (1);

CREATE TRIGGER research_experiment_capacity_immutable BEFORE UPDATE OR DELETE ON research_experiment_capacity FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_capacity_no_truncate BEFORE TRUNCATE ON research_experiment_capacity FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_input_blob_immutable BEFORE UPDATE OR DELETE ON research_experiment_input_blob FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_input_blob_no_truncate BEFORE TRUNCATE ON research_experiment_input_blob FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_experiment_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Private experiments cannot be deleted'; END IF; IF (to_jsonb(NEW)-ARRAY['head_revision_id','version','event_cursor','updated_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['head_revision_id','version','event_cursor','updated_at']) THEN RAISE EXCEPTION 'Experiment identity is immutable'; END IF; IF NEW.version < OLD.version OR NEW.event_cursor < OLD.event_cursor THEN RAISE EXCEPTION 'Experiment counters cannot decrease'; END IF; IF NEW.head_revision_id IS DISTINCT FROM OLD.head_revision_id THEN IF OLD.head_revision_id IS NOT NULL AND NEW.version <> OLD.version+1 THEN RAISE EXCEPTION 'New proposal head requires a new version'; END IF; IF NOT EXISTS (SELECT 1 FROM research_experiment_revision r WHERE r.id=NEW.head_revision_id AND r.experiment_id=NEW.id AND r.sequence=NEW.version) THEN RAISE EXCEPTION 'Proposal head version mismatch'; END IF; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_immutable BEFORE UPDATE OR DELETE ON research_experiment FOR EACH ROW EXECUTE FUNCTION ocean_research_experiment_guard();

CREATE TRIGGER research_experiment_no_truncate BEFORE TRUNCATE ON research_experiment FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_event_immutable BEFORE UPDATE OR DELETE ON research_experiment_event FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_event_no_truncate BEFORE TRUNCATE ON research_experiment_event FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_experiment_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Private experiments cannot be deleted'; END IF; IF (to_jsonb(NEW)-ARRAY['state','result_json','error_code','updated_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','result_json','error_code','updated_at']) THEN RAISE EXCEPTION 'Experiment identity is immutable'; END IF; IF OLD.state IN ('committed','conflict') THEN RAISE EXCEPTION 'Final experiment operation is immutable'; END IF; IF OLD.result_json IS NOT NULL AND NEW.result_json IS DISTINCT FROM OLD.result_json THEN RAISE EXCEPTION 'Operation result is immutable'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_operation_immutable BEFORE UPDATE OR DELETE ON research_experiment_operation FOR EACH ROW EXECUTE FUNCTION ocean_research_experiment_operation_guard();

CREATE TRIGGER research_experiment_operation_no_truncate BEFORE TRUNCATE ON research_experiment_operation FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_revision_immutable BEFORE UPDATE OR DELETE ON research_experiment_revision FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_revision_no_truncate BEFORE TRUNCATE ON research_experiment_revision FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_approval_immutable BEFORE UPDATE OR DELETE ON research_experiment_approval FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_approval_no_truncate BEFORE TRUNCATE ON research_experiment_approval FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_revision_file_immutable BEFORE UPDATE OR DELETE ON research_experiment_revision_file FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_revision_file_no_truncate BEFORE TRUNCATE ON research_experiment_revision_file FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_experiment_reservation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Private experiments cannot be deleted'; END IF; IF (to_jsonb(NEW)-ARRAY['state','updated_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','updated_at']) THEN RAISE EXCEPTION 'Experiment identity is immutable'; END IF; IF OLD.state IN ('accepted','released') OR NEW.state='released' OR (OLD.state='uncertain' AND NEW.state='reserved') THEN RAISE EXCEPTION 'C22 reservation cannot be released or rolled back'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_reservation_immutable BEFORE UPDATE OR DELETE ON research_experiment_reservation FOR EACH ROW EXECUTE FUNCTION ocean_research_experiment_reservation_guard();

CREATE TRIGGER research_experiment_reservation_no_truncate BEFORE TRUNCATE ON research_experiment_reservation FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE FUNCTION ocean_research_experiment_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Private experiments cannot be deleted'; END IF; IF (to_jsonb(NEW)-ARRAY['state','attempts','receipt_json','sent_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','attempts','receipt_json','sent_at']) THEN RAISE EXCEPTION 'Experiment identity is immutable'; END IF; IF OLD.state='sent' OR NEW.attempts < OLD.attempts OR (OLD.state='uncertain' AND NEW.state='pending') OR (OLD.receipt_json IS NOT NULL AND NEW.receipt_json IS DISTINCT FROM OLD.receipt_json) THEN RAISE EXCEPTION 'Delivery acknowledgement and counters are immutable'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_outbox_immutable BEFORE UPDATE OR DELETE ON research_experiment_outbox FOR EACH ROW EXECUTE FUNCTION ocean_research_experiment_outbox_guard();

CREATE TRIGGER research_experiment_outbox_no_truncate BEFORE TRUNCATE ON research_experiment_outbox FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable();

CREATE TRIGGER research_experiment_source_guard BEFORE INSERT ON research_experiment FOR EACH ROW EXECUTE FUNCTION ocean_evidence_insert_guard();

CREATE TRIGGER research_experiment_operation_source_guard BEFORE INSERT ON research_experiment_operation FOR EACH ROW EXECUTE FUNCTION ocean_evidence_insert_guard();

CREATE FUNCTION ocean_experiment_retirement_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.status='retired' AND OLD.status<>'retired' AND (EXISTS(SELECT 1 FROM research_experiment e WHERE e.investigation_id=OLD.id) OR EXISTS(SELECT 1 FROM research_experiment_operation o WHERE o.investigation_id=OLD.id)) THEN RAISE EXCEPTION 'Retained experiment prevents retirement'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_retirement_guard BEFORE UPDATE ON research_investigation FOR EACH ROW EXECUTE FUNCTION ocean_experiment_retirement_guard();

CREATE FUNCTION ocean_experiment_file_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF EXISTS(SELECT 1 FROM research_experiment e WHERE e.id=NEW.experiment_id AND e.head_revision_id=NEW.revision_id) OR NOT EXISTS(SELECT 1 FROM research_experiment_operation o WHERE o.experiment_id=NEW.experiment_id AND o.candidate_revision_id=NEW.revision_id AND o.user_id=NEW.user_id AND o.state IN ('prepared','uncertain','unavailable')) THEN RAISE EXCEPTION 'Only prepared revisions accept input files'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_file_insert_guard BEFORE INSERT ON research_experiment_revision_file FOR EACH ROW EXECUTE FUNCTION ocean_experiment_file_insert_guard();

CREATE FUNCTION ocean_experiment_reservation_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM id FROM research_experiment_capacity WHERE id=1 FOR UPDATE; IF NOT FOUND OR NEW.state<>'reserved' THEN RAISE EXCEPTION 'C22 reservations require fixed capacity and reserved state'; END IF; IF NOT EXISTS(SELECT 1 FROM research_experiment e JOIN research_experiment_revision r ON r.experiment_id=e.id AND r.id=e.head_revision_id JOIN research_investigation i ON i.id=e.investigation_id WHERE e.id=NEW.experiment_id AND r.id=NEW.revision_id AND e.user_id=NEW.user_id AND i.status='active' AND i.head_revision_id=r.context_revision_id) THEN RAISE EXCEPTION 'Only the current active proposal can reserve capacity'; END IF; RETURN NEW; END $$;

CREATE TRIGGER research_experiment_reservation_insert_guard BEFORE INSERT ON research_experiment_reservation FOR EACH ROW EXECUTE FUNCTION ocean_experiment_reservation_insert_guard();

UPDATE alembic_version SET version_num='20261020_0020' WHERE alembic_version.version_num = '20261019_0019';

-- Running upgrade 20261020_0020 -> 20261027_0021

DO $c23_offline$
DECLARE target_schema text := current_schema();
has_rows boolean;
BEGIN
IF target_schema IS NULL THEN RAISE EXCEPTION 'C23 target schema unavailable'; END IF;
EXECUTE replace($c23_ddl$CREATE TABLE research_experiment_execution (
    execution_id UUID NOT NULL, 
    reservation_id UUID NOT NULL, 
    owner_user_id UUID NOT NULL, 
    experiment_id UUID NOT NULL, 
    proposal_revision_id UUID NOT NULL, 
    approval_id UUID NOT NULL, 
    site_id VARCHAR(128) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    request_json TEXT NOT NULL, 
    envelope_json TEXT NOT NULL, 
    job_id VARCHAR(52) NOT NULL, 
    image_digest VARCHAR(71) NOT NULL, 
    approval_request_sha256 VARCHAR(64) NOT NULL, 
    execution_request_sha256 VARCHAR(64) NOT NULL, 
    envelope_sha256 VARCHAR(64) NOT NULL, 
    worker_id VARCHAR(64) NOT NULL, 
    source_sha256 VARCHAR(64) NOT NULL, 
    source_policy_sha256 VARCHAR(64) NOT NULL, 
    worker_source_sha256 VARCHAR(64) NOT NULL, 
    environment_sha256 VARCHAR(64) NOT NULL, 
    runtime_sha256 VARCHAR(64) NOT NULL, 
    profile_policy_sha256 VARCHAR(64) NOT NULL, 
    trusted_init_sha256 VARCHAR(64) NOT NULL, 
    adapter_source_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (execution_id), 
    CONSTRAINT uq_c23_execution_binding UNIQUE (execution_id, reservation_id, owner_user_id, envelope_sha256), 
    CONSTRAINT uq_c23_execution_key UNIQUE (site_id, owner_user_id, idempotency_key), 
    CONSTRAINT fk_c23_execution_reservation FOREIGN KEY(reservation_id, owner_user_id) REFERENCES research_experiment_reservation (id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_c23_execution_approval FOREIGN KEY(approval_id, experiment_id, proposal_revision_id, owner_user_id) REFERENCES research_experiment_approval (id, experiment_id, revision_id, user_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_c23_execution_site_key CHECK (length(site_id) BETWEEN 4 AND 128 AND substr(site_id,1,3)='v1:' AND length(idempotency_key) BETWEEN 1 AND 128), 
    CONSTRAINT ck_c23_execution_bytes CHECK (length(request_json) BETWEEN 2 AND 65536 AND length(envelope_json) BETWEEN 2 AND 1048576), 
    CONSTRAINT ck_c23_execution_material CHECK (length(job_id)=52 AND substr(job_id,1,4)='c23-' AND length(image_digest)=71 AND substr(image_digest,1,7)='sha256:'), 
    CONSTRAINT ck_c23_execution_approval_request_sha256 CHECK (length(approval_request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(approval_request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_execution_request_sha256 CHECK (length(execution_request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(execution_request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_worker_id CHECK (length(worker_id) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(worker_id, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_source_sha256 CHECK (length(source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_source_policy_sha256 CHECK (length(source_policy_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(source_policy_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_worker_source_sha256 CHECK (length(worker_source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(worker_source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_environment_sha256 CHECK (length(environment_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(environment_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_runtime_sha256 CHECK (length(runtime_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(runtime_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_profile_policy_sha256 CHECK (length(profile_policy_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(profile_policy_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_trusted_init_sha256 CHECK (length(trusted_init_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(trusted_init_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_execution_adapter_source_sha256 CHECK (length(adapter_source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(adapter_source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    UNIQUE (reservation_id), 
    UNIQUE (job_id)
)$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TABLE research_experiment_execution_event (
    id UUID NOT NULL, 
    execution_id UUID NOT NULL, 
    reservation_id UUID NOT NULL, 
    owner_user_id UUID NOT NULL, 
    envelope_sha256 VARCHAR(64) NOT NULL, 
    fence BIGINT NOT NULL, 
    kind VARCHAR(24) NOT NULL, 
    start_id UUID NOT NULL, 
    host_boot_id UUID NOT NULL, 
    journal_id UUID NOT NULL, 
    journal_epoch BIGINT NOT NULL, 
    profile_sha256 VARCHAR(64) NOT NULL, 
    preceding_journal_sha256 VARCHAR(64) NOT NULL, 
    result_sha256 VARCHAR(64), 
    terminal_sequence INTEGER, 
    terminal_head_sha256 VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_c23_event_execution FOREIGN KEY(execution_id, reservation_id, owner_user_id, envelope_sha256) REFERENCES research_experiment_execution (execution_id, reservation_id, owner_user_id, envelope_sha256) ON DELETE RESTRICT, 
    CONSTRAINT uq_c23_event_fence UNIQUE (execution_id, fence), 
    CONSTRAINT uq_c23_event_state UNIQUE (id, execution_id, fence), 
    CONSTRAINT ck_c23_event_state CHECK (fence >= 2 AND journal_epoch >= 1 AND kind IN ('start_consumed','publication_retained','closed')), 
    CONSTRAINT ck_c23_event_publication CHECK (kind <> 'publication_retained' OR result_sha256 IS NOT NULL), 
    CONSTRAINT ck_c23_event_terminal CHECK ((kind='closed' AND terminal_sequence IS NOT NULL AND terminal_sequence BETWEEN 1 AND 4096 AND terminal_head_sha256 IS NOT NULL AND result_sha256 IS NOT NULL) OR (kind<>'closed' AND terminal_sequence IS NULL AND terminal_head_sha256 IS NULL)), 
    CONSTRAINT ck_c23_event_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_event_profile_sha256 CHECK (length(profile_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(profile_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_event_preceding_journal_sha256 CHECK (length(preceding_journal_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(preceding_journal_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_event_result_sha256 CHECK (length(result_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(result_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_event_terminal_head_sha256 CHECK (length(terminal_head_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(terminal_head_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')
)$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TABLE research_experiment_execution_state (
    execution_id UUID NOT NULL, 
    fence BIGINT NOT NULL, 
    state VARCHAR(24) NOT NULL, 
    start_event_id UUID, 
    current_event_id UUID, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (execution_id), 
    CONSTRAINT fk_c23_state_event FOREIGN KEY(current_event_id, execution_id, fence) REFERENCES research_experiment_execution_event (id, execution_id, fence) ON DELETE RESTRICT, 
    CONSTRAINT ck_c23_state_fence CHECK ((state='reserved' AND fence=1 AND start_event_id IS NULL AND current_event_id IS NULL) OR (state IN ('start_consumed','publication_retained','closed') AND fence>=2 AND start_event_id IS NOT NULL AND current_event_id IS NOT NULL)), 
    FOREIGN KEY(execution_id) REFERENCES research_experiment_execution (execution_id) ON DELETE RESTRICT, 
    FOREIGN KEY(start_event_id) REFERENCES research_experiment_execution_event (id) ON DELETE RESTRICT
)$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TABLE research_experiment_termination_proof (
    id UUID NOT NULL, 
    execution_id UUID NOT NULL, 
    reservation_id UUID NOT NULL, 
    owner_user_id UUID NOT NULL, 
    envelope_sha256 VARCHAR(64) NOT NULL, 
    closed_event_id UUID NOT NULL, 
    closed_fence BIGINT NOT NULL, 
    binding_json TEXT NOT NULL, 
    host_boot_id UUID NOT NULL, 
    journal_id UUID NOT NULL, 
    journal_epoch BIGINT NOT NULL, 
    profile_sha256 VARCHAR(64) NOT NULL, 
    cgroup_path VARCHAR(63) NOT NULL, 
    cgroup_device BIGINT NOT NULL, 
    cgroup_inode BIGINT NOT NULL, 
    populated INTEGER NOT NULL, 
    delete_exit_code INTEGER NOT NULL, 
    create_intent_sequence INTEGER NOT NULL, 
    cleanup_intent_sequence INTEGER NOT NULL, 
    termination_sequence INTEGER NOT NULL, 
    terminal_sequence INTEGER NOT NULL, 
    cleanup_started_monotonic_ns BIGINT NOT NULL, 
    delete_acknowledged_monotonic_ns BIGINT NOT NULL, 
    populated_zero_monotonic_ns BIGINT NOT NULL, 
    terminal_recorded_monotonic_ns BIGINT NOT NULL, 
    issued_monotonic_ns BIGINT NOT NULL, 
    trust_scope VARCHAR(32) NOT NULL, 
    issuer_id VARCHAR(96) NOT NULL, 
    key_id VARCHAR(96) NOT NULL, 
    packet_bytes BYTEA NOT NULL, 
    create_intent_sha256 VARCHAR(64) NOT NULL, 
    cleanup_intent_sha256 VARCHAR(64) NOT NULL, 
    termination_sha256 VARCHAR(64) NOT NULL, 
    terminal_head_sha256 VARCHAR(64) NOT NULL, 
    terminal_result_sha256 VARCHAR(64) NOT NULL, 
    delete_command_sha256 VARCHAR(64) NOT NULL, 
    delete_acknowledgement_sha256 VARCHAR(64) NOT NULL, 
    raw_observation_sha256 VARCHAR(64) NOT NULL, 
    packet_sha256 VARCHAR(64) NOT NULL, 
    signature_sha256 VARCHAR(64) NOT NULL, 
    verification_policy_sha256 VARCHAR(64) NOT NULL, 
    verification_key_sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_c23_proof_execution FOREIGN KEY(execution_id, reservation_id, owner_user_id, envelope_sha256) REFERENCES research_experiment_execution (execution_id, reservation_id, owner_user_id, envelope_sha256) ON DELETE RESTRICT, 
    CONSTRAINT fk_c23_proof_closed_event FOREIGN KEY(closed_event_id, execution_id, closed_fence) REFERENCES research_experiment_execution_event (id, execution_id, fence) ON DELETE RESTRICT, 
    CONSTRAINT uq_c23_proof_release UNIQUE (id, execution_id, reservation_id, owner_user_id, envelope_sha256, closed_fence), 
    CONSTRAINT uq_c23_proof_packet UNIQUE (packet_sha256), 
    CONSTRAINT ck_c23_proof_kernel CHECK (closed_fence>=3 AND journal_epoch>=1 AND cgroup_device>=0 AND cgroup_inode>=1 AND populated=0 AND delete_exit_code=0), 
    CONSTRAINT ck_c23_proof_sequence CHECK (1<=create_intent_sequence AND create_intent_sequence<cleanup_intent_sequence AND cleanup_intent_sequence<termination_sequence AND termination_sequence<terminal_sequence AND terminal_sequence<=4096), 
    CONSTRAINT ck_c23_proof_clock CHECK (0<=cleanup_started_monotonic_ns AND cleanup_started_monotonic_ns<=delete_acknowledged_monotonic_ns AND delete_acknowledged_monotonic_ns<=populated_zero_monotonic_ns AND populated_zero_monotonic_ns<=terminal_recorded_monotonic_ns AND terminal_recorded_monotonic_ns<=issued_monotonic_ns), 
    CONSTRAINT ck_c23_proof_bytes CHECK (length(packet_bytes) BETWEEN 1 AND 16384 AND length(binding_json) BETWEEN 2 AND 8192 AND length(cgroup_path)=63), 
    CONSTRAINT ck_c23_proof_issuer CHECK (trust_scope IN ('synthetic-software-test','retained-operator') AND length(issuer_id) BETWEEN 1 AND 96 AND length(key_id) BETWEEN 1 AND 96), 
    CONSTRAINT ck_c23_proof_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_profile_sha256 CHECK (length(profile_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(profile_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_create_intent_sha256 CHECK (length(create_intent_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(create_intent_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_cleanup_intent_sha256 CHECK (length(cleanup_intent_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(cleanup_intent_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_termination_sha256 CHECK (length(termination_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(termination_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_terminal_head_sha256 CHECK (length(terminal_head_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(terminal_head_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_terminal_result_sha256 CHECK (length(terminal_result_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(terminal_result_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_delete_command_sha256 CHECK (length(delete_command_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(delete_command_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_delete_acknowledgement_sha256 CHECK (length(delete_acknowledgement_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(delete_acknowledgement_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_raw_observation_sha256 CHECK (length(raw_observation_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(raw_observation_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_packet_sha256 CHECK (length(packet_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(packet_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_signature_sha256 CHECK (length(signature_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(signature_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_verification_policy_sha256 CHECK (length(verification_policy_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(verification_policy_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    CONSTRAINT ck_c23_proof_verification_key_sha256 CHECK (length(verification_key_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(verification_key_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    UNIQUE (execution_id)
)$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TABLE research_experiment_release (
    id UUID NOT NULL, 
    execution_id UUID NOT NULL, 
    reservation_id UUID NOT NULL, 
    owner_user_id UUID NOT NULL, 
    envelope_sha256 VARCHAR(64) NOT NULL, 
    proof_id UUID NOT NULL, 
    closed_fence BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_c23_release_execution FOREIGN KEY(execution_id, reservation_id, owner_user_id, envelope_sha256) REFERENCES research_experiment_execution (execution_id, reservation_id, owner_user_id, envelope_sha256) ON DELETE RESTRICT, 
    CONSTRAINT fk_c23_release_proof FOREIGN KEY(proof_id, execution_id, reservation_id, owner_user_id, envelope_sha256, closed_fence) REFERENCES research_experiment_termination_proof (id, execution_id, reservation_id, owner_user_id, envelope_sha256, closed_fence) ON DELETE RESTRICT, 
    CONSTRAINT ck_c23_release_fence CHECK (closed_fence>=3), 
    CONSTRAINT ck_c23_release_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
    UNIQUE (execution_id), 
    UNIQUE (reservation_id), 
    UNIQUE (proof_id)
)$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_execution_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE r @S@.research_experiment_reservation; v @S@.research_experiment_revision;
        a @S@.research_experiment_approval;
BEGIN
 SELECT * INTO STRICT r FROM @S@.research_experiment_reservation WHERE id=NEW.reservation_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM @S@.research_experiment_outbox WHERE reservation_id=r.id) THEN
  RAISE EXCEPTION 'C23 cannot promote a fake reservation'; END IF;
 SELECT * INTO STRICT v FROM @S@.research_experiment_revision WHERE id=r.revision_id;
 SELECT * INTO STRICT a FROM @S@.research_experiment_approval WHERE id=r.approval_id;
 IF r.state<>'reserved' OR (NEW.owner_user_id,NEW.experiment_id,NEW.proposal_revision_id,NEW.approval_id,NEW.envelope_sha256)
    IS DISTINCT FROM (r.user_id,r.experiment_id,r.revision_id,r.approval_id,r.envelope_sha256)
    OR NEW.approval_request_sha256<>a.request_sha256 OR NEW.source_sha256<>v.source_sha256
    OR NEW.environment_sha256<>v.environment_sha256
    OR v.environment_json::jsonb->>'kind' IS DISTINCT FROM 'linux-gvisor'
    OR v.environment_json::jsonb->'test_only' IS DISTINCT FROM 'false'::jsonb
    OR NEW.image_digest IS DISTINCT FROM v.environment_json::jsonb->>'image_digest'
    OR NEW.execution_request_sha256<>encode(sha256(convert_to(NEW.request_json,'UTF8')),'hex')
    OR NEW.envelope_sha256<>encode(sha256(convert_to(NEW.envelope_json,'UTF8')),'hex')
    OR NEW.job_id<>'c23-'||substr(encode(sha256(convert_to('{"envelope":"'||NEW.envelope_sha256||'","reservation":"'||r.id::text||'","site":"'||NEW.site_id||'"}','UTF8')),'hex'),1,48)
 THEN RAISE EXCEPTION 'C23 immutable retained binding mismatch'; END IF;
 IF NEW.envelope_json::jsonb->>'version' IS DISTINCT FROM 'c22-execution-envelope-v1'
    OR NEW.envelope_json::jsonb->>'site_id' IS DISTINCT FROM NEW.site_id
    OR NEW.envelope_json::jsonb->>'experiment_id' IS DISTINCT FROM r.experiment_id::text
    OR NEW.envelope_json::jsonb->>'proposal_revision_id' IS DISTINCT FROM r.revision_id::text
    OR NEW.envelope_json::jsonb->>'reservation_id' IS DISTINCT FROM r.id::text
    OR NEW.envelope_json::jsonb->>'owner_user_id' IS DISTINCT FROM r.user_id::text
    OR NEW.envelope_json::jsonb->>'approval_id' IS DISTINCT FROM r.approval_id::text
    OR NEW.envelope_json::jsonb->'proposal' IS DISTINCT FROM v.proposal_json::jsonb
    OR NEW.envelope_json::jsonb->'environment' IS DISTINCT FROM v.environment_json::jsonb
    OR NEW.envelope_json::jsonb->'manifest' IS DISTINCT FROM v.manifest_json::jsonb
    OR NEW.envelope_json::jsonb->'binding' IS DISTINCT FROM jsonb_build_object(
       'investigation_id',v.investigation_id,'conversation_id',v.conversation_id,
       'context_revision_id',v.context_revision_id,'snapshot_id',v.snapshot_id,'context_payload_sha256',v.payload_sha256)
    OR NEW.envelope_json::jsonb->>'authority' IS DISTINCT FROM 'experimental'
    OR NEW.envelope_json::jsonb->>'scientific_approval' IS DISTINCT FROM 'not_independently_verified'
    OR NEW.envelope_json::jsonb->'hashes' IS DISTINCT FROM jsonb_build_object(
       'proposal_sha256',v.proposal_sha256,'code_sha256',v.code_sha256,
       'input_manifest_sha256',v.input_manifest_sha256,'environment_sha256',v.environment_sha256,
       'resources_sha256',v.resources_sha256)
    OR NEW.envelope_json::jsonb->'execution_performed' IS DISTINCT FROM 'false'::jsonb
 THEN RAISE EXCEPTION 'C23 retained envelope mismatch'; END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_outbox_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
BEGIN
 PERFORM id FROM @S@.research_experiment_reservation WHERE id=NEW.reservation_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM @S@.research_experiment_execution WHERE reservation_id=NEW.reservation_id) THEN
  RAISE EXCEPTION 'Fake outbox cannot bind a C23 execution'; END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_state_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE ev @S@.research_experiment_execution_event;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'C23 state cannot be deleted'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'reserved' OR NEW.fence<>1 OR NEW.start_event_id IS NOT NULL OR NEW.current_event_id IS NOT NULL THEN
   RAISE EXCEPTION 'C23 initial state must be reserved'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.execution_id<>OLD.execution_id OR OLD.state='closed' OR NEW.fence<>OLD.fence+1
    OR NOT ((OLD.state='reserved' AND NEW.state='start_consumed')
         OR (OLD.state='start_consumed' AND NEW.state IN ('publication_retained','closed'))
         OR (OLD.state='publication_retained' AND NEW.state='closed')) THEN
  RAISE EXCEPTION 'C23 state and fences are monotonic'; END IF;
 SELECT * INTO STRICT ev FROM @S@.research_experiment_execution_event WHERE id=NEW.current_event_id;
 IF (ev.execution_id,ev.fence,ev.kind) IS DISTINCT FROM (NEW.execution_id,NEW.fence,NEW.state)
    OR (OLD.start_event_id IS NOT NULL AND NEW.start_event_id IS DISTINCT FROM OLD.start_event_id)
    OR (OLD.state='reserved' AND NEW.start_event_id IS DISTINCT FROM ev.id) THEN
  RAISE EXCEPTION 'C23 state requires its exact immutable event'; END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_event_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE s @S@.research_experiment_execution_state; start_ev @S@.research_experiment_execution_event;
        current_ev @S@.research_experiment_execution_event;
BEGIN
 SELECT * INTO STRICT s FROM @S@.research_experiment_execution_state WHERE execution_id=NEW.execution_id FOR UPDATE;
 IF NEW.fence<>s.fence+1 OR s.state='closed' THEN RAISE EXCEPTION 'C23 stale event fence'; END IF;
 IF NEW.kind='start_consumed' THEN
  IF s.state<>'reserved' OR NEW.start_id<>NEW.id OR NEW.result_sha256 IS NOT NULL THEN
   RAISE EXCEPTION 'C23 start is one use'; END IF;
 ELSE
  SELECT * INTO STRICT start_ev FROM @S@.research_experiment_execution_event WHERE id=s.start_event_id;
  SELECT * INTO STRICT current_ev FROM @S@.research_experiment_execution_event WHERE id=s.current_event_id;
  IF (NEW.start_id,NEW.host_boot_id,NEW.journal_id,NEW.profile_sha256,NEW.preceding_journal_sha256)
     IS DISTINCT FROM (start_ev.start_id,start_ev.host_boot_id,start_ev.journal_id,start_ev.profile_sha256,start_ev.preceding_journal_sha256)
     OR NEW.journal_epoch<start_ev.journal_epoch OR NEW.journal_epoch<current_ev.journal_epoch
     OR NOT ((NEW.kind='publication_retained' AND s.state='start_consumed')
          OR (NEW.kind='closed' AND s.state IN ('start_consumed','publication_retained'))) THEN
   RAISE EXCEPTION 'C23 event must retain its original start identity'; END IF;
 END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_closed_binding(p_execution uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE e @S@.research_experiment_execution; s @S@.research_experiment_execution_state;
        ev @S@.research_experiment_execution_event;
BEGIN
 SELECT * INTO STRICT e FROM @S@.research_experiment_execution WHERE execution_id=p_execution;
 SELECT * INTO STRICT s FROM @S@.research_experiment_execution_state WHERE execution_id=p_execution;
 SELECT * INTO STRICT ev FROM @S@.research_experiment_execution_event WHERE id=s.current_event_id;
 IF s.state<>'closed' OR ev.kind<>'closed' OR ev.fence<>s.fence THEN
  RAISE EXCEPTION 'C23 execution is not closed'; END IF;
 RETURN (to_jsonb(e)-ARRAY['idempotency_key','request_json','envelope_json','created_at']) ||
  jsonb_build_object('closed_fence',s.fence,'host_boot_id',ev.host_boot_id,
   'journal_id',ev.journal_id,'journal_epoch',ev.journal_epoch,'profile_sha256',ev.profile_sha256);
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_proof_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE s @S@.research_experiment_execution_state; expected jsonb; packet jsonb; k jsonb; j jsonb;
        closed_ev @S@.research_experiment_execution_event;
BEGIN
 SELECT * INTO STRICT s FROM @S@.research_experiment_execution_state WHERE execution_id=NEW.execution_id FOR UPDATE;
 expected := @S@.ocean_c23_closed_binding(NEW.execution_id);
 SELECT * INTO STRICT closed_ev FROM @S@.research_experiment_execution_event WHERE id=s.current_event_id;
 packet := convert_from(NEW.packet_bytes,'UTF8')::jsonb;
 k := packet->'claims'->'kernel'; j := packet->'claims'->'journal';
 IF NEW.binding_json::jsonb IS DISTINCT FROM expected OR packet->'claims'->'binding' IS DISTINCT FROM expected
    OR NEW.closed_event_id IS DISTINCT FROM s.current_event_id OR NEW.closed_fence<>s.fence
    OR (NEW.terminal_sequence,NEW.terminal_head_sha256,NEW.terminal_result_sha256)
      IS DISTINCT FROM (closed_ev.terminal_sequence,closed_ev.terminal_head_sha256,closed_ev.result_sha256)
    OR NEW.packet_sha256<>encode(sha256(NEW.packet_bytes),'hex')
    OR packet->>'version' IS DISTINCT FROM 'c23-authenticated-termination-v1' OR packet->>'algorithm' IS DISTINCT FROM 'Ed25519'
    OR NEW.trust_scope IS DISTINCT FROM packet->>'trust_scope'
    OR NEW.issuer_id IS DISTINCT FROM packet->>'issuer_id' OR NEW.key_id IS DISTINCT FROM packet->>'key_id'
    OR NEW.signature_sha256 IS DISTINCT FROM encode(sha256(decode(packet->>'signature','hex')),'hex')
    OR (NEW.reservation_id::text,NEW.owner_user_id::text,NEW.envelope_sha256,NEW.host_boot_id::text,
        NEW.journal_id::text,NEW.journal_epoch,NEW.profile_sha256)
      IS DISTINCT FROM (expected->>'reservation_id',expected->>'owner_user_id',expected->>'envelope_sha256',
        expected->>'host_boot_id',expected->>'journal_id',(expected->>'journal_epoch')::bigint,expected->>'profile_sha256')
    OR NEW.cgroup_path IS DISTINCT FROM '/ocean-c23/'||(expected->>'job_id')
    OR k->>'delete_job_id' IS DISTINCT FROM expected->>'job_id'
    OR k->>'delete_runtime_sha256' IS DISTINCT FROM expected->>'runtime_sha256'
    OR k->>'delete_host_boot_id' IS DISTINCT FROM expected->>'host_boot_id'
 THEN RAISE EXCEPTION 'C23 proof does not match the retained closed binding'; END IF;
 IF (to_jsonb(NEW)-ARRAY['id','execution_id','reservation_id','owner_user_id','envelope_sha256','closed_event_id',
       'closed_fence','binding_json','host_boot_id','journal_id','journal_epoch','profile_sha256',
       'trust_scope','issuer_id','key_id','packet_bytes','packet_sha256','signature_sha256',
       'verification_policy_sha256','verification_key_sha256','created_at'])
    IS DISTINCT FROM ((k-ARRAY['delete_job_id','delete_runtime_sha256','delete_host_boot_id'])||j) THEN
  RAISE EXCEPTION 'C23 proof witness columns do not match authenticated packet'; END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_release_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM @S@.research_experiment_execution e
  JOIN @S@.research_experiment_execution_state s USING(execution_id)
  JOIN @S@.research_experiment_termination_proof p USING(execution_id)
  JOIN @S@.research_experiment_reservation r ON r.id=e.reservation_id
  JOIN @S@.research_experiment_revision v ON v.id=r.revision_id
  WHERE e.execution_id=NEW.execution_id AND p.id=NEW.proof_id AND s.state='closed'
   AND s.fence=NEW.closed_fence AND s.current_event_id=p.closed_event_id
   AND (NEW.reservation_id,NEW.owner_user_id,NEW.envelope_sha256,NEW.closed_fence)
     IS NOT DISTINCT FROM (p.reservation_id,p.owner_user_id,p.envelope_sha256,p.closed_fence)
   AND r.state<>'released' AND v.environment_json::jsonb->>'kind'='linux-gvisor'
   AND v.environment_json::jsonb->'test_only'='false'::jsonb
   AND NOT EXISTS(SELECT 1 FROM @S@.research_experiment_outbox o WHERE o.reservation_id=r.id)) THEN
  RAISE EXCEPTION 'C23 release requires exact closed execution and recorded proof'; END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_reserve(p jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE old @S@.research_experiment_execution; slot_number integer; identity @S@.research_experiment_execution;
BEGIN
 PERFORM id FROM @S@.research_experiment_capacity WHERE id=1 FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'C23 capacity singleton missing'; END IF;
 SELECT * INTO old FROM @S@.research_experiment_execution
  WHERE site_id=p->>'site_id' AND owner_user_id=(p->>'owner_user_id')::uuid AND idempotency_key=p->>'idempotency_key';
 IF FOUND THEN
  IF to_jsonb(old)-'created_at' IS DISTINCT FROM p THEN RAISE EXCEPTION 'C23 conflicting reserve replay'; END IF;
  RETURN old.execution_id;
 END IF;
 IF EXISTS(SELECT 1 FROM @S@.research_experiment_reservation WHERE user_id=(p->>'owner_user_id')::uuid AND state<>'released') THEN
  RAISE EXCEPTION 'C23 owner capacity unavailable'; END IF;
 SELECT n INTO slot_number FROM generate_series(0,1) AS n
  WHERE NOT EXISTS(SELECT 1 FROM @S@.research_experiment_reservation WHERE slot=n AND state<>'released') ORDER BY n LIMIT 1;
 IF slot_number IS NULL THEN RAISE EXCEPTION 'C23 global capacity unavailable'; END IF;
 INSERT INTO @S@.research_experiment_reservation(id,experiment_id,revision_id,approval_id,user_id,slot,state,envelope_sha256)
 VALUES((p->>'reservation_id')::uuid,(p->>'experiment_id')::uuid,(p->>'proposal_revision_id')::uuid,
        (p->>'approval_id')::uuid,(p->>'owner_user_id')::uuid,slot_number,'reserved',p->>'envelope_sha256');
 identity := jsonb_populate_record(NULL::@S@.research_experiment_execution,p||jsonb_build_object('created_at',clock_timestamp()));
 INSERT INTO @S@.research_experiment_execution SELECT identity.*;
 INSERT INTO @S@.research_experiment_execution_state(execution_id,fence,state) VALUES(identity.execution_id,1,'reserved');
 RETURN identity.execution_id;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_record_event(p jsonb,p_expected_fence bigint) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE old @S@.research_experiment_execution_event; ev @S@.research_experiment_execution_event;
        s @S@.research_experiment_execution_state;
BEGIN
 SELECT * INTO STRICT s FROM @S@.research_experiment_execution_state WHERE execution_id=(p->>'execution_id')::uuid FOR UPDATE;
 SELECT * INTO old FROM @S@.research_experiment_execution_event WHERE id=(p->>'id')::uuid;
 IF FOUND THEN
  IF to_jsonb(old)-'created_at' IS DISTINCT FROM p OR old.fence<>p_expected_fence+1 THEN
   RAISE EXCEPTION 'C23 conflicting event replay'; END IF;
  RETURN old.id;
 END IF;
 IF s.fence<>p_expected_fence OR (p->>'fence')::bigint<>p_expected_fence+1 THEN RAISE EXCEPTION 'C23 stale fence'; END IF;
 ev := jsonb_populate_record(NULL::@S@.research_experiment_execution_event,p||jsonb_build_object('created_at',clock_timestamp()));
 INSERT INTO @S@.research_experiment_execution_event SELECT ev.*;
 UPDATE @S@.research_experiment_execution_state
 SET fence=ev.fence,state=ev.kind,current_event_id=ev.id,
     start_event_id=CASE WHEN ev.kind='start_consumed' THEN ev.id ELSE start_event_id END, updated_at=clock_timestamp()
 WHERE execution_id=ev.execution_id;
 RETURN ev.id;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_record_proof(p jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE old @S@.research_experiment_termination_proof; proof @S@.research_experiment_termination_proof;
BEGIN
 PERFORM execution_id FROM @S@.research_experiment_execution_state WHERE execution_id=(p->>'execution_id')::uuid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'C23 execution state missing'; END IF;
 proof := jsonb_populate_record(NULL::@S@.research_experiment_termination_proof,p||jsonb_build_object('created_at',clock_timestamp()));
 SELECT * INTO old FROM @S@.research_experiment_termination_proof WHERE execution_id=proof.execution_id;
 IF FOUND THEN
  IF (to_jsonb(old)-'created_at') IS DISTINCT FROM (to_jsonb(proof)-'created_at') THEN
   RAISE EXCEPTION 'C23 conflicting proof replay'; END IF;
  RETURN old.id;
 END IF;
 INSERT INTO @S@.research_experiment_termination_proof SELECT proof.*;
 RETURN proof.id;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE FUNCTION @S@.ocean_c23_release(p_execution uuid,p_proof uuid,p_fence bigint,p_release uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
DECLARE e @S@.research_experiment_execution; s @S@.research_experiment_execution_state;
        r @S@.research_experiment_reservation; proof @S@.research_experiment_termination_proof;
        old @S@.research_experiment_release;
BEGIN
 PERFORM id FROM @S@.research_experiment_capacity WHERE id=1 FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'C23 capacity singleton missing'; END IF;
 SELECT * INTO STRICT e FROM @S@.research_experiment_execution WHERE execution_id=p_execution;
 SELECT * INTO STRICT r FROM @S@.research_experiment_reservation WHERE id=e.reservation_id FOR UPDATE;
 SELECT * INTO STRICT s FROM @S@.research_experiment_execution_state WHERE execution_id=e.execution_id FOR UPDATE;
 SELECT * INTO old FROM @S@.research_experiment_release WHERE reservation_id=r.id;
 IF FOUND THEN
  IF (old.execution_id,old.proof_id,old.closed_fence) IS DISTINCT FROM (p_execution,p_proof,p_fence) OR r.state<>'released' THEN
   RAISE EXCEPTION 'C23 conflicting release replay'; END IF;
  RETURN old.id;
 END IF;
 SELECT * INTO STRICT proof FROM @S@.research_experiment_termination_proof WHERE id=p_proof;
 IF s.state<>'closed' OR s.fence<>p_fence OR proof.closed_fence<>p_fence OR proof.execution_id<>p_execution
    OR proof.closed_event_id IS DISTINCT FROM s.current_event_id
    OR proof.binding_json::jsonb IS DISTINCT FROM @S@.ocean_c23_closed_binding(p_execution)
    OR EXISTS(SELECT 1 FROM @S@.research_experiment_outbox WHERE reservation_id=r.id) THEN
  RAISE EXCEPTION 'C23 release requires current closed fence and proof'; END IF;
 INSERT INTO @S@.research_experiment_release(id,execution_id,reservation_id,owner_user_id,envelope_sha256,proof_id,closed_fence)
 VALUES(p_release,e.execution_id,e.reservation_id,e.owner_user_id,e.envelope_sha256,p_proof,p_fence);
 UPDATE @S@.research_experiment_reservation SET state='released',updated_at=clock_timestamp() WHERE id=r.id;
 RETURN p_release;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$
CREATE OR REPLACE FUNCTION @S@.ocean_research_experiment_reservation_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Private experiments cannot be deleted'; END IF;
 IF (to_jsonb(NEW)-ARRAY['state','updated_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','updated_at']) THEN
  RAISE EXCEPTION 'Experiment identity is immutable'; END IF;
 IF OLD.state<>'released' AND NEW.state='released' THEN
  IF EXISTS(SELECT 1 FROM @S@.research_experiment_release l
    JOIN @S@.research_experiment_termination_proof p ON
     (p.id,p.execution_id,p.reservation_id,p.owner_user_id,p.envelope_sha256,p.closed_fence)=
     (l.proof_id,l.execution_id,l.reservation_id,l.owner_user_id,l.envelope_sha256,l.closed_fence)
    JOIN @S@.research_experiment_execution e ON
     (e.execution_id,e.reservation_id,e.owner_user_id,e.envelope_sha256)=
     (l.execution_id,l.reservation_id,l.owner_user_id,l.envelope_sha256)
    JOIN @S@.research_experiment_execution_state s ON s.execution_id=e.execution_id
    JOIN @S@.research_experiment_revision v ON v.id=OLD.revision_id
    WHERE l.reservation_id=OLD.id AND e.owner_user_id=OLD.user_id AND e.experiment_id=OLD.experiment_id
     AND e.proposal_revision_id=OLD.revision_id AND e.approval_id=OLD.approval_id
     AND e.envelope_sha256=OLD.envelope_sha256 AND s.state='closed' AND s.fence=p.closed_fence
     AND s.current_event_id=p.closed_event_id
     AND v.environment_json::jsonb->>'kind'='linux-gvisor' AND v.environment_json::jsonb->'test_only'='false'::jsonb
     AND NOT EXISTS(SELECT 1 FROM @S@.research_experiment_outbox o WHERE o.reservation_id=OLD.id)) THEN RETURN NEW; END IF;
  RAISE EXCEPTION 'C23 release requires immutable correlated proof ledger';
 END IF;
 IF OLD.state IN ('accepted','released') OR NEW.state='released' OR (OLD.state='uncertain' AND NEW.state='reserved') THEN
  RAISE EXCEPTION 'C22 reservation cannot be released or rolled back'; END IF;
 RETURN NEW;
END $$
$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_execution_insert_guard() FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_outbox_insert_guard() FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_state_guard() FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_event_insert_guard() FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_closed_binding(uuid) FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_proof_insert_guard() FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_release_insert_guard() FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_reserve(jsonb) FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_record_event(jsonb,bigint) FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_record_proof(jsonb) FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON FUNCTION @S@.ocean_c23_release(uuid,uuid,bigint,uuid) FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON TABLE @S@.research_experiment_execution FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_execution_immutable BEFORE UPDATE OR DELETE ON @S@.research_experiment_execution FOR EACH ROW EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_execution_no_truncate BEFORE TRUNCATE ON @S@.research_experiment_execution FOR EACH STATEMENT EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON TABLE @S@.research_experiment_execution_event FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_execution_event_immutable BEFORE UPDATE OR DELETE ON @S@.research_experiment_execution_event FOR EACH ROW EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_execution_event_no_truncate BEFORE TRUNCATE ON @S@.research_experiment_execution_event FOR EACH STATEMENT EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON TABLE @S@.research_experiment_execution_state FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_execution_state_no_truncate BEFORE TRUNCATE ON @S@.research_experiment_execution_state FOR EACH STATEMENT EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON TABLE @S@.research_experiment_termination_proof FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_termination_proof_immutable BEFORE UPDATE OR DELETE ON @S@.research_experiment_termination_proof FOR EACH ROW EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_termination_proof_no_truncate BEFORE TRUNCATE ON @S@.research_experiment_termination_proof FOR EACH STATEMENT EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$REVOKE ALL ON TABLE @S@.research_experiment_release FROM PUBLIC$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_release_immutable BEFORE UPDATE OR DELETE ON @S@.research_experiment_release FOR EACH ROW EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER research_experiment_release_no_truncate BEFORE TRUNCATE ON @S@.research_experiment_release FOR EACH STATEMENT EXECUTE FUNCTION @S@.ocean_context_revision_immutable()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER c23_execution_insert_guard BEFORE INSERT ON @S@.research_experiment_execution FOR EACH ROW EXECUTE FUNCTION @S@.ocean_c23_execution_insert_guard()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER c23_outbox_insert_guard BEFORE INSERT ON @S@.research_experiment_outbox FOR EACH ROW EXECUTE FUNCTION @S@.ocean_c23_outbox_insert_guard()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER c23_state_guard BEFORE INSERT OR UPDATE OR DELETE ON @S@.research_experiment_execution_state FOR EACH ROW EXECUTE FUNCTION @S@.ocean_c23_state_guard()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER c23_event_insert_guard BEFORE INSERT ON @S@.research_experiment_execution_event FOR EACH ROW EXECUTE FUNCTION @S@.ocean_c23_event_insert_guard()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER c23_proof_insert_guard BEFORE INSERT ON @S@.research_experiment_termination_proof FOR EACH ROW EXECUTE FUNCTION @S@.ocean_c23_proof_insert_guard()$c23_ddl$, '@S@', quote_ident(target_schema));
EXECUTE replace($c23_ddl$CREATE TRIGGER c23_release_insert_guard BEFORE INSERT ON @S@.research_experiment_release FOR EACH ROW EXECUTE FUNCTION @S@.ocean_c23_release_insert_guard()$c23_ddl$, '@S@', quote_ident(target_schema));
END $c23_offline$;

UPDATE alembic_version SET version_num='20261027_0021' WHERE alembic_version.version_num = '20261020_0020';

COMMIT;

