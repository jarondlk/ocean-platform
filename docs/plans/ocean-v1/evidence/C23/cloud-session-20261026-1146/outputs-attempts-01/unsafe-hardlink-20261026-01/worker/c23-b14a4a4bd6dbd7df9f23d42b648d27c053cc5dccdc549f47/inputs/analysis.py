# Operator-owned synthetic acceptance: unsafe-hardlink; nonce=826d54d7fc1d441e96751c41f0b27d75
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/unsafe-hardlink-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/unsafe-hardlink-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os
write_summary([['synthetic',1]])
os.link('summary.json','alias.json')
