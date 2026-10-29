"""Task Classifier for Adaptive Model Routing (T260027).

Deterministically classifies incoming RAG queries and Agent goals into standard task categories:
1. SIMPLE_CHAT
2. RAG_FACTUAL_QA
3. RAG_MULTI_DOCUMENT_SYNTHESIS
4. STRUCTURED_EXTRACTION
5. AGENT_TOOL_SELECTION
6. AGENT_MULTI_STEP_WORKFLOW
7. AGENT_WRITE_PROPOSAL
"""

import re
from typing import Any

from app.models.model_routing import TaskType

SYNTHESIS_PATTERNS = [
    r"\b(so sánh|tổng hợp|đối chiếu|phân tích toàn diện|tóm lược các|điểm khác biệt|tất cả tài liệu)\b",
    r"\b(compare|synthesize|contrast|cross-document|summarize all|across documents)\b",
]

WRITE_PATTERNS = [
    r"\b(tạo|thêm mới|ghi chú|lưu lại|soạn thảo|tạo tài liệu|bản nháp|ghi chép)\b",
    r"\b(create|write|draft|save|persist|insert document|make a note)\b",
]

MULTISTEP_PATTERNS = [
    r"\b(sau đó|tiếp tục|bước \d|rồi|kế tiếp|tuần tự|chuỗi bước)\b",
    r"\b(then|after that|step \d|subsequently|followed by|multi-step)\b",
]

EXTRACTION_PATTERNS = [
    r"\b(trích xuất|định dạng json|schema|trích thông tin|bảng biểu|trường dữ liệu)\b",
    r"\b(extract|json format|structured|schema|fields|key-value)\b",
]


class TaskClassificationResult:
    def __init__(
        self,
        task_type: str,
        confidence: float,
        rationale: str,
        matched_indicators: list[str] | None = None,
    ) -> None:
        self.task_type = task_type
        self.confidence = confidence
        self.rationale = rationale
        self.matched_indicators = matched_indicators or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "matched_indicators": self.matched_indicators,
        }


def classify_task(
    *,
    input_text: str,
    endpoint_hint: str | None = None,  # "rag_chat" | "agent" | "extraction"
    retrieved_chunk_count: int = 0,
    distinct_document_count: int = 0,
    forced_task_type: str | None = None,
) -> TaskClassificationResult:
    """Classify user intent or agent execution into deterministic taxonomy."""
    # 1. If explicit trusted hint provided and valid
    if forced_task_type and forced_task_type in TaskType.ALL:
        return TaskClassificationResult(
            task_type=forced_task_type,
            confidence=1.0,
            rationale=f"Explicitly designated task type: {forced_task_type}",
            matched_indicators=["explicit_override"],
        )

    text_lower = input_text.lower().strip()

    # 2. Agent Endpoint Classification
    if endpoint_hint == "agent":
        # Check WRITE proposal
        write_matches = [
            p for p in WRITE_PATTERNS if re.search(p, text_lower, re.IGNORECASE)
        ]
        if write_matches:
            return TaskClassificationResult(
                task_type=TaskType.AGENT_WRITE_PROPOSAL,
                confidence=0.95,
                rationale="Agent goal contains explicit mutation or document creation requests.",
                matched_indicators=write_matches,
            )

        # Check Multi-step workflow
        multistep_matches = [
            p for p in MULTISTEP_PATTERNS if re.search(p, text_lower, re.IGNORECASE)
        ]
        if multistep_matches:
            return TaskClassificationResult(
                task_type=TaskType.AGENT_MULTI_STEP_WORKFLOW,
                confidence=0.90,
                rationale="Agent goal indicates sequential, multi-step actions.",
                matched_indicators=multistep_matches,
            )

        # Default for Agent
        return TaskClassificationResult(
            task_type=TaskType.AGENT_TOOL_SELECTION,
            confidence=0.85,
            rationale="Agent goal requires tool selection and inspection.",
            matched_indicators=["agent_runtime_context"],
        )

    # 3. Extraction / Structured output check
    extraction_matches = [
        p for p in EXTRACTION_PATTERNS if re.search(p, text_lower, re.IGNORECASE)
    ]
    if endpoint_hint == "extraction" or extraction_matches:
        return TaskClassificationResult(
            task_type=TaskType.STRUCTURED_EXTRACTION,
            confidence=0.90,
            rationale="Query requires structured schema or JSON key-value extraction.",
            matched_indicators=extraction_matches,
        )

    # 4. RAG Chat Classification
    synthesis_matches = [
        p for p in SYNTHESIS_PATTERNS if re.search(p, text_lower, re.IGNORECASE)
    ]
    if distinct_document_count >= 2 or synthesis_matches:
        return TaskClassificationResult(
            task_type=TaskType.RAG_MULTI_DOCUMENT_SYNTHESIS,
            confidence=0.90 if distinct_document_count >= 2 else 0.85,
            rationale=f"Synthesis across {distinct_document_count} documents requested.",
            matched_indicators=synthesis_matches or [f"multi_doc_count={distinct_document_count}"],
        )

    if retrieved_chunk_count > 0:
        return TaskClassificationResult(
            task_type=TaskType.RAG_FACTUAL_QA,
            confidence=0.85,
            rationale=f"Factual Q&A grounded on {retrieved_chunk_count} retrieved chunks.",
            matched_indicators=[f"chunk_count={retrieved_chunk_count}"],
        )

    return TaskClassificationResult(
        task_type=TaskType.SIMPLE_CHAT,
        confidence=0.80,
        rationale="Conversational or knowledge question without workspace document grounding.",
        matched_indicators=["zero_retrieved_chunks"],
    )


class TaskClassifier:
    """Wrapper class providing object-oriented classification interface for router and API."""

    def classify(
        self,
        prompt: str,
        has_retrieved_context: bool = False,
        context_document_count: int = 0,
        requires_tools: bool = False,
        is_write_operation: bool = False,
        explicit_task_type: str | None = None,
    ) -> str:
        hint = None
        if requires_tools:
            hint = "agent"
        elif any(w in prompt.lower() for w in ["trích xuất", "json", "extract", "schema"]):
            hint = "extraction"

        chunk_count = context_document_count if has_retrieved_context else 0
        doc_count = context_document_count if has_retrieved_context else 0

        result = classify_task(
            input_text=prompt,
            endpoint_hint=hint,
            retrieved_chunk_count=chunk_count,
            distinct_document_count=doc_count,
            forced_task_type=explicit_task_type,
        )

        # Handle explicit write flag if flagged by caller for agent
        if requires_tools and is_write_operation:
            return TaskType.AGENT_WRITE_PROPOSAL

        return result.task_type

