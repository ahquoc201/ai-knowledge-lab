# Target Architecture: AI Knowledge Lab

## 1. Architectural Philosophy
AI Knowledge Lab follows a **Modular Monolith + Background Worker** design. This provides:
- Single repository simplicity and rapid local iteration.
- Strict module encapsulation preventing spaghetti dependencies.
- Clear separation between synchronous HTTP request/response loops and compute-heavy AI tasks (parsing, embeddings, reranking, agent loops).
- A clean path toward microservices if scale ever dictates.

```
+-----------------------------------------------------------------------------------+
|                           Web Application / UI (React + Vite)                    |
|       - Dashboard       - Document Library       - AI Chat       - Agent Studio   |
+-----------------------------------------------------------------------------------+
                                          | HTTPS / REST (JSON)
                                          v
+-----------------------------------------------------------------------------------+
|                           API Gateway & HTTP Layer (FastAPI)                      |
|                 Auth | Documents | Retrieval | RAG | Conversations                |
+-----------------------------------------------------------------------------------+
                                          |
        +---------------------------------+--------------------------------+
        |                                                                  |
        v                                                                  v
+-----------------------------+                           +-----------------------------+
|    Application Services     |                           |    Async Workers (Celery)   |
| - Ingestion & Chunking      | ---- Redis Task Queue --> | - Text extraction           |
| - Vector Search & Ranking   |                           | - Embedding computation     |
| - RAG & Citation Validator  |                           | - Document reindexing       |
| - Agent Runtime Engine      |                           | - Scheduled evaluations     |
+-----------------------------+                           +-----------------------------+
        |                                                                  |
        v                                                                  v
+-----------------------------------------------------------------------------------+
|                     Data Persistence Layer (PostgreSQL 17 + pgvector)             |
|   Users | Workspaces | Documents | Chunks (Vectors) | Conversations | Messages    |
+-----------------------------------------------------------------------------------+
```

## 2. Core Subsystems

### 2.1 Identity, Access & Workspaces
- Stateless JWT-based authentication.
- Resource isolation enforced at the repository query level (`WHERE user_id = :user_id` transitioning to `WHERE workspace_id = :workspace_id`).
- Role-based permissions (Viewer, Contributor, Admin, Owner).

### 2.2 Knowledge Ingestion & Vector Storage
- Multi-format file ingestion (TXT, Markdown, PDF, DOCX).
- Token-bounded chunking with configurable overlap.
- Embedding generation via HuggingFace `multilingual-e5-small` (384 dimensions).
- Atomic lease acquisition preventing concurrent worker collision with automatic heartbeat staleness recovery.

### 2.3 RAG & Evidence Grounding
- Cosine distance similarity retrieval with thresholding.
- Prompt construction with bounded history and token budgeting.
- Strict canonical citation syntax validation (`[Source N]`) with fail-closed rejection of uncited / malformed claims.
- Fallback answer contract when context contains insufficient evidence.

### 2.4 Agent Runtime & Tool Execution (Future Phase)
- State machine lifecycle: `PENDING -> RUNNING -> WAITING_APPROVAL -> COMPLETED / FAILED`.
- Sandboxed tool registry with permission checks and human-in-the-loop approval gates.
- Complete execution trace auditability.

### 2.5 Frontend Architecture
- **Framework**: React 18, TypeScript, Vite.
- **Styling**: Tailwind CSS with enterprise semantic design tokens.
- **State Management**: React Context for Auth & Session, native typed API client with centralized error and auth token handling.
- **Components**: Reusable, accessible UI components (Button, Input, Card, Badge, Modal, Spinner, Alert).
