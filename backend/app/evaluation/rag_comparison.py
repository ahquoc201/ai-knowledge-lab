"""Dense vs Hybrid retrieval comparison over two quality reports (T260033).

Pure functions over the JSON reports produced by ``build_rag_quality_report``. Both
reports must come from the same dataset id/version. Nothing here touches a database,
and the output is deterministic for identical inputs (no timestamps or latencies).
"""

from typing import Any

AGGREGATE_METRICS = (
    "hit_rate_at_1",
    "hit_rate_at_3",
    "hit_rate_at_5",
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "precision_at_5",
    "mrr_at_5",
    "retrieval_coverage",
    "chunk_recall_at_5",
    "chunk_mrr_at_5",
    "tenant_isolation_rate",
    "empty_candidate_rate",
    "empty_accepted_evidence_rate",
)

GROUP_METRICS = (
    "hit_rate_at_1",
    "hit_rate_at_5",
    "recall_at_5",
    "mrr_at_5",
    "chunk_recall_at_5",
    "refusal_leak_free_rate",
)

LEXICAL_PROVENANCE = ("keyword", "hybrid")


def _delta(dense: float | None, hybrid: float | None) -> float | None:
    if dense is None or hybrid is None:
        return None
    return round(hybrid - dense, 4)


def _compare_metric_dict(
    dense: dict[str, Any], hybrid: dict[str, Any], metrics: tuple[str, ...]
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for name in metrics:
        d, h = dense.get(name), hybrid.get(name)
        out[name] = {"dense": d, "hybrid": h, "delta": _delta(d, h)}
    return out


def _compare_groups(
    dense_groups: dict[str, Any], hybrid_groups: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in sorted(set(dense_groups) | set(hybrid_groups)):
        d = dense_groups.get(name, {})
        h = hybrid_groups.get(name, {})
        result[name] = {
            "total": d.get("total", h.get("total")),
            "answerable": d.get("answerable", h.get("answerable")),
            "refusal": d.get("refusal", h.get("refusal")),
            **_compare_metric_dict(d, h, GROUP_METRICS),
        }
    return result


def _rank_status(dense_rank: int | None, hybrid_rank: int | None) -> str:
    """Lower rank is better; None means the relevant item was not retrieved."""
    if dense_rank == hybrid_rank:
        return "unchanged"
    if dense_rank is None:
        return "improved"
    if hybrid_rank is None:
        return "regressed"
    return "improved" if hybrid_rank < dense_rank else "regressed"


def _lexical_supported(case: dict[str, Any]) -> bool:
    """True if a lexical branch contributed a chunk of an expected document."""
    expected = set(case.get("expected_documents", []))
    for key, provenance in zip(
        case.get("retrieved_keys", []), case.get("retrieval_provenance", []), strict=False
    ):
        if key in expected and provenance in LEXICAL_PROVENANCE:
            return True
    return False


def compare_reports(dense: dict[str, Any], hybrid: dict[str, Any]) -> dict[str, Any]:
    """Compare a Dense and a Hybrid report generated from the same dataset."""
    d_meta, h_meta = dense["metadata"], hybrid["metadata"]
    if (d_meta["dataset_id"], d_meta["dataset_version"]) != (
        h_meta["dataset_id"],
        h_meta["dataset_version"],
    ):
        raise ValueError(
            "Reports come from different datasets: "
            f"{d_meta['dataset_id']}@{d_meta['dataset_version']} vs "
            f"{h_meta['dataset_id']}@{h_meta['dataset_version']}"
        )

    dense_cases = {c["case_id"]: c for c in dense["cases"]}
    hybrid_cases = {c["case_id"]: c for c in hybrid["cases"]}
    if set(dense_cases) != set(hybrid_cases):
        raise ValueError("Reports do not contain the same case ids")

    case_rows: list[dict[str, Any]] = []
    for case_id, dc in dense_cases.items():  # dataset order preserved by report builder
        hc = hybrid_cases[case_id]
        answerable = bool(dc.get("expected_documents"))
        row: dict[str, Any] = {
            "case_id": case_id,
            "category": dc["category"],
            "language": dc.get("language"),
            "tags": dc.get("tags", []),
            "answerable": answerable,
            "dense_retrieved_keys": dc["retrieved_keys"],
            "hybrid_retrieved_keys": hc["retrieved_keys"],
            "top5_order_changed": dc["retrieved_keys"] != hc["retrieved_keys"],
        }
        if answerable:
            row.update(
                {
                    "dense_doc_rank": dc.get("first_relevant_doc_rank"),
                    "hybrid_doc_rank": hc.get("first_relevant_doc_rank"),
                    "doc_rank_status": _rank_status(
                        dc.get("first_relevant_doc_rank"),
                        hc.get("first_relevant_doc_rank"),
                    ),
                    "lexical_supported": _lexical_supported(hc),
                }
            )
            if dc.get("chunk_labeled"):
                row.update(
                    {
                        "dense_chunk_rank": dc.get("first_relevant_chunk_rank"),
                        "hybrid_chunk_rank": hc.get("first_relevant_chunk_rank"),
                        "chunk_rank_status": _rank_status(
                            dc.get("first_relevant_chunk_rank"),
                            hc.get("first_relevant_chunk_rank"),
                        ),
                    }
                )
        else:
            row["dense_cross_tenant_chunks"] = dc["cross_tenant_chunks"]
            row["hybrid_cross_tenant_chunks"] = hc["cross_tenant_chunks"]
        case_rows.append(row)

    answerable_rows = [r for r in case_rows if r["answerable"]]
    chunk_rows = [r for r in answerable_rows if "chunk_rank_status" in r]

    def ids(rows: list[dict[str, Any]], key: str, status: str) -> list[str]:
        return [r["case_id"] for r in rows if r.get(key) == status]

    summary = {
        "answerable_cases": len(answerable_rows),
        "doc_rank_improved": ids(answerable_rows, "doc_rank_status", "improved"),
        "doc_rank_regressed": ids(answerable_rows, "doc_rank_status", "regressed"),
        "doc_rank_unchanged_count": len(
            ids(answerable_rows, "doc_rank_status", "unchanged")
        ),
        "chunk_labeled_cases": len(chunk_rows),
        "chunk_rank_improved": ids(chunk_rows, "chunk_rank_status", "improved"),
        "chunk_rank_regressed": ids(chunk_rows, "chunk_rank_status", "regressed"),
        "hybrid_only_hits_at_5": [
            r["case_id"]
            for r in answerable_rows
            if r["dense_doc_rank"] is None and r["hybrid_doc_rank"] is not None
        ],
        "hybrid_lost_hits_at_5": [
            r["case_id"]
            for r in answerable_rows
            if r["dense_doc_rank"] is not None and r["hybrid_doc_rank"] is None
        ],
        "lexical_supported_cases": [
            r["case_id"] for r in answerable_rows if r["lexical_supported"]
        ],
        "top5_order_changed_cases": sum(1 for r in case_rows if r["top5_order_changed"]),
        "total_cases": len(case_rows),
    }

    return {
        "metadata": {
            "dataset_id": d_meta["dataset_id"],
            "dataset_version": d_meta["dataset_version"],
            "dense_strategy": d_meta.get("retrieval_strategy"),
            "hybrid_strategy": h_meta.get("retrieval_strategy"),
            "embedding_model": d_meta.get("embedding_model"),
            "k": d_meta.get("k"),
            "database_environment": d_meta.get("database_environment"),
        },
        "aggregate": _compare_metric_dict(
            dense["retrieval_metrics"], hybrid["retrieval_metrics"], AGGREGATE_METRICS
        ),
        "by_category": _compare_groups(
            dense["category_breakdown"], hybrid["category_breakdown"]
        ),
        "by_language": _compare_groups(
            dense.get("language_breakdown", {}), hybrid.get("language_breakdown", {})
        ),
        "by_tag": _compare_groups(
            dense.get("tag_breakdown", {}), hybrid.get("tag_breakdown", {})
        ),
        "summary": summary,
        "cases": case_rows,
    }


def _fmt(value: float | None, pct: bool = True) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%" if pct else f"{value:.4f}"


def _fmt_delta(value: float | None, pct: bool = True) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f}pp" if pct else f"{value:+.4f}"


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render the comparison as a GitHub-flavored Markdown report (deterministic)."""
    meta = comparison["metadata"]
    summary = comparison["summary"]
    lines = [
        f"# So sánh Dense vs Hybrid — `{meta['dataset_id']}` v`{meta['dataset_version']}`",
        "",
        f"- Chiến lược: `{meta['dense_strategy']}` vs `{meta['hybrid_strategy']}`",
        f"- Embedding: `{meta['embedding_model']}` | k={meta['k']} | DB: `{meta['database_environment']}`",
        f"- Số ca: {summary['total_cases']} ({summary['answerable_cases']} có đáp án)",
        "",
        "## 1. Chỉ số tổng hợp",
        "",
        "| Chỉ số | Dense | Hybrid | Δ |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for name, v in comparison["aggregate"].items():
        is_pct = name != "mrr_at_5" and name != "chunk_mrr_at_5"
        lines.append(
            f"| `{name}` | {_fmt(v['dense'], is_pct)} | {_fmt(v['hybrid'], is_pct)} "
            f"| {_fmt_delta(v['delta'], is_pct)} |"
        )

    for title, key in (
        ("2. Theo nhóm kiểm thử (category)", "by_category"),
        ("3. Theo ngôn ngữ truy vấn", "by_language"),
        ("4. Theo thẻ kịch bản (tag)", "by_tag"),
    ):
        groups = comparison[key]
        if not groups:
            continue
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |",
                "| :--- | :---: | :---: | :---: | :---: | :---: |",
            ]
        )
        for name, g in groups.items():
            def pair(metric: str, pct: bool = True, g: dict[str, Any] = g) -> str:
                m = g[metric]
                return f"{_fmt(m['dense'], pct)} → {_fmt(m['hybrid'], pct)}"

            lines.append(
                f"| `{name}` | {g['total']} ({g['answerable']}/{g['refusal']}) "
                f"| {pair('hit_rate_at_1')} | {pair('hit_rate_at_5')} "
                f"| {pair('recall_at_5')} | {pair('mrr_at_5', False)} |"
            )

    def listing(label: str, items: list[str]) -> str:
        return f"- **{label}** ({len(items)}): " + (
            ", ".join(f"`{i}`" for i in items) if items else "_không có_"
        )

    lines.extend(
        [
            "",
            "## 5. Thay đổi thứ hạng theo truy vấn",
            "",
            listing("Cải thiện hạng tài liệu", summary["doc_rank_improved"]),
            listing("Suy giảm hạng tài liệu", summary["doc_rank_regressed"]),
            f"- Không đổi hạng tài liệu: {summary['doc_rank_unchanged_count']}",
            listing("Chỉ Hybrid tìm thấy (Top-5)", summary["hybrid_only_hits_at_5"]),
            listing("Hybrid mất kết quả (Top-5)", summary["hybrid_lost_hits_at_5"]),
            listing("Có đóng góp lexical vào tài liệu đúng", summary["lexical_supported_cases"]),
            listing("Cải thiện hạng chunk", summary["chunk_rank_improved"]),
            listing("Suy giảm hạng chunk", summary["chunk_rank_regressed"]),
            f"- Ca có thứ tự Top-5 khác nhau: {summary['top5_order_changed_cases']}/{summary['total_cases']}",
            "",
            "| Case | Nhóm | Hạng doc D→H | Trạng thái | Hạng chunk D→H | Lexical |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]
    )
    for row in comparison["cases"]:
        if not row["answerable"]:
            continue
        chunk = (
            f"{row['dense_chunk_rank']} → {row['hybrid_chunk_rank']} ({row['chunk_rank_status']})"
            if "chunk_rank_status" in row
            else "—"
        )
        lines.append(
            f"| `{row['case_id']}` | {row['category']} "
            f"| {row['dense_doc_rank']} → {row['hybrid_doc_rank']} "
            f"| {row['doc_rank_status']} | {chunk} "
            f"| {'có' if row['lexical_supported'] else 'không'} |"
        )
    return "\n".join(lines) + "\n"
