"""Command-line interface for RAG quality evaluation and diagnostics (T260030).

Usage examples:
  # Fast, safe retrieval-only evaluation without database mutation or LLM load:
  python -m app.evaluation.rag_cli --mode retrieval-only

  # Full-RAG evaluation with citation and refusal grading:
  python -m app.evaluation.rag_cli --mode full-rag --output-md reports/rag_quality_summary.md
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.evaluation.rag_dataset import load_rag_dataset
from app.evaluation.rag_reporting import (
    build_rag_quality_report,
    render_rag_evaluation_markdown,
)
from app.evaluation.rag_runner import (
    EvaluationRunConfig,
    InMemoryCorpusRetriever,
    run_rag_evaluation,
)
from app.llm.ollama import get_ollama_llm_provider

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
        choices=["retrieval-only", "full-rag"],
        default="retrieval-only",
        help="Evaluation mode: 'retrieval-only' (no LLM, fast) or 'full-rag' (with generation)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of retrieved chunks (top-k)",
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
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum concurrent LLM requests (default: 1 for local CPU safety)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if not args.dataset.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {args.dataset}")

    logger.info(f"Loading evaluation dataset from: {args.dataset}")
    dataset = load_rag_dataset(args.dataset)
    logger.info(
        f"Loaded dataset '{dataset.dataset_id}' v{dataset.version} with "
        f"{len(dataset.documents)} documents and {len(dataset.cases)} cases."
    )

    logger.info("Initializing in-memory corpus index with embedding service...")
    retriever = InMemoryCorpusRetriever(dataset.documents)

    config = EvaluationRunConfig(
        mode=args.mode,
        k=args.k,
        concurrency_limit=args.max_concurrency,
    )

    llm = None
    llm_name = None
    if args.mode == "full-rag":
        logger.info("Connecting to local Ollama provider for full-RAG evaluation...")
        llm = get_ollama_llm_provider()
        llm_name = getattr(llm, "model", "qwen3:1.7b")

    logger.info(f"Starting evaluation in '{args.mode}' mode (k={args.k})...")
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
    logger.info(f"  Recall@1: {ret['recall_at_1'] * 100:.1f}%")
    logger.info(f"  Recall@3: {ret['recall_at_3'] * 100:.1f}%")
    logger.info(f"  Recall@5: {ret['recall_at_5'] * 100:.1f}%")
    logger.info(f"  Precision@5: {ret['precision_at_5'] * 100:.1f}%")
    logger.info(f"  MRR@5: {ret['mrr_at_5']:.4f}")
    logger.info(f"  Retrieval Coverage: {ret['retrieval_coverage'] * 100:.1f}%")
    logger.info(f"  Tenant Isolation Rate: {ret['tenant_isolation_rate'] * 100:.1f}%")
    if "generation_metrics" in report:
        gen = report["generation_metrics"]
        logger.info(f"  Overall Pass Rate: {gen['overall_pass_rate'] * 100:.1f}%")
        logger.info(f"  Accuracy Rate: {gen['accuracy_rate'] * 100:.1f}%")
        logger.info(f"  Correct Refusal Rate: {gen['correct_refusal_rate'] * 100:.1f}%")
        logger.info(f"  False Refusal Rate: {gen['false_refusal_rate'] * 100:.1f}%")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
