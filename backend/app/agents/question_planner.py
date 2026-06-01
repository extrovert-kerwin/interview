"""Question planning tool: generate one interview question at a time.

The selection of *which* category to ask next is delegated to
``app.services.bandit.select_category``. When the bandit is disabled
(``SELECTOR_STRATEGY=round_robin``), behaviour is byte-equivalent to the
legacy fixed schedule, so existing sessions remain unaffected.

The difficulty hint passed into the LLM prompt comes from
``app.services.difficulty.next_difficulty`` which implements an adaptive
PI controller (paper §4.3). The numeric value is also persisted on the
state so the bandit's reward shaping can use it later.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import label_difficulty
from app.agents.state import InterviewState
from app.services.bandit import build_context, select_category
from app.services.difficulty import next_difficulty
from app.services.llm import chat, extract_json

CATEGORIES = ["技术深度", "项目经验", "系统设计", "沟通表达", "学习能力"]
CATEGORY_ORDER = ["技术深度", "项目经验", "系统设计", "技术深度", "项目经验", "系统设计", "沟通表达", "学习能力"]

FRONTIER_POINTS = [
    "大模型应用工程化",
    "RAG 检索增强生成",
    "Agent 工作流与工具调用",
    "向量数据库与语义检索",
    "云原生与可观测性",
    "高并发系统设计",
    "数据安全与隐私保护",
    "模型评测与效果迭代",
    "前端性能与可访问性",
    "端侧 AI 与实时交互",
]

SYSTEM = """你是一位资深技术面试官。请只为当前轮次生成 1 道中文面试题。
严格输出 JSON，不要输出额外文本：
{
  "category": "技术深度 | 项目经验 | 系统设计 | 沟通表达 | 学习能力",
  "intent": "10-30字考察意图",
  "knowledge_points": ["2-4个待考察知识点，尽量包含前沿方向"],
  "question": "自然口吻的完整问题，聚焦候选人简历或上一轮回答"
}

