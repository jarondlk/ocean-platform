"""Stored guest-program AST and registry wiring only; no generated execution."""
import ast
import ctypes
import subprocess

import pytest

from sandbox.experiment.gcp import run_namespace_inheritance as wrapper


def test_registry_extends_only_one_fixed_case_without_changing_base():
    original = wrapper._BASE_CASES()
    result = wrapper.cases()
    assert set(result) == {*original, wrapper.CASE_NAME}
    assert all(result[name] == value for name, value in original.items())
    case = result[wrapper.CASE_NAME]
    assert case.name == wrapper.CASE_NAME and case.body == wrapper.PROGRAM
    assert case.expectation == 'completed' and case.outputs == (('summary.json', 'table'),)
    assert wrapper.CASE_NAME not in wrapper._BASE_CASES()
    assert wrapper.base.cases is wrapper._BASE_CASES


@pytest.mark.parametrize('failed', [False, True])
def test_main_temporarily_registers_case_and_restores_every_base_guard(monkeypatch, failed):
    original = wrapper.base.cases
    guards = {name: getattr(wrapper.base, name) for name in (
        'require_worker', 'run_case', 'verify_materials', 'verify_operator_fixture',
        '_admission', '_cleanup', 'evaluate_case')}
    argv = ['list-cases']

    def delegated(received):
        assert received is argv and wrapper.CASE_NAME in wrapper.base.cases()
        assert all(getattr(wrapper.base, name) is value for name, value in guards.items())
        if failed:
            raise ValueError('retained failure')
        return 7

    monkeypatch.setattr(wrapper.base, 'main', delegated)
    if failed:
        with pytest.raises(ValueError, match='retained failure'):
            wrapper.main(argv)
    else:
        assert wrapper.main(argv) == 7
    assert wrapper.base.cases is original


def test_conflicting_extra_case_refuses_instead_of_overriding(monkeypatch):
    monkeypatch.setattr(wrapper, '_BASE_CASES', lambda: {wrapper.CASE_NAME: object()})
    with pytest.raises(wrapper.base.OperatorError, match='already_registered'):
        wrapper.cases()


@pytest.mark.parametrize('source', [wrapper.PROGRAM, wrapper.EXEC_PROGRAM])
def test_each_probe_checks_actual_raw_errno_and_zero_identity_capabilities(source):
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == 'libc.syscall']
    assert len(calls) == 2
    assert [ast.literal_eval(call.args[0].args[0]) for call in calls] == [272, 435]
    assert ast.unparse(calls[0].args[1]) == 'ctypes.c_ulong(0)'
    assert [ast.unparse(value) for value in calls[1].args[1:]] == ['ctypes.c_void_p(0)', 'ctypes.c_size_t(0)']
    assert 'unshare_errno == errno.EPERM' in source
    assert 'clone3_errno == errno.ENOSYS' in source
    assert 'os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []' in source
    assert "{'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}" in source
    assert "os.uname().machine == 'x86_64'" in source


def test_guest_program_probes_parent_fork_exec_and_thread_without_local_execution():
    tree = ast.parse(wrapper.PROGRAM)
    assert "probe('main')" in wrapper.PROGRAM and "probe('after_fork')" in wrapper.PROGRAM
    assert "probe('after_exec')" in wrapper.EXEC_PROGRAM and "probe('thread')" in wrapper.PROGRAM
    fork = next(node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'os.fork')
    thread = next(node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'threading.Thread')
    assert fork < thread
    run = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'subprocess.run')
    argv = ast.literal_eval(run.args[0])
    assert argv == ['/usr/local/bin/python3', '-I', '-S', '-B', '-c', wrapper.EXEC_PROGRAM]
    assert any(value.arg == 'timeout' and ast.literal_eval(value.value) == 5 for value in run.keywords)
    assert 'ordinary_fork' in wrapper.PROGRAM and 'ordinary_exec_subprocess' in wrapper.PROGRAM
    assert "['ordinary_thread',True]" in wrapper.PROGRAM


def test_read_only_cli_listing_never_executes_stored_guest_code(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError('generated program or runtime executed during registry preparation')
    monkeypatch.setattr(ctypes, 'CDLL', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    wrapper.main(['list-cases'])
    assert wrapper.CASE_NAME in capsys.readouterr().out


def test_run_keeps_base_linux_guard_before_inputs_or_runtime(monkeypatch):
    def refused():
        raise wrapper.base.OperatorError('dedicated_linux_root_worker_required')
    def forbidden(*args, **kwargs):
        raise AssertionError('input/effect before dedicated worker guard')
    monkeypatch.setattr(wrapper.base, 'require_worker', refused)
    monkeypatch.setattr(wrapper.base, '_private_directory', forbidden)
    monkeypatch.setattr(wrapper.base, '_read', forbidden)
    args = ['run', '--case', wrapper.CASE_NAME, '--attempt-dir', '/unread',
            '--blueprint', '/unread', '--blueprint-sha256', 'a' * 64,
            '--host-controls', '/unread', '--host-controls-sha256', 'a' * 64,
            '--network-isolation', '/unread', '--network-isolation-sha256', 'a' * 64,
            '--normalization-receipt', '/unread', '--normalization-sha256', 'a' * 64]
    with pytest.raises(wrapper.base.OperatorError, match='dedicated_linux_root_worker_required'):
        wrapper.main(args)
    assert wrapper.base.cases is wrapper._BASE_CASES
