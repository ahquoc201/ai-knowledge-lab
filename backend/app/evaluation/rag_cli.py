"""Command-line interface for RAG quality evaluation and diagnostics (T260030 & T260031).

Usage examples:
  # Fast, safe retrieval-only evaluation without database mutation or LLM load:
  python -m app.evaluation.rag_cli --mode synthetic-in-memory

  # Real pgvector retrieval evaluation against isolated test database:
  python -m app.evaluation.rag_cli --mode real-pgvector --database-url postgresql+asyncpg://ailab:local_only_change_me@127.0.0.1:15432/ailab_eval_test

  # Bounded full-RAG evaluation pilot with Ollama qwen3:1.7b:
  python -m app.evaluation.rag_cli --mode full-rag --pilot-limit 10 --max-concurrency 1
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.evaluation.rag_comparison import compare_reports, render_comparison_markdown
from app.evaluation.rag_dataset import RAGDatasetManifest, load_rag_dataset
from app.evaluation.rag_reporting import (
    build_rag_quality_report,
    render_rag_evaluation_markdown,
)
from app.evaluation.rag_runner import (
    EvaluationRunConfig,
    InMemoryCorpusRetriever,
    run_rag_evaluation,
)
from app.evaluation.real_fixture_provisioner import (
    provision_real_rag_fixtures,
    verify_database_safety,
)
from app.evaluation.real_hybrid_retriever import RealHybridCorpusRetriever
from app.evaluation.real_pgvector_retriever import RealPgVectorCorpusRetriever
from app.llm.ollama import OllamaLLMProvider
from app.services.fusion import DEFAULT_DENSE_WEIGHT, DEFAULT_KEYWORD_WEIGHT

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("RAGEvalCLI")

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "evaluation"
    / "rag_quality_dataset_v2.json"
)

DEFAULT_OUTPUT_JSON = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "evaluation"
    / "reports"
    / "rag_quality_report.json"
)

DEFAULT_OUTPUT_MD = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "evaluation"
    / "reports"
    / "rag_quality_summary.md"
)

DEFAULT_DATABASE_URL = os.getenv(
    "EVAL_DATABASE_URL",
    (
        "postgresql+asyncpg://ailab:local_only_change_me@/ailab_eval_test?host=/tmp&port=15432"
        if os.path.exists("/tmp/.s.PGSQL.15432")
        else "postgresql+asyncpg://ailab:local_only_change_me@127.0.0.1:15432/ailab_eval_test"
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run comprehensive RAG quality evaluation and retrieval diagnostics."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to evaluation dataset JSON manifest",
    )
    parser.add_argument(
        "--mode",
        choices=[
            "synthetic-in-memory",
            "retrieval-only",
            "real-pgvector",
            "real-hybrid",
            "real-compare",
            "full-rag",
        ],
        default="real-pgvector",
        help=(
            "Evaluation mode: 'synthetic-in-memory'/'retrieval-only' (in-memory embeddings), "
            "'real-pgvector' (production PostgreSQL pgvector retrieval), "
            "'real-hybrid' (PostgreSQL pgvector + FTS + RRF hybrid retrieval), "
            "'real-compare' (Dense then Hybrid on the same provisioned fixtures, with "
            "comparison report), or "
            "'full-rag' (real pgvector retrieval + context assembly + LLM generation)"
        ),
    )
    parser.add_argument(
        "--rrf-k",
        type=int,
        default=60,
        help="RRF constant k for hybrid retrieval fusion (default: 60)",
    )
    parser.add_argument(
        "--dense-weight",
        type=float,
        default=DEFAULT_DENSE_WEIGHT,
        help=f"Dense weight for weighted RRF fusion (default: {DEFAULT_DENSE_WEIGHT})",
    )
    parser.add_argument(
        "--keyword-weight",
        type=float,
        default=DEFAULT_KEYWORD_WEIGHT,
        help=f"Keyword weight for weighted RRF fusion (default: {DEFAULT_KEYWORD_WEIGHT})",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=DEFAULT_DATABASE_URL,
        help="Database URL for real pgvector modes (MUST be an isolated test DB, NOT ailab)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of retrieved chunks (top-k)",
    )
    parser.add_argument(
        "--pilot-limit",
        type=int,
        default=None,
        help="Limit evaluation to the first N cases (ideal for bounded full-RAG pilots)",
    )
    parser.add_argument(
        "--case-ids",
        type=str,
        default=None,
        help="Comma-separated list of specific case IDs to evaluate (e.g. for balanced pilot subsets)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="Destination path for JSON report",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Destination path for Markdown summary",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="real-compare only: directory for dense/hybrid/comparison reports",
    )
    parser.add_argument(
        "--report-prefix",
        type=str,
        default="rag_eval",
        help="real-compare only: file name prefix for generated reports",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum concurrent LLM requests (default: 1 for local CPU safety)",
    )
    return parser.parse_args()


async def run_real_comparison(
    *,
    args: argparse.Namespace,
    dataset: RAGDatasetManifest,
    config: EvaluationRunConfig,
) -> None:
    """Run Dense then Hybrid on one provisioned fixture set and write a comparison.

    Both strategies see identical fixtures, embedding model, process and warm-up policy
    (one unscored warm-up query each). Writes <prefix>_dense/_hybrid reports and a
    <prefix>_comparison report into --output-dir.
    """
    if args.output_dir is None:
        raise SystemExit("--output-dir is required for --mode real-compare")

    db_name = verify_database_safety(args.database_url)
    logger.info(f"Pre-flight safety check passed for database '{db_name}'.")
    engine = create_async_engine(args.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reports: dict[str, dict] = {}

    try:
        async with provision_real_rag_fixtures(
            engine=engine, manifest=dataset, allow_fixture_writes=True
        ) as env:
            logger.info(
                f"Fixtures provisioned: {env.total_documents} docs, {env.total_chunks} chunks."
            )
            strategies = (
                (
                    "dense",
                    "dense (pgvector cosine)",
                    RealPgVectorCorpusRetriever(session_factory=session_factory, env=env),
                ),
                (
                    "hybrid",
                    f"hybrid (pgvector + FTS + RRF k={args.rrf_k} w_d={args.dense_weight} w_k={args.keyword_weight})",
                    RealHybridCorpusRetriever(
                        session_factory=session_factory,
                        env=env,
                        rrf_k=args.rrf_k,
                        dense_weight=args.dense_weight,
                        keyword_weight=args.keyword_weight,
                    ),
                ),
            )
            warmup_case = dataset.cases[0]
            for label, strategy_name, retriever in strategies:
                await retriever.search(
                    warmup_case.query, warmup_case.workspace_ref, args.k
                )  # unscored warm-up
                logger.info(f"Evaluating strategy '{strategy_name}'...")
                diagnostics = await run_rag_evaluation(
                    dataset=dataset, retriever=retriever, config=config
                )
                reports[label] = build_rag_quality_report(
                    dataset=dataset,
                    diagnostics=diagnostics,
                    config=config,
                    database_name=env.database_name,
                    retrieval_strategy=strategy_name,
                )
    finally:
        await engine.dispose()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.report_prefix
    for label, report in reports.items():
        if prefix.startswith("rag_quality_extended"):
            report_json_path = args.output_dir / f"rag_quality_report_extended_{label}.json"
            summary_md_path = args.output_dir / f"rag_quality_summary_extended_{label}.md"
        elif prefix.startswith("rag_quality_holdout"):
            report_json_path = args.output_dir / f"rag_quality_report_holdout_{label}.json"
            summary_md_path = args.output_dir / f"rag_quality_summary_holdout_{label}.md"
        else:
            report_json_path = args.output_dir / f"{prefix}_{label}_report.json"
            summary_md_path = args.output_dir / f"{prefix}_{label}_summary.md"

        report_json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        summary_md_path.write_text(
            render_rag_evaluation_markdown(report) + "\n", encoding="utf-8"
        )

    comparison = compare_reports(reports["dense"], reports["hybrid"])
    if prefix.startswith("rag_quality_extended"):
        comp_json_path = args.output_dir / "rag_quality_comparison_extended.json"
        comp_md_path = args.output_dir / "rag_quality_comparison_extended.md"
    elif prefix.startswith("rag_quality_holdout"):
        comp_json_path = args.output_dir / "rag_quality_comparison_holdout.json"
        comp_md_path = args.output_dir / "rag_quality_comparison_holdout.md"
    else:
        comp_json_path = args.output_dir / f"{prefix}_comparison.json"
        comp_md_path = args.output_dir / f"{prefix}_comparison.md"

    comp_json_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    comp_md_path.write_text(
        render_comparison_markdown(comparison), encoding="utf-8"
    )
    logger.info(f"Comparison reports written to {args.output_dir}")


async def main() -> None:
    args = parse_args()

    if not args.dataset.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {args.dataset}")

    logger.info(f"Loading evaluation dataset from: {args.dataset}")
    raw_dataset = load_rag_dataset(args.dataset)
    logger.info(
        f"Loaded dataset '{raw_dataset.dataset_id}' v{raw_dataset.version} with "
        f"{len(raw_dataset.documents)} documents and {len(raw_dataset.cases)} cases."
    )

    selected_cases = raw_dataset.cases
    if args.case_ids:
        target_ids = {cid.strip() for cid in args.case_ids.split(",") if cid.strip()}
        selected_cases = [c for c in raw_dataset.cases if c.case_id in target_ids]
        logger.info(f"Filtered by case-ids: {len(selected_cases)} cases selected.")
    elif args.pilot_limit is not None and args.pilot_limit > 0:
        logger.info(f"Applying pilot limit: evaluating first {args.pilot_limit} cases.")
        selected_cases = raw_dataset.cases[: args.pilot_limit]

    dataset = RAGDatasetManifest(
        dataset_id=raw_dataset.dataset_id,
        version=raw_dataset.version,
        description=raw_dataset.description,
        documents=raw_dataset.documents,
        cases=selected_cases,
    )

    config = EvaluationRunConfig(
        mode="full-rag" if args.mode == "full-rag" else "retrieval-only",
        k=args.k,
        concurrency_limit=args.max_concurrency,
        llm_timeout_seconds=180.0,
    )

    llm = None
    llm_name = None
    if args.mode == "full-rag":
        logger.info("Connecting to local Ollama provider for full-RAG evaluation...")
        llm = OllamaLLMProvider(timeout_seconds=180.0)
        llm_name = getattr(llm, "model", "qwen3:1.7b")

    if args.mode == "real-compare":
        await run_real_comparison(args=args, dataset=dataset, config=config)
        return

    is_real_stack = args.mode in ("real-pgvector", "real-hybrid", "full-rag")

    if is_real_stack:
        db_name = verify_database_safety(args.database_url)
        logger.info(
            f"Pre-flight safety check passed for database '{db_name}'. "
            "Initializing async engine with NullPool..."
        )
        engine = create_async_engine(args.database_url, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        try:
            logger.info(
                "Provisioning synthetic evaluation fixtures into isolated test database..."
            )
            async with provision_real_rag_fixtures(
                engine=engine,
                manifest=dataset,
                allow_fixture_writes=True,
            ) as env:
                logger.info(
                    f"Fixtures provisioned: {env.total_documents} docs, {env.total_chunks} chunks."
                )
                if args.mode == "real-hybrid":
                    logger.info(
                        f"Instantiating RealHybridCorpusRetriever (rrf_k={args.rrf_k}, "
                        f"dense_weight={args.dense_weight}, keyword_weight={args.keyword_weight})..."
                    )
                    retriever = RealHybridCorpusRetriever(
                        session_factory=session_factory,
                        env=env,
                        rrf_k=args.rrf_k,
                        dense_weight=args.dense_weight,
                        keyword_weight=args.keyword_weight,
                    )
                else:
                    logger.info("Instantiating RealPgVectorCorpusRetriever...")
                    retriever = RealPgVectorCorpusRetriever(
                        session_factory=session_factory,
                        env=env,
                    )

                logger.info(
                    f"Starting real-stack evaluation in '{args.mode}' mode "
                    f"({len(dataset.cases)} cases, k={args.k})..."
                )
                diagnostics = await run_rag_evaluation(
                    dataset=dataset,
                    retriever=retriever,
                    config=config,
                    llm=llm,
                )

                logger.info("Evaluation completed. Aggregating results...")
                report = build_rag_quality_report(
                    dataset=dataset,
                    diagnostics=diagnostics,
                    config=config,
                    llm_model_name=llm_name,
                    database_name=env.database_name,
                    retrieval_strategy=args.mode,
                )
        finally:
            await engine.dispose()
    else:
        logger.info("Initializing in-memory corpus index with embedding service...")
        retriever = InMemoryCorpusRetriever(dataset.documents)

        logger.info(
            f"Starting in-memory evaluation in '{args.mode}' mode "
            f"({len(dataset.cases)} cases, k={args.k})..."
        )
        diagnostics = await run_rag_evaluation(
            dataset=dataset,
            retriever=retriever,
            config=config,
            llm=llm,
        )

        logger.info("Evaluation completed. Aggregating results...")
        report = build_rag_quality_report(
            dataset=dataset,
            diagnostics=diagnostics,
            config=config,
            llm_model_name=llm_name,
            database_name="synthetic-in-memory",
            retrieval_strategy=args.mode,
        )

    # Save JSON report
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved machine-readable JSON report to: {args.output_json}")

    # Save Markdown report
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    md_content = render_rag_evaluation_markdown(report)
    with args.output_md.open("w", encoding="utf-8") as f:
        f.write(md_content)
        f.write("\n")
    logger.info(f"Saved Markdown executive summary to: {args.output_md}")

    # Log summary to console
    ret = report["retrieval_metrics"]
    logger.info("=" * 60)
    logger.info("EVALUATION SUMMARY:")
    logger.info(
        f"  Target Database: {report.get('metadata', {}).get('database_environment', 'N/A')}"
    )
    logger.info(f"  Recall@1: {ret['recall_at_1'] * 100:.1f}%")
    logger.info(f"  Recall@3: {ret['recall_at_3'] * 100:.1f}%")
    logger.info(f"  Recall@5: {ret['recall_at_5'] * 100:.1f}%")
    logger.info(f"  Hit Rate@1: {ret.get('hit_rate_at_1', 0.0) * 100:.1f}%")
    logger.info(f"  Hit Rate@3: {ret.get('hit_rate_at_3', 0.0) * 100:.1f}%")
    logger.info(f"  Hit Rate@5: {ret.get('hit_rate_at_5', 0.0) * 100:.1f}%")
    logger.info(f"  Precision@5: {ret['precision_at_5'] * 100:.1f}%")
    logger.info(f"  MRR@5: {ret['mrr_at_5']:.4f}")
    logger.info(f"  Retrieval Coverage: {ret['retrieval_coverage'] * 100:.1f}%")
    logger.info(f"  Tenant Isolation Rate: {ret['tenant_isolation_rate'] * 100:.1f}%")
    logger.info(
        f"  Empty Candidate Rate: {ret.get('empty_candidate_rate', 0.0) * 100:.1f}%"
    )
    logger.info(
        f"  Empty Accepted Evidence Rate: {ret.get('empty_accepted_evidence_rate', 0.0) * 100:.1f}%"
    )
    if "latency_profile" in report and "retrieval_latency" in report["latency_profile"]:
        lat = report["latency_profile"]
        logger.info(
            f"  Mean Total Retrieval Latency: {lat['retrieval_latency']['mean_ms']:.2f} ms"
        )
        if "query_embedding_latency" in lat:
            logger.info(
                f"  Mean Query Embedding Latency: {lat['query_embedding_latency']['mean_ms']:.2f} ms"
            )
        if "vector_search_latency" in lat:
            logger.info(
                f"  Mean Vector Search Latency: {lat['vector_search_latency']['mean_ms']:.2f} ms"
            )
    if "generation_metrics" in report:
        gen = report["generation_metrics"]
        logger.info(f"  Overall Pass Rate: {gen['overall_pass_rate'] * 100:.1f}%")
        logger.info(f"  Accuracy Rate: {gen['accuracy_rate'] * 100:.1f}%")
        logger.info(f"  Correct Refusal Rate: {gen['correct_refusal_rate'] * 100:.1f}%")
        logger.info(f"  False Refusal Rate: {gen['false_refusal_rate'] * 100:.1f}%")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
