# Operator-owned synthetic acceptance: namespace-inheritance; nonce=a4226f56fe4448fe904535dcf0046d1d
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/namespace-inheritance-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/namespace-inheritance-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
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
process = subprocess.run(['/usr/local/bin/python3','-I','-S','-B','-c',"import ctypes, errno, json, os\ndef probe(scope):\n    assert os.uname().machine == 'x86_64'\n    assert os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []\n    capabilities = {}\n    for line in open('/proc/self/status',encoding='ascii'):\n        name, _, value = line.partition(':')\n        if name in {'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}:\n            capabilities[name] = int(value.strip(),16)\n    assert len(capabilities) == 5 and all(value == 0 for value in capabilities.values())\n    libc = ctypes.CDLL(None,use_errno=True)\n    libc.syscall.restype = ctypes.c_long\n    ctypes.set_errno(0)\n    result = libc.syscall(ctypes.c_long(272),ctypes.c_ulong(0))\n    unshare_errno = ctypes.get_errno()\n    assert result == -1 and unshare_errno == errno.EPERM, (scope,'unshare',result,unshare_errno)\n    ctypes.set_errno(0)\n    result = libc.syscall(ctypes.c_long(435),ctypes.c_void_p(0),ctypes.c_size_t(0))\n    clone3_errno = ctypes.get_errno()\n    assert result == -1 and clone3_errno == errno.ENOSYS, (scope,'clone3',result,clone3_errno)\n    return {'scope':scope,'uid':os.getuid(),'gid':os.getgid(),\n            'unshare_errno':unshare_errno,'clone3_errno':clone3_errno,'capabilities_zero':True}\nprint(json.dumps(probe('after_exec'),sort_keys=True,separators=(',',':')))\n"],
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
    assert set(value) == {'scope','uid','gid','unshare_errno','clone3_errno','capabilities_zero'}
    assert value['uid'] == value['gid'] == 65532 and value['capabilities_zero'] is True
    assert value['unshare_errno'] == 1 and value['clone3_errno'] == 38
    rows.extend([[value['scope'] + '_unshare_errno',value['unshare_errno']],
                 [value['scope'] + '_clone3_errno',value['clone3_errno']],
                 [value['scope'] + '_uid',value['uid']],
                 [value['scope'] + '_capabilities_zero',value['capabilities_zero']]])
write_summary(rows + [['ordinary_fork',True],['ordinary_exec_subprocess',True],
                      ['ordinary_thread',True]])
