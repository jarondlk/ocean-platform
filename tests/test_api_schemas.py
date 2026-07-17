from api.main import _ollama_options
from api.schemas import ChatRequest, RetrieveRequest


def test_retrieve_request_accepts_top_k_alias():
    request = RetrieveRequest.model_validate(
        {"query": "temperature observations", "top_k": 2}
    )

    assert request.k == 2


def test_chat_request_exposes_expert_knobs():
    request = ChatRequest.model_validate(
        {
            "query": "temperature observations",
            "k": 12,
            "vector_weight": 0.8,
            "fts_weight": 0.2,
            "rrf_k": 30,
            "temperature": 0.25,
            "top_p": 0.7,
            "repeat_penalty": 1.2,
            "num_ctx": 16384,
            "num_predict": 512,
            "sampling_top_k": 40,
            "seed": 42,
            "inject_analysis": False,
        }
    )

    assert request.k == 12
    assert request.vector_weight == 0.8
    assert request.fts_weight == 0.2
    assert request.rrf_k == 30
    assert request.inject_analysis is False
    assert _ollama_options(request) == {
        "temperature": 0.25,
        "top_p": 0.7,
        "repeat_penalty": 1.2,
        "num_ctx": 16384,
        "num_predict": 512,
        "top_k": 40,
        "seed": 42,
    }
