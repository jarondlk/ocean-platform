"""AST/registry guards only; scientific imports are never executed on host."""
import ast
import ctypes
from pathlib import Path
import runpy
import subprocess

import pytest

from sandbox.experiment.gcp import run_scientific_import_diagnostic as diagnostic


def test_exactly_one_fixed_case_without_material_or_resource_overrides():
    before = diagnostic._BASE_CASES()
    after = diagnostic.cases()
    assert set(after) == {*before, diagnostic.CASE_NAME}
    case = after[diagnostic.CASE_NAME]
    assert case.body == diagnostic.PROGRAM and case.expectation == 'completed'
    assert case.resources is case.seeds is None
    assert case.outputs == (('summary.json', 'table'),)
    assert all(after[name] == value for name, value in before.items())


@pytest.mark.parametrize('failed', [False, True])
def test_registry_restored_and_all_base_guards_remain_identical(monkeypatch, failed):
    original = diagnostic.base.cases
    guards = {name: getattr(diagnostic.base, name) for name in (
        'require_worker','run_case','verify_materials','verify_operator_fixture',
        '_admission','_cleanup','evaluate_case')}
    def main(argv):
        assert argv == ['list-cases'] and diagnostic.CASE_NAME in diagnostic.base.cases()
        assert all(getattr(diagnostic.base,name) is value for name,value in guards.items())
        if failed:
            raise ValueError('failure retained')
        return 8
    monkeypatch.setattr(diagnostic.base,'main',main)
    if failed:
        with pytest.raises(ValueError,match='failure retained'):
            diagnostic.main(['list-cases'])
    else:
        assert diagnostic.main(['list-cases']) == 8
    assert diagnostic.base.cases is original


@pytest.mark.parametrize('exit_code', [0, 7])
def test_trusted_cli_entrypoint_propagates_base_exit_without_guest_execution(monkeypatch, exit_code):
    original = diagnostic.base.cases
    calls = []
    def delegated(argv):
        calls.append(argv)
        assert diagnostic.CASE_NAME in diagnostic.base.cases()
        return exit_code
    def forbidden(*_args, **_kwargs):
        raise AssertionError('scientific program or runtime executed by entrypoint test')
    monkeypatch.setattr(diagnostic.base, 'main', delegated)
    monkeypatch.setattr(ctypes, 'CDLL', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    with pytest.raises(SystemExit) as outcome:
        runpy.run_path(str(Path(diagnostic.__file__).resolve()), run_name='__main__')
    assert outcome.value.code == exit_code and calls == [None]
    assert diagnostic.base.cases is original


def test_conflicting_case_is_not_overwritten(monkeypatch):
    monkeypatch.setattr(diagnostic,'_BASE_CASES',lambda:{diagnostic.CASE_NAME:object()})
    with pytest.raises(diagnostic.base.OperatorError,match='already_registered'):
        diagnostic.cases()


def test_stored_program_directly_observes_datetime_then_numpy_and_retries():
    tree = ast.parse(diagnostic.PROGRAM)
    loop = next(node for node in tree.body if isinstance(node,ast.For)
                and ast.unparse(node.target) == '(label, name)')
    assert ast.literal_eval(loop.iter) == [
        ('_datetime_first','_datetime'),('datetime_first','datetime'),
        ('_pydatetime_first','_pydatetime'),('numpy','numpy'),
        ('_datetime_after_numpy','_datetime'),('datetime_after_numpy','datetime')]
    assert any(isinstance(node,ast.Call) and ast.unparse(node.func) == '__import__' for node in ast.walk(loop))
    assert "['diagnostic_only',True]" in diagnostic.PROGRAM
    assert "['numerical_acceptance',False]" in diagnostic.PROGRAM
    assert "['original_failed_numerical_case_reclassified',False]" in diagnostic.PROGRAM


def test_scalar_bounded_trace_and_guest_fd_scope_are_explicit():
    source = diagnostic.PROGRAM
    assert 'traceback.format_exc(limit=8)[-8192:]' in source
    assert 'for index in range(3)' in source and '[:2048]' in source
    assert "getattr(error,'errno',None)" in source and "getattr(error,'path',None)" in source
    assert 'resource.getrlimit(resource.RLIMIT_NOFILE)' in source
    assert "os.listdir('/proc/self/fd')" in source
    assert 'host Sentry/gofer FD quotas are separate' in source
    assert 'len(rows) <= 256' in source and '<= 192*1024' in source
    assert "os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []" in source
    assert "{'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}" in source


def test_listing_never_executes_scientific_program(monkeypatch,capsys):
    def forbidden(*args,**kwargs):
        raise AssertionError('scientific program executed during preparation')
    monkeypatch.setattr(subprocess,'run',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    diagnostic.main(['list-cases'])
    assert diagnostic.CASE_NAME in capsys.readouterr().out


def test_run_preserves_worker_guard_before_files_or_effects(monkeypatch):
    def denied():
        raise diagnostic.base.OperatorError('dedicated_linux_root_worker_required')
    def forbidden(*args,**kwargs):
        raise AssertionError('filesystem effect before worker guard')
    monkeypatch.setattr(diagnostic.base,'require_worker',denied)
    monkeypatch.setattr(diagnostic.base,'_private_directory',forbidden)
    monkeypatch.setattr(diagnostic.base,'_read',forbidden)
    args=['run','--case',diagnostic.CASE_NAME,'--attempt-dir','/unread',
          '--blueprint','/unread','--blueprint-sha256','a'*64,
          '--host-controls','/unread','--host-controls-sha256','a'*64,
          '--network-isolation','/unread','--network-isolation-sha256','a'*64,
          '--normalization-receipt','/unread','--normalization-sha256','a'*64]
    with pytest.raises(diagnostic.base.OperatorError,match='dedicated_linux_root_worker_required'):
        diagnostic.main(args)
    assert diagnostic.base.cases is diagnostic._BASE_CASES
