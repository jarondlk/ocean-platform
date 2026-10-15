"""Read-only C06 baseline probes; synthetic payloads, no provider or DB access."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


def main():
    import config
    import model_runtime
    import api.main as api_main
    from api.auth import CurrentUser, permissions_for_role
    from api.schemas import ChatRequest
    from tests.test_chat_source_scope import scope

    cases = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def probe_ollama(method, reason):
        content = '{"status":"ready"}' if method == 'structured_chat' else 'Synthetic partial answer'
        payload = {'message': {'content': content}, 'done': True}
        if reason is not None:
            payload['done_reason'] = reason
        with patch.object(model_runtime.requests, 'post', return_value=Response(payload)) as request:
            runtime = model_runtime.OllamaRuntime('http://synthetic.invalid')
            kwargs = {'model': 'synthetic-model', 'prompt': 'synthetic'}
            if method == 'structured_chat':
                kwargs.update(schema={'type': 'object'}, max_output_tokens=8, timeout=1)
            try:
                value = getattr(runtime, method)(**kwargs)
                result = {'returned': value, 'error': None}
            except ValueError as exc:
                result = {'returned': None, 'error': type(exc).__name__}
            cases.append({'provider': 'ollama', 'method': method, 'finish_reason': reason,
                          'calls': request.call_count, **result})

    def probe_vertex(method, reason):
        content = '{"status":"ready"}' if method == 'structured_chat' else 'Synthetic partial answer'
        response = SimpleNamespace(text=content, candidates=[SimpleNamespace(finish_reason=reason)],
                                   usage_metadata=None)
        calls = []

        def generate(**kwargs):
            calls.append(kwargs)
            return response

        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        runtime = model_runtime.VertexRuntime(project='synthetic-project', location='global',
                                             embedding_dim=2, client=client)
        kwargs = {'model': 'synthetic-model', 'prompt': 'synthetic'}
        if method == 'structured_chat':
            kwargs.update(schema={'type': 'object'}, max_output_tokens=8, timeout=1)
        try:
            value = getattr(runtime, method)(**kwargs)
            result = {'returned': value, 'error': None}
        except ValueError as exc:
            result = {'returned': None, 'error': type(exc).__name__}
        cases.append({'provider': 'vertex', 'method': method, 'finish_reason': reason,
                      'calls': len(calls), **result})

    for method in ('chat', 'structured_chat'):
        for reason in ('stop', 'length', None, 'unknown-synthetic-reason'):
            probe_ollama(method, reason)
        for reason in ('STOP', 'MAX_TOKENS', None, 'unknown-synthetic-reason'):
            probe_vertex(method, reason)

    # Invoke the actual API handler with a real Ollama adapter and a synthetic
    # length-stopped HTTP payload; stub all retrieval and persistence boundaries.
    completed = []
    persisted = []
    user = CurrentUser(id=None, email='synthetic@example.invalid', display_name='Synthetic',
                       role='researcher', auth_provider='synthetic', account_type='research',
                       status='active', permissions=permissions_for_role('researcher'))
    with ExitStack() as patches:
        patches.enter_context(patch.object(model_runtime.requests, 'post', return_value=Response({
            'message': {'content': 'Synthetic CTD answer cut mid-sentence'},
            'done': True, 'done_reason': 'length', 'eval_count': 8,
        })))
        patches.enter_context(patch.object(api_main, 'get_model_runtime',
                                          lambda: model_runtime.OllamaRuntime('http://synthetic.invalid')))
        patches.enter_context(patch.object(api_main, 'retrieve_with_expansion', return_value={
            'primary': [{'doc_id': 'c06-synthetic-ctd', 'source_type': 'ctd',
                         'text': 'Synthetic CTD salinity: 34 PSU', 'title': 'Synthetic CTD'}],
            'linked': [],
        }))
        patches.enter_context(patch.object(api_main, 'create_chat_interaction', return_value=None))
        patches.enter_context(patch.object(api_main, 'record_chat_options', side_effect=lambda **kw: persisted.append('options')))
        patches.enter_context(patch.object(api_main, 'record_chat_context', side_effect=lambda **kw: persisted.append('context')))
        patches.enter_context(patch.object(api_main, 'complete_chat_interaction', side_effect=lambda **kw: completed.append(kw)))
        patches.enter_context(patch.object(config, 'PERSIST_LOCAL_CHAT', False))
        answer = api_main.chat(ChatRequest(query='Describe the CTD salinity evidence',
                                          settings_mode='manual', evidence_scope=scope('ctd'),
                                          run_answer_audit=False), user=user)
    assert answer.outcome == 'answered' and completed[0]['outcome'] == 'answered'
    assert answer.answer == 'Synthetic CTD answer cut mid-sentence'
    ordinary_length = next(item for item in cases if item['provider'] == 'ollama'
                           and item['method'] == 'chat' and item['finish_reason'] == 'length')
    assert ordinary_length['returned'] and ordinary_length['error'] is None
    assert all(item['calls'] == 1 for item in cases)
    report = {
        'mode': 'read-only synthetic mocked-provider and stubbed API baseline probes',
        'provider_calls': False, 'database_calls': False, 'application_source_changes': False,
        'cases': cases,
        'F07_reproduced': True,
        'api_length_stop': {'outcome': answer.outcome, 'answer': answer.answer,
                            'completed_receipt_outcome': completed[0]['outcome'],
                            'stubbed_persistence_boundaries': persisted},
        'contract_gaps': ['ordinary Ollama length stop accepted as completed text and API answer',
                          'missing termination metadata accepted by both adapters and both methods',
                          'unknown Ollama finish accepted by both methods',
                          'common result, measured generation duration and optional usage absent'],
        'existing_safety': ['Ollama structured length rejects',
                            'Vertex ordinary MAX_TOKENS raises ModelOutputLimitError',
                            'Vertex structured MAX_TOKENS rejects',
                            'Vertex unknown finish rejects'],
    }
    (Path(__file__).resolve().parent / 'readiness-probes.json').write_text(json.dumps(report, indent=2) + '\n')
    print('F07 reproduced at actual Ollama adapter and API completed-answer boundary; 16 payload probes used no provider or DB.')


if __name__ == '__main__':
    main()
