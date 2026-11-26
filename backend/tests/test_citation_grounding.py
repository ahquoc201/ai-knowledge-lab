"""Tests for Citation Grounding & Answer Verification (T260041)."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.citation_grounding import (
    GroundingStatus,
    verify_answer_grounding,
)
from app.services.context_builder import ContextSource, RetrievalContext
from app.services.rag import answer_with_rag
from app.services.rag_prompt import INSUFFICIENT_CONTEXT_ANSWER
from app.services.rag_stream import UNVERIFIED_CITATION_ANSWER, answer_with_rag_stream
from tests.fakes import FakeLLMProvider

SOURCE_1_TEXT = (
    "# Sổ tay nhân sự Lumora 2026\n"
    "## 2. Nghỉ phép năm\n"
    "Nhân viên chính thức được hưởng 18 ngày nghỉ phép có lương mỗi năm. "
    "Số ngày phép chưa dùng hết phải sử dụng trước ngày 31 tháng 3."
)

SOURCE_2_TEXT = (
    "## 3. Làm việc từ xa\n"
    "Nhân viên được làm việc từ xa tối đa 2 ngày mỗi tuần. "
    "## 4. Lương và phúc lợi\n"
    "Mỗi nhân viên chính thức nhận phụ cấp ăn trưa 1.200.000 đồng mỗi tháng. "
    "## 5. Thiết bị làm việc\n"
    "Khi mất thiết bị, báo cho IT trong vòng 24 giờ qua kênh #it-helpdesk."
)


def _make_sources() -> list[ContextSource]:
    doc_id = uuid4()
    return [
        ContextSource(
            source_index=1,
            document_id=doc_id,
            chunk_id=uuid4(),
            chunk_index=0,
            content=SOURCE_1_TEXT,
            similarity=0.91,
            document_title="lumora_hr_handbook.md",
        ),
        ContextSource(
            source_index=2,
            document_id=doc_id,
            chunk_id=uuid4(),
            chunk_index=1,
            content=SOURCE_2_TEXT,
            similarity=0.88,
            document_title="lumora_hr_handbook.md",
        ),
    ]


# 1. Correct answer with correct citation
def test_grounding_case_01_correct_answer_correct_citation():
    sources = _make_sources()
    answer = "Nhân viên chính thức được hưởng 18 ngày nghỉ phép có lương mỗi năm. [Source 1]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.VERIFIED
    assert res.is_grounded is True
    assert res.unsupported_claims == ()
    assert res.latency_ms < 50.0


# 2. Correct answer with wrong citation (T260040 q01 regression)
def test_grounding_case_02_q01_wrong_citation_detected():
    sources = _make_sources()
    answer = "Nhân viên chính thức của Lumora được hưởng 18 ngày nghỉ phép có lương mỗi năm. [Source 2]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.UNSUPPORTED
    assert res.is_grounded is False
    assert len(res.unsupported_claims) == 1
    assert "num:18_ngày" in res.unsupported_claims[0].missing_anchors


# 3. Existing but unrelated source
def test_grounding_case_03_existing_unrelated_source():
    sources = _make_sources()
    answer = "Khi mất thiết bị, nhân viên báo qua kênh #it-helpdesk. [Source 1]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.UNSUPPORTED
    assert res.is_grounded is False
    assert "id:#it-helpdesk" in res.unsupported_claims[0].missing_anchors


# 4. Nonexistent source number
def test_grounding_case_04_nonexistent_source_index():
    sources = _make_sources()
    answer = "Nhân viên được hưởng 18 ngày nghỉ phép. [Source 9]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.UNSUPPORTED
    assert res.is_grounded is False
    assert "source_index:9" in res.unsupported_claims[0].missing_anchors


# 5. Correct numeric fact with incorrect unit
def test_grounding_case_05_numeric_fact_incorrect_unit():
    sources = _make_sources()
    answer = "Nhân viên chính thức được hưởng 18 giờ nghỉ phép mỗi năm. [Source 1]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.UNSUPPORTED
    assert res.is_grounded is False
    assert any("unit_mismatch" in a for a in res.unsupported_claims[0].missing_anchors)


# 6. Paraphrased evidence without numeric/code anchors -> INCONCLUSIVE (not rejected)
def test_grounding_case_06_paraphrase_marked_inconclusive_not_rejected():
    sources = _make_sources()
    answer = "Chính sách công ty quy định rõ quyền lợi nghỉ ngơi hằng năm cho nhân sự. [Source 1]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.INCONCLUSIVE
    assert res.is_grounded is True
    assert res.unsupported_claims == ()


# 7. Multiple valid source citations in one claim
def test_grounding_case_07_multiple_valid_citations_supported():
    sources = _make_sources()
    answer = (
        "Nhân viên được hưởng 18 ngày nghỉ phép [Source 1] "
        "và phụ cấp ăn trưa 1.200.000 đồng mỗi tháng [Source 2]."
    )
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.VERIFIED
    assert res.is_grounded is True


# 8. Contradictory source number
def test_grounding_case_08_contradictory_numeric_fact():
    sources = _make_sources()
    answer = "Nhân viên chính thức chỉ được hưởng 12 ngày nghỉ phép mỗi năm. [Source 1]"
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.UNSUPPORTED
    assert res.is_grounded is False
    assert "num:12_ngày" in res.unsupported_claims[0].missing_anchors


# 9. Date normalization (31/3 matches 31 tháng 3) & shorthand currency (1,2 triệu matches 1.200.000)
def test_grounding_date_and_currency_normalization():
    sources = _make_sources()
    answer = (
        "Phép chuyển sang năm sau phải dùng trước 31/3 [Source 1]. "
        "Phụ cấp ăn trưa là 1,2 triệu đồng mỗi tháng [Source 2]."
    )
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.VERIFIED
    assert res.is_grounded is True


# 10. Repeated citations
def test_grounding_case_11_repeated_citations():
    sources = _make_sources()
    answer = (
        "Nhân viên được hưởng 18 ngày phép mỗi năm [Source 1]. "
        "Phép dư phải dùng trước 31 tháng 3 [Source 1]."
    )
    res = verify_answer_grounding(answer, sources)
    assert res.status == GroundingStatus.VERIFIED
    assert res.is_grounded is True
    assert len(res.claims) == 2


# 11. Non-streaming RAG enforces grounding on q01 & preserves insufficient evidence
@pytest.mark.anyio
async def test_rag_non_streaming_rejects_q01_wrong_citation(monkeypatch):
    import app.services.rag as rag_mod

    sources = _make_sources()

    async def fake_retrieve(*args, **kwargs):
        return RetrievalContext(
            text=f"[Source 1]\n{SOURCE_1_TEXT}\n\n[Source 2]\n{SOURCE_2_TEXT}",
            sources=sources,
            retrieval_mode="dense",
        )

    monkeypatch.setattr(rag_mod, "retrieve_context", fake_retrieve)

    # q01 wrong citation: fact is in Source 1, LLM cites Source 2
    wrong_llm = FakeLLMProvider(
        response="Nhân viên chính thức của Lumora được hưởng 18 ngày nghỉ phép có lương mỗi năm. [Source 2]"
    )
    res_wrong = await answer_with_rag(
        session=MagicMock(),
        workspace_id=uuid4(),
        query="Nhân viên chính thức Lumora được hưởng bao nhiêu ngày nghỉ phép mỗi năm?",
        llm=wrong_llm,
    )
    assert res_wrong.answer == UNVERIFIED_CITATION_ANSWER
    assert res_wrong.sources == []
    assert res_wrong.grounding_status == "unsupported"

    # Insufficient evidence refusal remains untouched
    refusal_llm = FakeLLMProvider(response=INSUFFICIENT_CONTEXT_ANSWER)
    res_refusal = await answer_with_rag(
        session=MagicMock(),
        workspace_id=uuid4(),
        query="Chính sách giữ xe?",
        llm=refusal_llm,
    )
    assert res_refusal.answer == INSUFFICIENT_CONTEXT_ANSWER
    assert res_refusal.sources == []


# 12. Streaming RAG explicit post-generation verification policy
@pytest.mark.anyio
async def test_rag_streaming_detects_q01_and_signals_unsupported_in_answer_completed(monkeypatch):
    import app.services.rag_stream as stream_mod

    sources = _make_sources()

    async def fake_retrieve(*args, **kwargs):
        return RetrievalContext(
            text=f"[Source 1]\n{SOURCE_1_TEXT}\n\n[Source 2]\n{SOURCE_2_TEXT}",
            sources=sources,
            retrieval_mode="dense",
        )

    persisted_contents: list[str] = []

    async def fake_persist(*args, content: str, **kwargs):
        persisted_contents.append(content)
        return MagicMock(id=uuid4())

    async def fake_save_sources(*args, **kwargs):
        return None

    monkeypatch.setattr(stream_mod, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(stream_mod, "_persist_assistant_message", fake_persist)
    monkeypatch.setattr(stream_mod, "save_assistant_message_sources", fake_save_sources)

    wrong_stream_llm = FakeLLMProvider(
        stream_chunks=["Nhân viên chính thức được hưởng 18 ngày nghỉ phép mỗi năm. ", "[Source 2]"]
    )
    user = User(id=uuid4(), email="u@test.local")

    events: list[str] = []
    async for ev in answer_with_rag_stream(
        session=None,  # type: ignore[arg-type]
        user=user,
        conversation_id=uuid4(),
        workspace_id=uuid4(),
        query="Bao nhiêu ngày nghỉ phép?",
        llm=wrong_stream_llm,
    ):
        events.append(ev)

    joined = "".join(events)
    assert "event: token" in joined
    assert "event: answer_completed" in joined
    assert '"grounding_status": "unsupported"' in events[-1]
    assert UNVERIFIED_CITATION_ANSWER in events[-1]
    assert '"sources": []' in events[-1]
    # Persisted message must NOT save the ungrounded citation as verified
    assert persisted_contents == [UNVERIFIED_CITATION_ANSWER]


# 13. Report-only mode preserves answer while recording unsupported status
@pytest.mark.anyio
async def test_rag_report_only_mode_preserves_answer_but_marks_status(monkeypatch):
    import app.services.rag as rag_mod

    sources = _make_sources()

    async def fake_retrieve(*args, **kwargs):
        return RetrievalContext(text=SOURCE_1_TEXT, sources=sources, retrieval_mode="dense")

    monkeypatch.setattr(rag_mod, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(
        rag_mod,
        "get_settings",
        lambda: Settings(
            citation_grounding_enabled=True,
            citation_grounding_mode="report_only",
            database_url="postgresql+asyncpg://dummy:dummy@localhost/dummy",
            jwt_secret_key="dummy",
        ),
    )

    llm = FakeLLMProvider(response="Được hưởng 18 ngày nghỉ phép mỗi năm. [Source 2]")
    res = await answer_with_rag(
        session=MagicMock(),
        workspace_id=uuid4(),
        query="Bao nhiêu ngày?",
        llm=llm,
    )
    assert "18 ngày" in res.answer
    assert len(res.sources) == 2
    assert res.grounding_status == "unsupported"


# 14. Cross-workspace / stale source isolation check
def test_grounding_rejects_stale_or_foreign_chunk_index():
    ws_a_doc = uuid4()
    ws_a_chunk = DocumentChunk(
        id=uuid4(),
        document_id=ws_a_doc,
        chunk_index=0,
        content="Mức phụ cấp là 500.000 đồng mỗi ngày.",
        char_start=0,
        char_end=38,
    )
    authorized_sources = [
        ContextSource(
            source_index=1,
            document_id=ws_a_doc,
            chunk_id=ws_a_chunk.id,
            chunk_index=0,
            content=ws_a_chunk.content,
            similarity=0.9,
        )
    ]
    # Even if an LLM hallucinates [Source 2] from another workspace or previous turn, it is rejected
    res = verify_answer_grounding("Phụ cấp ăn trưa 1.200.000 đồng. [Source 2]", authorized_sources)
    assert res.status == GroundingStatus.UNSUPPORTED
    assert res.is_grounded is False
