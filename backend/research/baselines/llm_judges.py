"""LLM-as-judge baselines.

These simulate the *recipes* that recent LLM-eval papers describe, on top
of the same noisy/biased judge panel used by the rest of the harness. We
do not actually call an LLM here — every baseline is a parametric model
of how that recipe would re-process the panel's per-dim scores so the
comparison is apples-to-apples with our RW-MJ and DS / MACE numbers.

  * ``single_judge_cot`` — one CoT-prompted judge (Zheng et al. 2023).
  * ``majority_vote``    — discretise scores to a 5-point scale and pick
    the mode (Wang et al. 2024).
  * ``geval``            — probability-weighted scoring (Liu et al. 2023):
    sample multiple decodes per dim and average; we model multi-sample
    via repeated draws with reduced noise.
  * ``poll_jury``        — Verga et al. (2024) "Panel of LLM evaluators"
    with diversity bonus: average across judges, then small calibration
    shift from a reference scorer.
  * ``self_consistency_cot`` — Wang et al. 2024 self-consistency: K CoT
    rollouts per judge, majority vote per dim, then averaged.
  * ``prometheus2_style`` — Kim et al. 2024 reference-grounded: assume a
    rubric anchor (high-quality reference answer) reduces per-judge noise
    by a fixed multiplier.

Every baseline returns a unit-scale score in [0,1]. The same calibrator
plug-in used elsewhere can be applied on top.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np


def _per_dim_to_per_judge(per_dim: dict[str, list[float]], rubric_weights: dict[str, float]) -> list[float]:
    """Collapse per-dim per-judge scores to one number per judge by applying
    rubric weights. Input scores are in [0, 100]; output is in [0, 1].
    """
    n_judges = max(len(v) for v in per_dim.values()) if per_dim else 0
    out = []
    for j in range(n_judges):
        total = 0.0
        for d, scores in per_dim.items():
            if j < len(scores):
                total += (scores[j] / 100.0) * rubric_weights.get(d, 0.0)
        out.append(total)
    return out


def single_judge_cot(per_dim: dict[str, list[float]], rubric_weights: dict[str, float]) -> float:
    """First judge with CoT prompt — the most common LLM-as-judge default."""
    return _per_dim_to_per_judge(per_dim, rubric_weights)[0]


def majority_vote(per_dim: dict[str, list[float]], rubric_weights: dict[str, float], *, levels: int = 5) -> float:
    """Discretise to 5 levels per dim, pick the mode, then average."""
    out = 0.0
    for dim, scores in per_dim.items():
        bins = [int(round(s / 100.0 * (levels - 1))) for s in scores]
        cnt = Counter(bins)
        mode_val, _ = cnt.most_common(1)[0]
        out += (mode_val / (levels - 1)) * rubric_weights.get(dim, 0.0)
    return out


def geval(
    per_dim: dict[str, list[float]],
    rubric_weights: dict[str, float],
    *,
    n_samples: int = 5,
    sample_jitter: float = 0.04,
    rng: np.random.Generator | None = None,
) -> float:
    """G-Eval probability-weighted score (Liu et al. 2023).

    Approximation: each judge emits ``n_samples`` near-copies (probability
    distribution over score levels). We average them per judge then average
    across judges. Equivalent to noise-averaging the panel.
    """
    rng = rng or np.random.default_rng(0)
    out = 0.0
    for dim, scores in per_dim.items():
        per_judge_means = []
        for s in scores:
            unit = max(0.0, min(1.0, s / 100.0))
            draws = np.clip(unit + rng.normal(0, sample_jitter, size=n_samples), 0.0, 1.0)
            per_judge_means.append(float(np.mean(draws)))
        out += float(np.mean(per_judge_means)) * rubric_weights.get(dim, 0.0)
    return out


def poll_jury(per_dim: dict[str, list[float]], rubric_weights: dict[str, float], *, ref_shift: float = -0.015) -> float:
    """Verga et al. 2024 PoLL: mean over panel + a small reference-driven
    calibration shift to undo the panel's average over-confidence."""
    out = 0.0
    for dim, scores in per_dim.items():
        mean_unit = float(np.mean(scores) / 100.0)
        out += max(0.0, min(1.0, mean_unit + ref_shift)) * rubric_weights.get(dim, 0.0)
    return out


def self_consistency_cot(
    per_dim: dict[str, list[float]],
    rubric_weights: dict[str, float],
    *,
    n_rollouts: int = 5,
    rollout_jitter: float = 0.03,
    levels: int = 5,
    rng: np.random.Generator | None = None,
) -> float:
    """Wang et al. 2024 self-consistency over CoT decodes.

    Per judge: ``n_rollouts`` discretised samples, vote for mode; then
    average across judges. Levels = 5 (matches our rubric coarse-grain).
    """
    rng = rng or np.random.default_rng(0)
    out = 0.0
    for dim, scores in per_dim.items():
        votes_per_judge = []
        for s in scores:
            unit = max(0.0, min(1.0, s / 100.0))
            draws = np.clip(unit + rng.normal(0, rollout_jitter, size=n_rollouts), 0.0, 1.0)
            binned = [int(round(d * (levels - 1))) for d in draws]
            mode_val, _ = Counter(binned).most_common(1)[0]
            votes_per_judge.append(mode_val / (levels - 1))
        out += float(np.mean(votes_per_judge)) * rubric_weights.get(dim, 0.0)
    return out


def prometheus2_style(
    per_dim: dict[str, list[float]],
    rubric_weights: dict[str, float],
    *,
    noise_reduction: float = 0.4,
) -> float:
    """Reference-grounded scoring (Kim et al. 2024 Prometheus 2).

    Approximation: assume an anchor reference answer pulls each judge
    toward the inverse-variance mean by ``noise_reduction``. We compute
    the inverse-variance mean (assuming all judges share the noise) then
    shrink each judge's score toward it.
    """
    out = 0.0
    for dim, scores in per_dim.items():
        arr = np.array(scores) / 100.0
        ref = float(np.mean(arr))
        shrunk = arr * (1.0 - noise_reduction) + ref * noise_reduction
        out += float(np.mean(shrunk)) * rubric_weights.get(dim, 0.0)
    return out
