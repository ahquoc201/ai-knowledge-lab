# Current Architecture State (Audit as of T260020 / T260021)

## 1. System Overview
**AI Knowledge Lab** is an asynchronous, self-hosted knowledge management and retrieval-augmented generation (RAG) platform. The system is designed as a modular monolith in Python/FastAPI, utilizing PostgreSQL with pgvector for relational data and vector storage, Redis as a Celery broker, and Ollama for local LLM inference.

## 2. Component Inventory

### 2.1 Backend Modules (`backend/app`)
- **`core/`**: Central configuration (`config.py`), database session setup (`db/session.py`), security primitives (`security.py`), enum definitions (`document_status.py`, `message_role.py`), and Celery application initialization (`celery_app.py`).
- **`models/`**: SQLAlchemy declarative models:
  - `User`: Accounts with email, password hash, created/updated timestamps.
  - `Document`: Files and text documents with metadata (`source_type`, `storage_key`, `mime_type`), status lifecycle, and lease tokens (`processing_run_id`, `processing_heartbeat_at`).
  - `DocumentChunk`: Text chunks partitioned from documents with character offsets and 384-dimensional vector embeddings (`pgvector`).
  - `Conversation` & `Message`: Persistent chat sessions and messages with role attribution.
  - `MessageSource`: Many-to-many relationship mapping assistant messages to exact context sources cited.
- **`repositories/`**: Clean database access layer:
  - Transaction-safe atomic document processing claims and lease recovery.
  - Document chunk batch operations and vector similarity queries.
  - User and conversation persistence.
- **`services/`**: Core business domain logic:
  - `auth.py`: User registration and JWT credential verification.
  - `document.py` & `ingestion.py`: Safe document upload, file storage validation, text extraction, chunking, and worker task orchestration.
  - `retrieval.py` & `semantic_search.py`: Cosine distance vector search with user-isolation enforcement.
  - `rag.py`, `rag_prompt.py`, `citation_validation.py`: Prompt builder with bounded history budget, canonical refusal handling, and strict source citation parsing.
  - `evaluation/`: Retrieval quality benchmark engine (MRR, nDCG, Precision, Recall) with regression detection.
- **`tasks/`**: Celery worker tasks for background file extraction and chunk embedding with heartbeat renewal.

### 2.2 Infrastructure & Storage
- **PostgreSQL 17** (`pgvector/pgvector:0.8.6-pg17-bookworm`): Running on port 5433 (mapped from host 15432/5432 in various test environments).
- **Redis 7.4**: Task queue broker on port 16379.
- **Local File Storage**: UUID-keyed source files stored in `storage/uploads/` with path-traversal prevention.

### 2.3 Test Suite
- **356 Collected Tests**: Covering unit testing, mock services, concurrency lease claims, citation validation, prompt bounding, and retrieval evaluation metrics.

## 3. Key Architectural Gaps & Technical Debt (Identified during Audit)
1. **Frontend Absence (P0)**: The `frontend/` directory is completely empty (`.gitkeep` only). Users cannot interact with the platform visually.
2. **Missing CORS Configuration (P1)**: `backend/app/main.py` does not configure `CORSMiddleware`. Any modern SPA calling the API from a browser will be blocked.
3. **Workspace Model Not Yet Introduced (P2)**: Multi-tenancy currently relies solely on direct `user_id` ownership, rather than flexible team/workspace boundaries.
4. **Agent Runtime Not Yet Implemented (P2)**: Autonomous agent workflows and tool calling policies are scheduled for subsequent iterations (T260027+).
