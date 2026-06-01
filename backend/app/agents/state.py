"""Interview state shared across agents.

State is intentionally a TypedDict so it can be persisted as JSON. New fields
in the M3 / LinUCB upgrade are all optional and default to safe values when
absent, which keeps existing sessions backward compatible.
"""

from __future__ import annotations

from typing import Any, TypedDict


class InterviewState(TypedDict, total=False):
    session_id: str

    # 输入
    resume_text: str
    position: str
    difficulty: str  # junior / mid / senior

    # 解析 & 计划
    resume_profile: dict[str, Any]
    question_plan: list[dict[str, Any]]
    target_total_questions: int

    # 推进游标
    current_q_index: int
    follow_up_count: int

    # 历史问答
    qa_history: list[dict[str, Any]]
    pending_question: str
    pending_kind: str         # main / follow_up
    last_active_tool: str

    # 评估 & 报告
    evaluations: list[dict[str, Any]]
    final_report: dict[str, Any]

    # 控制位
    stage: str                # parsing / planning / interviewing / evaluating / done
    last_active_agent: str

    # ------------------------------------------------------------------
    # Memory schema (M3 / bandit upgrade).
    # All fields below are optional; absent → defaults to neutral values
    # via the helpers in app.agents.memory.
    # ------------------------------------------------------------------
    ability_estimate: float                   # latent ability in [0,1]
    score_window: list[float]                 # last K overall scores ∈ [0,1]
    per_topic_stats: dict[str, dict[str, Any]]  # category → {n, mean, last_seen, gaps}
    coverage_count: dict[str, int]             # category → times asked
    gap_set: list[str]                         # accumulated missing knowledge points
    next_direction_hints: list[str]            # eta_t hints from evaluator
    eval_provenance: list[str]                 # per-question provenance tag
    bandit_state: dict[str, Any]               # serialised LinUCB / Thompson arms
    difficulty_trajectory: list[float]         # numeric difficulty per turn
    chapter_trajectory: list[str]              # category per turn
