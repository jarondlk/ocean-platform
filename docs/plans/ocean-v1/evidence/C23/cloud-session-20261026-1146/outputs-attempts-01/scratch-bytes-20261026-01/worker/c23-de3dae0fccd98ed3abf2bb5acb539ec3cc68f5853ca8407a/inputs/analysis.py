# Operator-owned synthetic acceptance: scratch-bytes; nonce=761d359e45a24cbbbbe07e7850823127
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/scratch-bytes-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/scratch-bytes-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,errno
paths = ['/scratch/fill-' + str(i) for i in range(8)]
streams = [open(path,'wb',buffering=0) for path in paths]
denied = False
written = 0
try:
    for index in range(300):
        try:
            written += streams[index%8].write(b'X'*(512*1024))
        except OSError as error:
            assert error.errno == errno.ENOSPC
            denied = True
            break
finally:
    for stream in streams: stream.close()
    for path in paths: os.unlink(path)
assert denied
write_summary([['scratch_ENOSPC',True],['written_bytes',written]])
