"""T260040: request-local LLM model selection, timeouts and cancellation.

Deterministic concurrency tests: an ``asyncio.Barrier`` forces two requests to finish
routing before either starts generating, which is exactly the interleaving in which the
former shared ``llm.model = routed_model`` assignment leaked one request's model into
the other.
"""

import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest

from app.llm.base import LLMMessage, bind_model
from app.llm.ollama import OllamaLLMProvider
from app.models.message import Message
from app.models.user import User
from app.services import rag as rag_mod
from app.services import rag_stream as rag_stream_mod
from app.services.context_builder import ContextSource, RetrievalContext
from app.services.inference_governor import InferenceGovernor
from app.services.model_router import ModelRouter, RoutingDecisionResult
from app.services.rag import answer_with_rag
from app.services.rag_stream import answer_with_rag_stream

MESSAGES = [LLMMessage(role="user", content="q")]
BASE_MODEL = "base-model"


# ---------------------------------------------------------------------------
# Provider-level guarantees
# ---------------------------------------------------------------------------


def test_provider_is_immutable_and_with_model_is_request_local():
    shared = OllamaLLMProvider(base_url="http://llm.test", model=BASE_MODEL)

    with pytest.raises(dataclasses.FrozenInstanceError):
        shared.model = "other"  # type: ignore[misc]

    bound = shared.with_model("model-a")
    assert bound is not shared
    assert bound.model == "model-a"
    assert shared.model == BASE_MODEL
    # Every other setting is carried over unchanged.
    assert dataclasses.replace(bound, model=BASE_MODEL) == shared
    assert shared.with_model(BASE_MODEL) is shared
    assert shared.with_model(None) is shared


def test_bind_model_leaves_providers_without_model_selection_untouched():
    class Plain:
        model = "fixed"

    plain = Plain()
    assert bind_model(plain, "model-a") is plain  # type: ignore[arg-type]
    assert plain.model == "fixed"


def _patch_transport(monkeypatch, handler) -> list[dict]:
    """Route the provider's httpx clients through a MockTransport; return captured payloads."""
    captured: list[dict] = []
    real_client = httpx.AsyncClient

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return await handler(request)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(recording_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.llm.ollama.httpx.AsyncClient", client_factory)
    return captured


def _ndjson(*objects: dict) -> bytes:
    return b"".join(json.dumps(o).encode() + b"\n" for o in objects)


@pytest.mark.anyio
async def test_concurrent_provider_calls_send_their_own_model_and_options(monkeypatch):
    both_in_flight = asyncio.Barrier(2)

    async def handler(request: httpx.Request) -> httpx.Response:
        await both_in_flight.wait()
        body = json.loads(request.content)
        if body["stream"]:
            return httpx.Response(200, content=_ndjson(
                {"message": {"content": f"from {body['model']}"}, "done": False},
                {"message": {"content": ""}, "done": True, "prompt_eval_count": 3, "eval_count": 2},
            ))
        return httpx.Response(200, json={"message": {"content": f"from {body['model']}"}, "done": True})

    captured = _patch_transport(monkeypatch, handler)
    shared = OllamaLLMProvider(
        base_url="http://llm.test", model=BASE_MODEL, num_ctx=2048, num_predict=128, temperature=0.0, keep_alive="10m"
    )

    async def stream(model: str) -> str:
        return "".join([t async for t in shared.with_model(model).generate_stream(MESSAGES)])

    a, b = await asyncio.gather(shared.with_model("model-a").generate(MESSAGES), stream("model-b"))

    assert a == "from model-a"
    assert b == "from model-b"
    assert shared.model == BASE_MODEL
    assert sorted(p["model"] for p in captured) == ["model-a", "model-b"]
    for payload in captured:
        assert payload["options"] == {"num_ctx": 2048, "num_predict": 128, "temperature": 0.0}
        assert payload["keep_alive"] == "10m"
        assert payload["think"] is False


class _SlowLines(httpx.AsyncByteStream):
    def __init__(self, lines: list[bytes], delay: float) -> None:
        self.lines = lines
        self.delay = delay
        self.closed = asyncio.Event()

    async def __aiter__(self):
        for line in self.lines:
            await asyncio.sleep(self.delay)
            yield line

    async def aclose(self) -> None:
        self.closed.set()


@pytest.mark.anyio
async def test_stream_enforces_total_generation_deadline(monkeypatch):
    token = json.dumps({"message": {"content": "tok "}, "done": False}).encode() + b"\n"
    body = _SlowLines([token] * 50, delay=0.02)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=body)

    _patch_transport(monkeypatch, handler)
    provider = OllamaLLMProvider(base_url="http://llm.test", model=BASE_MODEL, total_timeout_seconds=0.1)

    received: list[str] = []
    with pytest.raises(httpx.ReadTimeout):
        async for tok in provider.generate_stream(MESSAGES):
            received.append(tok)
    assert 0 < len(received) < 50
    assert body.closed.is_set()