要求：
1. 只生成一道题。
2. 不要重复已经问过的问题。
3. junior 偏基础和项目细节，mid 偏权衡和设计，senior 偏架构、协作和抽象。
4. 知识点要让被面试者能提前知道本题考察什么，例如 RAG、Agent、云原生、可观测性、数据安全、工程化评测等。
5. 如果简历信息有限，也要围绕目标岗位提出可回答的问题。"""


def plan_questions(state: InterviewState) -> InterviewState:
    plan = list(state.get("question_plan") or [])
    target_total = int(state.get("target_total_questions") or 8)
    if len(plan) >= target_total:
        return {
            "stage": "evaluating",
            "pending_question": "",
            "last_active_agent": "InterviewAgent",
            "last_active_tool": "plan_questions",
        }

    next_index = len(plan) + 1
    chosen_category, sel_debug = select_category(
        state,
        next_index=next_index,
        rounds_total=target_total,
    )
    ctx_vec = build_context(state, chosen_category, rounds_total=target_total)
    diff_num, diff_label = next_difficulty(state)

    prefetched = state.get("prefetched_question")
    if isinstance(prefetched, dict) and prefetched.get("id") == f"q{next_index}":
        question = _clean_question(
            prefetched,
            next_index,
            prefetched.get("category") or chosen_category,
        )
        prefetched = None
    else:
        if state.get("prefetching_question_id") == f"q{next_index}":
            question = _fallback_one(
                state.get("position", "通用工程师"),
                next_index,
                chosen_category,
                state.get("resume_profile") or {},
            )
        else:
            question = generate_question(
                state,
                next_index,
                chosen_category,
                difficulty_label=diff_label,
            )

    question.setdefault("difficulty_numeric", float(diff_num))
    question.setdefault("difficulty_label", diff_label)
    question.setdefault("selector_debug", sel_debug)
    question.setdefault("bandit_context", ctx_vec)

    return {
        "question_plan": plan + [question],
        "prefetched_question": prefetched,
        "prefetching_question_id": "",
        "target_total_questions": target_total,
        "current_q_index": next_index - 1,
        "follow_up_count": 0,
        "stage": "interviewing",
        "last_active_agent": "InterviewAgent",
        "last_active_tool": "plan_questions",
    }


def generate_question(
    state: InterviewState,
    index: int,
    category: str | None = None,
    *,
    difficulty_label: str | None = None,
) -> dict[str, Any]:
    category = category or CATEGORY_ORDER[(index - 1) % len(CATEGORY_ORDER)]
    profile = state.get("resume_profile") or {}
    history = state.get("qa_history") or []
    position = state.get("position", "通用工程师")
    difficulty = difficulty_label or state.get("difficulty", "mid")
    hints = state.get("next_direction_hints") or []
    gaps = state.get("gap_set") or []
    try:
        llm = chat(temperature=0.7, max_tokens=2200)
        res = llm.invoke([
            SystemMessage(content=SYSTEM),
            HumanMessage(content=(
                f"目标岗位：{position}\n"
                f"难度（自适应控制器给出）：{difficulty}\n"
                f"当前题号：{index}\n"
                f"建议类别（来自带上下文的 bandit 选择）：{category}\n"
                f"评估器给出的下一步方向：{hints[-1] if hints else '（无）'}\n"
                f"已知薄弱点：{', '.join(gaps[-6:]) if gaps else '（暂无）'}\n"
                f"可选前沿知识点：{', '.join(FRONTIER_POINTS)}\n"
                f"候选人画像：\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n"
                f"已问答历史：\n{json.dumps(history[-4:], ensure_ascii=False, indent=2)}"
            )),
        ])
        parsed = extract_json(res.content)
        if isinstance(parsed, dict) and parsed.get("question"):
            return _clean_question(parsed, index, category)
    except Exception:
        pass
    return _fallback_one(position, index, category, profile)


def _clean_question(q: dict[str, Any], index: int, category: str) -> dict[str, Any]:
    points = _clean_points(q.get("knowledge_points"))
    if not points:
        points = _default_points(category, q.get("question") or "")
    cleaned = {
        "id": f"q{index}",
        "category": q.get("category") if q.get("category") in CATEGORIES else category,
        "intent": q.get("intent") or f"考察{category}和实际表达",
        "knowledge_points": points[:4],
        "question": q.get("question") or f"请结合你的经历谈谈一个{category}相关案例。",
    }
    for k in ("difficulty_numeric", "difficulty_label", "selector_debug", "bandit_context"):
        if k in q:
            cleaned[k] = q[k]
    return cleaned


def _fallback_one(position: str, index: int, category: str, profile: dict | None = None) -> dict[str, Any]:
    profile = profile or {}
    skills = profile.get("skills") or []
    projects = profile.get("projects") or []
    skill = skills[0] if skills else position
    project = projects[0].get("name") if projects and isinstance(projects[0], dict) else "你最近一个项目"
    templates = {
        "技术深度": (
            f"请结合 {skill}，讲一个你在实际项目里解决过的技术难点。"
            "重点说清楚方案、权衡、指标，以及如果引入大模型或自动化工具，你会怎样评估效果。"
        ),
        "项目经验": (
            f"请介绍 {project} 中你负责的核心部分，说明目标、方案、结果和个人贡献。"
            "如果这个项目要接入 RAG、Agent 或实时分析能力，你会优先改造哪里？"
        ),
        "系统设计": (
            f"如果要为 {position} 场景设计一个可扩展服务，你会如何拆分模块、设计数据流、处理异常，"
            "并保证可观测性、数据安全和后续模型效果迭代？"
        ),
        "沟通表达": "请讲一次你需要和产品、业务或其他工程同学对齐方案的经历，你是怎么推动共识，并把技术风险讲清楚的？",
        "学习能力": f"请说一个你最近快速学习并落地的新技术，它为什么适合 {position} 方向？你是怎么验证它真的有效的？",
    }
    return {
        "id": f"q{index}",
        "category": category,
        "intent": f"考察{category}、前沿理解和落地能力",
        "knowledge_points": _default_points(category, templates.get(category, "")),
        "question": templates.get(category, f"请围绕 {position} 分享一个有挑战的项目。"),
    }


def _fallback(position: str) -> list[dict[str, Any]]:
    return [_fallback_one(position, i, CATEGORY_ORDER[(i - 1) % len(CATEGORY_ORDER)]) for i in range(1, 9)]


def _clean_points(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    points: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in points:
            points.append(text[:32])
    return points


def _default_points(category: str, question: str = "") -> list[str]:
    if category == "技术深度":
        return ["核心技术原理", "性能优化", "模型评测与效果迭代"]
    if category == "项目经验":
        return ["项目目标拆解", "个人贡献", "RAG / Agent 落地机会"]
    if category == "系统设计":
        return ["高并发系统设计", "云原生与可观测性", "数据安全与隐私保护"]
    if category == "沟通表达":
        return ["跨团队协作", "风险沟通", "方案权衡"]
    if "前端" in question:
        return ["前端性能与可访问性", "实时交互体验", "端侧 AI"]
    return ["快速学习方法", "技术选型判断", "前沿技术落地"]
