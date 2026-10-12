
"""Run retrieval evaluation and save a portable baseline report."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.embedding import EMBEDDING_MODEL_NAME
from app.evaluation.fixture_manifest import load_fixture_manifest
from app.evaluation.fixture_provisioner import provision_retrieval_fixture
from app.evaluation.reporting import build_baseline_report
from app.evaluation.service import evaluate_semantic_search

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "evaluation"
    / "retrieval_fixtures.json"
)

DEFAULT_REPORT_PATH = (
    FIXTURE_PATH.parent / "reports" / "baseline.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real semantic retrieval baseline evaluation."
    )

    parser.add_argument(
        "--confirm-database",
        required=True,
        help="Expected database name, for example: ailab",
    )

    parser.add_argument(
        "--allow-fixture-writes",
        action="store_true",
        help="Authorize temporary fixture writes and cleanup",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="JSON report output path (must not already exist)",
    )

    return parser.parse_args()


def save_baseline_report(
    *,
    path: Path,
    report: dict,
) -> None:
    """Save JSON without overwriting an existing baseline."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("x", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    database = make_url(settings.database_url)

    if settings.app_env not in {"development", "test"}:
        raise PermissionError(
            "Evaluation is restricted to development/test"
        )

    if database.host not in {"127.0.0.1", "localhost", "::1"}:
        raise PermissionError(
            "This baseline CLI requires a local PostgreSQL endpoint"
        )

    if database.database != args.confirm_database:
        raise ValueError(
            "Database mismatch: expected "
            f"{args.confirm_database}, got {database.database}"
        )

    if not args.allow_fixture_writes:
        raise PermissionError(
            "Pass --allow-fixture-writes to authorize provisioning"
        )

    if args.output.exists():
        raise FileExistsError(
            f"Baseline report already exists: {args.output}"
        )

    manifest = load_fixture_manifest(FIXTURE_PATH)

    print(f"Environment : {settings.app_env}")
    print(f"Database    : {database.database}")
    print(f"Dataset     : {manifest.dataset_id} v{manifest.version}")
    print(f"Embedding   : {EMBEDDING_MODEL_NAME}")
    print(f"Documents   : {len(manifest.documents)}")
    print(f"Queries     : {len(manifest.cases)}")

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )

    reports = []

    try:
        async with provision_retrieval_fixture(
            engine=engine,
            manifest=manifest,
            allow_fixture_writes=True,
        ) as fixture:
            for k in (1, 3):
                report = await evaluate_semantic_search(
                    engine=engine,
                    dataset=fixture.dataset,
                    user_id=fixture.user_id,
                    k=k,
                )

                reports.append(report)

                print(f"\n{'=' * 48}")
                print(f"RETRIEVAL BASELINE @ K={k}")
                print(f"{'=' * 48}")

                print(
                    f"Mean Precision@{k}: "
                    f"{report.mean_precision_at_k:.4f}"
                )
                print(
                    f"Mean Recall@{k}   : "
                    f"{report.mean_recall_at_k:.4f}"
                )
                print(
                    f"MRR@{k}           : "
                    f"{report.mrr_at_k:.4f}"
                )

                print("\nPer-query results:")

                for result in report.results:
                    print(
                        f"  {result.case_id:<20} "
                        f"P={result.precision_at_k:.3f} "
                        f"R={result.recall_at_k:.3f} "
                        f"RR={result.reciprocal_rank_at_k:.3f}"
                    )

        print("\nFixture cleanup completed successfully.")

    finally:
        await engine.dispose()

    baseline = build_baseline_report(
        reports=reports,
        embedding_model=EMBEDDING_MODEL_NAME,
        retrieval_method="semantic-search-pgvector",
    )

    save_baseline_report(
        path=args.output,
        report=baseline,
    )

    print(f"Baseline report saved: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
