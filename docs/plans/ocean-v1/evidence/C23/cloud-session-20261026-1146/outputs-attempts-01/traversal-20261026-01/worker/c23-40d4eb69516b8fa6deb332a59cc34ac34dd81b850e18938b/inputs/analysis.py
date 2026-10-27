# Operator-owned synthetic acceptance: traversal; nonce=c767b07373094a3198fb5879734f16bd
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/traversal-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/traversal-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
for path in ['../outside.json','/inputs/escaped.json','/usr/local/escaped.json']:
    try:
        with open(path,'w') as stream: stream.write('unexpected')
    except OSError:
        pass
    else:
        raise AssertionError('traversal write escaped outputs/scratch')
write_summary([['outside_write_denied',True]])
