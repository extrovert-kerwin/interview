"""Contextual bandit for interview question-category selection.

Implements two policies used by the experiments in the paper:

  * ``round_robin`` — deterministic baseline (legacy ``CATEGORY_ORDER``).
  * ``linucb``      — disjoint LinUCB (Li et al., WWW 2010) with a small
    handcrafted feature vector per (state, arm).
  * ``thompson``    — Beta-Bernoulli Thompson sampling on coarse reward bins,
    kept as a non-contextual baseline.

Reward shaping (paper §4.2):

    r = w_score * (1 - |score - target|)            # difficulty match
      + w_cov   * (1 - coverage_ratio[c])           # coverage incentive
      + w_gap   * gap_density[c]                     # gap-driven exploration
      + w_res   * resume_affinity[c]                 # resume alignment

The bandit's serialisable state lives on ``InterviewState['bandit_state']`` so
it survives JSON round-trips. We deliberately keep numpy out of the API and
fall back to plain lists; the closed-form 6×6 inverse is cheap and avoids a
hard dependency on a heavy lib.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.agents.memory import (
    CATEGORIES,
    get_ability,
    get_coverage_count,
    get_gap_set,
    get_per_topic_stats,
    get_score_window,
)
from app.agents.state import InterviewState
from app.config import get_settings

ARMS: tuple[str, ...] = CATEGORIES
CTX_DIM: int = 6  # [bias, ability, coverage_ratio, topic_mean, gap_affinity, recency]

# IA-LinUCB import is deferred because research.ia_linucb imports BACK from
# this module (ARMS, LinUCBArm, build_context), creating a load-time cycle.
# We resolve the import on first dispatch and cache the result so subsequent
# selects pay no import cost. The flag is publicly read by /healthz/algorithms
# so an operator can verify the module is wired up before exercising the path.
#
# Critical design point: only ImportError-class failures (module missing /
# package not present in a slim deploy) trigger the silent fallback below.
# Runtime errors from select_ia_linucb itself are NOT swallowed — an operator
# who set SELECTOR_STRATEGY=ia_linucb actually hears about bugs instead of
# silently getting vanilla LinUCB.
_IA_LINUCB_AVAILABLE: bool | None = None  # tri-state: None=unresolved
_IALinUCBConfig: Any = None
_select_ia_linucb: Any = None


def _resolve_ia_linucb() -> bool:
    """Resolve the IA-LinUCB import lazily; cache the outcome."""
    global _IA_LINUCB_AVAILABLE, _IALinUCBConfig, _select_ia_linucb
    if _IA_LINUCB_AVAILABLE is not None:
        return _IA_LINUCB_AVAILABLE
    try:
        from research.ia_linucb import (  # type: ignore
            IALinUCBConfig as _Cfg,
            select_ia_linucb as _Sel,
        )
        _IALinUCBConfig = _Cfg
        _select_ia_linucb = _Sel
        _IA_LINUCB_AVAILABLE = True
    except ImportError:  # genuine "module not on path" / "package missing" case
        _IA_LINUCB_AVAILABLE = False
    return _IA_LINUCB_AVAILABLE

# Numpy-free linear algebra ---------------------------------------------------

def _eye(n: int, lam: float = 1.0) -> list[list[float]]:
    return [[lam if i == j else 0.0 for j in range(n)] for i in range(n)]


def _matvec(A: list[list[float]], x: Sequence[float]) -> list[float]:
    return [sum(A[i][j] * x[j] for j in range(len(x))) for i in range(len(A))]


def _outer(x: Sequence[float], y: Sequence[float]) -> list[list[float]]:
    return [[x[i] * y[j] for j in range(len(y))] for i in range(len(x))]


def _add(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    return [[A[i][j] + B[i][j] for j in range(len(A))] for i in range(len(A))]


def _scale(A: list[list[float]], s: float) -> list[list[float]]:
    return [[A[i][j] * s for j in range(len(A))] for i in range(len(A))]


def _dot(x: Sequence[float], y: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(x, y))


def _solve(A: list[list[float]], b: Sequence[float]) -> list[float]:
    """Solve A x = b via Gauss-Jordan with partial pivoting (small dims)."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        # pivot
        pivot = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot][col]) < 1e-12:
            M[pivot][col] = 1e-12  # ridge-style stabilisation
        M[col], M[pivot] = M[pivot], M[col]
        piv = M[col][col]
        M[col] = [v / piv for v in M[col]]
        for r in range(n):
            if r == col:
                continue
            factor = M[r][col]
            if factor == 0:
                continue
            M[r] = [M[r][k] - factor * M[col][k] for k in range(n + 1)]
    return [M[i][n] for i in range(n)]


