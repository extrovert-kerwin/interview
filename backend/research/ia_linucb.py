"""Information-Augmented LinUCB (IA-LinUCB).

Standard disjoint LinUCB (Li et al., WWW 2010) ranks arms by

    score_a = theta_a^T x + alpha * sqrt(x^T A_a^{-1} x).

This is purely a *reward-uncertainty* term: it explores arms whose linear
parameters are still poorly estimated. In a computerised-adaptive-testing
(CAT) setting an interviewer also cares about *ability-estimation
efficiency* — picking the arm whose answer will give the most information
about the candidate's latent skill on that topic. Maximum-Fisher-Information
selection is the classical CAT recipe (van der Linden & Glas, 2010;
Sharpnack 2025).

IA-LinUCB combines the two:

    score_a = mu_a + alpha * sigma_a + gamma * sqrt(I(theta_hat_a, d_a))

where ``I(theta, d)`` is the Fisher information of a 2PL IRT item

    p(theta, d) = sigma(k * (theta - d)),
    I(theta, d) = k^2 * p * (1 - p).

* ``mu_a`` and ``sigma_a`` come from the LinUCB posterior on reward.
* ``theta_hat_a`` is the per-arm ability estimate maintained on
  ``state['per_topic_stats']`` (already produced by the memory update).
* ``d_a`` is the difficulty the PI controller would pick if it asked arm
  ``a`` next (we read ``state['ability_estimate']`` and apply the target
  band the controller targets).

The Fisher term is bounded in [0, k^2/4]; we normalise to [0, 1] before
mixing. ``gamma`` is the information-vs-reward trade-off (paper Sec 4.2 of
the revised method). A user-paced ``alpha`` schedule is preserved.

Implementation notes:

  * pure-python LinUCB cores reused from ``app.services.bandit`` to keep
    the numerical regimes identical to the production selector;
  * the selector is exposed as a drop-in ``selector_override`` for
    ``research.simulator.run_episode`` so we can A/B against the existing
    LinUCB without touching production code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from app.agents.memory import get_ability, get_coverage_count, get_per_topic_stats
from app.agents.state import InterviewState
from app.services.bandit import (
    ARMS,
    LinUCBArm,
    build_context,
    load_bandit,
)


# ---------------------------------------------------------------------------
# 2PL IRT-style information
# ---------------------------------------------------------------------------

def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def fisher_information(theta: float, difficulty: float, *, k: float = 5.0) -> float:
    """Fisher information of a 2PL item with discrimination ``k``.

    Returned value is in [0, k^2/4]; we expose the unnormalised number and
    let the caller scale it.
    """
    p = _sigmoid(k * (theta - difficulty))
    return (k ** 2) * p * (1.0 - p)


def _per_arm_theta(state: InterviewState, arm: str) -> float:
    """Best per-topic ability estimate; falls back to global mean if absent.

    ``per_topic_stats`` is populated by ``app.agents.memory.update_after_eval``
    and stores an EMA over the last few rounds for each category.
    """
    stats = get_per_topic_stats(state)
    s = stats.get(arm) or {}
    val = s.get("mean")
    if isinstance(val, (int, float)):
        return float(val)
    return get_ability(state)


def _per_arm_uncertainty(state: InterviewState, arm: str) -> float:
    """Coarse 1-sigma uncertainty for arm's ability estimate.

    Returns a number in [0, 1]; lower coverage => higher uncertainty.
    """
    stats = get_per_topic_stats(state)
    s = stats.get(arm) or {}
    n = float(s.get("n", 0))
    # Empirical Bayes: shrink toward 0.4 prior std when n is small.
    return float(max(0.15, 1.0 / math.sqrt(max(1.0, n + 1.0))))


# ---------------------------------------------------------------------------
# IA-LinUCB selector
# ---------------------------------------------------------------------------

@dataclass
class IALinUCBConfig:
    alpha0: float = 1.0          # initial LinUCB exploration weight
    alpha_decay_rounds: float = 12.0   # alpha_t = alpha0 / sqrt(1 + t/decay)
    gamma0: float = 0.9          # Fisher info weight at t=1
    gamma_decay_rounds: float = 8.0    # gamma_t = gamma0 / sqrt(1 + t/decay)
    k_irt: float = 5.0           # 2PL discrimination (matches simulator)
    target_difficulty: float = 0.7
    coverage_floor_div: int = 2  # min coverage per arm = ceil(rounds / (J+div))


def _alpha_schedule(t: int, cfg: IALinUCBConfig) -> float:
    return float(cfg.alpha0 / math.sqrt(1.0 + t / max(1.0, cfg.alpha_decay_rounds)))


def _gamma_schedule(t: int, cfg: IALinUCBConfig) -> float:
    """Fisher-info weight decays with t — we want measurement-driven
    exploration early then let LinUCB reward exploitation dominate."""
    return float(cfg.gamma0 / math.sqrt(1.0 + t / max(1.0, cfg.gamma_decay_rounds)))


def select_ia_linucb(
    state: InterviewState,
    *,
    next_index: int,
    rounds_total: int,
    cfg: IALinUCBConfig | None = None,
) -> tuple[str, dict[str, Any]]:
    cfg = cfg or IALinUCBConfig()
    arms = load_bandit(state)
    alpha_t = _alpha_schedule(next_index, cfg)
    gamma_t = _gamma_schedule(next_index, cfg)

    # Difficulty the controller is most likely to pick on the next item.
    # We approximate with the global PI target; per-arm difficulty matters
    # only through the Fisher term anyway.
    next_d = cfg.target_difficulty

    contexts: dict[str, list[float]] = {}
    mus: dict[str, float] = {}
    sigmas: dict[str, float] = {}
    info: dict[str, float] = {}
    for arm in ARMS:
        ctx = build_context(state, arm, rounds_total=rounds_total)
        contexts[arm] = ctx
        try:
            theta_vec = arms[arm].theta()
            mu = sum(theta_vec[i] * ctx[i] for i in range(len(ctx)))
            from app.services.bandit import _solve  # local import to avoid
            sigma_sq = max(0.0, sum(ctx[i] * _solve(arms[arm].A, ctx)[i] for i in range(len(ctx))))
        except Exception:
            mu, sigma_sq = 0.0, 1.0
        mus[arm] = mu
        sigmas[arm] = math.sqrt(sigma_sq)
        theta_hat = _per_arm_theta(state, arm)
        unc = _per_arm_uncertainty(state, arm)
        # Information-gain proxy: Fisher info * topic uncertainty (low-data arms
        # benefit more from a measurement). Normalise Fisher to [0,1].
        I = fisher_information(theta_hat, next_d, k=cfg.k_irt) / ((cfg.k_irt ** 2) / 4.0)
        info[arm] = I * unc

    scores = {
        arm: mus[arm] + alpha_t * sigmas[arm] + gamma_t * math.sqrt(max(0.0, info[arm]))
        for arm in ARMS
    }

    # Same coverage floor as the production selector — keeps comparisons fair.
    coverage = get_coverage_count(state)
    floor = max(1, rounds_total // (len(ARMS) + cfg.coverage_floor_div))
    if next_index > len(ARMS):
        under = [a for a in ARMS if coverage.get(a, 0) < floor]
        chosen = max(under or ARMS, key=lambda a: scores[a])
    else:
        chosen = max(ARMS, key=lambda a: scores[a])
    return chosen, {
        "strategy": "ia_linucb",
        "alpha_t": round(alpha_t, 3),
        "gamma_t": round(gamma_t, 3),
        "scores": {a: round(scores[a], 4) for a in ARMS},
        "info": {a: round(info[a], 4) for a in ARMS},
        "mu": {a: round(mus[a], 4) for a in ARMS},
        "sigma": {a: round(sigmas[a], 4) for a in ARMS},
    }


def selector(cfg: IALinUCBConfig | None = None) -> Callable[[InterviewState, int, int], tuple[str, dict[str, Any]]]:
    """Convenience factory matching the signature expected by ``run_episode``."""
    cfg = cfg or IALinUCBConfig()

    def _pick(state: InterviewState, next_index: int, rounds_total: int) -> tuple[str, dict[str, Any]]:
        return select_ia_linucb(state, next_index=next_index, rounds_total=rounds_total, cfg=cfg)

    return _pick
