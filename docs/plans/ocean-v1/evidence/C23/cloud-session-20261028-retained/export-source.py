from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,stat,tarfile
assert os.geteuid()==0
root=Path('/var/lib/ocean-c23')
attempts=['retained-scientific-20261028-01','retained-owner-revoked-20261028-01']
paths=[]
for label in attempts:
 directory=root/'operator-acceptance'/label
 observation=json.loads((directory/'observations.json').read_bytes())
 assert observation['evaluation']['passed'] is True and observation['cleanup']['rootfs_unmounted'] is True
 assert all(str(directory) not in row for row in Path('/proc/self/mountinfo').read_text().splitlines())
 for path in directory.rglob('*'):
  info=path.lstat()
  assert stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
  if stat.S_ISREG(info.st_mode):paths.append(path)
for name in ('operator-source-20261027-08.json','image-preparation-quota-v3.json','runtime-preparation-quota-v3.json','rootfs-normalization-quota-v3.json','host-positive-retained-20261028.json','network-isolation-retained-20261028.json','retained-loopback-listeners-20261028.json'):
 paths.append(root/'evidence'/name)
files={};total=0
for path in sorted(paths):
 assert not path.is_symlink() and path.resolve()==path and path.is_relative_to(root)
 raw=path.read_bytes();assert len(raw)<=64*1024**2
 total+=len(raw);assert total<=128*1024**2
 files[str(path.relative_to(root))]={'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
receipt={'version':'c23-retained-completed-attempt-export-v1','recorded_at':datetime.now(timezone.utc).isoformat(),'export_boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'run_boot_id':'5f6a30d5-9277-4fd9-bee5-0b4285c294a4','source_commit':'501c80b7e5ee07f0990539baea3d8243f71d184a','files':files,'total_uncompressed_bytes':total,'cases':attempts,'qualification':'Readonly export after automatic STOP and a new export-only boot. Original completed same-boot observations and packets are copied unchanged; no new runtime execution, physical issuance or release is performed. Private control config/seed directories are explicitly excluded.'}
manifest=root/'evidence/retained-export-20261028-01.json'
with manifest.open('x') as stream:json.dump(receipt,stream,sort_keys=True,separators=(',',':'));stream.write('\n')
manifest.chmod(0o400)
archive=root/'evidence/retained-export-20261028-01.tar.gz'
with tarfile.open(archive,'x:gz',format=tarfile.PAX_FORMAT) as tar:
 for relative in files:tar.add(root/relative,arcname=relative,recursive=False)
 tar.add(manifest,arcname='evidence/retained-export-20261028-01.json',recursive=False)
archive.chmod(0o400)
print(json.dumps({'archive':str(archive),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archive_bytes':archive.stat().st_size,'member_files':len(files)+1,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'new_execution_or_issuance':False},sort_keys=True))
