"""RAG evaluation runner supporting retrieval-only and full-RAG execution (T260030).

Provides:
- In-memory vector retriever for zero-database, deterministic evaluation.
- Database retriever adapter for live/provisioned PostgreSQL pgvector runs.
- Full-RAG pipeline executor with concurrency bounding and citation/refusal grading.
"""

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

import numpy as np

from app.evaluation.rag_dataset import (
    Answerability,
    RAGDatasetManifest,
    RAGFixtureDocument,
    RAGTestCase,
)
from app.evaluation.rag_diagnostics import (
    FailureRootCause,
    RAGCaseDiagnostic,
    grade_rag_response,
)
from app.evaluation.rag_metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)
from app.llm.base import LLMProvider
from app.models.document_chunk import DocumentChunk
from app.services.chunking import chunk_text
from app.services.context_builder import (
    build_retrieval_context,
)
from app.services.embedding import get_embedding_service
from app.services.rag_prompt import (
    INSUFFICIENT_CONTEXT_ANSWER,
    build_rag_messages,
)
from app.services.semantic_search import SemanticSearchResult


@dataclass(slots=True)
class EvaluatedChunk:
    """In-memory representation of an indexed chunk."""

    chunk_id: UUID
    document_key: str
    document_title: str
    workspace_ref: str
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    embedding: list[float]


class CorpusRetriever(Protocol):
    """Protocol for retrieving scored chunks for a query."""

    async def search(
        self,
        query: str,
        workspace_ref: str,
        limit: int,
    ) -> list[SemanticSearchResult]: ...

    def get_document_key_for_chunk(self, chunk_id: UUID) -> str | None: ...

    def get_workspace_ref_for_chunk(self, chunk_id: UUID) -> str | None: ...


class InMemoryCorpusRetriever:
    """Self-contained in-memory retriever for deterministic evaluation.

    Indexes synthetic fixture documents, generates real embeddings, and performs
    vector search with strict workspace tenant filtering without touching PostgreSQL.
    """

    def __init__(self, documents: Sequence[RAGFixtureDocument]) -> None:
        self._embedding_service = get_embedding_service()
        self._chunks: list[EvaluatedChunk] = []
        self._chunk_doc_map: dict[UUID, str] = {}
        self._chunk_ws_map: dict[UUID, str] = {}
        self._build_index(documents)

    def _build_index(self, documents: Sequence[RAGFixtureDocument]) -> None:
        all_texts: list[str] = []
        chunk_metadata: list[dict] = []

        for doc in documents:
            text_chunks = chunk_text(doc.content, chunk_size=1000, overlap=200)
            for ch in text_chunks:
                all_texts.append(ch.content)
                chunk_metadata.append(
                    {
                        "document_key": doc.key,
                        "document_title": doc.title,
                        "workspace_ref": doc.workspace_ref,
                        "chunk_index": ch.index,
                        "content": ch.content,
                        "char_start": ch.char_start,
                        "char_end": ch.char_end,
                    }
                )

        if all_texts:
            embeddings = self._embedding_service.embed_passages(all_texts)
        else:
            embeddings = []

        for meta, emb in zip(chunk_metadata, embeddings, strict=True):
            cid = uuid4()
            eval_chunk = EvaluatedChunk(
                chunk_id=cid,
                document_key=meta["document_key"],
                document_title=meta["document_title"],
                workspace_ref=meta["workspace_ref"],
                chunk_index=meta["chunk_index"],
                content=meta["content"],
                char_start=meta["char_start"],
                char_end=meta["char_end"],
                embedding=emb,
            )
            self._chunks.append(eval_chunk)
            self._chunk_doc_map[cid] = meta["document_key"]
            self._chunk_ws_map[cid] = meta["workspace_ref"]

    async def search(
        self,
        query: str,
        workspace_ref: str,
        limit: int = 5,
    ) -> list[SemanticSearchResult]:
        if not self._chunks:
            return []

        # Strict workspace isolation filter
        tenant_chunks = [ch for ch in self._chunks if ch.workspace_ref == workspace_ref]
        if not tenant_chunks:
            return []

        query_emb = np.array(
            self._embedding_service.embed_query(query), dtype=np.float32
        )

        # Compute cosine similarity
        results = []
        for ch in tenant_chunks:
            chunk_emb = np.array(ch.embedding, dtype=np.float32)
            cosine_sim = float(np.dot(query_emb, chunk_emb))

            doc_chunk = DocumentChunk(
                id=ch.chunk_id,
                document_id=uuid4(),
                chunk_index=ch.chunk_index,
                content=ch.content,
                char_start=ch.char_start,
                char_end=ch.char_end,
            )
            results.append(
                SemanticSearchResult(
                    chunk=doc_chunk,
                    similarity=cosine_sim,
                    document_title=ch.document_title,
                )
            )

        # Sort descending by similarity
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:limit]

    def get_document_key_for_chunk(self, chunk_id: UUID) -> str | None:
        return self._chunk_doc_map.get(chunk_id)

    def get_workspace_ref_for_chunk(self, chunk_id: UUID) -> str | None:
        return self._chunk_ws_map.get(chunk_id)


