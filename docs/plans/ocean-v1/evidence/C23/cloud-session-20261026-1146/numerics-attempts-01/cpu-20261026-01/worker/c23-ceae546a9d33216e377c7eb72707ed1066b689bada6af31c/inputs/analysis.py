# Operator-owned synthetic acceptance: cpu; nonce=8b1f0404216b48e9abc9a2746a8dca48
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/cpu-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/cpu-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,time
children = []
for _ in range(4):
    pid = os.fork()
    if pid == 0:
        end = time.monotonic()+3
        value = 1
        while time.monotonic()<end: value = (value*3+1)%1000000007
        os._exit(0)
    children.append(pid)
for pid in children: assert os.waitpid(pid,0)[1] == 0
write_summary([['competing_cpu_workers',len(children)]])
