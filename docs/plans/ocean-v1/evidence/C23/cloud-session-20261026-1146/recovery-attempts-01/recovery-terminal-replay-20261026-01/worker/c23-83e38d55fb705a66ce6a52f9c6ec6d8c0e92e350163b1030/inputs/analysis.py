# Operator-owned synthetic acceptance: smoke; nonce=5766cb12fd034120aa5309fd15fcc0a8
INPUT_MACHINE='table-01.json'
HOST_CANARY='/unused-operator-recovery-canary'
HOST_SOCKET='/unused-operator-recovery.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,time
assert os.getuid()==65532 and os.getgid()==65532
write_summary([['operator_recovery_marker','5766cb12fd034120aa5309fd15fcc0a8']])
