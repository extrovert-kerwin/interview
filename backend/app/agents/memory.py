"""Interview memory primitives.

Defines the structured memory schema referenced in Section 3 of the paper.
Memory updates happen *after* each evaluated turn; the update is a pure
function so it can be unit-tested in isolation and replayed in the
simulation harness.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.agents.state import InterviewState

CATEGORIES: tuple[str, ...] = (
    "技术深度",
    "项目经验",
    "系统设计",
    "沟通表达",
    "学习能力",
)

DIFFICULTY_MAP = {"junior": 0.25, "mid": 0.55, "senior": 0.85}


# ---------------------------------------------------------------------------
# Read helpers — always return a sensible default when the field is missing.
# ---------------------------------------------------------------------------

def get_ability(state: InterviewState) -> float:
    val = state.get("ability_estimate")
    if isinstance(val, (int, float)):
        return float(val)
    return DIFFICULTY_MAP.get(str(state.get("difficulty", "mid")).lower(), 0.55)


def get_score_window(state: InterviewState, k: int = 5) -> list[float]:
    raw = state.get("score_window") or []
    out = [float(x) for x in raw if isinstance(x, (int, float))]
    return out[-k:]


def get_per_topic_stats(state: InterviewState) -> dict[str, dict[str, Any]]:
    return dict(state.get("per_topic_stats") or {})


def get_coverage_count(state: InterviewState) -> dict[str, int]:
    raw = state.get("coverage_count") or {}
    return {c: int(raw.get(c, 0)) for c in CATEGORIES}


def get_gap_set(state: InterviewState) -> list[str]:
    raw = state.get("gap_set") or []
    seen = set()
    out = []
    for g in raw:
        text = str(g).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def get_chapter_trajectory(state: InterviewState) -> list[str]:
    return [str(c) for c in (state.get("chapter_trajectory") or [])]


# ---------------------------------------------------------------------------
# Memory update — called once per evaluated turn.
# ---------------------------------------------------------------------------

def update_after_eval(
    state: InterviewState,
    *,
    category: str,
    difficulty_numeric: float,
    overall_score_unit: float,
    new_gaps: Iterable[str] = (),
    next_direction: str = "",
    provenance: str = "",
    window_k: int = 5,
    ema_alpha: float = 0.4,
) -> InterviewState:
    """Return a partial state dict with refreshed memory fields.

    overall_score_unit ∈ [0,1]. The function is purely additive: it never
    overwrites unrelated state, so it can be merged via ``state.update(patch)``.
    """
    window = get_score_window(state, window_k * 2)
    window = (window + [float(overall_score_unit)])[-window_k:]

    ability = get_ability(state)
    new_ability = ema_alpha * float(overall_score_unit) + (1 - ema_alpha) * ability
    new_ability = max(0.0, min(1.0, new_ability))

    stats = get_per_topic_stats(state)
    s = stats.get(category) or {"n": 0, "mean": 0.0, "gaps": []}
    n = int(s.get("n", 0))
    mean = float(s.get("mean", 0.0))
    new_n = n + 1
    new_mean = (mean * n + float(overall_score_unit)) / new_n
    s_gaps = list(s.get("gaps") or [])
    for g in new_gaps:
        if g and g not in s_gaps:
            s_gaps.append(str(g))
    stats[category] = {
        "n": new_n,
        "mean": new_mean,
        "last_score": float(overall_score_unit),
        "gaps": s_gaps[-12:],
    }

    coverage = get_coverage_count(state)
    coverage[category] = coverage.get(category, 0) + 1

    gap_set = get_gap_set(state)
    for g in new_gaps:
        text = str(g).strip()
        if text and text not in gap_set:
            gap_set.append(text)

    hints = list(state.get("next_direction_hints") or [])
    if next_direction:
        hints.append(str(next_direction))
        hints = hints[-10:]

    provenance_list = list(state.get("eval_provenance") or [])
    if provenance:
        provenance_list.append(str(provenance))

    diff_traj = list(state.get("difficulty_trajectory") or [])
    diff_traj.append(float(difficulty_numeric))

    chap_traj = get_chapter_trajectory(state)
    chap_traj.append(str(category))

    return {
        "ability_estimate": new_ability,
        "score_window": window,
        "per_topic_stats": stats,
        "coverage_count": coverage,
        "gap_set": gap_set[-40:],
        "next_direction_hints": hints,
        "eval_provenance": provenance_list[-40:],
        "difficulty_trajectory": diff_traj[-40:],
        "chapter_trajectory": chap_traj[-40:],
    }


def numeric_difficulty(label: str | float) -> float:
    if isinstance(label, (int, float)):
        return max(0.0, min(1.0, float(label)))
    return DIFFICULTY_MAP.get(str(label or "mid").lower(), 0.55)


def label_difficulty(value: float) -> str:
    if value <= 0.4:
        return "junior"
    if value <= 0.72:
        return "mid"
    return "senior"
