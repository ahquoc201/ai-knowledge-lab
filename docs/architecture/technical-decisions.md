# Architecture Decision Records (ADR)

## ADR-001: Modular Monolith vs Microservices
- **Status**: Accepted
- **Context**: The project needs high iteration velocity, clear data consistency, simple local developer onboarding, and zero unnecessary infrastructure overhead.
- **Decision**: Retain and enhance the Modular Monolith structure in Python/FastAPI while offloading heavy batch computation to background workers via Celery/Redis.
- **Consequences**:
  - Positive: Single codebase, unified migrations, fast end-to-end testing, easy self-hosting via Docker Compose.
  - Negative: All backend domains share the same deployment artifact (mitigated by strict module boundaries).

## ADR-002: Modern Enterprise Frontend Stack (React + TypeScript + Vite + Tailwind CSS)
- **Status**: Accepted
- **Context**: The frontend directory is currently empty. We need a performant, maintainable, type-safe SPA that seamlessly communicates with the existing FastAPI backend.
- **Decision**: Select React 18, TypeScript, Vite, and Tailwind CSS.
- **Consequences**:
  - Positive: Instant HMR with Vite, full type-safety matching backend schemas, zero bloated runtime UI libraries, easily themed via semantic CSS tokens.
  - Negative: Requires initial component setup for UI primitives (Button, Modal, Card, Input).

## ADR-003: CORS Security Configuration
- **Status**: Accepted
- **Context**: The backend API previously omitted `CORSMiddleware`, causing browser-based SPA requests from development servers (e.g. `http://localhost:5173`) to fail.
- **Decision**: Add configurable `CORSMiddleware` to FastAPI in `app/main.py`, driven by `cors_origins` in `app/core/config.py`.
- **Consequences**:
  - Positive: Allows safe web browser consumption while maintaining production origin restrictions.
  - Negative: Requires correct `.env` configuration in production.

## ADR-004: Evidence-Driven RAG & Fail-Closed Refusal Policy
- **Status**: Accepted
- **Context**: Generic LLM hallucination and fabricated citations degrade enterprise trust.
- **Decision**:
  - Strictly enforce canonical `[Source N]` validation.
  - If retrieval returns no sources or empty text, immediately return the canonical Vietnamese refusal message (`Không đủ thông tin trong tài liệu để trả lời câu hỏi này.`) without calling the LLM.
  - If LLM response contains invalid/unclosed citations, fail closed and refuse to present ungrounded content.
