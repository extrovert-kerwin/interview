"""Adaptive difficulty controller.

Two policies (selectable via ``DIFFICULTY_STRATEGY``):

  * ``heuristic``    — small look-up over the recent score window.
  * ``pi_control``   — proportional + integral controller that drives the
    candidate's success probability toward ``DIFFICULTY_TARGET``. The
    integral term gives memory of persistent error and lets the controller
    converge without oscillating after a single hard question.

Both return a numeric difficulty ∈ [0,1]; ``app.agents.memory.label_difficulty``
turns it back into the junior / mid / senior labels expected by the LLM prompt.
"""

from __future__ import annotations

from app.agents.memory import (
    DIFFICULTY_MAP,
    get_ability,
    get_score_window,
    label_difficulty,
    numeric_difficulty,
)
from app.agents.state import InterviewState
from app.config import get_settings


def _heuristic(state: InterviewState) -> float:
    base = numeric_difficulty(state.get("difficulty") or "mid")
    win = get_score_window(state, 3)
    if not win:
        return base
    avg = sum(win) / len(win)
    if avg > 0.78:
        return min(0.95, base + 0.10)
    if avg < 0.42:
        return max(0.10, base - 0.10)
    return base


def _pi_control(state: InterviewState) -> float:
    s = get_settings()
    target = float(s.difficulty_target)
    kp = float(s.difficulty_kp)
    ki = float(s.difficulty_ki)

    base = numeric_difficulty(state.get("difficulty") or "mid")
    ability = get_ability(state)
    win = get_score_window(state, 5)
    if not win:
        # Anchor on declared difficulty when we have no signal yet.
        return max(0.05, min(0.95, 0.5 * base + 0.5 * ability))

    # Error: how far above target the candidate is performing.
    # Positive error → candidate is acing it → raise difficulty.
    instant = win[-1] - target
    avg_err = sum(w - target for w in win) / len(win)

    raw = ability + kp * instant + ki * avg_err
    # Mild anchoring toward declared difficulty to avoid runaway extremes.
    raw = 0.85 * raw + 0.15 * base
    return max(0.05, min(0.95, raw))


def next_difficulty(state: InterviewState) -> tuple[float, str]:
    s = get_settings()
    strategy = (s.difficulty_strategy or "heuristic").lower()
    if strategy == "pi_control":
        value = _pi_control(state)
    else:
        value = _heuristic(state)
    return value, label_difficulty(value)
