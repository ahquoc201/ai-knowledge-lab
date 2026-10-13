# Product Engineering Roadmap

## Milestone Overview

### T260021: Product Architecture & Design System Foundation (Current)
- Complete repository & architecture audit.
- Document Current State, Target Architecture, ADRs, PRD, and Roadmap.
- Fix backend CORS policy to allow local web development.
- Scaffold React 18 + TypeScript + Vite + Tailwind CSS frontend application.
- Establish Design System Tokens (Modern Enterprise palette: `#F7F8FA`, `#111827`, `#2563EB`, `#E5E7EB`).
- Build reusable UI primitives (Button, Input, Card, Badge, Alert, Spinner, Modal).
- Build App Shell, Header, Sidebar Navigation, and responsive layout.
- Implement typed API client with automatic JWT token attachment.
- Deliver an operational vertical slice: Login / Register authentication flow + Document Library view connected to live backend APIs.

### T260022: Document Workspace Experience
- Complete interactive Document Library.
- Multi-file drag-and-drop upload with size & MIME validation.
- Live document metadata display, chunk viewer, and search/filter.
- Delete and reprocess action triggers.

### T260023: Reliable Document Ingestion & Progress
- Real-time ingestion progress visibility.
- Improved error feedback on parsing failures.
- Robust reprocessing and stale lease recovery observability.

### T260024: AI Chat & Evidence Grounding
- Conversation sidebar with history navigation.
- Streaming responses from RAG service.
- Clickable `[Source N]` citation pills with drawer preview of chunk content and similarity scores.
- Clean display of canonical refusal responses.

### T260025: Retrieval Quality & Hybrid Search
- Lexical search integration (PostgreSQL FTS).
- Reciprocal Rank Fusion (RRF) combining vector and keyword retrieval.
- Latency and accuracy benchmarking against golden dataset.

### T260026: Workspace & Multi-Tenancy Control
- Workspace model, membership invites, and RBAC (Admin, Member, Viewer).
- Strict workspace-level data isolation.

### T260027: Secure Agent Runtime & Research Assistant
- Agent execution state machine (`PENDING -> RUNNING -> WAITING_APPROVAL -> COMPLETED`).
- Read-only research tool registry (SearchDocs, FetchChunk, Summarize).
- Agent execution timeline UI with source attribution.

### T260028: Agent Security Policy & Human-in-the-Loop
- Permission gating and execution budgets.
- User approval prompt for side-effecting tools.
- Audit event logging.

### T260029+: Public Beta, Hardening & Developer Experience
- One-command `docker compose up` launch for all services.
- Production build optimization and deployment documentation.
- Comprehensive end-to-end user guide and public release.
