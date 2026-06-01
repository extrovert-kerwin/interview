"""Write the current planned question into pending_question."""

from __future__ import annotations

from app.agents.state import InterviewState


def ask_question(state: InterviewState) -> InterviewState:
    plan = state.get("question_plan") or []
    idx = state.get("current_q_index", 0)

    if idx >= len(plan):
        return {
            "pending_question": "",
            "stage": "evaluating",
            "last_active_agent": "InterviewAgent",
            "last_active_tool": "ask_question",
        }

    q = plan[idx]
    points = q.get("knowledge_points") or []
    point_text = f"\n待考察知识点：{'、'.join(points)}" if points else ""
    if idx == 0 and not state.get("qa_history"):
        profile = state.get("resume_profile") or {}
        name = profile.get("name") or "同学"
        question = (
            f"你好 {name}，欢迎来到本次模拟面试。我会一次问一道题，必要时会追问；"
            f"你也可以先按自己的思路回答，不用追求一次说完。\n\n"
            f"第 1 题（{q['category']}）：{q['question']}{point_text}"
        )
    else:
        question = f"第 {idx + 1} 题（{q['category']}）：{q['question']}{point_text}"

    return {
        "pending_question": question,
        "pending_kind": "main",
        "follow_up_count": 0,
        "stage": "interviewing",
        "last_active_agent": "InterviewAgent",
        "last_active_tool": "ask_question",
    }
