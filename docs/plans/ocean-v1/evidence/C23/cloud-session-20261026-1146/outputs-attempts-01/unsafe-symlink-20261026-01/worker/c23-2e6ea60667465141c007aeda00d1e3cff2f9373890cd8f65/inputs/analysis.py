# Operator-owned synthetic acceptance: unsafe-symlink; nonce=d4785def733c42498ef43c83060c2edb
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/unsafe-symlink-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/unsafe-symlink-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os
os.symlink('/inputs/analysis.py','summary.json')
