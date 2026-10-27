# Operator-owned synthetic acceptance: descendants; nonce=06d0c8cbf0d94da8bfec2a8fa8073159
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/descendants-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/descendants-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,time
reader,writer = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(reader)
    os.setsid()
    grandchild = os.fork()
    if grandchild:
        os._exit(0)
    os.write(writer,b'D')
    os.close(writer)
    while True:
        time.sleep(0.05)
os.close(writer)
assert os.read(reader,1) == b'D'
os.close(reader)
write_summary([['double_fork_descendant_started',True],['first_child_pid',pid]])
