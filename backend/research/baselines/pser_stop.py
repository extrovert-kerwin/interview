"""PSER (Predicted Standard-Error Reduction) credible-interval termination.

Choi et al. (2011) define a CAT stopping rule:

    stop after item t   iff  SE(theta_hat_t)  <  threshold,
    where SE(theta_hat_t) = 1 / sqrt( sum_{s<=t} I(theta_hat_s, d_s) ).

In our setting we maintain a running posterior over per-arm abilities; we
expose two stopping flavours so the harness can compare them:

  * ``fixed_budget`` — terminate after ``rounds`` items unconditionally
    (matches the production behaviour).
  * ``pser`` — terminate as soon as the *global* SE falls below
    ``se_threshold`` AND every arm has been visited at least
    ``min_coverage_per_arm`` times.

The PSER rule has the virtue of finishing fast on low-noise candidates
while spending extra items on ambiguous ones. We use it in §6 of the
revised method as the "flow improvement" baseline / target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PSERConfig:
    se_threshold: float = 0.20
    min_coverage_per_arm: int = 2
    max_rounds: int = 14
    k_irt: float = 5.0


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def fisher(theta: float, d: float, *, k: float) -> float:
    p = _sigmoid(k * (theta - d))
    return (k ** 2) * p * (1.0 - p)


def should_stop(
    *,
    round_idx: int,
    info_sum: float,
    per_arm_coverage: dict[str, int],
    cfg: PSERConfig,
) -> tuple[bool, dict]:
    if round_idx >= cfg.max_rounds:
        return True, {"reason": "max_rounds"}
    if any(c < cfg.min_coverage_per_arm for c in per_arm_coverage.values()):
        return False, {"reason": "coverage_floor"}
    if info_sum <= 0:
        return False, {"reason": "no_info"}
    se = 1.0 / math.sqrt(info_sum)
    if se <= cfg.se_threshold:
        return True, {"reason": "se_below_threshold", "se": round(se, 4)}
    return False, {"reason": "se_above_threshold", "se": round(se, 4)}
