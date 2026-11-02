"""One fixed reviewed raw cohort -> private beta quarantine; never promotion."""
import base64
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse

import google_crc32c

PROJECT='ocean-v1-beta-20261101';BUCKET=PROJECT+'-quarantine'
ROOT=Path('/Users/jaronchai/Documents/GitHub/provenance-eco-rag')
SOURCE=Path('/private/tmp/ocean-beta-existing-raw-quarantine-20261102')
EVIDENCE=ROOT/'docs/plans/ocean-v1/beta/raw-quarantine-20261102'
PREFIX='v1/raw-imports/local-20261102-e62eb0e62ad1/'
ARCHIVE='e62eb0e62ad1a1b0b9354944cb46b3b1d818fd12b5076b1e2749fb317cf471cb'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
def save(name,value):
 with (EVIDENCE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def checks(path):
 s=path.lstat();assert stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600 and not path.is_symlink()
 crc=google_crc32c.Checksum();sha=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):crc.update(block);sha.update(block)
 current=path.lstat()
 stable=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_nlink,v.st_uid,v.st_gid,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
 assert stable(current)==stable(s)
 return {'bytes':s.st_size,'sha256':sha.hexdigest(),'crc32c':base64.b64encode(crc.digest()).decode()}
def main():
 assert sys.argv[1:]==['--apply'],'Exact --apply required'
 preparation=json.loads((SOURCE/'preparation-receipt.json').read_text())
 assert preparation['state']=='raw_quarantine_prepared_and_verified' and preparation['files']==1860
 assert preparation['archive_verification']=={'bytes':91934720,'members':1863,'payload_files':1860,'sha256':ARCHIVE}
 assert preparation['path_amendment_revision']=='b34a62a9168b58f8aba96632fe213bf08fc8a9f3'
 assert stat.S_IMODE(SOURCE.stat().st_mode)==0o700 and not SOURCE.is_symlink()
 files={name:checks(SOURCE/name) for name in ['raw-quarantine.tar','source-manifest.json','transfer-manifest.json','scope-amendment.json']}
 assert files['raw-quarantine.tar']['sha256']==ARCHIVE
 assert files['source-manifest.json']['sha256']==preparation['source_manifest_sha256']
 assert files['transfer-manifest.json']['sha256']==preparation['transfer_manifest_sha256']
 assert files['scope-amendment.json']['sha256']==preparation['path_amendment_sha256']
 assert not (EVIDENCE/'upload-selection.json').exists(),'Existing upload attempt; inspect without blind retry'
 r=subprocess.run(['/opt/homebrew/bin/gcloud','auth','print-access-token','--project='+PROJECT,'--quiet'],capture_output=True,text=True,check=True,timeout=30)
 token=r.stdout.strip();opener=urllib.request.build_opener(NoRedirect())
 def request(path,media=False,allow_missing=False):
  assert path.startswith('https://storage.googleapis.com/storage/v1/b/'+BUCKET)
  req=urllib.request.Request(path,headers={'Authorization':'Bearer '+token,'Accept-Encoding':'identity'})
  try:
   response=opener.open(req,timeout=45)
  except urllib.error.HTTPError as e:
   if allow_missing and e.code==404:return {'http_status':404}
   raise RuntimeError('Fixed beta quarantine request failed with HTTP '+str(e.code)) from None
  if media:return response
  with response:return json.load(response)
 base='https://storage.googleapis.com/storage/v1/b/'+BUCKET
 bucket=request(base)
 assert bucket['name']==BUCKET and bucket['projectNumber']=='534831104543' and bucket['location']=='ASIA-NORTHEAST1'
 assert bucket['iamConfiguration']['uniformBucketLevelAccess']['enabled'] and bucket['iamConfiguration']['publicAccessPrevention']=='enforced'
 policy=request(base+'/iam');assert all(not {'allUsers','allAuthenticatedUsers'}.intersection(v['members']) for v in policy.get('bindings',[]))
 save('bucket-before-upload.json',bucket)
 for name in files:
  path=base+'/o/'+urllib.parse.quote(PREFIX+name,safe='')
  assert request(path,allow_missing=True)=={'http_status':404},'Existing raw object; do not overwrite'
 save('upload-selection.json',{'state':'selected_once','project_id':PROJECT,'bucket':BUCKET,'prefix':PREFIX,'source_code_revision':preparation['path_amendment_revision'],'objects':files,'source_files':1860,'payload_bytes':89159370,'purpose':'private raw quarantine; not published or C09 sealed','source_mutation':False,'if_generation_match':0})
 outcomes=[]
 for name,expected in files.items():
  assert checks(SOURCE/name)==expected,'Local package changed before upload'
  cmd=['/opt/homebrew/bin/gcloud','storage','cp',str(SOURCE/name),'gs://'+BUCKET+'/'+PREFIX+name,'--project='+PROJECT,'--if-generation-match=0','--custom-metadata=sha256='+expected['sha256']+',purpose=raw-quarantine','--quiet']
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
  if r.returncode:raise RuntimeError('Quarantine copy outcome requires fixed-object inspection; no automatic retry')
  url=base+'/o/'+urllib.parse.quote(PREFIX+name,safe='');actual=request(url)
  assert actual['bucket']==BUCKET and actual['name']==PREFIX+name and int(actual['size'])==expected['bytes'] and actual['crc32c']==expected['crc32c']
  assert actual['metadata']['sha256']==expected['sha256']
  with request(url+'?alt=media&generation='+actual['generation'],media=True) as response:
   size=0;digest=hashlib.sha256()
   for block in iter(lambda:response.read(1024*1024),b''):size+=len(block);assert size<=expected['bytes'];digest.update(block)
  assert size==expected['bytes'] and digest.hexdigest()==expected['sha256']
  assert checks(SOURCE/name)==expected,'Local package changed during upload'
  result={'state':'uploaded_and_download_sha256_verified','name':actual['name'],'generation':actual['generation'],**expected}
  save(name.replace('.','-')+'-upload.json',result);outcomes.append(result)
 save('upload-complete.json',{'state':'private_raw_quarantine_complete','project_id':PROJECT,'bucket':BUCKET,'prefix':PREFIX,'objects':outcomes,'payload_files':1860,'payload_bytes':89159370,'scientific_approval':False,'C09_snapshot_sealed':False,'catalogue_registered':False,'published_or_promoted':False,'legacy_or_local_source_mutation':False,'new_runtime_legacy_access':False})
 print(json.dumps({'state':'private_raw_quarantine_complete','objects':len(outcomes),'payload_files':1860,'payload_bytes':89159370,'each_object_download_sha256_verified':True,'published_or_promoted':False}))
if __name__=='__main__':main()
