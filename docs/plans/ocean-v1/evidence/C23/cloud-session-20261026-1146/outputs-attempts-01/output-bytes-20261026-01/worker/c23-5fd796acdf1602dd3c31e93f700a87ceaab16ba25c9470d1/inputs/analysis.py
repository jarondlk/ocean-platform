# Operator-owned synthetic acceptance: output-bytes; nonce=baa9b39142ce47f287e4aa970261744f
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/output-bytes-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/output-bytes-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,errno
paths = ['/outputs/.fill-a','/outputs/.fill-b']
streams = [open(path,'wb',buffering=0) for path in paths]
denied = False
written = 0
try:
    for index in range(64):
        try:
            written += streams[index%2].write(b'X'*4096)
        except OSError as error:
            assert error.errno == errno.ENOSPC
            denied = True
            break
finally:
    for stream in streams: stream.close()
    for path in paths: os.unlink(path)
assert denied
write_summary([['aggregate_output_ENOSPC',True],['written_bytes',written]])
