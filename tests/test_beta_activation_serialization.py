"""Frozen Unicode activation bytes through the renderer and runtime reader."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from api.v1_catalogue_host import (
    CatalogueHostConfigurationError, _canonical, load_snapshot_catalogue,
)
from ingestion.artifact_store import BoundedLocalStore
from orchestration.catalogue_service import CatalogueServiceError
from tests.catalogue_service_support import fixture_user
from tests.test_beta_snapshot_catalogue import PREPARE, sealed as sealed

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('beta_activation_renderer',
    ROOT / 'deploy/gcp/beta/snapshot-api/render_configuration.py')
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


def activation(sealed):
    document = json.loads((sealed[1] / 'activation.json').read_bytes())
    document.update(research_enabled=True,
        authorization_ref='chat-20261105-prioritize-beta-research-questions',
        policy_revision='beta:research:synthetic-serialization')
    document['snapshots'][0]['descriptor']['label']['ja'] = '合成CTDカタログ'
    document['qualifications'].append('合成データ。科学的承認はありません。')
    return document


def publish_synthetic(sealed, tmp_path, raw, *, expected_sha256=None):
    digest = expected_sha256 or hashlib.sha256(raw).hexdigest()
    binding = RENDERER.binding_document(digest)
    source = tmp_path / 'research-source.json'
    source.write_bytes(RENDERER.canonical(binding))
    source.chmod(0o444)
    path = sealed[1] / 'store' / binding['activation_object']
    path.write_bytes(raw)
    return source, path


def load_research(sealed, source):
    return load_snapshot_catalogue(source, project_id=PREPARE.PROJECT,
        site_id='v1:' + PREPARE.PROJECT, cursor_key=b'stable-private-test-cursor-key' * 2,
        context_retention=True, research_retention=True, _allow_test_owner=True,
        _test_store=BoundedLocalStore(sealed[1] / 'store'))


@pytest.mark.parametrize('encoding', ['renderer_ascii', 'existing_utf8'])
def test_rendered_unicode_activation_loads_without_rewriting_frozen_bytes(sealed, tmp_path, encoding):
    document = activation(sealed)
    ascii_raw, utf8_raw = RENDERER.canonical(document), _canonical(document)
    assert ascii_raw != utf8_raw
    raw = ascii_raw if encoding == 'renderer_ascii' else utf8_raw
    private = tmp_path / 'prospective-activation.json'
    private.write_bytes(raw)
    private.chmod(0o600)
    source = tmp_path / 'rendered-source.json'
    digest = hashlib.sha256(raw).hexdigest()
    report = RENDERER.render(activation=private, activation_sha256=digest,
        output=source, research_enabled=True)
    # The build copies this opaque renderer output into a root-owned 0444 file.
    source.chmod(0o444)
    frozen_path = sealed[1] / 'store' / RENDERER.binding_document(digest)['activation_object']
    frozen_path.write_bytes(raw)
    control = sealed[1] / 'store/v1/catalogue/control.json'
    before = control.read_bytes()

    service, browser = load_research(sealed, source)
    actor = fixture_user(role='admin')
    scope = PREPARE.scope().model_dump(mode='json')
    assert browser.discover({'scope': scope}, actor)['total'] == 1
    result = service.list({'snapshot_id': sealed[2]['index_id'], 'scope': scope,
        'filters': {'kinds': ['dataset']}, 'limit': 100}, actor)
    assert len(result['items']) == 1
    assert report['activation_sha256'] == digest
    assert service.resolver.authority.initial.data == raw
    assert private.read_bytes() == frozen_path.read_bytes() == raw
    assert control.read_bytes() == before


@pytest.mark.parametrize('encoding', ['indent', 'key_order', 'mixed_unicode', 'duplicate', 'trailing_space'])
def test_hash_pinned_but_noncanonical_activation_serializations_are_rejected(sealed, tmp_path, encoding):
    document = activation(sealed)
    raw = RENDERER.canonical(document)
    if encoding == 'indent':
        raw = (json.dumps(document, indent=1, sort_keys=True) + '\n').encode()
    elif encoding == 'key_order':
        raw = (json.dumps(dict(reversed(list(document.items()))), indent=2) + '\n').encode()
    elif encoding == 'mixed_unicode':
        raw = raw.replace(b'\\u5408', '合'.encode(), 1)
    elif encoding == 'duplicate':
        raw = raw.replace(b'{\n', b'{\n  "research_enabled": true,\n', 1)
    else:
        raw += b' '
    assert raw not in (RENDERER.canonical(document), _canonical(document))
    source, _ = publish_synthetic(sealed, tmp_path, raw)
    with pytest.raises(CatalogueHostConfigurationError):
        load_research(sealed, source)


def test_equivalent_unicode_document_cannot_replace_the_pinned_activation_bytes(sealed, tmp_path):
    document = activation(sealed)
    ascii_raw, utf8_raw = RENDERER.canonical(document), _canonical(document)
    source, _ = publish_synthetic(sealed, tmp_path, utf8_raw,
        expected_sha256=hashlib.sha256(ascii_raw).hexdigest())
    with pytest.raises(CatalogueHostConfigurationError):
        load_research(sealed, source)


def test_rendered_unicode_activation_still_requires_its_original_generation(sealed, tmp_path):
    raw = RENDERER.canonical(activation(sealed))
    source, path = publish_synthetic(sealed, tmp_path, raw)
    _, browser = load_research(sealed, source)
    path.write_bytes(raw)
    with pytest.raises(CatalogueServiceError):
        browser.discover({'scope': PREPARE.scope().model_dump(mode='json')}, fixture_user(role='admin'))