# Feature construction --------------------------------------------------------

def _topic_mean(stats: dict[str, dict[str, Any]], cat: str) -> float:
    s = stats.get(cat) or {}
    val = s.get("mean")
    if isinstance(val, (int, float)):
        return float(val)
    return 0.55


def _resume_affinity(profile: dict | None, category: str) -> float:
    """Quick token-overlap proxy: does the resume mention this category at all?"""
    if not profile:
        return 0.4
    haystack = " ".join([
        " ".join(profile.get("skills") or []),
        " ".join(p.get("name", "") + " " + p.get("summary", "") for p in (profile.get("projects") or []) if isinstance(p, dict)),
        profile.get("summary", "") if isinstance(profile.get("summary"), str) else "",
    ]).lower()
    keywords = {
        "技术深度": ["python", "java", "go", "rust", "算法", "原理", "底层", "性能", "深度"],
        "项目经验": ["项目", "上线", "产品", "feature", "项目经历"],
        "系统设计": ["架构", "高并发", "分布式", "微服务", "可观测", "稳定性", "云原生"],
        "沟通表达": ["协作", "沟通", "对齐", "评审", "推动", "团队"],
        "学习能力": ["学习", "新技术", "调研", "持续", "成长", "开源", "前沿"],
    }
    hits = sum(1 for kw in keywords.get(category, []) if kw in haystack)
    return min(1.0, hits / 3.0)


def build_context(
    state: InterviewState,
    arm: str,
    *,
    rounds_total: int,
) -> list[float]:
    """6-dim feature for the (state, arm) pair used by LinUCB."""
    ability = get_ability(state)
    coverage = get_coverage_count(state)
    stats = get_per_topic_stats(state)
    profile = state.get("resume_profile") or {}

    total_count = max(1, sum(coverage.values()))
    cov_ratio = coverage.get(arm, 0) / total_count
    topic_mean = _topic_mean(stats, arm)
    gaps = get_gap_set(state)
    gap_affinity = min(1.0, len(gaps) / 8.0)
    chap = list(state.get("chapter_trajectory") or [])
    last_pos = max([i for i, c in enumerate(chap) if c == arm], default=-1)
    recency = 1.0 - ((rounds_total - 1 - last_pos) / max(1, rounds_total)) if last_pos >= 0 else 0.0
    bias = 1.0

    res_aff = _resume_affinity(profile, arm)
    # Pack: bias, ability, coverage_ratio (penalty if already saturated),
    #       topic_mean (helps difficulty match), gap_affinity * res_aff,
    #       recency (penalise spamming the same category back-to-back).
    return [bias, ability, 1.0 - cov_ratio, topic_mean, max(gap_affinity, res_aff), 1.0 - recency]


def reward(
    *,
    overall_score_unit: float,
    target_difficulty: float,
    coverage_ratio: float,
    gap_resolved: bool,
    resume_aff: float,
) -> float:
    s = get_settings()
    diff_match = 1.0 - abs(float(overall_score_unit) - float(target_difficulty))
    cov_bonus = 1.0 - max(0.0, min(1.0, coverage_ratio))
    gap_bonus = 1.0 if gap_resolved else 0.0
    return (
        1.0 * diff_match
        + s.bandit_lambda_coverage * cov_bonus
        + s.bandit_lambda_gap * gap_bonus
        + s.bandit_lambda_resume * resume_aff
    )


