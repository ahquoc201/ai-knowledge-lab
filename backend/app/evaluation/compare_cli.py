
"""Compare retrieval evaluation reports from the command line."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.evaluation.regression import compare_retrieval_reports


def load_report(path: Path) -> dict[str, Any]:
    """Read a JSON evaluation report."""

    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError(
            f"Report must be a JSON object: {path}"
        )

    return data


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect retrieval quality regressions "
            "between two evaluation reports."
        )
    )

    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Path to the reference baseline JSON",
    )

    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="Path to the candidate evaluation JSON",
    )

    parser.add_argument(
        "--allowed-drop",
        type=float,
        default=0.0,
        help=(
            "Maximum permitted absolute metric drop "
            "(default: 0.0)"
        ),
    )

    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Return 0 for PASS, 1 for regression or invalid reports."""

    args = parse_args(argv)

    try:
        baseline = load_report(args.baseline)
        candidate = load_report(args.candidate)

        findings = compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
            allowed_drop=args.allowed_drop,
        )

    except (OSError, ValueError, TypeError) as exc:
        print(
            f"INVALID REPORT: {exc}",
            file=sys.stderr,
        )
        return 1

    print("Retrieval Quality Regression Check")
    print(f"Dataset     : {baseline['dataset_id']}")
    print(f"Version     : {baseline['dataset_version']}")
    print(f"Baseline    : {args.baseline}")
    print(f"Candidate   : {args.candidate}")
    print(f"Allowed drop: {args.allowed_drop:.4f}")

    if not findings:
        print("\nPASS: No retrieval regressions detected.")
        return 0

    print(
        f"\nFAIL: Detected {len(findings)} "
        "retrieval metric regressions."
    )

    for finding in findings:
        case_label = finding.case_id or "aggregate"

        print(
            f"  K={finding.k} "
            f"case={case_label} "
            f"metric={finding.metric}"
        )
        print(
            f"    {finding.baseline:.4f} "
            f"-> {finding.candidate:.4f} "
            f"(drop={finding.drop:.4f})"
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
