"""C23 formal prerequisite/source/evidence audit; no component selection.

Prepared before C22 delivery. Refuses to emit a readiness receipt until the
explicit later delivery checkpoint is already pushed and its source-bound C22
acceptance is complete. Reads local Git objects/refs and frozen pure C22 gate
helpers only; no fetch/network, application tests, runtime probe or services.

  python docs/plans/ocean-v1/evidence/c23-readiness-2026-10-21/audit.py \
    --delivery-checkpoint <pushed-C22-delivery-metadata-commit>

--check only verifies an already saved receipt and never creates another one.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PLAN = ROOT / 'docs/plans/ocean-v1'
C22 = PLAN / 'evidence/C22'
SOURCE = '66b41063a77561ad959b27eed3e9920747fd6563'
ORIGINAL = '2213306acf9fbb369472cae9f7d9ca881dcd9afd'
RUN_ID = 39539257759
SOURCE_SHA256 = '62e7cb3a58e884ee5578f8c4fa27ce6e282e42366feeb7e9b16050ca8097ce97'
FORMAL = ('C22',)
FROZEN_HELPERS = {
    'freeze_local.py': '126ca0225504af5489bcd04c80470b6aeaf98822e03a63f841d8cca314186564',
    'record_delivery.py': '6f0c1fdb5918d6935dfe64d8e9897a7eee4aff61b55d7e89acf4369992194f81',
}
PREFIXES = ('api', 'db', 'schema', 'orchestration', 'ingestion', 'preprocessing',
            'retrieval', 'evaluation', 'scripts', 'tests', 'migrations', 'frontend-v1', 'frontend',
            'config.py', 'model_runtime.py', '.github/workflows/tests.yml', 'requirements')
PLANNING_FILES = (
    'README.md', 'MASTER_PLAN.md', 'DECISIONS.md', 'STATUS.md', 'ACCEPTANCE_MAP.md',
    'SITE_SEPARATION.md', 'UI_UX_BRIEF.md', 'PROMPTS.md', 'components.json',
    'components/C22-experiment-proposals.md', 'components/C23-python-sandbox.md',
    'handoffs/C22.md',
)


class AuditRefused(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AuditRefused(message)


def sha(value):
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else ROOT / candidate
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def read(value):
    candidate = Path(value)
    return json.loads((candidate if candidate.is_absolute() else ROOT / candidate).read_text())


def rel(value):
    candidate = Path(value).resolve()
    require(candidate.is_relative_to(ROOT), 'Audit path escapes the repository')
    return str(candidate.relative_to(ROOT))


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT).decode().strip()


def blobs(revision, names):
    """Hash exact committed blobs in bounded chunks, without changing Git state."""
    result = {}
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name in sorted(names):
            require('\n' not in name and '\r' not in name, 'Invalid Git blob path')
            process.stdin.write(f'{revision}:{name}\n'.encode())
            process.stdin.flush()
            header = process.stdout.readline().split()
            require(len(header) == 3 and header[1] == b'blob', f'Committed blob is missing: {name}')
            remaining, digest = int(header[2]), hashlib.sha256()
            while remaining:
                chunk = process.stdout.read(min(remaining, 1024 * 1024))
                require(chunk, f'Truncated Git blob: {name}')
                digest.update(chunk)
                remaining -= len(chunk)
            require(process.stdout.read(1) == b'\n', 'Invalid Git batch framing')
            result[name] = digest.hexdigest()
        process.stdin.close()
        require(process.wait(timeout=60) == 0, 'Git blob reader failed')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()
    return result


def committed_evidence(checkpoint):
    listing = subprocess.check_output(['git', 'ls-tree', '-r', '-z', checkpoint, '--', rel(C22)], cwd=ROOT)
    names = []
    for record in listing.split(b'\0'):
        if not record:
            continue
        metadata, filename = record.split(b'\t', 1)
        mode, kind, _ = metadata.split()
        require(mode in {b'100644', b'100755'} and kind == b'blob', 'C22 evidence cannot be a symlink or submodule')
        names.append(filename.decode())
    require(names, 'The pushed checkpoint contains no C22 evidence')
    return blobs(checkpoint, names)


def pure_helpers(local):
    # Validate the exact files before importing their pure definitions. Neither
    # main() nor the network-reading pushed_source() function is ever invoked.
    for filename, expected in FROZEN_HELPERS.items():
        require(sha(C22 / filename) == expected
                and local['evidence_files'].get(rel(C22 / filename)) == expected,
                f'Frozen C22 helper changed: {filename}')
    sys.dont_write_bytecode = True
    modules = {}
    for filename, name in (('freeze_local.py', 'freeze_local'), ('record_delivery.py', 'c22_delivery_readiness')):
        spec = importlib.util.spec_from_file_location(name, C22 / filename)
        require(spec is not None and spec.loader is not None, 'Cannot load the frozen pure validator')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules[filename] = module
    return modules['freeze_local.py'], modules['record_delivery.py']


def literal(path, name):
    module = ast.parse(path.read_text(), filename=str(path))
    found = [node.value for node in module.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    require(len(found) == 1, f'Contract version assignment is ambiguous: {name}')
    value = ast.literal_eval(found[0])
    require(isinstance(value, str), 'Expected a literal contract version')
    return value


def versions():
    result = {
        'experiment_http': literal(ROOT / 'schema/research_experiments.py', 'EXPERIMENT_VERSION'),
        'frozen_export': literal(ROOT / 'orchestration/frozen_experiment_export.py', 'VERSION'),
        'machine_input': literal(ROOT / 'orchestration/frozen_experiment_export.py', 'MACHINE_VERSION'),
        'migration': literal(ROOT / 'migrations/versions/20261020_0020_research_experiments.py', 'revision'),
        'migration_parent': literal(ROOT / 'migrations/versions/20261020_0020_research_experiments.py', 'down_revision'),
    }
    expected = {'experiment_http': 'research-experiments-v1', 'frozen_export': 'c22-frozen-experiment-export-v1',
                'machine_input': 'c22-lossless-machine-table-v1', 'migration': '20261020_0020',
                'migration_parent': '20261019_0019'}
    require(result == expected, 'C22 versioned seam no longer matches the accepted contracts')
    module = ast.parse((ROOT / 'orchestration/research_experiments.py').read_text())
    envelopes = [value.value for node in ast.walk(module) if isinstance(node, ast.Dict)
                 for key, value in zip(node.keys, node.values, strict=True)
                 if isinstance(key, ast.Constant) and key.value == 'version'
                 and isinstance(value, ast.Constant) and value.value == 'c22-execution-envelope-v1']
    require(envelopes, 'The exact accepted C22 execution envelope version is absent')
    result['execution_envelope'] = 'c22-execution-envelope-v1'
    return result


def collect(checkpoint_argument):
    delivery_path = C22 / 'delivery.json'
    require(delivery_path.is_file(), 'C22 delivery is absent; C23 readiness cannot be accepted')
    delivered = read(delivery_path)
    require(delivered.get('component') == 'C22'
            and delivered.get('state') == 'Complete for authorized separate-v1 synthetic/local C22 implementation and exact-source hosted acceptance'
            and delivered.get('source_commit') == SOURCE, 'C22 exact-source delivery is not Complete')
    local = read(delivered['local_receipt']['path'])
    helper, delivery_helper = pure_helpers(local)
    checkpoint = helper.commit(checkpoint_argument)
    require(git('branch', '--show-current') == 'overhaul', 'Readiness must remain on overhaul')
    helper.ancestry(SOURCE, checkpoint)
    helper.ancestry(checkpoint, 'HEAD')
    # origin/overhaul must already have been updated by the parent's authorized
    # push. This audit performs no fetch, ls-remote or other network operation.
    helper.ancestry(checkpoint, 'origin/overhaul')
    changed_after_source = git('diff', '--name-only', SOURCE, checkpoint).splitlines()
    require(all(name.startswith('docs/plans/ocean-v1/') for name in changed_after_source),
            'Delivery metadata checkpoint changes application source')
    require(sha(delivered['local_receipt']['path']) == delivered['local_receipt']['sha256'], 'Local receipt hash changed')
    require(sha(delivered['hosted_receipt']['path']) == delivered['hosted_receipt']['sha256'], 'Hosted receipt hash changed')
    context = helper.source_context(SOURCE, local['inputs']['source_map'], local['inputs']['amendment_map'], ORIGINAL)
    require(context['source_sha256'] == SOURCE_SHA256 and len(context['files']) == 25
            and delivered['source_files'] == local['files'] == context['files']
            and delivered['source_sha256'] == local['source_sha256'] == SOURCE_SHA256,
            'The final25 C22 accepted source map does not match')
    start, supersessions = helper.preservation(context)
    require(len(supersessions) == 12 and delivered['intentional_source_supersessions'] == supersessions,
            'C22 source supersessions are not explicitly reconciled')
    tested = local['tested_transitive_source_files']
    require(len(tested) == 726, 'The accepted726 tested transitive source paths are incomplete')
    helper.verify(tested)
    require(blobs(SOURCE, tested) == tested, 'Tested transitive hashes differ from committed C22 source')
    require(blobs(SOURCE, context['files']) == context['files'], 'Final25 hashes differ from the source commit')
    effective = {**start['prior_source_files'], **context['files']}
    helper.verify(effective)
    require(blobs(SOURCE, effective) == effective, 'A baseline source/configuration changed without acceptance')
    require(all(effective[name] == value for name, value in tested.items()), 'Transitive map conflicts with prior/source reconciliation')
    observed = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--',
                                        *PREFIXES], cwd=ROOT).decode().split('\0')
    observed = {name for name in observed if name and (ROOT / name).is_file()}
    broad_after = helper.load(Path(local['inputs']['backend_result']).parent / 'source-after.json')
    require(observed == set(broad_after), 'Application/test source inventory has additions or deletions after C22 acceptance')
    helper.verify(local['evidence_files'])
    backend = local['checks']['backend']
    backend_now, _ = helper.audit_backend(context, local['inputs']['backend_result'], backend['passed'], backend['skipped'],
                                           local['inputs']['backend_qualification'])
    require(backend_now == backend, 'Local backend reconciliation no longer matches the frozen receipt')
    native, static = helper.audit_native(context), helper.audit_static(context)
    reviews, frontend = helper.audit_reviews_and_export(), helper.audit_frontend_reuse()
    require(native == local['checks']['actual_postgres'] and static == local['checks']['static']
            and reviews == local['checks']['independent_reviews'] and frontend == local['checks']['frontend_reuse'],
            'Frozen local prerequisite gates changed')
    hosted = read(delivered['hosted_receipt']['path'])
    checked_hosted = delivery_helper.hosted_gates(delivered['hosted_receipt']['path'], context, RUN_ID, backend,
                                                 hosted['checks']['backend']['skipped'], 9)
    require(checked_hosted['checks'] == delivered['checks'] and checked_hosted['run'] == delivered['hosted_run'],
            'Delivered hosted run/checks do not match the exact successful source run')
    require(checked_hosted['run']['head_sha'] == SOURCE and checked_hosted['run']['id'] == RUN_ID,
            'A superseded hosted run cannot satisfy C23 readiness')
    committed = committed_evidence(checkpoint)
    helper.verify(committed)
    current_evidence = {rel(item) for item in C22.rglob('*') if item.is_file() and '__pycache__' not in item.parts}
    require(set(committed) == current_evidence, 'Every current C22 evidence file must be frozen in the pushed delivery checkpoint')
    require(committed.get(rel(delivery_path)) == sha(delivery_path), 'The pushed checkpoint does not contain this exact delivery')
    require(blobs(checkpoint, start['prior_evidence_files']) == start['prior_evidence_files'],
            'A historical evidence Git blob changed')
    graph = read(PLAN / 'components.json')
    require(graph.get('schema_version') == 1 and graph.get('release') == '1.0.0', 'Unexpected planning graph version')
    definitions = {item['id']: item for item in graph['components']}
    require(definitions['C23']['dependencies'] == list(FORMAL), 'C23 formal prerequisites changed')
    spec = (PLAN / 'components/C23-python-sandbox.md').read_text()
    require('**Prerequisites:** C22.' in spec and '**Status:** Not started.' in spec, 'C23 spec is no longer unselected with C22 as its sole prerequisite')
    require('Real Linux/gVisor containment evidence is required' in (PLAN / 'PROMPTS.md').read_text(),
            'The mandatory real runtime acceptance boundary is missing')
    require('Latest delivered implementation: **C22' in (PLAN / 'STATUS.md').read_text(), 'STATUS still identifies an older delivered component')
    require(re.search(r'(?im)^State:\s*Complete\b', (PLAN / 'handoffs/C22.md').read_text()), 'C22 handoff is not Complete')
    require('**Status:** Complete' in (PLAN / 'components/C22-experiment-proposals.md').read_text(), 'C22 specification still reports incomplete work')
    original_map = helper.load(local['inputs']['source_map'])['files']
    amendment_path = local['inputs']['amendment_map']
    chain = {}
    for name, current in sorted(context['files'].items()):
        prior = original_map.get(name)
        witnesses = []
        if prior is not None:
            witnesses.append({'receipt': local['inputs']['source_map'], 'receipt_sha256': sha(local['inputs']['source_map']),
                              'source_commit': ORIGINAL, 'sha256': prior})
        else:
            prior = start['prior_source_files'].get(name)
            require(prior is not None, 'New amendment source has no retained prior witness')
            witnesses.append({'receipt': rel(C22 / 'start-snapshot.json'), 'receipt_sha256': sha(C22 / 'start-snapshot.json'),
                              'source_commit': start['base_commit'], 'sha256': prior})
        if prior != current or name not in original_map:
            witnesses.append({'receipt': amendment_path, 'receipt_sha256': sha(amendment_path),
                              'source_commit': SOURCE, 'sha256': current})
        witnesses.append({'receipt': rel(delivery_path), 'receipt_sha256': sha(delivery_path),
                          'source_commit': SOURCE, 'sha256': current})
        chain[name] = {'original_sha256': prior, 'current_sha256': current, 'acceptance_chain': witnesses}
    planning = {rel(PLAN / name): sha(PLAN / name) for name in PLANNING_FILES}
    receipt_pins = {**committed, rel(C22 / 'start-snapshot.json'): sha(C22 / 'start-snapshot.json')}
    inventory_path = HERE / 'existing-vm-inventory.json'
    require(inventory_path.is_file(), 'The supplemental existing-VM planning inventory is missing')
    inventory_pin = {rel(inventory_path): sha(inventory_path)}
    receipt_pins.update(inventory_pin)
    return {'component': 'C23', 'audited_at': datetime.now(timezone.utc).isoformat(),
        'state': 'Formal C22 prerequisite verified; awaiting root selection of authorized local C23 work',
        'ready_for_local_implementation_selection': True, 'component_selected': False, 'C23_complete': False,
        'formal_prerequisites': list(FORMAL), 'planning_schema_version': graph['schema_version'],
        'planning_release': graph['release'], 'branch': 'overhaul', 'head': git('rev-parse', 'HEAD'),
        'source_commit': SOURCE, 'pushed_delivery_checkpoint': checkpoint,
        'original_C22_source_commit': ORIGINAL, 'formal_current_source_files': context['files'],
        'formal_current_source_sha256': SOURCE_SHA256, 'formal_source_entries': len(chain),
        'original_C22_accepted_entries': len(original_map), 'unique_source_paths': len(context['files']),
        'source_entries': chain, 'C22_tested_transitive_source_files': tested,
        'C22_prior_source_and_config_reconciliation': effective, 'intentional_source_supersessions': supersessions,
        'contract_versions': versions(), 'C22_delivery': {'path': rel(delivery_path), 'sha256': sha(delivery_path),
            'source_commit': SOURCE, 'hosted_run_id': RUN_ID, 'hosted_url': hosted['run']['html_url'],
            'checks': delivered['checks'], 'local_checks': delivered['local_checks']},
        'immutable_input_receipt_pins_sha256': receipt_pins, 'planning_document_pins_sha256': planning,
        'preservation': {'protected_files': start['preservation'], 'protected_counts': delivered['protected_counts'],
                         'prior_evidence_files': start['prior_evidence_files'], 'prior_evidence_count': 1204,
                         'C22_committed_evidence_count': len(committed), 'git_checkpoint': checkpoint},
        'frozen_pure_helper_sha256': {rel(C22 / name): value for name, value in FROZEN_HELPERS.items()},
        'supplemental_runtime_inventory_sha256': inventory_pin,
        'external_runtime_gate': {'status': 'unverified', 'actual_runtime_probed_by_audit': False,
            'blocks_authorized_local_implementation': False, 'blocks_C23_completion': True,
            'blocks_real_execution_dispatch': True,
            'required': ['Explicit compatible Linux host and pinned gVisor runtime/image identity',
                         'Real no-network/metadata/host-file/socket and package-installation containment evidence',
                         'Whole-process-tree termination, timeout/cancellation and uncertain recovery proof',
                         'Actual CPU/memory/PID/aggregate disk/input/output enforcement and safe output validation',
                         'Image/input/code mismatch rejection and repeatable numerical fixtures under declared seeds/tolerances'],
            'authorization': 'No host installation, container execution, Linux/cloud provisioning or real experiment authorization is inferred'},
        'authorized_local_boundary': ['Strict supervisor/envelope/result ports and explicit deterministic fakes',
            'Additive execution/result/lease persistence and verified termination capacity-release contracts',
            'Safe staging/output validators, pinned image/lock/profile preparation and marked synthetic acceptance harnesses'],
        'checks_run': 'Read-only source/receipt/log/Git reconciliation; no application tests, services, containers, network or generated Python',
        'findings': [], 'missing_decisions_for_authorized_local_implementation': [],
        'qualifications': ['Push evidence uses the already updated local origin/overhaul ref; this audit performs no remote query or fetch',
            'C22 fake acceptance and unit/configuration checks cannot prove Linux/gVisor containment or scientific correctness',
            'Existing local VM connection configurations are recorded by a separate read-only inventory; they do not establish a reachable compatible Linux/gVisor runtime',
            'The historical COMPONENTS narrative opening does not determine progress; dependencies use components.json and delivery/status/handoff evidence',
            'Readiness does not select C23 or mark it Complete; real runtime, C24 target configuration, data transfer and deployment remain separately gated']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery-checkpoint')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    output = HERE / 'verification.json'
    if args.check:
        require(args.delivery_checkpoint is None, '--check does not create/reselect a checkpoint')
        saved = read(output)
        local = read(C22 / 'verification.json')
        helper, _ = pure_helpers(local)
        for key in ('formal_current_source_files', 'C22_tested_transitive_source_files',
                    'C22_prior_source_and_config_reconciliation', 'immutable_input_receipt_pins_sha256',
                    'planning_document_pins_sha256', 'audit_files_sha256'):
            helper.verify(saved[key])
        helper.verify(saved['preservation']['prior_evidence_files'])
        for files in saved['preservation']['protected_files'].values():
            helper.verify(files)
        helper.ancestry(saved['pushed_delivery_checkpoint'], 'HEAD')
        helper.ancestry(saved['pushed_delivery_checkpoint'], 'origin/overhaul')
        print('Saved C23 readiness source/receipt/preservation pins match; no selection or writes')
        return
    require(args.delivery_checkpoint is not None, '--delivery-checkpoint must explicitly identify the pushed C22 metadata')
    require(not output.exists(), 'Original readiness receipts are immutable; use a new audit chain')
    report = collect(args.delivery_checkpoint)
    report['audit_files_sha256'] = {rel(HERE / name): sha(HERE / name) for name in ('audit.py', 'formal-map.md')}
    with output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'ready_for_local_implementation_selection': True, 'component_selected': False,
                      'formal_source_paths': report['unique_source_paths'], 'tested_transitive_paths': 726,
                      'preserved_prior_evidence': 1204, 'runtime_gate': 'unverified; real dispatch remains disabled',
                      'verification_sha256': sha(output)}))


if __name__ == '__main__':
    try:
        main()
    except (AuditRefused, OSError, ValueError, KeyError, subprocess.SubprocessError, RuntimeError) as error:
        raise SystemExit('C23 readiness refused: ' + str(error)) from None
