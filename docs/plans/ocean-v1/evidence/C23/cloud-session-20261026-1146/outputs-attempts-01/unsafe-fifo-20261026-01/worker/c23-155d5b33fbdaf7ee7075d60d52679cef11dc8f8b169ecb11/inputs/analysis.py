# Operator-owned synthetic acceptance: unsafe-fifo; nonce=a143819591244fdfb1f35221b7a5126b
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/unsafe-fifo-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/unsafe-fifo-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os
os.mkfifo('summary.json')
