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

## Running Tests

Run backend tests:

```bash
cd backend
.venv/bin/pytest -q --tb=short
```

## Project Structure

- backend/: Backend application.
- frontend/: React application.
- ai-lab/: AI experiments and model training.
- docs/: Technical documentation.
- infrastructure/: Infrastructure configuration.
- scripts/: Development and operations scripts.

