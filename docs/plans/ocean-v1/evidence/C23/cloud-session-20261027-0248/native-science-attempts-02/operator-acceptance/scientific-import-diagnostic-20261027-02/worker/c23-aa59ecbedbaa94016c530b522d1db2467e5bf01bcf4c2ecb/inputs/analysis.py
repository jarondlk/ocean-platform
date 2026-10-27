# Operator-owned synthetic acceptance: scientific-import-diagnostic; nonce=f959c15c49cd46428e31c273aed113ca
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/scientific-import-diagnostic-20261027-02/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/scientific-import-diagnostic-20261027-02/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import json, os, resource, stat, sys, traceback
assert os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []
rows = [['diagnostic_only',True],['numerical_acceptance',False],
        ['uid',os.getuid()],['gid',os.getgid()],['python',sys.version[:512]],
        ['fd_scope','guest process only; host Sentry/gofer FD quotas are separate'],
        ['import_order','_datetime,datetime,_pydatetime,numpy,_datetime retry,datetime retry']]
def scalar(value,limit=2048):
    if value is None or type(value) in (bool,int):
        return value
    return str(value)[:limit]
def failure(label,error):
    rows.extend([[label + '.error_type',type(error).__name__[:128]],
                 [label + '.errno',scalar(getattr(error,'errno',None),128)],
                 [label + '.name',scalar(getattr(error,'name',None),512)],
                 [label + '.path',scalar(getattr(error,'path',None),512)],
                 [label + '.error',scalar(error,2048)],
                 [label + '.trace',traceback.format_exc(limit=8)[-8192:]]])
    chain = error.__cause__ or error.__context__
    seen = set()
    for index in range(3):
        if chain is None or id(chain) in seen:
            break
        seen.add(id(chain))
        rows.append([label + '.cause_' + str(index),
                     (type(chain).__name__ + ': ' + str(chain))[:2048]])
        chain = chain.__cause__ or chain.__context__
def process_observation(label):
    limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    rows.extend([[label + '.rlimit_nofile_soft',limits[0]],
                 [label + '.rlimit_nofile_hard',limits[1]]])
    try:
        descriptors = os.listdir('/proc/self/fd')
        assert len(descriptors) <= 512
        rows.append([label + '.guest_fd_count',len(descriptors)])
    except Exception as error:
        failure(label + '.fd_observation',error)
process_observation('baseline')
with open('/proc/self/status',encoding='ascii') as stream:
    status = stream.read(65537)
assert len(status) <= 65536
capabilities = {}
for line in status.splitlines():
    name, _, value = line.partition(':')
    if name in {'FDSize','Threads','VmRSS','VmSize','NoNewPrivs'}:
        rows.append(['baseline.status.' + name,value.strip()[:256]])
    if name in {'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}:
        capabilities[name] = int(value.strip(),16)
assert len(capabilities) == 5 and all(value == 0 for value in capabilities.values())
rows.append(['capabilities_zero',True])
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS'):
    rows.append(['environment.' + name,scalar(os.environ.get(name),128)])
paths = ['/usr/local/lib/python3.12/datetime.py',
         '/usr/local/lib/python3.12/_pydatetime.py']
try:
    with os.scandir('/usr/local/lib/python3.12/lib-dynload') as entries:
        names = []
        for entry in entries:
            if entry.name.startswith('_datetime.') and entry.name.endswith('.so'):
                names.append(entry.name)
                assert len(names) <= 8
    paths.extend('/usr/local/lib/python3.12/lib-dynload/' + name for name in sorted(names))
except Exception as error:
    failure('datetime_extension_discovery',error)
for index,path in enumerate(paths):
    label = 'module_path_' + str(index)
    rows.append([label,path])
    try:
        info = os.stat(path,follow_symlinks=False)
        rows.extend([[label + '.mode',oct(stat.S_IMODE(info.st_mode))],
                     [label + '.uid',info.st_uid],[label + '.gid',info.st_gid],
                     [label + '.nlink',info.st_nlink],[label + '.size',info.st_size]])
    except Exception as error:
        failure(label,error)
succeeded = {}
for label,name in [('_datetime_first','_datetime'),('datetime_first','datetime'),
                   ('_pydatetime_first','_pydatetime'),('numpy','numpy'),
                   ('_datetime_after_numpy','_datetime'),('datetime_after_numpy','datetime')]:
    process_observation(label + '.before')
    try:
        module = __import__(name)
        succeeded[label] = True
        rows.extend([[label + '.ok',True],
                     [label + '.file',scalar(getattr(module,'__file__',None),512)],
                     [label + '.version',scalar(getattr(module,'__version__',None),128)]])
    except Exception as error:
        succeeded[label] = False
        rows.append([label + '.ok',False])
        failure(label,error)
    process_observation(label + '.after')
rows.extend([['numpy_import_succeeded',succeeded.get('numpy',False)],
             ['original_failed_numerical_case_reclassified',False]])
assert len(rows) <= 256
assert len(json.dumps({'columns':['probe','value'],'rows':rows},ensure_ascii=False).encode()) <= 192*1024
write_summary(rows)
