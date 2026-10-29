# AI Knowledge Lab

An AI-powered knowledge management platform built with Python, FastAPI, PostgreSQL, React, and PyTorch.

## Project Goals

- Learn professional Backend Engineering.
- Build REST APIs with FastAPI.
- Integrate multiple AI models.
- Implement Retrieval-Augmented Generation (RAG).
- Understand Transformer architecture.
- Train and deploy a small language model.
- Practice automated testing, Docker, and CI/CD.

## Tech Stack

### Backend
- Python 3.12
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic

### Frontend
- React
- TypeScript
- Vite

### AI
- PyTorch
- Hugging Face
- Ollama
- pgvector

- Celery
- Redis
- Docker
- GitHub Actions

## Quick Start

### 1. Infrastructure Services

Start PostgreSQL (pgvector) and Redis containers:

```bash
docker compose up -d
```

### 2. Celery Background Worker

To process background document ingestion and vectorization tasks:

```bash
./scripts/start-worker.sh
```

Or manually from the `backend/` directory:

```bash
cd backend
.venv/bin/celery -A app.core.celery_app worker --loglevel=info --concurrency=2
```

### 3. Backend API

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm run dev
```

## Key Modules & Platform Features

- **T260020 - T260024:** Enterprise Ingestion, RAG Reliability, Secure Workspaces & RBAC.
- **T260025:** Governed AI Agent Runtime with Tool Policy Enforcement & Human Approval.
- **T260026:** AI Agent Evaluation Framework & Reliability Benchmarking.
- **T260027:** AI Model Registry, Capability Discovery & Adaptive Model Routing.
- **T260028:** Agent Reliability, Concurrency Governor, Distributed Rate Limiting & Operations Dashboard.

## Running Tests

Run backend tests:

```bash
cd backend
.venv/bin/pytest -q --tb=short
.venv/bin/ruff check app/ tests/
```

Run frontend build & tests:

```bash
cd frontend
npm run build
npx playwright test --reporter=line
```

## Project Structure

- backend/: Backend application.
- frontend/: React application.
- ai-lab/: AI experiments and model training.
- docs/: Technical documentation.
- infrastructure/: Infrastructure configuration.
- scripts/: Development and operations scripts.

