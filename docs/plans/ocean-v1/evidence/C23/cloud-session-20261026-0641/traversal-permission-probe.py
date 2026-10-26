"""Trusted host permission probe only; never an analysis/runtime fallback."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

assert sys.platform == 'linux' and os.getuid() == os.geteuid() == 0
assert os.uname().machine == 'x86_64'
root = Path('/var/lib/ocean-c23-gofer-permission-probe-01')
root.mkdir(mode=0o700)
secret = root / 'private.txt'
secret.write_bytes(b'synthetic permission canary only\n')
secret.chmod(0o400)
journal = root / 'private-journal'
journal.mkdir(mode=0o700)
acl = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in (
    (1, 7, 0xffffffff), (2, 1, 100000), (4, 0, 0xffffffff),
    (16, 1, 0xffffffff), (32, 0, 0xffffffff)))
try:
    os.setxattr(root, 'system.posix_acl_access', acl)
    assert os.getxattr(root, 'system.posix_acl_access') == acl
    child = r'''
import json, os
from pathlib import Path
root = Path('/var/lib/ocean-c23-gofer-permission-probe-01')
assert os.getuid() == os.getgid() == 100000 and not os.getgroups()
assert root.stat().st_mode & 0o777 == 0o710
assert (root/'private.txt').stat().st_uid == 0
denials = {}
for name, operation in (
    ('directory_listing', lambda: os.listdir(root)),
    ('private_file_read', lambda: (root/'private.txt').read_bytes()),
    ('private_journal_search', lambda: os.listdir(root/'private-journal')),
    ('create_child', lambda: (root/'forbidden').write_bytes(b'x'))):
    try:
        operation()
    except PermissionError:
        denials[name] = True
    else:
        raise AssertionError(name)
print(json.dumps({'uid': os.getuid(), 'gid': os.getgid(),
    'known_name_stat_allowed': True, 'denials': denials}, sort_keys=True))
'''
    completed = subprocess.run(['/usr/bin/setpriv', '--reuid=100000', '--regid=100000',
        '--clear-groups', '/usr/bin/python3', '-I', '-S', '-B', '-c', child],
        capture_output=True, timeout=10, check=True)
    print(completed.stdout.decode('ascii'), end='')
finally:
    os.removexattr(root, 'system.posix_acl_access')
    assert root.stat().st_mode & 0o777 == 0o700
    secret.unlink()
    journal.rmdir()
    root.rmdir()
