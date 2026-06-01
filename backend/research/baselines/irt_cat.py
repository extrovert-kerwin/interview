"""Maximum Fisher-Information selector (BanditCAT-style baseline).

Pure CAT formulation (van der Linden & Glas, 2010): pick the next item /
arm whose 2PL Fisher information is highest at the current ability
estimate. We use the per-topic ability EMA already stored on
``state['per_topic_stats']`` to instantiate a per-arm theta and assume the
PI controller would offer a difficulty equal to ``target`` (matches the
production controller's set-point).

This baseline ignores resume affinity, coverage shaping, and reward — it is
the *informational* counterpart to LinUCB. We pair it with a hard coverage
floor identical to the production selector so it is forced to visit every
arm at least a few times.
"""

from __future__ import annotations

import math
from typing import Any

from app.agents.memory import get_ability, get_coverage_count, get_per_topic_stats
from app.agents.state import InterviewState
from app.services.bandit import ARMS


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _theta(state: InterviewState, arm: str) -> float:
    stats = get_per_topic_stats(state)
    s = stats.get(arm) or {}
    val = s.get("mean")
    if isinstance(val, (int, float)):
        return float(val)
    return get_ability(state)


def select_irt_cat(
    state: InterviewState,
    *,
    next_index: int,
    rounds_total: int,
    target: float = 0.7,
    k: float = 5.0,
) -> tuple[str, dict[str, Any]]:
    info: dict[str, float] = {}
    for arm in ARMS:
        theta = _theta(state, arm)
        p = _sigmoid(k * (theta - target))
        info[arm] = (k ** 2) * p * (1.0 - p)

    coverage = get_coverage_count(state)
    floor = max(1, rounds_total // (len(ARMS) + 2))
    if next_index > len(ARMS):
        under = [a for a in ARMS if coverage.get(a, 0) < floor]
        chosen = max(under or ARMS, key=lambda a: info[a])
    else:
        chosen = max(ARMS, key=lambda a: info[a])
    return chosen, {"strategy": "irt_cat", "info": {a: round(info[a], 4) for a in ARMS}}


def selector(target: float = 0.7, k: float = 5.0):
    def _pick(state: InterviewState, next_index: int, rounds_total: int):
        return select_irt_cat(state, next_index=next_index, rounds_total=rounds_total, target=target, k=k)
    return _pick
