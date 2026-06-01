"""LLM-based follow-up decision for the interview agent.

Design: Dynamic Slot Generation approach (arXiv:2412.16943).
The LLM identifies which information "slots" are missing from the candidate's
answer (technical depth, tradeoffs, concrete evidence, process), then decides
whether a follow-up is warranted and generates a targeted question for the
most critical missing slot.

Falls back to heuristic scoring if the LLM call fails.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import InterviewState

MAX_FOLLOW_UPS = 1

OFF_TOPIC_WORDS = (
    "天气", "火锅", "吃饭", "睡觉", "旅游", "电影", "游戏", "随便",
    "不知道", "不会", "没做过", "不清楚", "无", "n/a",
    "weather", "food", "movie", "game",
)

DETAIL_MARKERS = (
    "背景", "目标", "方案", "实现", "架构", "权衡", "取舍", "指标", "结果",
    "优化", "监控", "评估", "复盘", "风险", "成本", "延迟", "准确率", "召回",
    "RAG", "Agent", "缓存", "队列", "数据库", "模型", "上线",
)

# Slot labels shown in follow-up prompts
SLOT_LABELS = {
    "mechanism": "核心机制",
    "tradeoff": "方案权衡",
    "evidence": "量化证据",
    "process": "实施过程",
    "result": "结果与复盘",
}

_FOLLOW_UP_SYSTEM = """\
你是一位经验丰富的技术面试官，正在评估候选人的回答。

你的任务：
1. 识别候选人回答中"信息槽"（information slots）的缺失情况。
2. 判断是否需要追问，以及生成针对最关键缺口的追问问题。

评估五个信息槽：
- mechanism：核心技术机制（原理、实现细节、边界条件）
- tradeoff：方案权衡（为什么选这个方案、与其他方案的对比、代价）
- evidence：量化证据（数据、指标、规模、具体数字）
- process：实施过程（怎么推进的、遇到什么难点、如何解决）
- result：结果与复盘（上线效果、改进了什么、下次会怎么做不同）

判断规则：
- 如果回答明显偏题（无关话题、敷衍）→ action: retry
- 如果已经是第二次追问（follow_up_count >= 1）→ action: next
- 如果有 ≥ 2 个槽严重缺失 且 这是第一次追问机会 → action: follow_up
- 否则 → action: next

重要：不要因为回答长度短就判断追问。简短但精准的回答可以直接进入下一题。

