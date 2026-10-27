# Operator-owned synthetic acceptance: processes; nonce=3c2091f349164a6ba202160a45e3683c
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/processes-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/processes-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,time,errno
count = 0
denied = False
for _ in range(160):
    try:
        pid = os.fork()
    except OSError as error:
        assert error.errno == errno.EAGAIN
        denied = True
        break
    if pid == 0:
        time.sleep(25)
        os._exit(0)
    count += 1
assert denied and 1 <= count <= 126
write_summary([['forks_before_EAGAIN',count],['guest_task_bound',128]])
