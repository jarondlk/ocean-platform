import pytest
from pydantic import ValidationError

from api.main import _ollama_options
from api.schemas import ChatRequest, RetrieveRequest


def test_retrieve_request_accepts_top_k_alias():
    request = RetrieveRequest.model_validate(
        {"query": "temperature observations", "top_k": 2}
    )

    assert request.k == 2


def test_retrieve_request_normalizes_weights_and_rejects_disabled_backends():
    request = RetrieveRequest.model_validate(
        {"query": "temperature observations", "vector_weight": 0.2, "fts_weight": 0.2}
    )
    assert request.vector_weight == 0.5
    assert request.fts_weight == 0.5

    with pytest.raises(ValidationError, match="weight must be greater than zero"):
        RetrieveRequest.model_validate(
            {"query": "temperature observations", "vector_weight": 0, "fts_weight": 0}
        )


def test_chat_request_exposes_expert_knobs():
    request = ChatRequest.model_validate(
        {
            "query": "temperature observations",
            "k": 12,
            "vector_weight": 0.8,
            "fts_weight": 0.2,
            "rrf_k": 30,
            "expand_evidence": False,
            "max_linked_sources": 12,
            "temperature": 0.25,
            "top_p": 0.7,
            "repeat_penalty": 1.2,
            "num_ctx": 16384,
            "num_predict": 512,
            "sampling_top_k": 40,
            "seed": 42,
            "inject_analysis": False,
            "run_answer_audit": False,
        }
    )

    assert request.k == 12
    assert request.vector_weight == 0.8
    assert request.fts_weight == 0.2
    assert request.rrf_k == 30
    assert request.expand_evidence is False
    assert request.max_linked_sources == 12
    assert request.inject_analysis is False
    assert request.run_answer_audit is False
    assert _ollama_options(request) == {
        "temperature": 0.25,
        "top_p": 0.7,
        "repeat_penalty": 1.2,
        "num_ctx": 16384,
        "num_predict": 512,
        "top_k": 40,
        "seed": 42,
    }


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RetrieveRequest(query="q" * 4001),
        lambda: ChatRequest(query="valid", model="m" * 256),
    ],
)
def test_security_sensitive_request_strings_are_bounded(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize(('requested', 'effective'), [(None, 1600), (4096, 1600), (32, 32)])
def test_vertex_options_report_effective_output_limit(monkeypatch, requested, effective):
    import config
    monkeypatch.setattr(config, 'MODEL_PROVIDER', 'vertex')
    monkeypatch.setattr(config, 'CHAT_MAX_OUTPUT_TOKENS', 1600)
    request = ChatRequest(query='edna samples', num_predict=requested)
    assert _ollama_options(request)['num_predict'] == effective


@pytest.mark.parametrize('available', [True, False])
def test_model_discovery_exposes_server_limit_even_when_provider_unavailable(monkeypatch, available):
    from types import SimpleNamespace
    import api.main as api_main
    import config
    monkeypatch.setattr(config, 'MODEL_PROVIDER', 'vertex')
    monkeypatch.setattr(config, 'CHAT_MAX_OUTPUT_TOKENS', 1600)

    def list_models(**kwargs):
        if not available:
            raise ConnectionError('unavailable')
        return [{'name': config.CHAT_MODEL}]

    monkeypatch.setattr(api_main, 'get_model_runtime', lambda: SimpleNamespace(list_models=list_models, provider='vertex', endpoint='vertex://project/global'))
    payload = api_main.models()
    assert payload.available == available
    assert payload.max_output_tokens == 1600
