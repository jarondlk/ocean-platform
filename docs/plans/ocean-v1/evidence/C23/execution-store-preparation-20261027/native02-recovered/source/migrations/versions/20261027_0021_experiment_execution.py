"""C23 opt-in retained execution identity and proof-correlated capacity release.

No roles, credentials, serving routes or verifier keys are created. Functions
start with PUBLIC execution revoked; explicit isolated bootstrap is required.
PostgreSQL records the restricted recorder's authenticated assertions. It does
not verify Ed25519 or establish physical termination itself.
"""
from alembic import op

revision = "20261027_0021"
down_revision = "20261020_0020"
branch_labels = None
depends_on = None

TABLE_DDL = ("CREATE TABLE research_experiment_execution (\n\texecution_id UUID NOT NULL, \n\treservation_id UUID NOT NULL, \n\towner_user_id UUID NOT NULL, \n\texperiment_id UUID NOT NULL, \n\tproposal_revision_id UUID NOT NULL, \n\tapproval_id UUID NOT NULL, \n\tsite_id VARCHAR(128) NOT NULL, \n\tidempotency_key VARCHAR(128) NOT NULL, \n\trequest_json TEXT NOT NULL, \n\tenvelope_json TEXT NOT NULL, \n\tjob_id VARCHAR(52) NOT NULL, \n\timage_digest VARCHAR(71) NOT NULL, \n\tapproval_request_sha256 VARCHAR(64) NOT NULL, \n\texecution_request_sha256 VARCHAR(64) NOT NULL, \n\tenvelope_sha256 VARCHAR(64) NOT NULL, \n\tworker_id VARCHAR(64) NOT NULL, \n\tsource_sha256 VARCHAR(64) NOT NULL, \n\tsource_policy_sha256 VARCHAR(64) NOT NULL, \n\tworker_source_sha256 VARCHAR(64) NOT NULL, \n\tenvironment_sha256 VARCHAR(64) NOT NULL, \n\truntime_sha256 VARCHAR(64) NOT NULL, \n\tprofile_policy_sha256 VARCHAR(64) NOT NULL, \n\ttrusted_init_sha256 VARCHAR(64) NOT NULL, \n\tadapter_source_sha256 VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (execution_id), \n\tCONSTRAINT uq_c23_execution_binding UNIQUE (execution_id, reservation_id, owner_user_id, envelope_sha256), \n\tCONSTRAINT uq_c23_execution_key UNIQUE (site_id, owner_user_id, idempotency_key), \n\tCONSTRAINT fk_c23_execution_reservation FOREIGN KEY(reservation_id, owner_user_id) REFERENCES research_experiment_reservation (id, user_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_c23_execution_approval FOREIGN KEY(approval_id, experiment_id, proposal_revision_id, owner_user_id) REFERENCES research_experiment_approval (id, experiment_id, revision_id, user_id) ON DELETE RESTRICT, \n\tCONSTRAINT ck_c23_execution_site_key CHECK (length(site_id) BETWEEN 4 AND 128 AND substr(site_id,1,3)='v1:' AND length(idempotency_key) BETWEEN 1 AND 128), \n\tCONSTRAINT ck_c23_execution_bytes CHECK (length(request_json) BETWEEN 2 AND 65536 AND length(envelope_json) BETWEEN 2 AND 1048576), \n\tCONSTRAINT ck_c23_execution_material CHECK (length(job_id)=52 AND substr(job_id,1,4)='c23-' AND length(image_digest)=71 AND substr(image_digest,1,7)='sha256:'), \n\tCONSTRAINT ck_c23_execution_approval_request_sha256 CHECK (length(approval_request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(approval_request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_execution_request_sha256 CHECK (length(execution_request_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(execution_request_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_worker_id CHECK (length(worker_id) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(worker_id, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_source_sha256 CHECK (length(source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_source_policy_sha256 CHECK (length(source_policy_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(source_policy_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_worker_source_sha256 CHECK (length(worker_source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(worker_source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_environment_sha256 CHECK (length(environment_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(environment_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_runtime_sha256 CHECK (length(runtime_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(runtime_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_profile_policy_sha256 CHECK (length(profile_policy_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(profile_policy_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_trusted_init_sha256 CHECK (length(trusted_init_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(trusted_init_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_execution_adapter_source_sha256 CHECK (length(adapter_source_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(adapter_source_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tUNIQUE (reservation_id), \n\tUNIQUE (job_id)\n)", "CREATE TABLE research_experiment_execution_event (\n\tid UUID NOT NULL, \n\texecution_id UUID NOT NULL, \n\treservation_id UUID NOT NULL, \n\towner_user_id UUID NOT NULL, \n\tenvelope_sha256 VARCHAR(64) NOT NULL, \n\tfence BIGINT NOT NULL, \n\tkind VARCHAR(24) NOT NULL, \n\tstart_id UUID NOT NULL, \n\thost_boot_id UUID NOT NULL, \n\tjournal_id UUID NOT NULL, \n\tjournal_epoch BIGINT NOT NULL, \n\tprofile_sha256 VARCHAR(64) NOT NULL, \n\tpreceding_journal_sha256 VARCHAR(64) NOT NULL, \n\tresult_sha256 VARCHAR(64), \n\tterminal_sequence INTEGER, \n\tterminal_head_sha256 VARCHAR(64), \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_c23_event_execution FOREIGN KEY(execution_id, reservation_id, owner_user_id, envelope_sha256) REFERENCES research_experiment_execution (execution_id, reservation_id, owner_user_id, envelope_sha256) ON DELETE RESTRICT, \n\tCONSTRAINT uq_c23_event_fence UNIQUE (execution_id, fence), \n\tCONSTRAINT uq_c23_event_state UNIQUE (id, execution_id, fence), \n\tCONSTRAINT ck_c23_event_state CHECK (fence >= 2 AND journal_epoch >= 1 AND kind IN ('start_consumed','publication_retained','closed')), \n\tCONSTRAINT ck_c23_event_publication CHECK (kind <> 'publication_retained' OR result_sha256 IS NOT NULL), \n\tCONSTRAINT ck_c23_event_terminal CHECK ((kind='closed' AND terminal_sequence IS NOT NULL AND terminal_sequence BETWEEN 1 AND 4096 AND terminal_head_sha256 IS NOT NULL AND result_sha256 IS NOT NULL) OR (kind<>'closed' AND terminal_sequence IS NULL AND terminal_head_sha256 IS NULL)), \n\tCONSTRAINT ck_c23_event_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_event_profile_sha256 CHECK (length(profile_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(profile_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_event_preceding_journal_sha256 CHECK (length(preceding_journal_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(preceding_journal_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_event_result_sha256 CHECK (length(result_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(result_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_event_terminal_head_sha256 CHECK (length(terminal_head_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(terminal_head_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = '')\n)", "CREATE TABLE research_experiment_execution_state (\n\texecution_id UUID NOT NULL, \n\tfence BIGINT NOT NULL, \n\tstate VARCHAR(24) NOT NULL, \n\tstart_event_id UUID, \n\tcurrent_event_id UUID, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (execution_id), \n\tCONSTRAINT fk_c23_state_event FOREIGN KEY(current_event_id, execution_id, fence) REFERENCES research_experiment_execution_event (id, execution_id, fence) ON DELETE RESTRICT, \n\tCONSTRAINT ck_c23_state_fence CHECK ((state='reserved' AND fence=1 AND start_event_id IS NULL AND current_event_id IS NULL) OR (state IN ('start_consumed','publication_retained','closed') AND fence>=2 AND start_event_id IS NOT NULL AND current_event_id IS NOT NULL)), \n\tFOREIGN KEY(execution_id) REFERENCES research_experiment_execution (execution_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(start_event_id) REFERENCES research_experiment_execution_event (id) ON DELETE RESTRICT\n)", "CREATE TABLE research_experiment_termination_proof (\n\tid UUID NOT NULL, \n\texecution_id UUID NOT NULL, \n\treservation_id UUID NOT NULL, \n\towner_user_id UUID NOT NULL, \n\tenvelope_sha256 VARCHAR(64) NOT NULL, \n\tclosed_event_id UUID NOT NULL, \n\tclosed_fence BIGINT NOT NULL, \n\tbinding_json TEXT NOT NULL, \n\thost_boot_id UUID NOT NULL, \n\tjournal_id UUID NOT NULL, \n\tjournal_epoch BIGINT NOT NULL, \n\tprofile_sha256 VARCHAR(64) NOT NULL, \n\tcgroup_path VARCHAR(63) NOT NULL, \n\tcgroup_device BIGINT NOT NULL, \n\tcgroup_inode BIGINT NOT NULL, \n\tpopulated INTEGER NOT NULL, \n\tdelete_exit_code INTEGER NOT NULL, \n\tcreate_intent_sequence INTEGER NOT NULL, \n\tcleanup_intent_sequence INTEGER NOT NULL, \n\ttermination_sequence INTEGER NOT NULL, \n\tterminal_sequence INTEGER NOT NULL, \n\tcleanup_started_monotonic_ns BIGINT NOT NULL, \n\tdelete_acknowledged_monotonic_ns BIGINT NOT NULL, \n\tpopulated_zero_monotonic_ns BIGINT NOT NULL, \n\tterminal_recorded_monotonic_ns BIGINT NOT NULL, \n\tissued_monotonic_ns BIGINT NOT NULL, \n\ttrust_scope VARCHAR(32) NOT NULL, \n\tissuer_id VARCHAR(96) NOT NULL, \n\tkey_id VARCHAR(96) NOT NULL, \n\tpacket_bytes BYTEA NOT NULL, \n\tcreate_intent_sha256 VARCHAR(64) NOT NULL, \n\tcleanup_intent_sha256 VARCHAR(64) NOT NULL, \n\ttermination_sha256 VARCHAR(64) NOT NULL, \n\tterminal_head_sha256 VARCHAR(64) NOT NULL, \n\tterminal_result_sha256 VARCHAR(64) NOT NULL, \n\tdelete_command_sha256 VARCHAR(64) NOT NULL, \n\tdelete_acknowledgement_sha256 VARCHAR(64) NOT NULL, \n\traw_observation_sha256 VARCHAR(64) NOT NULL, \n\tpacket_sha256 VARCHAR(64) NOT NULL, \n\tsignature_sha256 VARCHAR(64) NOT NULL, \n\tverification_policy_sha256 VARCHAR(64) NOT NULL, \n\tverification_key_sha256 VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_c23_proof_execution FOREIGN KEY(execution_id, reservation_id, owner_user_id, envelope_sha256) REFERENCES research_experiment_execution (execution_id, reservation_id, owner_user_id, envelope_sha256) ON DELETE RESTRICT, \n\tCONSTRAINT fk_c23_proof_closed_event FOREIGN KEY(closed_event_id, execution_id, closed_fence) REFERENCES research_experiment_execution_event (id, execution_id, fence) ON DELETE RESTRICT, \n\tCONSTRAINT uq_c23_proof_release UNIQUE (id, execution_id, reservation_id, owner_user_id, envelope_sha256, closed_fence), \n\tCONSTRAINT uq_c23_proof_packet UNIQUE (packet_sha256), \n\tCONSTRAINT ck_c23_proof_kernel CHECK (closed_fence>=3 AND journal_epoch>=1 AND cgroup_device>=0 AND cgroup_inode>=1 AND populated=0 AND delete_exit_code=0), \n\tCONSTRAINT ck_c23_proof_sequence CHECK (1<=create_intent_sequence AND create_intent_sequence<cleanup_intent_sequence AND cleanup_intent_sequence<termination_sequence AND termination_sequence<terminal_sequence AND terminal_sequence<=4096), \n\tCONSTRAINT ck_c23_proof_clock CHECK (0<=cleanup_started_monotonic_ns AND cleanup_started_monotonic_ns<=delete_acknowledged_monotonic_ns AND delete_acknowledged_monotonic_ns<=populated_zero_monotonic_ns AND populated_zero_monotonic_ns<=terminal_recorded_monotonic_ns AND terminal_recorded_monotonic_ns<=issued_monotonic_ns), \n\tCONSTRAINT ck_c23_proof_bytes CHECK (length(packet_bytes) BETWEEN 1 AND 16384 AND length(binding_json) BETWEEN 2 AND 8192 AND length(cgroup_path)=63), \n\tCONSTRAINT ck_c23_proof_issuer CHECK (trust_scope IN ('synthetic-software-test','retained-operator') AND length(issuer_id) BETWEEN 1 AND 96 AND length(key_id) BETWEEN 1 AND 96), \n\tCONSTRAINT ck_c23_proof_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_profile_sha256 CHECK (length(profile_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(profile_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_create_intent_sha256 CHECK (length(create_intent_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(create_intent_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_cleanup_intent_sha256 CHECK (length(cleanup_intent_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(cleanup_intent_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_termination_sha256 CHECK (length(termination_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(termination_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_terminal_head_sha256 CHECK (length(terminal_head_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(terminal_head_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_terminal_result_sha256 CHECK (length(terminal_result_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(terminal_result_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_delete_command_sha256 CHECK (length(delete_command_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(delete_command_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_delete_acknowledgement_sha256 CHECK (length(delete_acknowledgement_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(delete_acknowledgement_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_raw_observation_sha256 CHECK (length(raw_observation_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(raw_observation_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_packet_sha256 CHECK (length(packet_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(packet_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_signature_sha256 CHECK (length(signature_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(signature_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_verification_policy_sha256 CHECK (length(verification_policy_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(verification_policy_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tCONSTRAINT ck_c23_proof_verification_key_sha256 CHECK (length(verification_key_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(verification_key_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tUNIQUE (execution_id)\n)", "CREATE TABLE research_experiment_release (\n\tid UUID NOT NULL, \n\texecution_id UUID NOT NULL, \n\treservation_id UUID NOT NULL, \n\towner_user_id UUID NOT NULL, \n\tenvelope_sha256 VARCHAR(64) NOT NULL, \n\tproof_id UUID NOT NULL, \n\tclosed_fence BIGINT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_c23_release_execution FOREIGN KEY(execution_id, reservation_id, owner_user_id, envelope_sha256) REFERENCES research_experiment_execution (execution_id, reservation_id, owner_user_id, envelope_sha256) ON DELETE RESTRICT, \n\tCONSTRAINT fk_c23_release_proof FOREIGN KEY(proof_id, execution_id, reservation_id, owner_user_id, envelope_sha256, closed_fence) REFERENCES research_experiment_termination_proof (id, execution_id, reservation_id, owner_user_id, envelope_sha256, closed_fence) ON DELETE RESTRICT, \n\tCONSTRAINT ck_c23_release_fence CHECK (closed_fence>=3), \n\tCONSTRAINT ck_c23_release_envelope_sha256 CHECK (length(envelope_sha256) = 64 AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(envelope_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''), \n\tUNIQUE (execution_id), \n\tUNIQUE (reservation_id), \n\tUNIQUE (proof_id)\n)")

