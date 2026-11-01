"""Bounded Docker smoke for explicit beta image digests; no cloud or secret access.

Images must already be available in the Docker daemon. All containers have no
network, no published ports and no real credentials. Frontend HTTP is exercised
inside its own namespace using its packaged Node runtime.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


REGISTRY = 'asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/'
MANIFEST = '/opt/ocean/source-manifest.json'
API_PROBE = r'''
import hashlib,json,os,sys
from pathlib import Path
assert os.geteuid() != 0
assert 'DATABASE_URL' not in os.environ
assert 'OCEAN_V1_DATABASE_URL' not in os.environ
raw=Path('/opt/ocean/source-manifest.json').read_bytes()
manifest=json.loads(raw)
import api.v1_host as host
assert 'api.main' not in sys.modules
assert sys.platform == 'linux'
assert host.MIGRATION_HEAD == '20261027_0021'
print(json.dumps({'uid':os.geteuid(),'manifest_sha256':hashlib.sha256(raw).hexdigest(),
 'manifest':manifest,'v1_host_imported':True,'legacy_entry_imported':False,
 'database_credentials_supplied':False}))
'''
FRONTEND_PROBE = r'''
const fs=require('node:fs'),crypto=require('node:crypto'),http=require('node:http');
const assert=require('node:assert/strict');
assert(process.getuid()>0);
assert.equal(process.platform,'linux');
const raw=fs.readFileSync('/opt/ocean/source-manifest.json');
console.log(JSON.stringify({uid:process.getuid(),manifest_sha256:crypto.createHash('sha256').update(raw).digest('hex'),manifest:JSON.parse(raw)}));
const call=(path,host='beta.oceaninfobio.com')=>new Promise((resolve,reject)=>{
 const req=http.get({hostname:'127.0.0.1',port:8080,path,headers:{host,'x-forwarded-proto':'https','x-forwarded-port':'443'}},res=>{
  const chunks=[];let size=0;
  res.on('data',chunk=>{size+=chunk.length;if(size>2*1024*1024){req.destroy(new Error('Response exceeds smoke bound'));}else chunks.push(chunk);});
  res.on('error',reject);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(chunks)}));
 });req.setTimeout(3000,()=>req.destroy(new Error('HTTP smoke deadline')));req.on('error',reject);
});
(async()=>{
 let login;
 for(let i=0;i<20;i++){
  try{login=await call('/login');break;}catch(error){if(i===19)throw error;await new Promise(resolve=>setTimeout(resolve,200));}
 }
 assert.equal(login.status,200);assert.match(login.body.toString(),'Sign in to OCEAN');
 const links=[...login.body.toString().matchAll(/<link\b[^>]*href="([^"]+)"[^>]*>/g)].map(m=>m[1]);
 const css=links.find(path=>path.startsWith('/_next/static/')&&/\.css(?:\?|$)/.test(path));
 assert(css,'Built login must reference a local generated CSS asset');
 const asset=await call(css);assert.equal(asset.status,200);assert(asset.body.length>0);assert.match(String(asset.headers['content-type']),/text\/css/);
 const denied=await call('/login','wrong-host.invalid');assert.equal(denied.status,403);
 const runtime=await call('/v1/runtime');assert.equal(runtime.status,401);
 console.log(JSON.stringify({http:{login_status:login.status,css_status:asset.status,css_bytes:asset.body.length,wrong_host_status:denied.status,unauthenticated_runtime_status:runtime.status},google_callback_tested:false,database_or_science_available:false}));
})().catch(error=>{console.error('Container HTTP smoke failed: '+error.message);process.exitCode=1;});
'''


class SmokeFailure(RuntimeError):
    """Bounded probe or contract failure, without credentials in diagnostics."""


def validate_image(value: str, kind: str) -> str:
    if not re.fullmatch(re.escape(REGISTRY + kind) + r'@sha256:[a-f0-9]{64}', value):
        raise argparse.ArgumentTypeError('Use the explicit digest of the named beta image')
    return value


class DockerSmoke:
    def __init__(self, docker: str, seconds: int = 120):
        self.docker = docker
        self.deadline = time.monotonic() + seconds
        self.owned_names: list[str] = []
        self.commands: list[dict] = []
        self.cleanup: list[dict] = []

    def run(self, args: list[str], *, expected: int = 0, timeout: int = 30) -> subprocess.CompletedProcess:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise SmokeFailure('The 120-second smoke deadline expired')
        try:
            result = subprocess.run([self.docker, *args], capture_output=True, text=True,
                timeout=min(timeout, remaining), check=False)
        except subprocess.TimeoutExpired:
            raise SmokeFailure('A bounded Docker command exceeded its deadline') from None
        # Probe source and synthetic settings are non-secret, but keep the receipt compact.
        self.commands.append({'operation': args[0], 'returncode': result.returncode,
            'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
            'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest()})
        if result.returncode != expected:
            raise SmokeFailure(f'Docker {args[0]} returned {result.returncode}; expected {expected}: '
                + result.stderr[-2000:])
        return result

    def options(self, suffix: str) -> list[str]:
        name = 'ocean-beta-smoke-' + suffix + '-' + uuid.uuid4().hex
        self.owned_names.append(name)
        return ['--name', name, '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--pids-limit=256', '--memory=2g', '--cpus=1',
            '--tmpfs=/tmp:rw,nosuid,nodev,size=67108864']

    def close(self) -> None:
        # Never enumerate/delete other containers. Names were generated only by this invocation.
        for name in reversed(self.owned_names):
            try:
                result = subprocess.run([self.docker, 'rm', '-f', name], capture_output=True,
                    text=True, timeout=10, check=False)
                absent = result.returncode == 0 or 'No such container' in result.stderr
                self.cleanup.append({'container_name': name, 'removed_or_already_absent': absent,
                    'returncode': result.returncode})
            except subprocess.TimeoutExpired:
                self.cleanup.append({'container_name': name, 'removed_or_already_absent': False,
                    'error': 'cleanup deadline'})


def manifest_check(probe: dict, kind: str, revision: str, expected_sha256: str) -> dict:
    if probe['uid'] <= 0 or probe['manifest_sha256'] != expected_sha256:
        raise SmokeFailure('Container identity or embedded context manifest does not match')
    manifest = probe['manifest']
    if kind == 'api':
        if (manifest['version'] != 'ocean-v1-beta-api-context-v1'
                or manifest['revision'] != revision or manifest['project_id'] != 'ocean-v1-beta-20261101'):
            raise SmokeFailure('API context identity does not match the selected source')
        canonical = json.dumps(manifest['sources'], sort_keys=True, separators=(',', ':'))
        if hashlib.sha256(canonical.encode()).hexdigest() != manifest['source_manifest_sha256']:
            raise SmokeFailure('API embedded source inventory is inconsistent')
        count = len(manifest['sources'])
    else:
        if (manifest['version'] != 'beta-frontend-source-context-v1'
                or manifest['source_commit'] != revision
                or manifest['synthetic_preview_graph_included'] is not False
                or manifest['credentials_or_generated_files_included'] is not False):
            raise SmokeFailure('Frontend context identity does not match the selected source')
        count = len(manifest['source_files'])
    return {'uid': probe['uid'], 'manifest_sha256': expected_sha256, 'source_file_count': count,
        'source_commit': revision}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-image', required=True, type=lambda v: validate_image(v, 'frontend'))
    parser.add_argument('--api-image', required=True, type=lambda v: validate_image(v, 'api'))
    parser.add_argument('--revision', required=True)
    parser.add_argument('--frontend-manifest-sha256', required=True)
    parser.add_argument('--api-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if (not re.fullmatch(r'[a-f0-9]{40}', args.revision)
            or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in
                [args.frontend_manifest_sha256, args.api_manifest_sha256])):
        parser.error('Full source commit and manifest SHA256 values are required')
    if args.output.exists() or args.output.is_symlink():
        parser.error('The evidence output must be a new file')
    docker = shutil.which('docker')
    if docker is None:
        parser.error('Docker CLI and an existing daemon with both images are required')
    smoke = DockerSmoke(docker)
    receipt = {'version': 'ocean-beta-container-smoke-v1', 'started_at': datetime.now(timezone.utc).isoformat(),
        'status': 'failed', 'source_commit': args.revision,
        'images': {'frontend': args.frontend_image, 'api': args.api_image},
        'container_network': 'none', 'ports_published': False, 'real_credentials_supplied': False,
        'google_callback_tested': False, 'deployment_accepted': False, 'checks': {}}
    try:
        for kind, image in [('frontend', args.frontend_image), ('api', args.api_image)]:
            inspected = json.loads(smoke.run(['image', 'inspect', image]).stdout)
            if len(inspected) != 1 or inspected[0]['Config'].get('User') in {'', '0', '0:0', 'root'}:
                raise SmokeFailure('Image default user must be explicitly non-root')
            if inspected[0]['Os'] != 'linux' or inspected[0]['Architecture'] != 'amd64':
                raise SmokeFailure('The accepted beta image must target Linux amd64')
            receipt['checks'][kind + '_default_user'] = inspected[0]['Config']['User']
        api = smoke.run(['run', *smoke.options('api-import'), '--entrypoint=python',
            args.api_image, '-c', API_PROBE])
        probe = json.loads(api.stdout)
        receipt['checks']['api_import'] = manifest_check(probe, 'api', args.revision, args.api_manifest_sha256)
        receipt['checks']['api_import'].update({'v1_host_imported': probe['v1_host_imported'],
            'legacy_entry_imported': probe['legacy_entry_imported']})
        rejected = smoke.run(['run', *smoke.options('api-default'), args.api_image], expected=2)
        if rejected.stderr.strip() != 'Explicit production beta project required':
            raise SmokeFailure('Unconfigured API must refuse startup before database configuration')
        receipt['checks']['api_default_refuses_unconfigured_startup'] = True
        env = {'DEPLOYMENT_ENV': 'production', 'AUTH_MODE': 'required', 'ENABLE_MOCK_LOGIN': 'false',
            'PERSIST_LOCAL_CHAT': 'false', 'V1_PUBLIC_ORIGIN': 'https://beta.oceaninfobio.com',
            'AUTH_URL': 'https://beta.oceaninfobio.com', 'V1_API_ORIGIN': 'http://127.0.0.1:8000',
            'V1_AUTH_SECRET': 'a' * 64, 'V1_INTERNAL_AUTH_SECRET': 'b' * 64,
            'V1_INTERNAL_AUTH_ISSUER': 'ocean-v1-frontend', 'V1_INTERNAL_AUTH_AUDIENCE': 'ocean-v1-api',
            'V1_GOOGLE_CLIENT_ID': 'fixture-client.apps.googleusercontent.com',
            'V1_GOOGLE_CLIENT_SECRET': 'fixture-oauth-secret-not-live'}
        options = smoke.options('frontend')
        name = smoke.owned_names[-1]
        smoke.run(['run', '--detach', *options,
            *[part for key, value in env.items() for part in ['--env', key + '=' + value]], args.frontend_image])
        result = smoke.run(['exec', name, 'node', '-e', FRONTEND_PROBE], timeout=35)
        lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if len(lines) != 2:
            raise SmokeFailure('Expected the manifest and HTTP probe records')
        receipt['checks']['frontend'] = manifest_check(lines[0], 'frontend', args.revision, args.frontend_manifest_sha256)
        receipt['checks']['frontend'].update(lines[1])
        state = json.loads(smoke.run(['inspect', name]).stdout)[0]
        if state['HostConfig']['NetworkMode'] != 'none' or state['State']['Running'] is not True:
            raise SmokeFailure('The frontend did not remain alive with network disabled')
        receipt['status'] = 'passed'
    except (SmokeFailure, KeyError, ValueError, OSError) as exc:
        receipt['error'] = str(exc)
    finally:
        smoke.close()
        receipt['commands'] = smoke.commands
        receipt['cleanup'] = smoke.cleanup
        if not all(item['removed_or_already_absent'] for item in smoke.cleanup):
            receipt['status'] = 'failed'
            receipt['cleanup_error'] = 'An owned container requires operator inspection'
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'output': str(args.output),
        'checks': sorted(receipt['checks']), 'owned_containers_cleaned': all(
            item['removed_or_already_absent'] for item in smoke.cleanup)}))
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
