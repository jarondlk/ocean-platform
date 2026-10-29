"""Matrix never converts omitted checks or local history into release acceptance."""
from pathlib import Path

import pytest

from evaluation.system_acceptance_matrix import BINDINGS, GATE_MEMBERS, build_matrix, master_requirements

SOURCE = 'sha256:' + 'a' * 64
MASTER = Path('docs/plans/ocean-v1/ACCEPTANCE_MAP.md').read_text()


def checks():
    values = {key: {'id': key, 'status': 'passed', 'sha256': 'b' * 64}
        for keys in BINDINGS.values() for key in keys}
    values['original-c23-physical-evidence']['source_revision'] = 'c' * 40
    values['catalogue-scale-lab-budget'] = {'id': 'catalogue-scale-lab-budget', 'status': 'passed', 'sha256': 'd' * 64}
    return values


def test_every_master_requirement_and_gate_is_accounted_without_release_authority():
    output = build_matrix(master_text=MASTER, source_revision=SOURCE, checks=checks())
    report = output['acceptance_report']
    assert {row['id'] for row in output['matrix']} == set(BINDINGS) | set(GATE_MEMBERS)
    assert report['preparation_complete'] is True
    assert report['release_status'] == 'not_run' and report['release_accepted'] is False
    assert all(row['full_operational_acceptance'] == 'not_run' for row in output['matrix'])


def test_missing_browser_or_measured_budget_failure_prevents_preparation_pass():
    values = checks()
    del values['browser-research']
    values['catalogue-scale-lab-budget']['status'] = 'failed'
    output = build_matrix(master_text=MASTER, source_revision=SOURCE, checks=values)
    report = output['acceptance_report']
    assert report['preparation_complete'] is False and report['preparation_status'] == 'failed'
    states = {row['requirement_id']: row['status'] for row in report['results']}
    assert states['G3.preparation'] == 'failed'
    assert states['R16.preparation'] == 'not_run'


def test_changed_master_definition_requires_explicit_binding():
    with pytest.raises(ValueError):
        master_requirements(MASTER.replace('| R33 |', '| R34 |'))
    with pytest.raises(ValueError):
        master_requirements(MASTER.replace('| G9 —', '| G10 —'))


def test_unrecognized_external_observation_status_cannot_pass():
    values = checks()
    values['browser-research']['status'] = 'unverified'
    with pytest.raises(ValueError, match='Unknown acceptance observation status'):
        build_matrix(master_text=MASTER, source_revision=SOURCE, checks=values)
