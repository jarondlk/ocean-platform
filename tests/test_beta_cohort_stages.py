"""Explicit deployment stages must not silently activate or inspect held eDNA."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from deploy.gcp.beta.data import prepare_cohorts as preparation
from deploy.gcp.beta.data import prepare_metagenome as meta, prepare_sst as sst, prepare_edna as edna


def arguments():
    return {'raw_package':Path('/private/tmp/synthetic-raw-cohort'),
        'sst_publication':Path('/private/tmp/synthetic-regional-sst'),
        'edna_metadata':Path('/private/tmp/held-edna-metadata'),
        'edna_normalized':Path('/private/tmp/held-edna-normalized')}


def synthetic_dependencies(monkeypatch):
    calls = []
    def metagenome_bytes(path, root):
        calls.append(('meta-source', path, root))
        return {'synthetic':True}, {'synthetic-provenance':True}
    def planned_metagenome(inputs):
        assert inputs == {'synthetic':True}
        calls.append(('meta-normalize',))
        return {'dataset':'synthetic-meta-dataset', 'frames':'synthetic-meta-frames',
            'captured':'synthetic-meta-captured'}
    def sst_bytes(path):
        calls.append(('sst-source',path))
        return b'synthetic-sst-source'
    def regional_dataset(data):
        assert data == b'synthetic-sst-source'
        calls.append(('sst-normalize',))
        return ('synthetic-sst-dataset','synthetic-sst-frames','synthetic-sst-captured')
    monkeypatch.setattr(meta,'verified_metagenome_bytes',metagenome_bytes)
    monkeypatch.setattr(meta,'planned_metagenome',planned_metagenome)
    monkeypatch.setattr(sst,'verified_publication_bytes',sst_bytes)
    monkeypatch.setattr(sst,'regional_dataset',regional_dataset)
    return calls


def test_meta_sst_excludes_edna_without_touching_its_metadata_or_payloads(monkeypatch):
    calls = synthetic_dependencies(monkeypatch)
    def held_edna_must_not_be_read(*args,**kwargs):
        pytest.fail('Held eDNA source was accessed by the meta-sst stage')
    monkeypatch.setattr(edna,'verified_bundles',held_edna_must_not_be_read)
    monkeypatch.setattr(edna,'normalized_datasets',held_edna_must_not_be_read)
    groups = preparation.qualified_groups(cohort_set='meta-sst',**arguments())
    triples = [triple for group in groups for triple in group['datasets']]
    assert [triple[0] for triple in triples] == ['synthetic-meta-dataset','synthetic-sst-dataset']
    assert [call[0] for call in calls] == ['meta-source','meta-normalize','sst-source','sst-normalize']
    assert tuple(groups[0]['qualifications']) == meta.QUALIFICATIONS
    assert tuple(groups[1]['qualifications']) == sst.QUALIFICATIONS


def test_all_qualified_includes_every_explicit_edna_bundle_without_silently_dropping_one(monkeypatch):
    calls = synthetic_dependencies(monkeypatch)
    def source_bundles(metadata, normalized):
        calls.append(('edna-source', metadata, normalized))
        yield {'synthetic-bundle':1}
        yield {'synthetic-bundle':2}
    def normalized_datasets(bundle):
        identity = bundle['synthetic-bundle']
        calls.append(('edna-normalize',identity))
        return [(f'synthetic-edna-{identity}',f'synthetic-frames-{identity}',f'synthetic-captured-{identity}')]
    monkeypatch.setattr(edna,'verified_bundles',source_bundles)
    monkeypatch.setattr(edna,'normalized_datasets',normalized_datasets)
    groups = preparation.qualified_groups(cohort_set='all-qualified',**arguments())
    triples = [triple for group in groups for triple in group['datasets']]
    assert [triple[0] for triple in triples] == ['synthetic-meta-dataset','synthetic-sst-dataset','synthetic-edna-1','synthetic-edna-2']
    assert tuple(groups[-1]['qualifications']) == edna.QUALIFICATIONS
    assert [call[0] for call in calls].count('edna-source') == 1
    assert [call for call in calls if call[0]=='edna-normalize'] == [('edna-normalize',1),('edna-normalize',2)]


@pytest.mark.parametrize('stage',[None,'','all','unknown','META-SST',' meta-sst',True,[],{}])
def test_unsupported_stage_refuses_before_source_validation_data_or_output_io(monkeypatch,stage):
    def forbidden(*args,**kwargs):
        pytest.fail('Invalid stage triggered source/data/output IO')
    monkeypatch.setattr(preparation,'source_pins',forbidden)
    monkeypatch.setattr(preparation,'qualified_groups',forbidden)
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    monkeypatch.setattr(Path,'mkdir',forbidden)
    monkeypatch.setattr(Path,'exists',forbidden)
    with pytest.raises(ValueError,match='Explicit supported cohort set'):
        preparation.prepare(cohort_set=stage,revision='not-selected',output=Path('/private/tmp/no-output'),
            base_catalogue=Path('/private/tmp/no-base'),**arguments())


def test_stage_argument_has_no_default_at_python_boundary():
    with pytest.raises(TypeError,match='cohort_set'):
        preparation.prepare(revision='not-selected',output=Path('/private/tmp/no-output'),
            base_catalogue=Path('/private/tmp/no-base'),**arguments())
    with pytest.raises(TypeError,match='cohort_set'):
        preparation.qualified_groups(**arguments())


def test_receipt_identifies_selected_stage_and_explicit_latency_deferral():
    selected = preparation.cohort_receipt('meta-sst')
    assert selected['cohort_set'] == 'meta-sst'
    assert set(selected['deferred_families']) == {'edna_metabarcoding'}
    reason = selected['deferred_families']['edna_metabarcoding']
    assert '15.076610' in reason and '15second' in reason and 'cloud latency remains unaccepted' in reason
    assert 'data are unchanged' in reason
    all_qualified = preparation.cohort_receipt('all-qualified')
    assert all_qualified == {'cohort_set':'all-qualified','deferred_families':{}}


def cli_arguments():
    return ['prepare_cohorts.py','--revision','0'*40,'--output','/private/tmp/no-output',
        '--base-catalogue','/private/tmp/no-base','--raw-package','/private/tmp/no-raw',
        '--sst-publication','/private/tmp/no-sst','--edna-metadata','/private/tmp/no-edna-metadata',
        '--edna-normalized','/private/tmp/no-edna-normalized','--prepare']


@pytest.mark.parametrize('extra',[[],['--cohort-set','unknown']])
def test_cli_requires_exact_stage_before_preparation_is_called(monkeypatch,extra):
    def forbidden(**kwargs):
        pytest.fail('Invalid CLI stage reached scientific preparation')
    monkeypatch.setattr(preparation,'prepare',forbidden)
    monkeypatch.setattr(sys,'argv',cli_arguments()+extra)
    with pytest.raises(SystemExit) as exc:
        preparation.main()
    assert exc.value.code == 2


def test_cli_passes_explicit_stage_and_reports_deferral_without_private_group_payloads(monkeypatch,capsys):
    observed = {}
    def selected(**kwargs):
        observed.update(kwargs)
        return {**preparation.cohort_receipt(kwargs['cohort_set']),
            'state':'synthetic-no-IO','new_groups':[{'private-payload':'must-not-print'}]}
    monkeypatch.setattr(preparation,'prepare',selected)
    monkeypatch.setattr(sys,'argv',cli_arguments()+['--cohort-set','meta-sst'])
    assert preparation.main() == 0
    output = capsys.readouterr().out
    assert observed['cohort_set']=='meta-sst'
    assert json.loads(output)['deferred_families']['edna_metabarcoding']
    assert 'new_groups' not in output and 'must-not-print' not in output
