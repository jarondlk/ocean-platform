# Operator-owned synthetic acceptance: namespaces; nonce=01ce980c93164a8da186530076cb2978
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/namespaces-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/namespaces-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import ctypes, errno, os, signal, subprocess, threading
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
namespace_bits = [0x00020000,0x02000000,0x04000000,0x08000000,
                  0x10000000,0x20000000,0x40000000]
observations = []
def denied(name,number,*arguments,expected=errno.EPERM,clone_child=False):
    ctypes.set_errno(0)
    result = libc.syscall(ctypes.c_long(number),*arguments)
    actual_errno = ctypes.get_errno()
    if clone_child and result == 0:
        # An unexpected clone child must not continue any probe.
        os._exit(0)
    if clone_child and result > 0:
        os.waitpid(result,0)
    assert result == -1 and actual_errno == expected, (name,result,actual_errno,expected)
    observations.append([name,actual_errno])
# AMD64 Linux syscall numbers; no host syscall is issued by setup.
# unshare(0) and setns(-1) errno distinguish early deny from ordinary
# success/FD validation; neither invalid clone3 input proves userns alone.
for bit in [0,*namespace_bits,0x80]:
    denied('unshare_' + hex(bit),272,ctypes.c_ulong(bit))
denied('setns_invalid_fd',308,ctypes.c_long(-1),ctypes.c_ulong(0))
for bit in namespace_bits:
    denied('clone_' + hex(bit),56,ctypes.c_ulong(bit|signal.SIGCHLD),
           ctypes.c_void_p(0),ctypes.c_void_p(0),ctypes.c_void_p(0),
           ctypes.c_ulong(0),clone_child=True)
clone_args = (ctypes.c_uint64*11)()
clone_args[0] = 0x10000000
clone_args[4] = signal.SIGCHLD
denied('clone3_newuser',435,ctypes.byref(clone_args),
       ctypes.c_size_t(ctypes.sizeof(clone_args)),expected=errno.ENOSYS,clone_child=True)
denied('clone3_invalid_pointer',435,ctypes.c_void_p(1),
       ctypes.c_size_t(ctypes.sizeof(clone_args)),expected=errno.ENOSYS,clone_child=True)
denied('clone3_zero_size',435,ctypes.c_void_p(0),ctypes.c_size_t(0),
       expected=errno.ENOSYS,clone_child=True)
os.mkdir('/scratch/ns-probe')
target = ctypes.c_char_p(b'/scratch/ns-probe')
denied('mount_tmpfs',165,ctypes.c_char_p(b'tmpfs'),target,
       ctypes.c_char_p(b'tmpfs'),ctypes.c_ulong(0),
       ctypes.c_char_p(b'size=4096,nr_inodes=4'))
denied('mount_bind',165,ctypes.c_char_p(b'/inputs'),target,
       ctypes.c_void_p(0),ctypes.c_ulong(4096),ctypes.c_void_p(0))
denied('mount_remount',165,ctypes.c_void_p(0),ctypes.c_char_p(b'/scratch'),
       ctypes.c_void_p(0),ctypes.c_ulong(32|1),ctypes.c_void_p(0))
denied('umount2',166,ctypes.c_char_p(b'/scratch'),ctypes.c_int(0))
os.rmdir('/scratch/ns-probe')
# Compatibility controls are deliberately after all risky clone calls
# so those calls run before this program creates any Python thread.
pid = os.fork()
if pid == 0:
    os._exit(0)
waited,status = os.waitpid(pid,0)
assert waited == pid and os.waitstatus_to_exitcode(status) == 0
process = subprocess.run(['/usr/local/bin/python3','-I','-S','-B','-c',
    'print("ordinary-child-ok")'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
assert process.returncode == 0 and process.stdout == b'ordinary-child-ok\n'
threaded = []
worker = threading.Thread(target=lambda: threaded.append('ordinary-thread-ok'))
worker.start()
worker.join(timeout=3)
assert not worker.is_alive() and threaded == ['ordinary-thread-ok']
write_summary(observations + [['uid',os.getuid()],['capabilities_zero',True],
    ['ordinary_fork',True],['ordinary_subprocess',True],['ordinary_thread',True]])
