# Operator-owned synthetic acceptance: containment; nonce=bfdfd013cf214049a5bbd8370f9f6c85
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/containment-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/containment-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os, socket, importlib.util, subprocess
interface_names = {name for _,name in socket.if_nameindex()}
assert interface_names == {'lo'}
ipv4_routes = open('/proc/net/route',encoding='ascii').read().splitlines()[1:]
assert all(line.split()[0] == 'lo' for line in ipv4_routes if line.strip())
try:
    ipv6_routes = open('/proc/net/ipv6_route',encoding='ascii').read().splitlines()
except FileNotFoundError:
    ipv6_routes = None
if ipv6_routes is not None:
    assert all(line.split()[-1] == 'lo' for line in ipv6_routes if line.strip())
for address,port in [('1.1.1.1',443),('169.254.169.254',80)]:
    connection = socket.socket()
    connection.settimeout(1)
    try:
        connection.connect((address,port))
    except OSError:
        pass
    else:
        raise AssertionError('network unexpectedly reachable: ' + address)
    finally:
        connection.close()
try:
    open(HOST_CANARY,'rb').read(1)
except OSError:
    pass
else:
    raise AssertionError('host canary readable')
connection = socket.socket(socket.AF_UNIX)
try:
    connection.connect(HOST_SOCKET)
except OSError:
    pass
else:
    raise AssertionError('host socket reachable')
finally:
    connection.close()
for path in ['/inputs/analysis.py','/inputs/new-file','/usr/local/c23-write',
             '/tmp/c23-write','/dev/shm/c23-write','/run/c23-write','/var/tmp/c23-write']:
    try:
        with open(path,'ab') as stream:
            stream.write(b'no')
    except OSError:
        pass
    else:
        raise AssertionError('forbidden write succeeded: ' + path)
assert importlib.util.find_spec('pip') is None
assert importlib.util.find_spec('ensurepip') is None
assert subprocess.run(['/usr/local/bin/python3','-m','pip','--version'],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3).returncode != 0
try:
    os.readlink('/proc/1/fd/1')
except OSError:
    pass
else:
    raise AssertionError('trusted frame FD readable')
mounts = open('/proc/self/mountinfo',encoding='utf-8').read()
for path in ['/tmp','/dev/shm']:
    assert any(line.split()[4] == path and 'ro' in line.split()[5].split(',')
               for line in mounts.splitlines())
write_summary([['external_network_denied',True],['metadata_denied',True],
               ['host_file_socket_denied',True],['forbidden_writes_denied',True],
               ['pip_absent',True],['trusted_frame_fd_denied',True],
               ['guest_interfaces',','.join(sorted(interface_names))],
               ['ipv4_route_rows',len(ipv4_routes)],
               ['ipv6_route_readback','present' if ipv6_routes is not None else 'not_exposed']])