# LinUCB core -----------------------------------------------------------------

@dataclass
class LinUCBArm:
    d: int = CTX_DIM
    A: list[list[float]] = field(default_factory=lambda: _eye(CTX_DIM, 1.0))
    b: list[float] = field(default_factory=lambda: [0.0] * CTX_DIM)
    n: int = 0

    def theta(self) -> list[float]:
        return _solve(self.A, self.b)

    def ucb(self, x: Sequence[float], alpha: float) -> float:
        theta = self.theta()
        mean = _dot(theta, x)
        A_inv_x = _solve(self.A, x)
        var = max(0.0, _dot(x, A_inv_x))
        return mean + alpha * math.sqrt(var)

    def update(self, x: Sequence[float], r: float) -> None:
        self.A = _add(self.A, _outer(x, x))
        self.b = [self.b[i] + r * x[i] for i in range(self.d)]
        self.n += 1

    def to_dict(self) -> dict:
        return {"d": self.d, "A": self.A, "b": self.b, "n": self.n}

    @classmethod
    def from_dict(cls, data: dict | None) -> "LinUCBArm":
        if not isinstance(data, dict):
            return cls()
        d = int(data.get("d", CTX_DIM))
        A = data.get("A")
        b = data.get("b")
        if not (isinstance(A, list) and isinstance(b, list) and len(A) == d and len(b) == d):
            return cls()
        return cls(d=d, A=[list(row) for row in A], b=list(b), n=int(data.get("n", 0)))


def load_bandit(state: InterviewState) -> dict[str, LinUCBArm]:
    raw = (state.get("bandit_state") or {}).get("arms") or {}
    return {arm: LinUCBArm.from_dict(raw.get(arm)) for arm in ARMS}


def serialise_bandit(arms: dict[str, LinUCBArm]) -> dict:
    return {"arms": {a: arms[a].to_dict() for a in ARMS}}


# Policy entry points ---------------------------------------------------------

