"""Read-only verification of the one-constant job renderer supersession."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    data = json.loads((HERE / 'supersession.json').read_text())
    base = HERE.parent
    original = json.loads((base / 'receipt.json').read_text())
    assert sha(base / 'receipt.json') == data['prior_receipt_sha256']
    old = HERE / data['old_source_copy']
    assert sha(old) == data['from_sha256'] == original['source_pins'][data['path']]
    current = ROOT / data['path']
    assert sha(current) == data['to_sha256']
    assert old.read_bytes().replace(data['from_revision'].encode(), data['to_revision'].encode()) == current.read_bytes()
    assert data['to_revision'] == '8b06a1b993cbca53ded0a9e79e1acb5ba58f3089'
    for name, digest in original['source_pins'].items():
        if name != data['path']:
            assert sha(ROOT / name) == digest, name
    for name, digest in data['prior_artifact_sha256'].items():
        assert sha(base / name) == digest, name
    assert len(data['new_render_checks']) == 4
    assert all(c['new_operator_revision_in_environment_and_confirmation'] and c['api_source_unchanged']
               and not c['real_secret_or_image_reference'] for c in data['new_render_checks'])
    return {'verified': True, 'intentional_source_supersessions': 1, 'synthetic_job_binding_checks': 4,
            'prior_setup_artifacts_preserved': len(data['prior_artifact_sha256']), 'cloud_apply_performed': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