TABLES = (
    'research_experiment_execution', 'research_experiment_execution_event',
    'research_experiment_execution_state', 'research_experiment_termination_proof',
    'research_experiment_release',
)

OLD_RESERVATION_GUARD = "CREATE OR REPLACE FUNCTION ocean_research_experiment_reservation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Private experiments cannot be deleted'; END IF; IF (to_jsonb(NEW)-ARRAY['state','updated_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','updated_at']) THEN RAISE EXCEPTION 'Experiment identity is immutable'; END IF; IF OLD.state IN ('accepted','released') OR NEW.state='released' OR (OLD.state='uncertain' AND NEW.state='reserved') THEN RAISE EXCEPTION 'C22 reservation cannot be released or rolled back'; END IF; RETURN NEW; END $$"

FUNCTION_SQL = (
r"""
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
""",
r"""
CREATE FUNCTION @S@.ocean_c23_outbox_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,@S@,pg_temp AS $$
BEGIN
 PERFORM id FROM @S@.research_experiment_reservation WHERE id=NEW.reservation_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM @S@.research_experiment_execution WHERE reservation_id=NEW.reservation_id) THEN
  RAISE EXCEPTION 'Fake outbox cannot bind a C23 execution'; END IF;
 RETURN NEW;
END $$
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
r"""
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
""",
)

FUNCTION_SIGNATURES = (
 'ocean_c23_execution_insert_guard()', 'ocean_c23_outbox_insert_guard()',
 'ocean_c23_state_guard()', 'ocean_c23_event_insert_guard()',
 'ocean_c23_closed_binding(uuid)', 'ocean_c23_proof_insert_guard()',
 'ocean_c23_release_insert_guard()', 'ocean_c23_reserve(jsonb)',
 'ocean_c23_record_event(jsonb,bigint)', 'ocean_c23_record_proof(jsonb)',
 'ocean_c23_release(uuid,uuid,bigint,uuid)',
)


def _schema():
    # Existing migrations use the explicitly configured connection search path.
    # Capture its current schema once and qualify every new function reference.
    return op.get_bind().dialect.identifier_preparer.quote_schema(
        op.get_bind().exec_driver_sql('SELECT current_schema()').scalar_one())


def upgrade():
    schema = _schema()
    for ddl in TABLE_DDL:
        op.execute(ddl)
    for statement in FUNCTION_SQL:
        op.execute(statement.replace('@S@', schema))
    for signature in FUNCTION_SIGNATURES:
        op.execute(f'REVOKE ALL ON FUNCTION {schema}.{signature} FROM PUBLIC')
    for table in TABLES:
        op.execute(f'REVOKE ALL ON TABLE {schema}.{table} FROM PUBLIC')
        if table != 'research_experiment_execution_state':
            op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION {schema}.ocean_context_revision_immutable()')
        op.execute(f'CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {schema}.{table} FOR EACH STATEMENT EXECUTE FUNCTION {schema}.ocean_context_revision_immutable()')
    for table, name, timing in (
        ('research_experiment_execution','execution_insert_guard','INSERT'),
        ('research_experiment_outbox','outbox_insert_guard','INSERT'),
        ('research_experiment_execution_state','state_guard','INSERT OR UPDATE OR DELETE'),
        ('research_experiment_execution_event','event_insert_guard','INSERT'),
        ('research_experiment_termination_proof','proof_insert_guard','INSERT'),
        ('research_experiment_release','release_insert_guard','INSERT'),
    ):
        op.execute(f'CREATE TRIGGER c23_{name} BEFORE {timing} ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION {schema}.ocean_c23_{name}()')


def downgrade():
    schema = _schema()
    for table in TABLES:
        # ACCESS EXCLUSIVE prevents a concurrent insertion after the emptiness
        # check. Refuse before dropping anything, within Alembic's transaction.
        op.execute(f'LOCK TABLE {schema}.{table} IN ACCESS EXCLUSIVE MODE')
    for table in TABLES:
        if op.get_bind().exec_driver_sql(f'SELECT EXISTS(SELECT 1 FROM {schema}.{table})').scalar_one():
            raise RuntimeError('Cannot downgrade populated C23 execution history')
    op.execute(OLD_RESERVATION_GUARD.replace('FUNCTION ocean_', f'FUNCTION {schema}.ocean_', 1))
    op.execute(f'DROP TRIGGER c23_outbox_insert_guard ON {schema}.research_experiment_outbox')
    # State references events, proof and release; drop in dependency order.
    for table in ('research_experiment_release','research_experiment_termination_proof',
                  'research_experiment_execution_state','research_experiment_execution_event','research_experiment_execution'):
        op.drop_table(table)
    for signature in reversed(FUNCTION_SIGNATURES):
        op.execute(f'DROP FUNCTION {schema}.{signature}')
