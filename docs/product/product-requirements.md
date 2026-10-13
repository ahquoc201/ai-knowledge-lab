# Product Requirements Document (PRD)

## 1. Product Statement
**AI Knowledge Lab** is an open-source, evidence-driven, self-hosted AI knowledge workspace. It empowers individuals, engineering teams, and researchers to organize proprietary documents, conduct semantic searches, engage in grounded RAG discussions with full source provenance, and run controlled AI agent research workflows.

## 2. Target User Personas
1. **Software Engineers & Technical Leads**: Need fast, accurate answers from system architectures, API docs, and incident reports without hallucination.
2. **Researchers & Analysts**: Require exact citations to verify every claim against the original papers or technical specifications.
3. **Privacy-Conscious Organizations**: Need self-hosted deployments keeping data completely inside their local or private cloud infrastructure.

## 3. Product Principles
- **Evidence-First**: No unverified answers; every synthesized paragraph must point to real source chunks.
- **Transparency**: Clear status visibility during ingestion, retrieval ranking, and agent tool execution.
- **Data Control**: Zero vendor lock-in; open-source models (Ollama, HuggingFace embeddings) and PostgreSQL storage.
- **Simplicity**: Clean enterprise UI without visual noise.

## 4. MVP Core User Journey
1. **Authenticate**: User registers and logs into the workspace.
2. **Ingest Documents**: User uploads files (TXT, PDF, Markdown) with immediate status feedback (`PENDING -> PROCESSING -> READY`).
3. **Inspect Library**: User reviews chunking breakdown and ingestion health.
4. **Natural Language Search & Q&A**: User queries the knowledge base and receives grounded answers with clickable source citations.
5. **Inspect Sources**: User views exact similarity scores and source chunk excerpts.