def select_category(
    state: InterviewState,
    *,
    next_index: int,
    rounds_total: int,
    strategy: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (chosen_category, debug_info) given current memory state."""
    s = get_settings()
    strategy = (strategy or s.selector_strategy or "round_robin").lower()
    if strategy == "round_robin":
        order = _round_robin_order()
        chosen = order[(next_index - 1) % len(order)]
        return chosen, {"strategy": "round_robin", "scores": {}}

    if strategy == "thompson":
        return _thompson_pick(state, next_index, rounds_total)

    if strategy == "ia_linucb":
        if _resolve_ia_linucb():
            return _select_ia_linucb(
                state,
                next_index=next_index,
                rounds_total=rounds_total,
                cfg=_IALinUCBConfig(alpha0=s.bandit_alpha),
            )
        # Module missing in this deploy. Fall through to LinUCB but mark the
        # debug payload so /healthz/algorithms and trace logs reveal the
        # downgrade — silently substituting LinUCB would mislead the operator.
        chosen, dbg = _linucb_pick(state, next_index, rounds_total, alpha=s.bandit_alpha)
        dbg["strategy"] = "linucb"
        dbg["requested_strategy"] = "ia_linucb"
        dbg["dispatch_note"] = "ia_linucb_unavailable_fell_back_to_linucb"
        return chosen, dbg

    return _linucb_pick(state, next_index, rounds_total, alpha=s.bandit_alpha)


def _round_robin_order() -> list[str]:
    return ["技术深度", "项目经验", "系统设计", "技术深度", "项目经验", "系统设计", "沟通表达", "学习能力"]


def _linucb_pick(
    state: InterviewState,
    next_index: int,
    rounds_total: int,
    *,
    alpha: float,
) -> tuple[str, dict[str, Any]]:
    arms = load_bandit(state)

    # Eta_t hint nudges UCB: if evaluator suggested a direction, bump its arm.
    s = get_settings()
    hint_text = ""
    if s.eta_hint_enabled:
        hints = state.get("next_direction_hints") or []
        hint_text = str(hints[-1]) if hints else ""
    hint_bonus = {arm: (0.25 if hint_text and arm in hint_text else 0.0) for arm in ARMS}

    scores: dict[str, float] = {}
    contexts: dict[str, list[float]] = {}
    for arm in ARMS:
        ctx = build_context(state, arm, rounds_total=rounds_total)
        contexts[arm] = ctx
        try:
            ucb = arms[arm].ucb(ctx, alpha)
        except Exception:
            ucb = 0.0
        scores[arm] = ucb + hint_bonus[arm]

    coverage = get_coverage_count(state)
    target_min = max(1, rounds_total // (len(ARMS) + 2))
    # Hard coverage floor: never let an arm sit at 0 once we've done >|ARMS| rounds
    if next_index > len(ARMS):
        under = [a for a in ARMS if coverage.get(a, 0) < target_min]
        if under:
            chosen = max(under, key=lambda a: scores[a])
        else:
            chosen = max(ARMS, key=lambda a: scores[a])
    else:
        chosen = max(ARMS, key=lambda a: scores[a])

    return chosen, {
        "strategy": "linucb",
        "alpha": alpha,
        "scores": {a: round(scores[a], 4) for a in ARMS},
        "context": {a: [round(v, 3) for v in contexts[a]] for a in ARMS},
        "hint": hint_text,
    }


def _thompson_pick(
    state: InterviewState,
    next_index: int,
    rounds_total: int,
) -> tuple[str, dict[str, Any]]:
    """Beta-Bernoulli Thompson on a discretised reward (>median = success)."""
    raw = (state.get("bandit_state") or {}).get("ts_arms") or {}
    samples: dict[str, float] = {}
    for arm in ARMS:
        a = float(raw.get(arm, {}).get("alpha", 1.0))
        b = float(raw.get(arm, {}).get("beta", 1.0))
        samples[arm] = random.betavariate(a, b)
    chosen = max(ARMS, key=lambda a: samples[a])
    return chosen, {
        "strategy": "thompson",
        "scores": {a: round(samples[a], 4) for a in ARMS},
    }


def update_after_reward(
    state: InterviewState,
    *,
    chosen_arm: str,
    context: Sequence[float] | None,
    reward_value: float,
    rounds_total: int,
) -> dict[str, Any]:
    """Return a partial state patch with the updated bandit_state."""
    s = get_settings()
    bandit_state = dict(state.get("bandit_state") or {})

    if (s.selector_strategy or "round_robin").lower() == "thompson":
        ts = dict(bandit_state.get("ts_arms") or {})
        arm_state = dict(ts.get(chosen_arm) or {"alpha": 1.0, "beta": 1.0})
        success = 1.0 if reward_value >= 0.55 else 0.0
        arm_state["alpha"] = float(arm_state.get("alpha", 1.0)) + success
        arm_state["beta"] = float(arm_state.get("beta", 1.0)) + (1.0 - success)
        ts[chosen_arm] = arm_state
        bandit_state["ts_arms"] = ts
        return {"bandit_state": bandit_state}

    arms = load_bandit(state)
    if context is None:
        context = build_context(state, chosen_arm, rounds_total=rounds_total)
    arms[chosen_arm].update(list(context), float(reward_value))
    bandit_state.update(serialise_bandit(arms))
    return {"bandit_state": bandit_state}


# ---------------------------------------------------------------------------
# Convenience for experiments: estimate per-arm UCB without mutating state.
# ---------------------------------------------------------------------------

def snapshot_scores(
    state: InterviewState,
    *,
    rounds_total: int,
    alpha: float | None = None,
) -> dict[str, float]:
    s = get_settings()
    alpha = float(alpha if alpha is not None else s.bandit_alpha)
    arms = load_bandit(state)
    out: dict[str, float] = {}
    for arm in ARMS:
        ctx = build_context(state, arm, rounds_total=rounds_total)
        try:
            out[arm] = arms[arm].ucb(ctx, alpha)
        except Exception:
            out[arm] = 0.0
    return out
