"""Q6 read-only binding refuses wrong identity, open leases and corrupt steps."""
import pytest

from scripts import beta_b1_q6_diagnostic as q6
from tests.test_beta_b1_diagnostic import Connection, Cursor


class Q6Cursor(Cursor):
    def __init__(self, *, head=None, **kwargs):
        kwargs.setdefault('model', ('committed', 'completed', 'STOP', 5313, 283, 5600, 4096, True, 1))
        super().__init__(head=head or ('queued', 'other', 34500, 2, 1, 0, True,
            'completed', True, 'sent', True, 2, 1, 0), **kwargs)

    def fetchall(self):
        if len(self.queries) == 2:
            return [self.head]
        if len(self.queries) == 4:
            return []  # Queued synthesis has no generation yet.
        return [self.model]


def test_exact_q6_binding_and_empty_queued_answer_emit_only_metadata():
    cursor = Q6Cursor()
    result = q6.collect(Connection(cursor))
    assert result['answer_job_id'] == q6.JOB_ID and result['delivery_id'] == q6.DELIVERY_ID
    assert result['head']['exact_frozen_context_and_task_binding_verified']
    assert result['generations']['research_answer'] == [] and not result['model_queue_or_sql_write']
    assert cursor.queries[1][1] == q6.PARAMS
    for query, _ in cursor.queries:
        assert query.startswith('SELECT') and 'request_json' not in query
        assert "->'content'" not in query and "->>'content'" not in query


@pytest.mark.parametrize('index,value', [(0, 'running'), (6, False), (7, 'running'),
    (8, False), (9, 'pending'), (10, False), (12, 2), (4, 0), (2, True)])
def test_active_unbound_or_invalid_shared_state_is_rejected(index, value):
    cursor = Q6Cursor()
    head = list(cursor.head)
    head[index] = value
    cursor.head = tuple(head)
    with pytest.raises(ValueError):
        q6.collect(Connection(cursor))


def test_wrong_readonly_identity_or_corrupt_model_is_rejected():
    for cursor in [Q6Cursor(identity=('other', 'ocean_v1_beta', 'on', 'repeatable read')),
                   Q6Cursor(model=('prepared', None, None, None, None, None, None, False, 1))]:
        with pytest.raises(ValueError):
            q6.collect(Connection(cursor))


def test_a_terminal_answer_requires_all_counted_generation_attempts():
    cursor = Q6Cursor(head=('completed', 'other', 65000, 2, 2, 0, True, 'completed', True, 'sent', True, 2, 1, 0))
    with pytest.raises(ValueError):
        q6.collect(Connection(cursor))  # Missing answer step cannot become a pass.
