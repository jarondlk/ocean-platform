# Operator-owned synthetic acceptance: smoke; nonce=91f341fb08d44418b40b3b703a07cdc0
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/smoke-20261026-01/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/smoke-20261026-01/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import os, json
assert os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []
values = {}
for line in open('/proc/self/status', encoding='ascii'):
    name, _, value = line.partition(':')
    if name in {'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}:
        values[name] = int(value.strip(),16)
assert len(values) == 5 and all(value == 0 for value in values.values())
source = json.load(open('/inputs/' + INPUT_MACHINE, encoding='utf-8'))
assert source['operator_int64_probe'] == [9223372036854775806, 9223372036854775807]
write_summary([['uid',os.getuid()],['gid',os.getgid()],['capabilities_zero',True],
               ['exact_int64',source['operator_int64_probe'][-1]]])
