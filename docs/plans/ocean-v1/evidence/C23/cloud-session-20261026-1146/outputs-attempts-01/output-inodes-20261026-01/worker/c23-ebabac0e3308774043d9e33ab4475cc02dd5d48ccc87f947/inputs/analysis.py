# Operator-owned synthetic acceptance: output-inodes; nonce=429df6441ee14873b88c884ff5776e65
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/output-inodes-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/output-inodes-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os,errno
names = []
denied = False
for index in range(520):
    name = '/outputs/.inode-' + str(index)
    try:
        with open(name,'xb'): pass
    except OSError as error:
        assert error.errno == errno.ENOSPC
        denied = True
        break
    names.append(name)
for name in names: os.unlink(name)
assert denied and 1 <= len(names) <= 511
write_summary([['output_inode_ENOSPC',True],['files_created',len(names)]])
