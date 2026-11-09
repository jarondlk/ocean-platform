"""Fixed Research grant proposal; rendering performs no SQL or cloud operation.

No role creation, credentials, account writes, memberships, deletion, wildcard
table grants or caller SQL are supported. Apply only as a separately reviewed
operator transaction after checking the actual database and existing ACLs.
"""
READ_TABLES = (
    "app_user", "alembic_version", "research_investigation", "research_conversation",
    "research_context_revision", "research_context_operation",
    "research_run", "research_run_input_history", "research_run_event", "research_run_payload",
    "research_run_step", "research_run_attempt", "research_run_manifest", "research_run_outbox",
    "research_evidence_blob", "research_evidence_receipt", "research_evidence_protection",
    "research_evidence_dependency", "research_evidence_context_dependency", "research_answer_job",
    "research_answer_event", "research_answer_payload", "research_answer_step", "research_answer_attempt",
    "research_answer_outbox", "research_answer_input_history", "research_answer",
)
API_INSERT = (
    "research_run", "research_run_input_history", "research_run_event", "research_run_outbox",
    "research_answer_job", "research_answer_event", "research_answer_input_history", "research_answer_outbox",
)
CONTROLLER_INSERT = (
    "research_run_event", "research_run_payload", "research_run_step", "research_run_attempt",
    "research_run_manifest", "research_answer_event", "research_answer_payload", "research_answer_step",
    "research_answer_attempt", "research_answer",
)
EVIDENCE_INSERT = (
    "research_evidence_blob", "research_evidence_receipt", "research_evidence_protection",
    "research_evidence_dependency", "research_evidence_context_dependency",
)
COMMON_UPDATE = {
    "research_run": ("effective_question", "status", "version", "input_version", "clarification_id",
        "event_cursor", "active_elapsed_ms", "tool_actions", "model_calls", "malformed_repairs",
        "lease_epoch", "lease_until", "active_started_at", "cancellation_requested", "checkpoint_json",
        "manifest_json", "controller_result_json", "reason_code", "updated_at"),
    "research_run_outbox": ("state", "attempts", "sent_at"),
    "research_answer_job": ("status", "version", "event_cursor", "cancellation_requested", "active_elapsed_ms",
        "tool_actions", "model_calls", "malformed_repairs", "active_started_at", "lease_epoch", "lease_until",
        "manifest_json", "pack_sha256", "reason_code", "updated_at"),
    "research_answer_outbox": ("state", "attempts", "sent_at"),
    "research_evidence_receipt": ("state",), "research_evidence_protection": ("state",),
    "research_evidence_context_dependency": ("state",),
}
CONTROLLER_UPDATE = {
    "research_run_step": ("outcome_sha256", "state"),
    "research_answer_step": ("outcome_sha256", "state"),
    # PostgreSQL row locking needs UPDATE on at least one column. C21 locks the
    # investigation while publishing evidence; no context/head editing is added.
    "research_investigation": ("updated_at",),
}
ROLES = {"ocean_v1_serving": API_INSERT, "ocean_v1_research_controller": CONTROLLER_INSERT}

OWNER_LOCK_SQL = """CREATE FUNCTION public.ocean_v1_beta_research_owner_lock(owner_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $body$
BEGIN
  PERFORM 1 FROM public.app_user WHERE id = owner_id FOR NO KEY UPDATE;
END
$body$;
REVOKE ALL ON FUNCTION public.ocean_v1_beta_research_owner_lock(uuid) FROM PUBLIC;"""


def statements():
    """Closed, reviewable statements; preserves existing C17/auth/limiter grants."""
    output = [OWNER_LOCK_SQL]
    for role, inserts in ROLES.items():
        output.append(f'GRANT CONNECT ON DATABASE ocean_v1_beta TO "{role}";')
        output.append(f'GRANT USAGE ON SCHEMA public TO "{role}";')
        for table in READ_TABLES:
            output.append(f'GRANT SELECT ON TABLE public."{table}" TO "{role}";')
        for table in (*inserts, *EVIDENCE_INSERT):
            output.append(f'GRANT INSERT ON TABLE public."{table}" TO "{role}";')
        updates = {**COMMON_UPDATE, **(CONTROLLER_UPDATE if role == "ocean_v1_research_controller" else {})}
        for table, columns in updates.items():
            names = ", ".join('"' + c + '"' for c in columns)
            output.append(f'GRANT UPDATE ({names}) ON TABLE public."{table}" TO "{role}";')
        output.append(f'GRANT EXECUTE ON FUNCTION public.ocean_v1_beta_research_owner_lock(uuid) TO "{role}";')
    return tuple(output)
