"""Deterministic Claim-to-Evidence Citation Grounding Verification (T260041).

Detects cases where an LLM produces syntactically valid [Source N] citations
that do not actually support the factual claims in the answer (e.g. T260040 q01:
citing [Source 2] for "18 ngày nghỉ phép" when that fact only exists in [Source 1]).

Important semantic scope:
- VERIFIED means deterministic fact-anchor matching (numbers, units, dates,
  identifiers, verbatim quotes) with consistent local negation polarity, NOT
  full NLI semantic entailment.
- UNSUPPORTED means cited source(s) clearly lack a required factual anchor, have
  a unit mismatch, have a negation polarity contradiction, or a factual claim
  lacks any [Source N] citation.
- INCONCLUSIVE means automated deterministic verification cannot establish
  support (e.g. pure paraphrase, or derived arithmetic such as 18 + 2 = 20);
  never falsely rejected as unsupported, and never falsely labeled as verified.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from app.services.context_builder import ContextSource

_CITATION_MARKER_RE = re.compile(r"\[Source\s+([1-9][0-9]*)\]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<!\d)[.!?](?!\d)\s+|\n+")

# Numbers including Vietnamese dot-thousands (1.200.000), comma-thousands (1,200,000),
# decimals (1,2 / 1.5), and optional Vietnamese/English scale words + units.
_NUMBER_WITH_UNIT_RE = re.compile(
    r"(?<![a-zA-Z0-9_#/])"
    r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?:\s*(triệu|nghìn|ngàn|tỷ|k))?"
    r"(?:\s*(%|ngày|giờ|phút|giây|tuần|tháng|năm|đồng|vnd|usd|gb|mb|kb|tb|lần|người))?"
    r"(?![a-zA-Z0-9_])",
    flags=re.IGNORECASE,
)

# Date patterns: "31 tháng 3", "31/3", "31/03", "31-03-2026"
_DATE_TEXT_RE = re.compile(r"\b(\d{1,2})\s+tháng\s+(\d{1,2})(?:\s+năm\s+(\d{4}))?\b", re.IGNORECASE)
_DATE_SLASH_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")

# Identifiers: #channel, uppercase codes with digits/hyphens (SEV3, RPO, HTTP-503, T260040)
_CHANNEL_RE = re.compile(r"#[a-zA-Z0-9_-]{2,}")
_CODE_IDENTIFIER_RE = re.compile(r"\b(?:[A-Z]{2,}[0-9]+|[A-Z]+-[A-Z0-9-]+|RPO|RTO|SLA|API|SQL|ACID|MVCC|HNSW)\b")

# Verbatim quotations
_QUOTE_RE = re.compile(r'"([^"]{8,})"|«([^»]{8,})»')
_NEGATION_RE = re.compile(
    r"(?<!\w)(?:không|chưa|cấm|not|never|cannot|can't|won't|doesn't|don't|isn't|aren't)(?!\w)",
    flags=re.IGNORECASE,
)

_SCALE_MULTIPLIERS = {
    "triệu": 1_000_000,
    "nghìn": 1_000,
    "ngàn": 1_000,
    "k": 1_000,
    "tỷ": 1_000_000_000,
}

_UNIT_ALIASES = {
    "vnđ": "đồng",
    "vnd": "đồng",
    "đ": "đồng",
    "ngàn": "nghìn",
}


class GroundingStatus(str, Enum):
    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class ClaimGroundingResult:
    claim_text: str
    cited_indices: tuple[int, ...]
    status: GroundingStatus
    matched_anchors: tuple[str, ...]
    missing_anchors: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class AnswerGroundingResult:
    status: GroundingStatus
    is_grounded: bool
    claims: tuple[ClaimGroundingResult, ...]
    unsupported_claims: tuple[ClaimGroundingResult, ...]
    latency_ms: float = 0.0


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def _parse_numeric_value(raw_num: str, scale: str | None) -> float | None:
    """Parse Vietnamese/English formatted numbers into a canonical float."""
    cleaned = raw_num.strip()
    if not cleaned:
        return None

    # Pattern like 1.200.000 or 1,200,000 (thousand separators)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
        base = float(cleaned.replace(".", ""))
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", cleaned):
        base = float(cleaned.replace(",", ""))
    else:
        # Decimal like 1,2 or 1.5
        base = float(cleaned.replace(",", "."))

    if scale:
        mult = _SCALE_MULTIPLIERS.get(scale.lower())
        if mult:
            base *= mult
    return base


def _normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.lower().strip()
    return _UNIT_ALIASES.get(u, u)


def _extract_dates(text: str) -> set[tuple[int, int]]:
    dates: set[tuple[int, int]] = set()
    for m in _DATE_TEXT_RE.finditer(text):
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            dates.add((day, month))
    for m in _DATE_SLASH_RE.finditer(text):
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            dates.add((day, month))
    return dates


def _extract_numbers_and_units(text: str) -> list[tuple[float, str | None, str]]:
    """Return list of (numeric_value, normalized_unit, raw_span)."""
    # Mask out date spans so date digits (31/3, 31 tháng 3) aren't double-counted as standalone numbers
    masked = _DATE_TEXT_RE.sub(" ", text)
    masked = _DATE_SLASH_RE.sub(" ", masked)

    items: list[tuple[float, str | None, str]] = []
    for m in _NUMBER_WITH_UNIT_RE.finditer(masked):
        raw_num, scale, unit = m.group(1), m.group(2), m.group(3)
        val = _parse_numeric_value(raw_num, scale)
        if val is not None:
            items.append((val, _normalize_unit(unit), m.group(0).strip()))
    return items


def _numbers_match(a: float, b: float) -> bool:
    if a == b:
        return True
    if a == 0 or b == 0:
        return False
    return abs(a - b) <= 1e-6 * max(abs(a), abs(b))


def _is_derived_two_operand(
    target: float,
    target_unit: str | None,
    evidence_nums: list[tuple[float, str | None, str]],
) -> bool:
    """Check if target equals a + b or a - b for two distinct numbers in evidence."""
    pool = [
        ev[0]
        for ev in evidence_nums
        if target_unit is None or ev[1] is None or ev[1] == target_unit
    ]
    n = len(pool)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = pool[i], pool[j]
            if _numbers_match(target, a + b) or _numbers_match(target, abs(a - b)):
                return True
    return False


def _has_factual_anchors(text: str) -> bool:
    norm = _normalize_text(text)
    return bool(
        _extract_dates(norm)
        or _extract_numbers_and_units(norm)
        or _CHANNEL_RE.search(norm)
        or _CODE_IDENTIFIER_RE.search(text)
        or _QUOTE_RE.search(text)
    )


def _negation_contradicts(
    norm_claim: str,
    norm_evidence: str,
    matched_spans: list[str],
) -> bool:
    """Compare negation polarity between claim and evidence sentences holding matched anchors."""
    if not matched_spans:
        return False
    claim_neg = bool(_NEGATION_RE.search(norm_claim))
    ev_sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(norm_evidence) if s.strip()]
    anchor_sentences = [
        s for s in ev_sentences if any(sp.lower() in s for sp in matched_spans)
    ]
    if not anchor_sentences:
        return False
    ev_neg = any(bool(_NEGATION_RE.search(s)) for s in anchor_sentences)
    return claim_neg != ev_neg


def _verify_claim_against_evidence(
    claim_text: str,
    cited_indices: tuple[int, ...],
    evidence_text: str,
) -> ClaimGroundingResult:
    norm_claim = _normalize_text(claim_text)
    norm_evidence = _normalize_text(evidence_text)

    matched: list[str] = []
    missing: list[str] = []
    derived_anchors: list[str] = []

    # 1. Dates
    claim_dates = _extract_dates(norm_claim)
    evidence_dates = _extract_dates(norm_evidence)
    for d in sorted(claim_dates):
        label = f"date:{d[0]}/{d[1]}"
        if d in evidence_dates:
            matched.append(label)
        else:
            missing.append(label)

    # 2. Numbers & units
    claim_nums = _extract_numbers_and_units(norm_claim)
    evidence_nums = _extract_numbers_and_units(norm_evidence)
    for val, unit, raw_span in claim_nums:
        val_str = str(int(val)) if val.is_integer() else str(val)
        anchor_label = f"num:{val_str}" + (f"_{unit}" if unit else "")

        matching_ev = [ev for ev in evidence_nums if _numbers_match(val, ev[0])]
        if not matching_ev:
            if _is_derived_two_operand(val, unit, evidence_nums):
                derived_anchors.append(anchor_label)
            else:
                missing.append(anchor_label)
            continue

        if unit is not None:
            ev_units = {ev[1] for ev in matching_ev if ev[1] is not None}
            if ev_units and unit not in ev_units:
                missing.append(f"{anchor_label}(unit_mismatch_vs_{','.join(sorted(ev_units))})")
                continue

        matched.append(raw_span)

    # 3. Channel & Code Identifiers
    for m in _CHANNEL_RE.finditer(norm_claim):
        ch = m.group(0)
        if ch in norm_evidence:
            matched.append(ch)
        else:
            missing.append(f"id:{ch}")

    for m in _CODE_IDENTIFIER_RE.finditer(claim_text):
        code = m.group(0)
        if code in evidence_text or code.lower() in norm_evidence:
            matched.append(code)
        else:
            missing.append(f"code:{code}")

    # 4. Verbatim quotes
    for m in _QUOTE_RE.finditer(claim_text):
        q = (m.group(1) or m.group(2) or "").strip()
        if _normalize_text(q) in norm_evidence:
            matched.append(f"quote:{q[:24]}")
        else:
            missing.append(f"quote:{q[:24]}")

    if missing:
        return ClaimGroundingResult(
            claim_text=claim_text,
            cited_indices=cited_indices,
            status=GroundingStatus.UNSUPPORTED,
            matched_anchors=tuple(matched),
            missing_anchors=tuple(missing),
            reason=f"Missing or mismatched factual anchors in cited source(s) {list(cited_indices)}: {', '.join(missing)}",
        )

    if derived_anchors:
        return ClaimGroundingResult(
            claim_text=claim_text,
            cited_indices=cited_indices,
            status=GroundingStatus.INCONCLUSIVE,
            matched_anchors=tuple(matched),
            missing_anchors=(),
            reason=f"Derived arithmetic anchors ({', '.join(derived_anchors)}) require reasoning over source numbers.",
        )

    if matched and _negation_contradicts(norm_claim, norm_evidence, matched):
        return ClaimGroundingResult(
            claim_text=claim_text,
            cited_indices=cited_indices,
            status=GroundingStatus.UNSUPPORTED,
            matched_anchors=tuple(matched),
            missing_anchors=("polarity_contradiction",),
            reason="Negation polarity contradiction between claim and cited source sentence.",
        )

    if matched:
        return ClaimGroundingResult(
            claim_text=claim_text,
            cited_indices=cited_indices,
            status=GroundingStatus.VERIFIED,
            matched_anchors=tuple(matched),
            missing_anchors=(),
            reason="All deterministic factual anchors matched in cited source(s).",
        )

    return ClaimGroundingResult(
        claim_text=claim_text,
        cited_indices=cited_indices,
        status=GroundingStatus.INCONCLUSIVE,
        matched_anchors=(),
        missing_anchors=(),
        reason="No deterministic numeric, date, identifier, or quote anchors in claim.",
    )


def verify_answer_grounding(
    answer: str,
    sources: list[ContextSource],
) -> AnswerGroundingResult:
    """Verify that cited sources actually support the claims in the generated answer."""
    import time

    t0 = time.perf_counter()

    source_map = {s.source_index: s for s in sources}
    raw_segments = [seg.strip() for seg in _SENTENCE_SPLIT_RE.split(answer) if seg.strip()]

    # Merge citation-only segments (e.g. "... mỗi năm. [Source 2]") onto the preceding sentence
    merged_segments: list[str] = []
    for seg in raw_segments:
        clean_seg = _CITATION_MARKER_RE.sub("", seg).strip()
        if not clean_seg and _CITATION_MARKER_RE.search(seg) and merged_segments:
            merged_segments[-1] = f"{merged_segments[-1]} {seg}"
        else:
            merged_segments.append(seg)

    claim_results: list[ClaimGroundingResult] = []
    for seg in merged_segments:
        cited = []
        for m in _CITATION_MARKER_RE.finditer(seg):
            idx = int(m.group(1))
            if idx not in cited:
                cited.append(idx)

        if not cited:
            if _has_factual_anchors(seg):
                claim_results.append(
                    ClaimGroundingResult(
                        claim_text=seg,
                        cited_indices=(),
                        status=GroundingStatus.UNSUPPORTED,
                        matched_anchors=(),
                        missing_anchors=("citation_missing",),
                        reason="Factual claim contains verifiable anchors but has no [Source N] citation.",
                    )
                )
            continue

        clean_claim = _CITATION_MARKER_RE.sub("", seg).strip()
        if not clean_claim:
            continue

        # Check that all cited indices exist in current response sources
        missing_idx = [idx for idx in cited if idx not in source_map]
        if missing_idx:
            claim_results.append(
                ClaimGroundingResult(
                    claim_text=clean_claim,
                    cited_indices=tuple(cited),
                    status=GroundingStatus.UNSUPPORTED,
                    matched_anchors=(),
                    missing_anchors=tuple(f"source_index:{i}" for i in missing_idx),
                    reason=f"Cited source index {missing_idx} not present in response context.",
                )
            )
            continue

        combined_evidence = "\n".join(source_map[idx].content for idx in cited)
        claim_results.append(
            _verify_claim_against_evidence(clean_claim, tuple(cited), combined_evidence)
        )

    unsupported = tuple(c for c in claim_results if c.status == GroundingStatus.UNSUPPORTED)
    if unsupported:
        overall = GroundingStatus.UNSUPPORTED
        is_grounded = False
    elif claim_results and all(c.status == GroundingStatus.VERIFIED for c in claim_results):
        overall = GroundingStatus.VERIFIED
        is_grounded = True
    else:
        overall = GroundingStatus.INCONCLUSIVE
        is_grounded = True

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    return AnswerGroundingResult(
        status=overall,
        is_grounded=is_grounded,
        claims=tuple(claim_results),
        unsupported_claims=unsupported,
        latency_ms=latency_ms,
    )
