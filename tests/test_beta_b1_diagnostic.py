"""Privacy and fail-closed cases for the fixed read-only Q5 diagnostic."""

import pytest

from scripts import beta_b1_diagnostic as diagnostic


class Cursor:
    def __init__(self, *, identity=None, head=None, model=None):
        self.identity = identity or ('ocean_v1_research_controller', 'ocean_v1_beta', 'on', 'repeatable read')
        self.head = head or ('unavailable', 'generation_incomplete', 55801, 2, 2, 0, True, 'completed', True)
        self.model = model or ('committed', 'failed', 'ClientError', None, None, None, 4096, True, 1)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return self.identity

    def fetchall(self):
        if len(self.queries) == 2:
            return [self.head]
        return [self.model]


class Connection:
    def __init__(self, cursor):
        self.c = cursor

    def cursor(self):
        return self.c


def test_fixed_projection_preserves_missing_usage_and_excludes_private_content():
    cursor = Cursor()
    result = diagnostic.collect(Connection(cursor))
    assert result['head']['reason_code'] == 'generation_incomplete'
    assert result['generations']['research_answer'][0]['usage']['input_tokens'] is None
    assert result['raw_content_selected_or_emitted'] is False
    for sql, _ in cursor.queries:
        assert sql.startswith('SELECT')
        assert 'request_json' not in sql and "->'content'" not in sql and "->>'content'" not in sql
    assert cursor.queries[1][1] == (diagnostic.RUN_ID, diagnostic.JOB_ID)
    assert 'LIMIT 15' in cursor.queries[2][0]


@pytest.mark.parametrize('changes', [
    {'identity': ('other', 'ocean_v1_beta', 'on', 'repeatable read')},
    {'identity': ('ocean_v1_research_controller', 'ocean_v1_beta', 'off', 'repeatable read')},
    {'head': ('running', 'other', 10, 0, 1, 0, False, 'completed', True)},
    {'head': ('unavailable', 'other', 10, 0, 15, 0, True, 'completed', True)},
    {'model': ('prepared', None, None, None, None, None, None, None, 1)},
    {'model': ('committed', 'failed', 'ClientError', None, None, None, 4096, False, 1)},
    {'model': ('committed', 'failed', 'ClientError', -1, None, None, 4096, True, 1)},
    {'model': ('committed', 'failed', 'ClientError', True, None, None, 4096, True, 1)},
])
def test_rejects_wrong_identity_active_heads_corruption_or_invalid_counts(changes):
    with pytest.raises(ValueError):
        diagnostic.collect(Connection(Cursor(**changes)))
