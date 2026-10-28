"""Unsupported host SQLite skips real-journal fixtures without weakening admission."""
import sqlite3
from types import SimpleNamespace

import pytest

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.journal import DurableExecutionJournal
from tests import retained_admission_support
from tests import test_experiment_sandbox_physical_termination as physical_tests
from tests import test_experiment_sandbox_retained_context as context_tests
from tests.test_experiment_sandbox_journal import BOOT, HOST, driver


@pytest.mark.parametrize('entry', ['physical', 'context', 'native_hooks'])
def test_old_sqlite_skips_before_real_journal_or_native_fixture_effects(tmp_path, monkeypatch, entry):
    # Simulate the Ubuntu Python host capability at the fixture gate only.
    # No production query/result or accepted SQLite minimum is replaced.
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 45, 1))
    untouched = tmp_path / 'must-not-be-created'
    with pytest.raises(pytest.skip.Exception, match='SQLite'):
        if entry == 'native_hooks':
            retained_admission_support.configured_native(None, untouched, monkeypatch)
        else:
            fixture = physical_tests.physical if entry == 'physical' else context_tests.case
            next(fixture.__wrapped__(None, untouched, monkeypatch))
    assert not untouched.exists()


def test_fixture_gates_leave_production_queried_old_sqlite_rejection_intact(tmp_path):
    root = (tmp_path / 'control').resolve()
    root.mkdir(mode=0o700)
    with pytest.raises(SandboxError, match='sandbox_journal_sqlite_version'):
        DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST,
                                sqlite_module=driver('3.45.1'))
    assert list(root.iterdir()) == []


def test_old_sqlite_native_case_skips_before_requesting_postgres_fixture(tmp_path, monkeypatch):
    from tests.integration import test_retained_admission_postgres as native_tests
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 45, 1))
    requested = []

    def forbidden(name):
        requested.append(name)
        pytest.fail('Unsupported SQLite must skip before requesting the PostgreSQL fixture')

    untouched = tmp_path / 'must-not-be-created'
    with pytest.raises(pytest.skip.Exception, match='SQLite'):
        next(native_tests.case.__wrapped__(untouched, monkeypatch,
                                          SimpleNamespace(getfixturevalue=forbidden)))
    assert not requested
    assert not untouched.exists()
