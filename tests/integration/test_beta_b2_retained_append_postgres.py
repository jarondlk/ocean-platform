"""Actual C21 readback after unrelated seals; only a disposable PostgreSQL DB."""
import pytest
from sqlalchemy import text

from ingestion.scientific_catalogue_inputs import load_registry
from orchestration.catalogue_registration import register_scientific_snapshot
from orchestration.research_evidence import ResearchEvidenceError
from schema.scientific_catalogue_fixtures import seal_scientific_fixture
from tests.integration.test_research_evidence_postgres import (
    actual as actual, completed, disposable_database as disposable_database,
    isolated as isolated, pytestmark as pytestmark,
)


@pytest.mark.parametrize('change', ['append_only', 'policy', 'revoke', 'unreference'])
def test_retained_receipt_survives_an_unrelated_index_only_under_current_authority(actual, change):
    fixture, evidence = actual
    run = completed(fixture)
    receipt = evidence.ensure_retained(run['id'], 1, fixture.user).receipts[0]
    with fixture.retained.factory() as session:
        before = session.scalar(text('SELECT row_to_json(r)::text FROM research_run r WHERE id=:id'), {'id': run['id']})
    store, original = fixture.retained.store, receipt.binding.snapshot_id
    registry = load_registry(*store.read(original))
    new = seal_scientific_fixture(store, registry.metadata, registry.tables,
        publication='b2-unrelated-new-immutable-index')
    register_scientific_snapshot(store=store, snapshot_id=new,
        registration_id='synthetic:b2-unrelated-new-index')
    if change == 'policy':
        fixture.retained.policy[original].add('synthetic:changed-current-policy')
    elif change == 'revoke':
        store.revoke(original)
    elif change == 'unreference':
        reference, identity = fixture.retained.registrations[original].references[-1]
        store.remove_reference(identity, reference)
    payload = {'receipt_id': receipt.id, 'expected_sha256': receipt.sha256}
    if change == 'append_only':
        result = evidence.invoke('open', payload, fixture.user)
        assert result['receipt']['id'] == receipt.id
        assert result['receipt']['sha256'] == receipt.sha256
        listing = evidence.invoke('list', {**fixture.address(run), 'input_version': 1}, fixture.user)
        assert listing['total'] == 1 and listing['items'][0]['sha256'] == receipt.sha256
    else:
        with pytest.raises(ResearchEvidenceError):
            evidence.invoke('open', payload, fixture.user)
    with fixture.retained.factory() as session:
        assert session.scalar(text('SELECT row_to_json(r)::text FROM research_run r WHERE id=:id'), {'id': run['id']}) == before
