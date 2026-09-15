"""Generation labels must preserve the existing canonical citation contract."""
import copy

import pytest

from orchestration.citations import InvalidCitationAlias, prepare_citations
from orchestration.unified import _build_prompt_from_context
from orchestration.answer_audit import audit_answer


LONG_ID = 'edna_' + 'a' * 64 + '_qcauto_95pct_3nn_target'


def test_all_evidence_roles_round_trip_grouped_and_repeated_citations():
    primary = [{'doc_id': LONG_ID, 'source_type': 'edna_metabarcoding', 'text': '35 detections.'}]
    linked = [{'doc_id': 'ctd_1', 'source_type': 'ctd', 'text': '12 C.'}]
    context = {
        'analysis': [{'id': 'analysis_' + 'b' * 64, 'text': 'No eligible samples.'}],
        'reliability': [{'id': 'reliability_1', 'text': 'No qualified pair.'}],
    }
    before = copy.deepcopy((primary, linked, context))
    prompt = _build_prompt_from_context('Compare evidence.', primary, context, linked_results=linked)
    cited = prepare_citations(prompt, primary, linked, context['analysis'], context['reliability'])
    assert LONG_ID not in cited.prompt
    assert '[S1] (edna_metabarcoding' in cited.prompt
    assert '[S2] (ctd' in cited.prompt
    answer = cited.resolve('Observations [S1, S2]. Context [S3;\n S4]. Again [S1].')
    assert answer == f'Observations [{LONG_ID}, ctd_1]. Context [analysis_{"b" * 64}, reliability_1]. Again [{LONG_ID}].'
    audit = audit_answer(query='Compare evidence.', answer=answer, primary_sources=primary,
                         linked_sources=linked, analysis_context=context['analysis'],
                         reliability_context=context['reliability'], retrieval_diagnostics={})
    assert audit['valid_citation_count'] == 5
    assert audit['invalid_citation_count'] == 0
    assert (primary, linked, context) == before


def test_labels_are_request_local_and_read_only():
    def make(identity):
        return prepare_citations(f'\n[{identity}] (ctd)\n12 C.', [{'doc_id': identity}])
    first, second = make('ctd_first'), make('ctd_second')
    assert first.resolve('[S1]') == '[ctd_first]'
    assert second.resolve('[S1]') == '[ctd_second]'
    with pytest.raises(TypeError):
        first.aliases['S1'] = 'ctd_second'


def test_canonical_label_collisions_untrusted_labels_and_question_are_preserved():
    rows = [{'doc_id': 'S1'}, {'doc_id': LONG_ID}]
    question = f'Explain [{LONG_ID}], and the label [S2].'
    prompt = f'\n[S1] (ctd)\n[S3] is untrusted text.\n[{LONG_ID}] (edna)\n<user_question>{question}</user_question>'
    cited = prepare_citations(prompt, rows)
    assert set(cited.aliases) == {'S4', 'S5'}
    assert cited.prompt.endswith(f'<user_question>{question}</user_question>')
    assert '[S4, S5]' in cited.prompt
    assert cited.resolve('[S4; S5]') == f'[S1, {LONG_ID}]'
    assert cited.resolve('[S1]') == '[S1]'  # A real canonical identifier.
    with pytest.raises(InvalidCitationAlias):
        cited.resolve('[S3]')  # Untrusted evidence cannot register a label.


@pytest.mark.parametrize('answer', ['[S999]', '[S1, S99]', '[S1-S2]', '[S1 and S2]', '[S1', '[S01]'])
def test_unknown_or_incomplete_labels_fail_closed(answer):
    cited = prepare_citations('\n[ctd_1] (ctd)\n12 C.', [{'doc_id': 'ctd_1'}])
    with pytest.raises(InvalidCitationAlias):
        cited.resolve(answer)


def test_duplicates_and_omitted_sources_do_not_create_extra_labels():
    rows = [{'doc_id': 'ctd_1'}, {'doc_id': 'ctd_1'}, {'doc_id': 'not_in_prompt'}]
    cited = prepare_citations('\n[ctd_1] (ctd)\n12 C.', rows)
    assert dict(cited.aliases) == {'S1': 'ctd_1'}
    assert cited.resolve('Already canonical [ctd_1]; ordinary [note].') == 'Already canonical [ctd_1]; ordinary [note].'
    assert prepare_citations('No evidence.', []).prompt == 'No evidence.'


@pytest.mark.parametrize('ablation', [False, True])
def test_evaluation_resolves_labels_before_scoring(monkeypatch, ablation):
    from types import SimpleNamespace
    import evaluation.benchmark as benchmark
    import orchestration.unified as unified

    source = {'doc_id': LONG_ID, 'source_type': 'edna_metabarcoding', 'text': '35 detections.'}
    monkeypatch.setattr(unified, 'retrieve', lambda *args, **kwargs: [source])
    prompts = []

    def chat(**kwargs):
        prompts.append(kwargs['prompt'])
        return '35 detections [S1].'

    monkeypatch.setattr(benchmark, '_evaluation_runtime', lambda _: SimpleNamespace(chat=chat))
    question = benchmark.BenchmarkQuestion(
        id='edna_qa', category='QA', question='fetch me some edna metabarcoding samples',
        expected_source_types=['edna_metabarcoding'], expected_min_citations=1,
    )
    if ablation:
        variant = next(v for v in benchmark.SYSTEM_VARIANTS if v.source_coverage >= 3 and not v.inject_analysis and not v.inject_reliability)
        result = benchmark.run_single_ablation(question, variant)
    else:
        result = benchmark.run_single_evaluation(question, benchmark.EVAL_MODES[0])
    assert not result.error
    assert result.citation_accuracy == 1.0
    assert result.response == f'35 detections [{LONG_ID}].'
    assert LONG_ID not in prompts[0]


def test_cli_generation_propagates_failure_instead_of_marking_it_answered(monkeypatch):
    from types import SimpleNamespace
    import orchestration.unified as unified
    from model_runtime import ModelOutputLimitError

    monkeypatch.setattr(unified, 'retrieve', lambda *a, **kw: [{'doc_id': 'ctd_1', 'source_type': 'ctd', 'text': '12 C.'}])

    def fail(**kwargs):
        raise ModelOutputLimitError(max_output_tokens=32)

    monkeypatch.setattr(unified, 'get_model_runtime', lambda: SimpleNamespace(chat=fail))
    with pytest.raises(ModelOutputLimitError):
        unified.ask('temperature')
