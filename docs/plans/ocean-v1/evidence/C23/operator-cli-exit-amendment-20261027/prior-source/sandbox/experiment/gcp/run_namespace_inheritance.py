"""One additive operator-only guest case; retain every base harness guard.

The stored program is parsed locally, never executed by this module. The base
Linux/gVisor adapter is the sole execution path. This is synthetic containment
evidence, not retained C22 authority or scientific approval.
"""
from __future__ import annotations

import ast
import textwrap

from sandbox.experiment.gcp import run_operator_acceptance as base

VERSION = 'c23-operator-namespace-inheritance-v1'
CASE_NAME = 'namespace-inheritance'
_BASE_CASES = base.cases

_PROBE = textwrap.dedent('''
    import ctypes, errno, json, os
    def probe(scope):
        assert os.uname().machine == 'x86_64'
        assert os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []
        capabilities = {}
        for line in open('/proc/self/status',encoding='ascii'):
            name, _, value = line.partition(':')
            if name in {'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}:
                capabilities[name] = int(value.strip(),16)
        assert len(capabilities) == 5 and all(value == 0 for value in capabilities.values())
        libc = ctypes.CDLL(None,use_errno=True)
        libc.syscall.restype = ctypes.c_long
        ctypes.set_errno(0)
        result = libc.syscall(ctypes.c_long(272),ctypes.c_ulong(0))
        unshare_errno = ctypes.get_errno()
        assert result == -1 and unshare_errno == errno.EPERM, (scope,'unshare',result,unshare_errno)
        ctypes.set_errno(0)
        result = libc.syscall(ctypes.c_long(435),ctypes.c_void_p(0),ctypes.c_size_t(0))
        clone3_errno = ctypes.get_errno()
        assert result == -1 and clone3_errno == errno.ENOSYS, (scope,'clone3',result,clone3_errno)
        return {'scope':scope,'uid':os.getuid(),'gid':os.getgid(),
                'unshare_errno':unshare_errno,'clone3_errno':clone3_errno,'capabilities_zero':True}
''').lstrip()

EXEC_PROGRAM = _PROBE + "print(json.dumps(probe('after_exec'),sort_keys=True,separators=(',',':')))\n"

PROGRAM = _PROBE + textwrap.dedent(f'''
    import subprocess, threading
    observations = [probe('main')]
    reader, writer = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(reader)
        try:
            value = json.dumps(probe('after_fork'),sort_keys=True,separators=(',',':')).encode('ascii')
            assert len(value) <= 1024 and os.write(writer,value) == len(value)
            os.close(writer)
            os._exit(0)
        except BaseException:
            os._exit(1)
    os.close(writer)
    value = os.read(reader,4097)
    os.close(reader)
    waited, status = os.waitpid(child,0)
    assert waited == child and os.waitstatus_to_exitcode(status) == 0 and len(value) <= 1024
    observations.append(json.loads(value))
    process = subprocess.run(['/usr/local/bin/python3','-I','-S','-B','-c',{EXEC_PROGRAM!r}],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
    assert process.returncode == 0 and len(process.stdout) <= 1024 and process.stderr == b''
    observations.append(json.loads(process.stdout))
    # No fork follows thread creation. Each raw child probe runs before this.
    threaded = []
    thread = threading.Thread(target=lambda: threaded.append(probe('thread')))
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive() and len(threaded) == 1
    observations.extend(threaded)
    assert [value['scope'] for value in observations] == ['main','after_fork','after_exec','thread']
    rows = []
    for value in observations:
        assert set(value) == {{'scope','uid','gid','unshare_errno','clone3_errno','capabilities_zero'}}
        assert value['uid'] == value['gid'] == 65532 and value['capabilities_zero'] is True
        assert value['unshare_errno'] == 1 and value['clone3_errno'] == 38
        rows.extend([[value['scope'] + '_unshare_errno',value['unshare_errno']],
                     [value['scope'] + '_clone3_errno',value['clone3_errno']],
                     [value['scope'] + '_uid',value['uid']],
                     [value['scope'] + '_capabilities_zero',value['capabilities_zero']]])
    write_summary(rows + [['ordinary_fork',True],['ordinary_exec_subprocess',True],
                          ['ordinary_thread',True]])
''').lstrip()


def cases():
    """Extend a fresh registry with exactly one fixed, AST-validated case."""
    result = dict(_BASE_CASES())
    if CASE_NAME in result:
        raise base.OperatorError('inheritance_case_already_registered')
    ast.parse(PROGRAM)
    ast.parse(EXEC_PROGRAM)
    result[CASE_NAME] = base.OperatorCase(CASE_NAME, PROGRAM)
    return result


def main(argv=None):
    """Delegate parsing/admission/staging/runtime/cleanup to the base harness."""
    original = base.cases
    base.cases = cases
    try:
        return base.main(argv)
    finally:
        base.cases = original


if __name__ == '__main__':
    main()