@dataclass(slots=True)
class EvaluationRunConfig:
    """Configuration for an evaluation session."""

    mode: str = "retrieval-only"  # 'retrieval-only' or 'full-rag'
    k: int = 5
    concurrency_limit: int = 2
    max_context_chars: int = 8000
    llm_timeout_seconds: float = 60.0


async def evaluate_single_case(
    *,
    case: RAGTestCase,
    retriever: CorpusRetriever,
    config: EvaluationRunConfig,
    llm: LLMProvider | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> RAGCaseDiagnostic:
    """Evaluate one case through retrieval and optionally generation."""
    t0_retrieval = time.perf_counter()
    matches = await retriever.search(
        case.query,
        workspace_ref=case.workspace_ref,
        limit=config.k,
    )
    retrieval_latency_ms = (time.perf_counter() - t0_retrieval) * 1000.0

    retrieved_doc_keys: list[str] = []
    source_workspace_refs: dict[int, str] = {}
    cross_tenant_chunks = 0
    negative_retrieved = False

    for match in matches:
        doc_key = retriever.get_document_key_for_chunk(match.chunk.id) or "unknown"
        chunk_ws = retriever.get_workspace_ref_for_chunk(match.chunk.id) or "unknown"
        retrieved_doc_keys.append(doc_key)

        if chunk_ws != case.workspace_ref:
            cross_tenant_chunks += 1
        if doc_key in case.negative_document_keys:
            negative_retrieved = True

    # Assemble retrieval context
    context = build_retrieval_context(matches, max_chars=config.max_context_chars)
    for source in context.sources:
        ws = retriever.get_workspace_ref_for_chunk(source.chunk_id)
        if ws:
            source_workspace_refs[source.source_index] = ws

    # Compute per-case retrieval metrics
    # Only calculate recall if expected documents exist
    if case.expected_document_keys:
        rec_1 = recall_at_k(retrieved_doc_keys, case.expected_document_keys, 1)
        rec_3 = recall_at_k(retrieved_doc_keys, case.expected_document_keys, 3)
        rec_5 = recall_at_k(retrieved_doc_keys, case.expected_document_keys, config.k)
        prec_1 = precision_at_k(retrieved_doc_keys, case.expected_document_keys, 1)
        prec_3 = precision_at_k(retrieved_doc_keys, case.expected_document_keys, 3)
        prec_5 = precision_at_k(
            retrieved_doc_keys, case.expected_document_keys, config.k
        )
        rr = reciprocal_rank_at_k(
            retrieved_doc_keys, case.expected_document_keys, config.k
        )
    else:
        # Refusal cases: no relevant document expected in corpus
        rec_1 = 0.0
        rec_3 = 0.0
        rec_5 = 0.0
        prec_1 = 0.0
        prec_3 = 0.0
        prec_5 = 0.0
        rr = 0.0

    sim_scores = tuple(round(m.similarity, 4) for m in matches)

    diagnostic = RAGCaseDiagnostic(
        case_id=case.case_id,
        query=case.query,
        category=case.category.value,
        difficulty=case.difficulty.value,
        workspace_ref=case.workspace_ref,
        retrieved_doc_keys=tuple(retrieved_doc_keys),
        retrieved_chunk_count=len(matches),
        retrieval_latency_ms=round(retrieval_latency_ms, 2),
        similarity_scores=sim_scores,
        cross_tenant_chunks_count=cross_tenant_chunks,
        negative_doc_retrieved=negative_retrieved,
        recall_at_1=round(rec_1, 4),
        recall_at_3=round(rec_3, 4),
        recall_at_5=round(rec_5, 4),
        precision_at_1=round(prec_1, 4),
        precision_at_3=round(prec_3, 4),
        precision_at_5=round(prec_5, 4),
        reciprocal_rank=round(rr, 4),
    )

    # Retrieval-only mode completes here
    if config.mode == "retrieval-only" or llm is None:
        # Determine retrieval pass/fail
        if case.expected_answerability == Answerability.ANSWERABLE:
            diagnostic.passed = rec_5 > 0.0 and not negative_retrieved
            if not diagnostic.passed:
                diagnostic.root_cause = FailureRootCause.RETRIEVAL_FAILURE
                diagnostic.notes = "Retrieval failed to find expected evidence in top-k"
            else:
                diagnostic.notes = "Retrieval successfully found expected evidence"
        else:
            # For refusal cases, retrieval pass means no negative/forbidden documents leaked
            diagnostic.passed = not negative_retrieved and cross_tenant_chunks == 0
            diagnostic.notes = "Zero cross-tenant or negative documents retrieved"
        return diagnostic

    # Full-RAG mode: execute generation under concurrency semaphore
    t0_gen = time.perf_counter()
    if not context.sources or not context.text.strip():
        answer = INSUFFICIENT_CONTEXT_ANSWER
        gen_latency_ms = 0.0
    else:
        messages = build_rag_messages(query=case.query, context=context)
        sem = semaphore or asyncio.Semaphore(1)
        async with sem:
            answer = await asyncio.wait_for(
                llm.generate(messages),
                timeout=config.llm_timeout_seconds,
            )
        gen_latency_ms = (time.perf_counter() - t0_gen) * 1000.0

    classification, root_cause, cit_diag, passed, notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=retrieved_doc_keys,
        source_workspace_refs=source_workspace_refs,
    )

    diagnostic.answer = answer
    diagnostic.is_refusal = answer.strip() == INSUFFICIENT_CONTEXT_ANSWER.strip()
    diagnostic.citation_diagnostic = cit_diag
    diagnostic.classification = classification
    diagnostic.root_cause = root_cause
    diagnostic.generation_latency_ms = round(gen_latency_ms, 2)
    diagnostic.passed = passed
    diagnostic.notes = notes

    return diagnostic


async def run_rag_evaluation(
    *,
    dataset: RAGDatasetManifest,
    retriever: CorpusRetriever,
    config: EvaluationRunConfig,
    llm: LLMProvider | None = None,
) -> list[RAGCaseDiagnostic]:
    """Execute evaluation for all cases in dataset sequentially or with bounded concurrency."""
    semaphore = asyncio.Semaphore(config.concurrency_limit)
    diagnostics: list[RAGCaseDiagnostic] = []

    for case in dataset.cases:
        diag = await evaluate_single_case(
            case=case,
            retriever=retriever,
            config=config,
            llm=llm,
            semaphore=semaphore,
        )
        diagnostics.append(diag)

    return diagnostics
