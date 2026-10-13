
# RAG Reliability & Answer Quality

**Task:** T260020
**Project:** AI Knowledge Lab
**Status:** Implemented, pending final regression and merge

## 1. Overview

This feature improves the reliability of Retrieval-Augmented Generation (RAG) through:

- Deterministic empty-context handling
- Retrieved context character budgeting
- Conversation history character budgeting
- Citation validation
- Explicit insufficient-evidence refusal handling

The existing `POST /api/v1/rag/ask` contract is preserved.

## 2. Architecture

```text
Authenticated RAG Request
          |
          v
    Retrieve Context
          |
          v
    Context Builder
    max 8,000 chars
          |
          +-- No usable context --> Insufficient-context response
          |
          v
    RAG Prompt Builder
    history max 4,000 chars
          |
          v
      LLM Provider
          |
          v
    Refusal Detection
          |
          +-- Canonical refusal --> Answer + sources=[]
          |
          v
    Citation Validator
          |
          +-- Invalid --> Verification fallback + sources=[]
          |
          +-- Valid --> Original answer + retrieved sources
          |
          v
    RAG API / Persistence
```

## 3. Context Budget

Implementation: `app/services/context_builder.py`

Default limit: `8,000 characters`.

Rules:

1. Preserve retrieval ranking.
2. Count source headers and separators within the budget.
3. Skip empty or whitespace-only chunks.
4. Truncate a chunk when necessary.
5. Stop after a truncated chunk or when the next source cannot fit.
6. Keep source indices contiguous.
7. Store only the included text in `ContextSource.content`.
8. Reject invalid budget values.

Character budgeting is not equivalent to token budgeting.

## 4. History Budget

Implementation: `app/services/rag_prompt.py`

Default limit: `4,000 characters`.

Rules:

1. Input history must be ordered oldest to newest.
2. Prioritize recent messages.
3. Preserve chronological order in the final prompt.
4. Prefer complete messages.
5. If the newest message exceeds the budget, retain its ending.
6. Include role prefixes and newline separators in the budget.
7. Reject invalid budget values.

The conversation history service separately limits the number of messages loaded from PostgreSQL, with a default of 10.

## 5. Citation Validation

Implementation: `app/services/citation_validation.py`

Only canonical citation markers are accepted:

`[Source N]`

where N must be a positive integer without leading zeros and must reference an available source.

Examples:

| Citation | Result |
|---|---|
| `[Source 1]` | Valid if Source 1 exists |
| `[Source 9]` | Invalid if Source 9 does not exist |
| `[Source abc]` | Invalid |
| `[source 1]` | Invalid |
| `[Source: 1]` | Invalid |
| `[Source-1]` | Invalid |
| `[ Source 1]` | Invalid |
| Unclosed source marker | Invalid for supported detected patterns |

The validator returns:

- `is_valid`
- `cited_indices`
- `invalid_citations`

It checks citation syntax and existence, not whether a claim is semantically supported by a source.

## 6. Fallback Policy

### Empty retrieval context

Do not invoke the LLM.

Return:

`Không đủ thông tin trong tài liệu để trả lời câu hỏi này.`

with `sources=[]`.

### Explicit LLM refusal

Accept only the exact canonical refusal after trimming surrounding whitespace.

Return the normalized refusal with `sources=[]`.

### Invalid or missing citations

Return:

`Không thể xác minh câu trả lời từ tài liệu được truy xuất.`

with `sources=[]`.

### Valid citations

Return the original answer and retrieved sources.

## 7. API and Persistence

The API response schema remains unchanged.

The RAG Service validates the generated answer before the API persists it.

Conversation history stores the processed assistant answer and its associated sources.

Invalid citation responses must not persist the original unverified LLM output as the assistant message.

## 8. Testing

Relevant test modules:

- `tests/test_context_builder.py`
- `tests/test_rag_prompt.py`
- `tests/test_citation_validation.py`
- `tests/test_rag.py`
- `tests/test_rag_api.py`

Run focused tests:

```bash
uv run pytest tests/test_context_builder.py tests/test_rag_prompt.py tests/test_citation_validation.py tests/test_rag.py tests/test_rag_api.py -q
```

Run full regression:

```bash
uv run pytest -q --tb=short
uv run ruff check .
git diff --check
```

## 9. Known Limitations

1. **Citation existence is not claim verification.** A valid citation may still be attached to an unsupported statement.
2. **Character budgets are not token budgets.** The total prompt size is not guaranteed to fit every LLM context window.
3. **Chunk truncation is character-based.** It may cut sentences or otherwise reduce semantic completeness.
4. **Citation parsing is pattern-based.** It does not detect every possible malformed or alternative citation format.
5. **Refusal detection is strict.** Semantically equivalent refusal wording may be replaced by the verification fallback.
6. **History budgeting is prompt-side.** It does not independently reduce database retrieval costs.

Potential future research includes token-aware prompt budgeting, claim-level grounding, citation repair, and grounded-answer quality evaluation.
