"""Setup tool: parse resume and plan questions in one LLM call."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.question_planner import CATEGORIES, _fallback
from app.agents.state import InterviewState
from app.services.llm import chat, extract_json

SYSTEM = """You are a senior technical interviewer. Read the resume and create a Chinese interview setup.
Return strict JSON only:
{
  "profile": {
    "name": "candidate name or 候选人",
    "years_of_experience": 0,
    "current_title": "current title",
    "skills": ["up to 12 skills"],
    "projects": [
      {"name": "project name", "role": "role", "highlight": "short highlight"}
    ],
    "highlights": ["3 concrete resume highlights worth probing"]
  },
  "questions": [
    {
      "id": "q1",
      "category": "技术深度 | 项目经验 | 系统设计 | 沟通表达 | 学习能力",
      "intent": "short assessment intent",
      "question": "natural Chinese interview question"
    }
  ]
}

Create exactly 8 questions. Cover all five categories. Tailor questions to the resume,
target position, and difficulty. Use Chinese for candidate-facing text."""


def setup_interview(state: InterviewState) -> InterviewState:
    resume = state.get("resume_text", "").strip()
    position = state.get("position", "通用工程师")
    difficulty = state.get("difficulty", "mid")

    if not resume:
        profile = _fallback_profile()
        questions = _fallback(position)
    else:
        try:
            llm = chat(temperature=0.5, max_tokens=10000)
            res = llm.invoke([
                SystemMessage(content=SYSTEM),
                HumanMessage(content=(
                    f"Target position: {position}\n"
                    f"Difficulty: {difficulty}\n"
                    f"Resume text:\n{resume[:7000]}"
                )),
            ])
            data = extract_json(res.content)
            profile = data.get("profile", {}) if isinstance(data, dict) else {}
            questions = data.get("questions", []) if isinstance(data, dict) else []
        except Exception:
            profile = _fallback_profile()
            questions = _fallback(position)

    return {
        "resume_profile": _clean_profile(profile),
        "question_plan": _clean_questions(questions, position),
        "current_q_index": 0,
        "follow_up_count": 0,
        "qa_history": [],
        "evaluations": [],
        "stage": "interviewing",
        "last_active_agent": "InterviewAgent",
        "last_active_tool": "setup_interview",
    }


def _fallback_profile() -> dict:
    return {
        "name": "候选人",
        "years_of_experience": 0,
        "current_title": "",
        "skills": [],
        "projects": [],
        "highlights": [],
    }


def _clean_profile(profile: object) -> dict:
    if not isinstance(profile, dict):
        return _fallback_profile()
    cleaned = _fallback_profile()
    cleaned.update({
        "name": profile.get("name") or "候选人",
        "years_of_experience": profile.get("years_of_experience") or 0,
        "current_title": profile.get("current_title") or "",
        "skills": _as_list(profile.get("skills"))[:12],
        "projects": _as_list(profile.get("projects"))[:4],
        "highlights": _as_list(profile.get("highlights"))[:3],
    })
    return cleaned


def _clean_questions(questions: object, position: str) -> list[dict]:
    source = questions if isinstance(questions, list) and questions else _fallback(position)
    cleaned: list[dict] = []
    for i, q in enumerate(source[:8], start=1):
        if not isinstance(q, dict):
            continue
        cleaned.append({
            "id": q.get("id") or f"q{i}",
            "category": q.get("category") or CATEGORIES[(i - 1) % len(CATEGORIES)],
            "intent": q.get("intent") or "",
            "question": q.get("question") or f"请围绕 {position} 介绍一个最有挑战的项目。",
        })
    if len(cleaned) < 8:
        fallback = _fallback(position)
        seen = {q["id"] for q in cleaned}
        cleaned.extend(q for q in fallback if q["id"] not in seen)
    return cleaned[:8]


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []
