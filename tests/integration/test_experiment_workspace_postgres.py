"""C25 C22 read compatibility after a real native-PG C23 restricted release.

The signed proof is an explicitly synthetic software fixture. This test does
not replace immutable Linux containment receipts or accept physical execution.
"""
import os

import pytest

from tests.integration import test_experiment_execution_postgres as execution

pytestmark = pytest.mark.skipif(os.environ.get('RUN_C23_POSTGRES_INTEGRATION') != '1',
    reason='requires explicitly identified owned C23 PostgreSQL; no service is started')
disposable_database = execution.disposable_database
isolated = execution.isolated
role_database = execution.role_database
actual = execution.actual


def test_public_c22_read_after_native_c23_proof_bound_release(actual):
    store, binding = execution.reserved(actual)
    closed = execution.closed(store, binding, publish=True)
    proof = store.record_verified_termination(execution_id=binding.execution_id,
        packet_bytes=execution.packet(actual, closed))
    release = store.release_terminated(execution_id=binding.execution_id,
        proof_id=proof, expected_fence=closed.closed_fence)
    assert release
    fixture = actual.fixture
    public = fixture.service.invoke('get', {'experiment_id': binding.experiment_id}, fixture.user)['experiment']
    assert public['dispatch']['status'] == 'unavailable'
    assert public['dispatch']['reservation_id'] is None and public['dispatch']['eligible'] is False
    assert public['execution_performed'] is False
    assert public['proposal_revision_id'] == binding.proposal_revision_id
    assert store.load_closed_binding(binding.execution_id) == closed
