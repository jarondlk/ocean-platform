# Operator-owned synthetic acceptance: memory; nonce=8fed9b6f812c42c19b53dccaaf55c918
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/memory-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/memory-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import time
values = []
for _ in range(1024):
    value = bytearray(1024*1024)
    for offset in range(0,len(value),4096): value[offset] = 1
    values.append(value)
raise AssertionError('memory limit not enforced')