@pytest.mark.anyio
async def test_non_stream_total_deadline_maps_to_httpx_timeout(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"message": {"content": "late"}})

    _patch_transport(monkeypatch, handler)
    provider = OllamaLLMProvider(base_url="http://llm.test", model=BASE_MODEL, total_timeout_seconds=0.05)
    with pytest.raises(httpx.ReadTimeout):
        await provider.generate(MESSAGES)


@pytest.mark.anyio
async def test_stream_error_line_is_raised_not_swallowed(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson(
            {"message": {"content": "Partial"}, "done": False},
            {"error": "model runner has unexpectedly stopped"},
        ))

    _patch_transport(monkeypatch, handler)
    provider = OllamaLLMProvider(base_url="http://llm.test", model=BASE_MODEL)
    with pytest.raises(httpx.HTTPError):
        async for _ in provider.generate_stream(MESSAGES):
            pass


@pytest.mark.anyio
async def test_closing_stream_early_closes_upstream_response(monkeypatch):
    token = json.dumps({"message": {"content": "tok "}, "done": False}).encode() + b"\n"
    body = _SlowLines([token] * 100, delay=0.0)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=body)

    _patch_transport(monkeypatch, handler)
    provider = OllamaLLMProvider(base_url="http://llm.test", model=BASE_MODEL)

    gen = provider.generate_stream(MESSAGES)
    assert await gen.__anext__() == "tok "
    await gen.aclose()  # what Starlette does when the client disconnects
    assert body.closed.is_set()


# ---------------------------------------------------------------------------
# RAG-level isolation (streaming and non-streaming share the same routing)
# ---------------------------------------------------------------------------


class RecordingProvider:
    """Model-selectable fake provider that records the model each generation used.

    ``model`` is read at generation time, after both requests have passed the barrier,
    so a shared-state mutation would make both requests record the last routed model.
    """

    def __init__(self, model: str, log: list[tuple[str, str]], barrier: asyncio.Barrier) -> None:
        self.model = model
        self.log = log
        self.barrier = barrier

    def with_model(self, model: str) -> "RecordingProvider":
        return RecordingProvider(model, self.log, self.barrier)

    async def _answer(self, messages: list[LLMMessage]) -> str:
        await self.barrier.wait()
        tag = messages[-1].content.split("Current question:\n", 1)[1].split("\n", 1)[0]
        self.log.append((tag, self.model))
        return f"Answer generated by {self.model} [Source 1]."

    async def generate(self, messages: list[LLMMessage]) -> str:
        return await self._answer(messages)

    async def generate_stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        yield await self._answer(messages)


def _context() -> RetrievalContext:
    source = ContextSource(
        source_index=1,
        document_id=uuid4(),
        chunk_id=uuid4(),
        chunk_index=0,
        content="Evidence.",
        similarity=0.9,
        document_title="Doc",
        char_start=0,
        char_end=9,
    )
    return RetrievalContext(text="[Source 1]\nEvidence.", sources=[source])