输出严格 JSON，不要输出其他文字：
{
  "missing_slots": ["mechanism", "tradeoff", ...],
  "action": "next" | "follow_up" | "retry",
  "follow_up_question": "针对最关键缺失槽的追问（仅 action=follow_up 时填写，其他情况空字符串）",
  "reasoning": "一句话说明判断依据"
}"""


def judge_follow_up(state: InterviewState) -> InterviewState:
    plan = state.get("question_plan") or []
    idx = state.get("current_q_index", 0)
    history = state.get("qa_history") or []
    follow_count = state.get("follow_up_count", 0)
    target_total = int(state.get("target_total_questions") or 8)

    if idx >= len(plan) or not history:
        return _advance(state, target_total)

    q = plan[idx]
    last = history[-1]
    answer = _latest_answer(last)

    # Short-circuit: obviously off-topic → retry without LLM
    if _looks_off_topic(answer):
        return _retry(q, "这段回答和当前问题关联不大。请回到题目本身，结合真实经历说明背景、做法、取舍和结果。")

    # Already used follow-up quota → advance
    if follow_count >= MAX_FOLLOW_UPS:
        return _advance(state, target_total)

    # Try LLM-based slot detection
    decision = _llm_judge(q, last, answer, follow_count)
    if decision is None:
        # Fallback to heuristic
        decision = _heuristic_judge(q, answer, follow_count)

    if decision["action"] == "retry":
        return _retry(q, decision.get("message", ""))
    if decision["action"] == "follow_up":
        question = decision.get("follow_up_question") or _fallback_follow_up(q)
        return {
            "pending_question": f"追问：{question}",
            "pending_kind": "follow_up",
            "follow_up_count": follow_count + 1,
            "stage": "interviewing",
            "last_active_agent": "InterviewAgent",
            "last_active_tool": "judge_follow_up",
        }

    return _advance(state, target_total)


def _llm_judge(q: dict, item: dict, answer: str, follow_count: int) -> dict | None:
    """Call LLM to detect missing slots and decide follow-up action."""
    try:
        from app.services.llm import chat, extract_json

        follow_ups = item.get("follow_ups") or []
        follow_up_text = ""
        if follow_ups:
            follow_up_text = "\n追问回答：\n" + "\n".join(
                f"  - 追问：{f.get('question', '')}\n    回答：{f.get('answer', '')}"
                for f in follow_ups
            )

        points = q.get("knowledge_points") or []
        user_msg = (
            f"面试题（{q.get('category', '')}）：{q.get('question', '')}\n"
            f"考察意图：{q.get('intent', '')}\n"
            f"待考察知识点：{', '.join(points)}\n\n"
            f"候选人回答：{answer}"
            f"{follow_up_text}\n\n"
            f"当前已追问次数：{follow_count}"
        )

        llm = chat(temperature=0.2, max_tokens=600)
        res = llm.invoke([SystemMessage(content=_FOLLOW_UP_SYSTEM), HumanMessage(content=user_msg)])
        parsed = extract_json(res.content)
        if not isinstance(parsed, dict):
            return None
        action = parsed.get("action", "next")
        if action not in ("next", "follow_up", "retry"):
            action = "next"
        return {
            "action": action,
            "follow_up_question": parsed.get("follow_up_question", ""),
            "missing_slots": parsed.get("missing_slots", []),
        }
    except Exception:
        return None


def _heuristic_judge(q: dict, answer: str, follow_count: int) -> dict:
    """Local rubric fallback when LLM is unavailable."""
    quality = _answer_quality(q, answer)
    if quality < 58:
        category = _normalize_category(q.get("category"))
        templates = {
            "技术深度": "可以再补充一个关键技术细节吗？比如核心机制、指标、边界条件或你做过的取舍。",
            "项目经验": "可以结合一个具体项目展开吗？请说明你的职责、方案、遇到的难点和最后结果。",
            "系统设计": "可以继续说明稳定性和扩展性设计吗？例如队列、缓存、监控、降级或数据一致性。",
            "沟通表达": "可以把答案按「背景-行动-结果」再具体化一点吗？",
            "学习能力": "可以补充你如何复盘和改进的吗？最好给出一个真实例子。",
        }
        return {
            "action": "follow_up",
            "follow_up_question": templates.get(category, templates["沟通表达"]),
        }
    return {"action": "next"}


def _fallback_follow_up(q: dict) -> str:
    category = _normalize_category(q.get("category"))
    templates = {
        "技术深度": "可以补充核心机制、关键指标或你做过的方案权衡吗？",
        "项目经验": "可以具体说说你在这个场景里负责了什么、遇到的最大难点是什么吗？",
        "系统设计": "可以补充稳定性、扩展性或数据一致性的设计思路吗？",
        "沟通表达": "可以用「背景-行动-结果」结构再具体描述一遍吗？",
        "学习能力": "可以补充你是如何验证这个新技术确实有效、以及后续怎么复盘的吗？",
    }
    return templates.get(category, "可以结合具体项目经历补充更多细节吗？")


def _latest_answer(item: dict) -> str:
    follow_ups = item.get("follow_ups") or []
    if follow_ups:
        return (follow_ups[-1].get("answer") or "").strip()
    return (item.get("answer") or "").strip()


def _looks_off_topic(answer: str) -> bool:
    normalized = answer.strip().lower()
    if len(normalized) < 8:
        return True
    if any(word.lower() in normalized for word in OFF_TOPIC_WORDS) and len(normalized) < 80:
        return True
    if re.fullmatch(r"[\W_0-9a-zA-Z]{1,12}", normalized):
        return True
    return False


def _answer_quality(q: dict, answer: str) -> int:
    score = 30
    score += min(28, len(answer) // 7)
    marker_hits = sum(1 for m in DETAIL_MARKERS if m.lower() in answer.lower())
    score += min(24, marker_hits * 4)
    points = q.get("knowledge_points") or []
    point_hits = sum(1 for p in points if _soft_match(answer, str(p)))
    if points:
        score += round(18 * point_hits / len(points))
    if re.search(r"\d+|%|ms|qps|并发|提升|降低", answer, re.IGNORECASE):
        score += 8
    if any(word in answer for word in ("因为", "所以", "但是", "相比", "权衡", "取舍")):
        score += 8
    return max(0, min(100, score))


def _soft_match(answer: str, phrase: str) -> bool:
    if not phrase:
        return False
    if phrase.lower() in answer.lower():
        return True
    tokens = [t for t in re.split(r"[\s/、,，;；]+", phrase) if len(t) >= 2]
    return bool(tokens) and any(t.lower() in answer.lower() for t in tokens)


def _normalize_category(category: object) -> str:
    text = str(category or "")
    if "技术" in text:
        return "技术深度"
    if "项目" in text:
        return "项目经验"
    if "系统" in text or "架构" in text:
        return "系统设计"
    if "学习" in text:
        return "学习能力"
    if "沟通" in text or "表达" in text:
        return "沟通表达"
    return text if text in ("技术深度", "项目经验", "系统设计", "沟通表达", "学习能力") else "沟通表达"


def _retry(q: dict, message: str | None = None) -> dict:
    prompt = message or "请回到当前问题，结合实际经历说明背景、做法、取舍和结果。"
    return {
        "pending_question": f"提示：{prompt}\n\n当前问题：{q.get('question', '')}",
        "pending_kind": "follow_up",
        "stage": "interviewing",
        "last_active_agent": "InterviewAgent",
        "last_active_tool": "judge_follow_up",
    }


def _advance(state: InterviewState, target_total: int | None = None) -> dict:
    plan = state.get("question_plan") or []
    target_total = target_total or int(state.get("target_total_questions") or 8)
    next_idx = state.get("current_q_index", 0) + 1
    if next_idx >= target_total:
        return {
            "current_q_index": next_idx,
            "pending_question": "",
            "stage": "evaluating",
            "last_active_agent": "InterviewAgent",
            "last_active_tool": "judge_follow_up",
        }
    return {
        "current_q_index": min(next_idx, len(plan)),
        "follow_up_count": 0,
        "pending_question": "",
        "stage": "planning",
        "last_active_agent": "InterviewAgent",
        "last_active_tool": "judge_follow_up",
    }
