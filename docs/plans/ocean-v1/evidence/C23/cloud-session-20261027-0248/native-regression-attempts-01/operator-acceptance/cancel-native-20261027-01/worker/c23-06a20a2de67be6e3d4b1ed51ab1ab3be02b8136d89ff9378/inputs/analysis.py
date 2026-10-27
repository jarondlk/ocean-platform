# Operator-owned synthetic acceptance: cancel; nonce=7515a3dab9eb41e0805b11fb02e0dbe9
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/cancel-native-20261027-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/cancel-native-20261027-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import time
while True: time.sleep(0.05)
