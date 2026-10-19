"""Add private durable v1 research execution; no legacy lifecycle changes."""
from alembic import op
import sqlalchemy as sa
revision = '20261019_0018'
down_revision = '20261018_0017'
branch_labels = None
depends_on = None

def upgrade():
    op.create_unique_constraint('uq_research_conversation_identity', 'research_conversation', ['investigation_id', 'id'])
    op.create_unique_constraint('uq_research_context_revision_binding', 'research_context_revision', ['investigation_id', 'id', 'snapshot_id', 'payload_sha256'])
    op.execute("""
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
)
    """)
    op.execute('CREATE INDEX ix_research_run_conversation ON research_run (user_id, investigation_id, conversation_id, created_at, id)')
    op.execute("""
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
)
    """)
    op.execute("""
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
)
    """)
    op.execute("""
CREATE TABLE research_run_payload (
	run_id UUID NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	payload_json TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (run_id, sha256), 
	CONSTRAINT ck_research_run_retained_hash CHECK (length(sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), 
	FOREIGN KEY(run_id) REFERENCES research_run (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
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
)
    """)
    op.execute("""
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
)
    """)
    op.execute("""
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
)
    """)
    op.execute("""
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
)
    """)
    _guards()

def _guards():
    op.execute('CREATE TRIGGER research_run_input_history_immutable BEFORE UPDATE OR DELETE ON research_run_input_history FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_event_immutable BEFORE UPDATE OR DELETE ON research_run_event FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_payload_immutable BEFORE UPDATE OR DELETE ON research_run_payload FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_attempt_immutable BEFORE UPDATE OR DELETE ON research_run_attempt FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_manifest_immutable BEFORE UPDATE OR DELETE ON research_run_manifest FOR EACH ROW EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_no_truncate BEFORE TRUNCATE ON research_run FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_input_history_no_truncate BEFORE TRUNCATE ON research_run_input_history FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_event_no_truncate BEFORE TRUNCATE ON research_run_event FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_payload_no_truncate BEFORE TRUNCATE ON research_run_payload FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_step_no_truncate BEFORE TRUNCATE ON research_run_step FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_attempt_no_truncate BEFORE TRUNCATE ON research_run_attempt FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_manifest_no_truncate BEFORE TRUNCATE ON research_run_manifest FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute('CREATE TRIGGER research_run_outbox_no_truncate BEFORE TRUNCATE ON research_run_outbox FOR EACH STATEMENT EXECUTE FUNCTION ocean_context_revision_immutable()')
    op.execute("""
CREATE FUNCTION ocean_research_run_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Research execution history is retained'; END IF;
IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.investigation_id IS DISTINCT FROM OLD.investigation_id OR NEW.conversation_id IS DISTINCT FROM OLD.conversation_id OR NEW.revision_id IS DISTINCT FROM OLD.revision_id OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256 OR NEW.context_json IS DISTINCT FROM OLD.context_json OR NEW.original_question IS DISTINCT FROM OLD.original_question OR NEW.continuation_of IS DISTINCT FROM OLD.continuation_of OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.version < OLD.version OR NEW.input_version < OLD.input_version OR NEW.event_cursor < OLD.event_cursor OR NEW.active_elapsed_ms < OLD.active_elapsed_ms OR NEW.tool_actions < OLD.tool_actions OR NEW.model_calls < OLD.model_calls OR NEW.malformed_repairs < OLD.malformed_repairs OR NEW.lease_epoch < OLD.lease_epoch OR (OLD.status IN ('completed','partial','cancelled','failed') AND NEW IS DISTINCT FROM OLD) THEN RAISE EXCEPTION 'Research execution identity and committed outcomes are immutable'; END IF;
RETURN NEW; END $$
    """)
    op.execute('CREATE TRIGGER research_run_guard BEFORE UPDATE OR DELETE ON research_run FOR EACH ROW EXECUTE FUNCTION ocean_research_run_guard()')
    op.execute("""
CREATE FUNCTION ocean_research_run_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Research execution history is retained'; END IF;
IF NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.step_id IS DISTINCT FROM OLD.step_id OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.request_sha256 IS DISTINCT FROM OLD.request_sha256 OR NEW.request_json IS DISTINCT FROM OLD.request_json OR NEW.created_at IS DISTINCT FROM OLD.created_at OR OLD.state = 'committed' THEN RAISE EXCEPTION 'Research execution identity and committed outcomes are immutable'; END IF;
RETURN NEW; END $$
    """)
    op.execute('CREATE TRIGGER research_run_step_guard BEFORE UPDATE OR DELETE ON research_run_step FOR EACH ROW EXECUTE FUNCTION ocean_research_run_step_guard()')
    op.execute("""
CREATE FUNCTION ocean_research_run_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Research execution history is retained'; END IF;
IF NEW.id IS DISTINCT FROM OLD.id OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.input_version IS DISTINCT FROM OLD.input_version OR NEW.delivery_id IS DISTINCT FROM OLD.delivery_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'Research execution identity and committed outcomes are immutable'; END IF;
RETURN NEW; END $$
    """)
    op.execute('CREATE TRIGGER research_run_outbox_guard BEFORE UPDATE OR DELETE ON research_run_outbox FOR EACH ROW EXECUTE FUNCTION ocean_research_run_outbox_guard()')

def downgrade():
    op.execute('LOCK TABLE research_run, research_run_input_history, research_run_event, research_run_payload, research_run_step, research_run_attempt, research_run_manifest, research_run_outbox IN ACCESS EXCLUSIVE MODE')
    for table in ('research_run', 'research_run_input_history', 'research_run_event', 'research_run_payload', 'research_run_step', 'research_run_attempt', 'research_run_manifest', 'research_run_outbox'):
        if op.get_bind().execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')).scalar():
            raise RuntimeError('Retain durable research history; populated C20 storage cannot be downgraded')
    op.drop_table('research_run_outbox')
    op.drop_table('research_run_manifest')
    op.drop_table('research_run_attempt')
    op.drop_table('research_run_step')
    op.drop_table('research_run_payload')
    op.drop_table('research_run_event')
    op.drop_table('research_run_input_history')
    op.drop_table('research_run')
    op.execute('DROP FUNCTION ocean_research_run_guard()')
    op.execute('DROP FUNCTION ocean_research_run_step_guard()')
    op.execute('DROP FUNCTION ocean_research_run_outbox_guard()')
    op.drop_constraint('uq_research_context_revision_binding', 'research_context_revision', type_='unique')
    op.drop_constraint('uq_research_conversation_identity', 'research_conversation', type_='unique')
