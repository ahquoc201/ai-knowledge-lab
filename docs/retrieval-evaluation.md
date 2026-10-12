
# Retrieval Evaluation & Quality Regression

## 1. Overview

Task: T260019

The Retrieval Evaluation module measures semantic search quality
using a versioned Golden Dataset.

The current implementation supports:

- Precision@K
- Recall@K
- MRR@K
- Golden Dataset validation
- Isolated fixture provisioning
- Baseline JSON reporting
- Retrieval regression detection
- Offline regression checks in GitHub Actions

## 2. Architecture

Main components:

| Module | Responsibility |
|---|---|
| `metrics.py` | Calculate retrieval quality metrics |
| `models.py` | Define evaluation data models |
| `runner.py` | Evaluate ranked retrieval results |
| `dataset.py` | Load Golden Datasets containing chunk UUIDs |
| `dataset_validator.py` | Validate chunk ownership and references |
| `adapters.py` | Connect evaluation to Semantic Search |
| `service.py` | Execute evaluation with a consistent DB snapshot |
| `fixture_manifest.py` | Load portable document-based fixtures |
| `fixture_provisioner.py` | Create and clean up isolated test data |
| `reporting.py` | Build portable evaluation reports |
| `regression.py` | Detect retrieval quality regressions |
| `cli.py` | Run real retrieval evaluation |
| `compare_cli.py` | Compare two JSON reports |

Evaluation flow:

```text
Retrieval Fixture Manifest
           |
           v
Prepare chunks and embeddings
           |
           v
Provision isolated database user
           |
           v
Persist documents and chunks
           |
           v
Build Golden Dataset
           |
           v
Semantic Search Evaluation
           |
           v
Precision / Recall / MRR
           |
           v
Cleanup fixture resources
           |
           v
Save JSON report
```

## 3. Golden Dataset

Fixture path:

`backend/datasets/evaluation/retrieval_fixtures.json`

Initial dataset:

- Dataset ID: `ai-knowledge-lab-retrieval`
- Version: `1.0`
- Documents: 4
- Evaluation queries: 8
- Topics: PostgreSQL, Redis, FastAPI, Docker

Each case references document keys rather than persistent
database UUIDs.

The Fixture Provisioner converts those keys into actual
chunk UUIDs during each evaluation run.

## 4. Run Retrieval Evaluation

Run commands from the `backend/` directory.

Prerequisites:

- PostgreSQL with pgvector is available.
- Database migrations have been applied.
- The embedding model is accessible.
- `APP_ENV` is `development` or `test`.
- The database target has been verified.

Generate the initial baseline:

```bash
uv run python -m app.evaluation.cli \
  --confirm-database ailab \
  --allow-fixture-writes
```

Default output:

`datasets/evaluation/reports/baseline.json`

The CLI refuses to overwrite an existing report.

To create a separate candidate report:

```bash
uv run python -m app.evaluation.cli \
  --confirm-database ailab \
  --allow-fixture-writes \
  --output datasets/evaluation/reports/candidate.json
```

Do not automatically commit temporary candidate reports.

## 5. Baseline Results

Initial baseline with `intfloat/multilingual-e5-small`:

| Metric | K=1 | K=3 |
|---|---:|---:|
| Mean Precision | 1.0000 | 0.3333 |
| Mean Recall | 1.0000 | 1.0000 |
| MRR | 1.0000 | 1.0000 |

All eight queries retrieved their relevant chunk at rank 1.

Precision@3 is 0.3333 because each query currently
has one relevant chunk among three retrieved results.

These results validate the initial retrieval pipeline.
They do not establish production-level search quality.

## 6. Regression Guard

Compare the committed baseline against a new candidate:

```bash
uv run python -m app.evaluation.compare_cli \
  --baseline datasets/evaluation/reports/baseline.json \
  --candidate datasets/evaluation/reports/candidate.json
```

Optional absolute tolerance:

```bash
uv run python -m app.evaluation.compare_cli \
  --baseline datasets/evaluation/reports/baseline.json \
  --candidate datasets/evaluation/reports/candidate.json \
  --allowed-drop 0.05
```

Exit codes:

- `0`: No regression exceeding the tolerance.
- `1`: Regression detected or report invalid.
- `2`: Invalid command-line arguments.

The comparator checks both aggregate metrics and
individual query metrics.

Reports must use compatible dataset versions,
evaluation K values, and case IDs.

Comparing a baseline to itself does not measure
the quality of a new retrieval implementation.

## 7. CI/CD

Workflow:

`.github/workflows/retrieval-evaluation.yml`

GitHub Actions runs:

- Ruff
- Offline retrieval evaluation unit tests
- Regression Guard unit tests

The workflow currently does not run:

- PostgreSQL integration tests
- Embedding model inference
- Real retrieval baseline evaluation
- Baseline-to-candidate quality comparison

Real retrieval evaluation is a separate verification
step requiring an actual candidate report.

## 8. Safety

Fixture provisioning creates a temporary, inactive
evaluation user with isolated documents and chunks.

The database write transaction is atomic.

Cleanup is performed when the evaluation context exits.

Restrictions:

- Explicit authorization is required.
- Only development/test environments are permitted.
- Confirm the actual database target before execution.
- Never run fixture provisioning against production.
- Never use a production database disguised as development.

Cleanup cannot be guaranteed if the process is killed,
the machine crashes, or database connectivity is lost.

Orphan cleanup is a future improvement.

## 9. Future Improvements

- Larger, more diverse Golden Datasets
- Multi-chunk documents and multiple relevant results
- Difficult and ambiguous queries
- Query-level error analysis
- Retrieval latency measurements
- Automated candidate evaluation
- Production-grade regression thresholds
- Orphan fixture cleanup