@pytest.fixture
def isolated_rag(monkeypatch):
    """Patch retrieval, persistence and routing; route each workspace to its own model."""
    workspace_models: dict[UUID, str] = {}

    async def fake_retrieve(**kwargs):
        return _context()

    async def fake_select_model(self, session, task_type, workspace_id=None, **kwargs):
        await asyncio.sleep(0)  # yield so the other request can route in between
        return RoutingDecisionResult(
            selected_model=workspace_models[workspace_id],
            task_type=str(task_type),
            policy_id=None,
            policy_version="test",
            candidate_evaluations=[],
            selection_reason="per-workspace test policy",
            fallback_chain=[],
        )

    async def fake_persist(session, **kwargs):
        return Message(id=uuid4(), conversation_id=kwargs["conversation_id"], role=kwargs["role"], content=kwargs["content"])

    async def fake_save_sources(*args, **kwargs):
        return None

    governor = InferenceGovernor(max_concurrency=4, max_queue_size=4, queue_timeout_seconds=5)
    for mod in (rag_mod, rag_stream_mod):
        monkeypatch.setattr(mod, "retrieve_context", fake_retrieve)
    monkeypatch.setattr("app.services.inference_governor.get_inference_governor", lambda: governor)
    monkeypatch.setattr(rag_stream_mod, "get_inference_governor", lambda: governor)
    monkeypatch.setattr(ModelRouter, "select_model", fake_select_model)
    monkeypatch.setattr(rag_stream_mod, "create_workspace_conversation_message", fake_persist)
    monkeypatch.setattr(rag_stream_mod, "save_assistant_message_sources", fake_save_sources)
    return workspace_models


async def _run_stream(llm, *, workspace_id: UUID, query: str) -> dict:
    events = []
    async for chunk in answer_with_rag_stream(
        object(),  # type: ignore[arg-type] - any non-None session enables routing
        user=User(id=uuid4(), email=f"{uuid4().hex}@example.com"),
        conversation_id=uuid4(),
        workspace_id=workspace_id,
        query=query,
        llm=llm,
    ):
        events.append(json.loads(chunk.split("data: ", 1)[1]))
    return events[-1]


async def _run_ask(llm, *, workspace_id: UUID, query: str):
    return await answer_with_rag(
        object(),  # type: ignore[arg-type]
        user_id=uuid4(),
        workspace_id=workspace_id,
        query=query,
        llm=llm,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["stream+stream", "ask+ask", "stream+ask"])
async def test_concurrent_rag_requests_keep_their_own_routed_model(isolated_rag, kind):
    ws_a, ws_b = uuid4(), uuid4()
    isolated_rag[ws_a] = "model-a"
    isolated_rag[ws_b] = "model-b"
    log: list[tuple[str, str]] = []
    shared = RecordingProvider(BASE_MODEL, log, asyncio.Barrier(2))

    first, second = kind.split("+")
    runners = {"stream": _run_stream, "ask": _run_ask}
    result_a, result_b = await asyncio.gather(
        runners[first](shared, workspace_id=ws_a, query="question-from-A"),
        runners[second](shared, workspace_id=ws_b, query="question-from-B"),
    )

    assert sorted(log) == [("question-from-A", "model-a"), ("question-from-B", "model-b")]
    assert shared.model == BASE_MODEL

    def answer_and_model(result):
        if isinstance(result, dict):
            assert result["event"] == "answer_completed"
            return result["answer"], result["model_name"]
        return result.answer, result.model_name

    assert answer_and_model(result_a) == ("Answer generated by model-a [Source 1].", "model-a")
    assert answer_and_model(result_b) == ("Answer generated by model-b [Source 1].", "model-b")


@pytest.mark.anyio
async def test_routing_failure_falls_back_to_default_model_without_mutation(isolated_rag, monkeypatch):
    async def broken_select_model(self, *args, **kwargs):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(ModelRouter, "select_model", broken_select_model)
    log: list[tuple[str, str]] = []
    shared = RecordingProvider(BASE_MODEL, log, asyncio.Barrier(1))

    result = await _run_ask(shared, workspace_id=uuid4(), query="q")
    assert result.model_name == BASE_MODEL
    assert log == [("q", BASE_MODEL)]
