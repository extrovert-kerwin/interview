"""Critic / validator for LLM judge outputs.

Implements two layers:
  1. Schema + range validation for a single LLM judge response.
  2. Cross-judge consistency check for an aggregated multi-judge ensemble.

Both layers return a ``ValidationResult`` so the caller can decide whether to
keep the judge, drop it, or trigger a rule-based fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


REQUIRED_DIMENSIONS = (
    "relevance",
    "knowledge",
    "specificity",
    "reasoning",
    "completeness",
    "reflection",
    "follow_up",
)


@dataclass
class ValidationResult:
    ok: bool
    issues: list[str] = field(default_factory=list)
    clamped: bool = False
    score: float | None = None

    def fail(self, msg: str) -> "ValidationResult":
        self.ok = False
        self.issues.append(msg)
        return self


def validate_single_judge(parsed: Any) -> ValidationResult:
    """Schema + value-range check on a single judge JSON object."""
    res = ValidationResult(ok=True)
    if not isinstance(parsed, dict):
        return res.fail("not_a_dict")
    raw = parsed.get("rubric_scores")
    if not isinstance(raw, dict):
        return res.fail("missing_rubric_scores")
    found = 0
    for dim in REQUIRED_DIMENSIONS:
        entry = raw.get(dim)
        if entry is None:
            res.issues.append(f"missing_dim:{dim}")
            continue
        score = entry.get("score") if isinstance(entry, dict) else entry
        if not isinstance(score, (int, float)):
            res.issues.append(f"non_numeric:{dim}")
            continue
        if not 0 <= float(score) <= 100:
            res.clamped = True
            res.issues.append(f"out_of_range:{dim}")
        found += 1
    if found < len(REQUIRED_DIMENSIONS) // 2:
        return res.fail("too_few_dimensions")
    return res


def cross_judge_consistency(
    per_dim_scores: dict[str, list[float]],
    *,
    max_spread: float = 45.0,
) -> ValidationResult:
    """Flag a multi-judge ensemble whose disagreement is pathologically large.

    ``max_spread`` is the largest tolerated max-min spread per dimension on a
    0-100 scale. Anything larger usually means one judge misread the question.
    """
    res = ValidationResult(ok=True)
    flagged = 0
    for dim, scores in per_dim_scores.items():
        if len(scores) < 2:
            continue
        spread = max(scores) - min(scores)
        if spread > max_spread:
            res.issues.append(f"high_spread:{dim}:{spread:.1f}")
            flagged += 1
    if flagged >= max(2, len(per_dim_scores) // 2):
        return res.fail("ensemble_inconsistent")
    return res
