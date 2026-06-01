"""LLM-powered rubric evaluator for interview answers.

Scoring design:
- Primary: G-Eval / Prometheus hybrid (arXiv:2303.16634, arXiv:2310.08491)
  * System prompt provides explicit rubric with per-dimension criteria
  * Model produces chain-of-thought reasoning BEFORE assigning scores
  * Explicit anti-verbosity instruction (arXiv:2406.07791 bias mitigation)
  * Falls back to local heuristic scoring if LLM call fails
- Multi-judge ensemble (paper §4.1): N runs at different temperatures,
  per-dimension trimmed mean + cross-judge consistency check.
- Calibration layer (paper §4.1): Platt or linear post-hoc map, with
  consensus-weighted blending toward the raw rule-based score.
- Local heuristics kept as fallback (G-Eval-style multi-criteria, MT-Bench
  multi-turn calibration, Prometheus-style custom rubrics).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import CATEGORIES as MEMORY_CATEGORIES
from app.agents.state import InterviewState
from app.config import get_settings
from app.services.calibration import load_calibrator
from app.services.validator import (
    REQUIRED_DIMENSIONS,
    cross_judge_consistency,
    validate_single_judge,
)

# Lazy import: research.rw_multi_judge is only loaded when RW-MJ is selected.
try:
    from research.rw_multi_judge import RWMJAggregator, RWMJConfig  # type: ignore
    _RWMJ_AVAILABLE = True
except Exception:  # pragma: no cover - research package may be absent in slim deploys
    RWMJAggregator = None  # type: ignore
    RWMJConfig = None  # type: ignore
    _RWMJ_AVAILABLE = False

# Per-session RW-MJ state, keyed by session_id. Reset when a new session
# starts. The OS process owns this dict — it does not survive restarts,
# which matches RW-MJ's "online over a single session" design.
_SESSION_RWMJ_STATE: dict[str, dict[str, RWMJAggregator]] = {}


def _rwmj_for(session_id: str, dim: str) -> RWMJAggregator:
    sess = _SESSION_RWMJ_STATE.setdefault(session_id or "_global", {})
    if dim not in sess:
        sess[dim] = RWMJAggregator(cfg=RWMJConfig())
    return sess[dim]


def reset_session_rwmj(session_id: str) -> None:
    """Drop any RW-MJ state for the given session. Called at session start
    so a re-run of the same session_id starts cold."""
    _SESSION_RWMJ_STATE.pop(session_id, None)

RUBRIC = {
    "relevance":    {"label": "相关性",    "weight": 0.18},
    "knowledge":    {"label": "知识覆盖",  "weight": 0.20},
    "specificity":  {"label": "证据具体性","weight": 0.18},
    "reasoning":    {"label": "逻辑推理",  "weight": 0.16},
    "completeness": {"label": "结构完整",  "weight": 0.14},
    "reflection":   {"label": "复盘改进",  "weight": 0.08},
    "follow_up":    {"label": "追问响应",  "weight": 0.06},
}

STOPWORDS = {
    "一个", "这个", "那个", "然后", "就是", "因为", "所以", "可以", "进行", "通过", "我们",
    "项目", "系统", "问题", "回答", "技术", "方案", "the", "and", "for", "with",
}

REASONING_MARKERS = (
    "因为", "所以", "导致", "权衡", "取舍", "相比", "瓶颈", "原因", "目标", "约束", "风险",
    "指标", "监控", "验证", "评估", "优化", "tradeoff", "latency", "metric",
)

RESULT_MARKERS = (
    "%", "ms", "qps", "并发", "延迟", "吞吐", "准确率", "召回", "成本", "提升", "降低",
    "上线", "落地", "结果", "效果", "复盘", "改进",
)

OFF_TOPIC_MARKERS = (
    "天气", "火锅", "吃饭", "睡觉", "旅游", "电影", "游戏", "随便", "不知道", "不会",
    "没做过", "不清楚", "weather", "food", "movie", "game", "n/a",
)

# ---------------------------------------------------------------------------
# Prometheus-style rubric description for each dimension (1-100 scale)
# ---------------------------------------------------------------------------
_RUBRIC_CRITERIA = """
**相关性（relevance, 权重 18%）**
90-100: 完全紧扣题目意图和知识点，每句话都有价值
70-89: 大体相关，有少量偏离
50-69: 部分相关，但涉及较多不相关内容
0-49: 基本偏题或只是复述题目

**知识覆盖（knowledge, 权重 20%）**
90-100: 明确覆盖 ≥75% 的待考察知识点，并有深入解释
70-89: 覆盖约一半知识点，有一定深度
50-69: 只提到知识点名称，缺乏实质解释
0-49: 几乎未覆盖任何待考察知识点

**证据具体性（specificity, 权重 18%）**
90-100: 有具体数字/指标/案例，可验证，来自真实经历
70-89: 有部分具体细节，但还可以更精确
50-69: 主要是泛泛而论，缺少具体支撑
0-49: 完全抽象，没有任何具体证据

**逻辑推理（reasoning, 权重 16%）**
90-100: 清晰讲明了为什么，有取舍分析，因果链完整
70-89: 有基本推理，但不够完整
50-69: 只陈述结论，缺少原因
0-49: 没有任何推理

**结构完整（completeness, 权重 14%）**
90-100: 有背景→问题→方案→结果→复盘完整结构
70-89: 覆盖大部分结构要素
50-69: 只涵盖 1-2 个要素
0-49: 结构完全缺失

**复盘改进（reflection, 权重 8%）**
90-100: 有明确的效果数据、教训和下次会如何改进
70-89: 提到了结果或改进点
50-69: 仅简单提及，缺乏细节
0-49: 没有任何复盘

**追问响应（follow_up, 权重 6%）**
如果有追问：90-100=追问后补充了实质信息；50-69=追问后仍然泛泛；0-49=追问无效
如果没有追问：给 65 分（中性）
"""

_EVAL_SYSTEM = f"""\
你是一位资深技术面试评估专家，使用 Prometheus 风格的细粒度 rubric 评分（arXiv:2310.08491）。

**反偏差指令（arXiv:2406.07791）**
- 不要因为回答长就给高分——简短精准 > 冗长模糊
- 不要因为格式好看（分点、markdown）就给高分
- 不要偏爱听起来"有把握"的语气——要看实质内容

**评分标准（每项 0-100）**
{_RUBRIC_CRITERIA}

**输出格式**：严格 JSON，不输出其他文字：
{{
  "reasoning": "逐维度分析（中文，2-4句）",
  "rubric_scores": {{
    "relevance":    {{"score": 0-100}},
    "knowledge":    {{"score": 0-100}},
    "specificity":  {{"score": 0-100}},
    "reasoning":    {{"score": 0-100}},
    "completeness": {{"score": 0-100}},
    "reflection":   {{"score": 0-100}},
    "follow_up":    {{"score": 0-100}}
  }},
  "strengths": "本题最突出的优点（1-2句）",
  "gaps": "最需要改进的地方（1-2句）",
  "covered_knowledge_points": ["实际覆盖到的知识点名称列表"]
}}"""


def evaluate(state: InterviewState) -> InterviewState:
    plan = state.get("question_plan") or []
    history = state.get("qa_history") or []

    # Separate skipped/missing questions (handled locally) from scorable ones
    scorable_qs, scorable_items, local_results = [], [], {}
    for q in plan:
        item = next((h for h in history if h.get("q_id") == q.get("id")), None)
        if not item:
            local_results[q.get("id")] = _missing(q)
            continue
        answer = (item.get("answer") or "").strip()
        combined = " ".join([answer, *[(f.get("answer") or "") for f in (item.get("follow_ups") or [])]]).strip()
        if _is_skipped(item, answer):
            local_results[q.get("id")] = _empty_eval(q, "跳过未作答", "本题被跳过，缺少可验证证据。")
        elif _is_off_topic(combined):
            local_results[q.get("id")] = _empty_eval(q, "回答与问题弱相关", "需要回到题目本身，围绕背景、方案、权衡和结果作答。", off_topic=True)
        else:
            scorable_qs.append(q)
            scorable_items.append(item)

    # Batch LLM scoring: one call (or J calls for multi-judge) for all scorable questions.
    session_id = str(state.get("session_id") or "")
    batch_results = _llm_batch_score(scorable_qs, scorable_items, session_id=session_id) if scorable_qs else {}

    cleaned = []
    for i, q in enumerate(plan):
        qid = q.get("id")
        if qid in local_results:
            cleaned.append(local_results[qid])
        elif qid in batch_results:
            cleaned.append(batch_results[qid])
        else:
            # Individual fallback (batch parse failed for this question)
            idx = next((j for j, sq in enumerate(scorable_qs) if sq.get("id") == qid), None)
            if idx is not None:
                cleaned.append(_llm_score_item(scorable_qs[idx], scorable_items[idx]) or _score_item(scorable_qs[idx], scorable_items[idx]))
            else:
                cleaned.append(_missing(q))

    # Roll the per-question evaluations into the memory / bandit state so the
    # next interview session (or replayed simulation) starts warm.
    patch: dict[str, Any] = {
        "evaluations": cleaned,
        "stage": "reporting",
        "last_active_agent": "InterviewAgent",
    }
    memory_patch = _fold_into_memory(state, plan, cleaned)
    if memory_patch:
        patch.update(memory_patch)
    return patch


def _fold_into_memory(
    state: InterviewState,
    plan: list[dict],
    cleaned: list[dict],
) -> dict[str, Any]:
    """Replay each evaluated turn through memory + bandit updates.

    We do this in the evaluator (rather than incrementally per turn) because
    the existing graph evaluates the entire transcript in one shot; the order
    is deterministic and the updates are pure functions on a draft state.
    """
    try:
        from app.agents.memory import numeric_difficulty, update_after_eval
        from app.services.bandit import build_context, reward, update_after_reward
    except Exception:
        return {}

    s = get_settings()
    draft = dict(state)
    rounds_total = max(len(plan), int(state.get("target_total_questions") or len(plan) or 1))

    for q, ev in zip(plan, cleaned):
        score_unit = max(0.0, min(1.0, float(ev.get("score", 0)) / 100.0))
        category = str(q.get("category") or "")
        if not category:
            continue
        difficulty_num = float(q.get("difficulty_numeric") or numeric_difficulty(state.get("difficulty") or "mid"))
        new_gaps = _split_gaps(ev.get("gaps"))

        # 1) memory update
        mem_patch = update_after_eval(
            draft,
            category=category,
            difficulty_numeric=difficulty_num,
            overall_score_unit=score_unit,
            new_gaps=new_gaps,
            next_direction=str(ev.get("next_direction") or ""),
            provenance=f"{ev.get('id')}:{category}:{int(score_unit * 100)}",
        )
        draft.update(mem_patch)

        # 2) bandit update — only meaningful when the planner used a bandit policy.
        if (s.selector_strategy or "round_robin").lower() != "round_robin":
            ctx = q.get("bandit_context") or build_context(draft, category, rounds_total=rounds_total)
            cov_count = draft.get("coverage_count") or {}
            cov_ratio = cov_count.get(category, 0) / max(1, sum(cov_count.values()) or 1)
            r = reward(
                overall_score_unit=score_unit,
                target_difficulty=s.difficulty_target,
                coverage_ratio=cov_ratio,
                gap_resolved=bool(ev.get("covered_knowledge_points")),
                resume_aff=0.5,
            )
            ban_patch = update_after_reward(
                draft,
                chosen_arm=category,
                context=ctx,
                reward_value=r,
                rounds_total=rounds_total,
            )
            draft.update(ban_patch)

    # Only return the memory / bandit slice — the caller already has `cleaned`.
    keys = (
        "ability_estimate", "score_window", "per_topic_stats", "coverage_count",
        "gap_set", "next_direction_hints", "eval_provenance",
        "difficulty_trajectory", "chapter_trajectory", "bandit_state",
    )
    return {k: draft[k] for k in keys if k in draft}


def _split_gaps(text: Any) -> list[str]:
    if not text:
        return []
    raw = str(text)
    out: list[str] = []
    for piece in re.split(r"[；;。,，]", raw):
        p = piece.strip()
        if 3 < len(p) < 80:
            out.append(p)
    return out[:3]


_BATCH_EVAL_SYSTEM = f"""\
你是一位资深技术面试评估专家，使用 Prometheus 风格的细粒度 rubric 评分（arXiv:2310.08491）。

**反偏差指令（arXiv:2406.07791）**
- 不要因为回答长就给高分——简短精准 > 冗长模糊
- 不要因为格式好看（分点、markdown）就给高分
- 不要偏爱听起来"有把握"的语气——要看实质内容

**评分标准（每项 0-100）**
{_RUBRIC_CRITERIA}

你将收到多道面试题及候选人回答，每题用 ---题目N--- 分隔。
对每道题单独评分，返回 JSON 数组，每个元素对应一道题（顺序一致）：
[
  {{
    "reasoning": "逐维度分析（中文，2-4句）",
    "rubric_scores": {{
      "relevance": {{"score": 0-100}},
      "knowledge": {{"score": 0-100}},
      "specificity": {{"score": 0-100}},
      "reasoning": {{"score": 0-100}},
      "completeness": {{"score": 0-100}},
      "reflection": {{"score": 0-100}},
      "follow_up": {{"score": 0-100}}
    }},
    "strengths": "本题最突出的优点（1-2句）",
    "gaps": "最需要改进的地方（1-2句）",
    "covered_knowledge_points": ["实际覆盖到的知识点名称列表"],
    "next_direction": "下一题建议聚焦的类别（技术深度/项目经验/系统设计/沟通表达/学习能力）+ 一句话原因，限 30 字"
  }},
  ...
]
严格只输出 JSON 数组，不输出其他文字。"""


# Ablation variant: same schema, but explicitly forbids the rationale field so
# we can isolate the contribution of chain-of-thought scoring (paper §6.1).
_BATCH_EVAL_SYSTEM_NO_COT = f"""\
你是一位资深技术面试评估专家。请直接给出每个维度的分数，无需先输出推理过程。

**评分标准（每项 0-100）**
{_RUBRIC_CRITERIA}

返回 JSON 数组，每个元素对应一道题（顺序一致）：
[
  {{
    "rubric_scores": {{
      "relevance": {{"score": 0-100}},
      "knowledge": {{"score": 0-100}},
      "specificity": {{"score": 0-100}},
      "reasoning": {{"score": 0-100}},
      "completeness": {{"score": 0-100}},
      "reflection": {{"score": 0-100}},
      "follow_up": {{"score": 0-100}}
    }},
    "strengths": "本题最突出的优点（1-2句）",
    "gaps": "最需要改进的地方（1-2句）",
    "covered_knowledge_points": ["实际覆盖到的知识点名称列表"],
    "next_direction": "下一题建议聚焦的类别 + 一句话原因，限 30 字"
  }},
  ...
]
严格只输出 JSON 数组，不输出其他文字。"""


def _llm_batch_score(questions: list[dict], items: list[dict], session_id: str = "") -> dict[str, dict]:
    """LLM scoring entry point with optional multi-judge aggregation.

    When ``settings.llm_multi_judge_count > 1`` we run J independent passes
    (different temperatures), validate each one, and aggregate per-dimension.
    The per-question consensus is propagated into ``_assemble_llm_result``
    via the ``consensus`` argument so calibration can soften unreliable
    scores back toward the rule-based baseline.
    """
    if not questions:
        return {}

    s = get_settings()
    judge_count = max(1, int(s.llm_multi_judge_count))
    temps = list(s.llm_judge_temperatures) or [0.1]
    if len(temps) < judge_count:
        temps = (temps * (judge_count // len(temps) + 1))[:judge_count]
    else:
        temps = temps[:judge_count]

    user_msg = _build_batch_prompt(questions, items)
    judge_outputs: list[list[dict]] = []
    for j in range(judge_count):
        parsed = _run_single_judge(user_msg, temps[j], len(questions), use_cot=s.llm_use_cot)
        if parsed is None:
            continue
        judge_outputs.append(parsed)
        # Short-circuit: in the default single-judge mode, no need to try more.
        if judge_count == 1:
            break

    if not judge_outputs:
        return {}

    if judge_count == 1:
        return _assemble_batch(questions, items, judge_outputs[0], consensus=None, judge_panel=None)

    aggregated, panel = _aggregate_judges(judge_outputs, len(questions), session_id=session_id)
    return _assemble_batch(questions, items, aggregated, consensus=panel, judge_panel=panel)


def _build_batch_prompt(questions: list[dict], items: list[dict]) -> str:
    sections = []
    for i, (q, item) in enumerate(zip(questions, items)):
        answer = (item.get("answer") or "").strip()
        follow_ups = item.get("follow_ups") or []
        follow_up_section = ""
        if follow_ups:
            follow_up_section = "\n追问与回答：\n" + "\n".join(
                f"  追问：{f.get('question', '')}\n  回答：{f.get('answer', '')}"
                for f in follow_ups
            )
        points = q.get("knowledge_points") or []
        sections.append(
            f"---题目{i + 1}---\n"
            f"类别：{q.get('category', '')}  意图：{q.get('intent', '')}\n"
            f"知识点：{', '.join(points)}\n"
            f"题目：{q.get('question', '')}\n"
            f"回答：{answer}{follow_up_section}"
        )
    return "\n\n".join(sections)


def _run_single_judge(
    user_msg: str,
    temperature: float,
    n_questions: int,
    *,
    use_cot: bool,
) -> list[dict] | None:
    """One LLM pass; returns a list of parsed dicts (one per question)."""
    try:
        from app.services.llm import chat, extract_json

        system_prompt = _BATCH_EVAL_SYSTEM if use_cot else _BATCH_EVAL_SYSTEM_NO_COT
        llm = chat(temperature=float(temperature), max_tokens=min(4000, 900 * n_questions))
        res = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_msg)])
        parsed = extract_json(res.content)
        if not isinstance(parsed, list) or len(parsed) != n_questions:
            return None
        # Schema-validate each entry up-front; drop the whole pass on egregious failures.
        ok = 0
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            if validate_single_judge(entry).ok:
                ok += 1
        if ok < max(1, n_questions // 2):
            return None
        return parsed
    except Exception:
        return None


def _aggregate_judges(
    judge_outputs: list[list[dict]],
    n_questions: int,
    session_id: str = "",
) -> tuple[list[dict], list[dict]]:
    """Per-question rubric-score aggregation across J judges.

    The aggregator is selected by ``settings.judge_aggregator``:
      * ``trimmed`` (default) — symmetric trimmed mean per rubric dimension.
        Equivalent to the original production behaviour.
      * ``rwmj`` — Reliability-Weighted Multi-Judge (paper §3.8). Per-judge
        bias + variance are maintained online via EMA inside one session;
        per-rubric-dimension state is kept independent so that, e.g., a
        judge that drifts on \texttt{specificity} doesn't pollute its
        \texttt{relevance} weight.

    Returns ``(aggregated_entries, panel_info)`` where ``panel_info[i]`` carries
    the cross-judge spread + consensus signals needed by the calibrator.
    """
    s = get_settings()
    trim = max(0.0, min(0.4, float(s.judge_outlier_trim)))
    use_rwmj = (str(getattr(s, "judge_aggregator", "trimmed")).lower() == "rwmj") and _RWMJ_AVAILABLE

    aggregated: list[dict] = []
    panel_info: list[dict] = []

    for i in range(n_questions):
        per_dim: dict[str, list[float]] = {d: [] for d in REQUIRED_DIMENSIONS}
        reasonings: list[str] = []
        strengths_pool: list[str] = []
        gaps_pool: list[str] = []
        coverage_pool: list[list[str]] = []

        for entry_list in judge_outputs:
            entry = entry_list[i] if i < len(entry_list) else None
            if not isinstance(entry, dict):
                continue
            rs = entry.get("rubric_scores") or {}
            for d in REQUIRED_DIMENSIONS:
                raw = rs.get(d)
                val = raw.get("score") if isinstance(raw, dict) else raw
                if isinstance(val, (int, float)):
                    per_dim[d].append(_clamp(float(val)))
            if entry.get("reasoning"):
                reasonings.append(str(entry["reasoning"]))
            if entry.get("strengths"):
                strengths_pool.append(str(entry["strengths"]))
            if entry.get("gaps"):
                gaps_pool.append(str(entry["gaps"]))
            if isinstance(entry.get("covered_knowledge_points"), list):
                coverage_pool.append([str(x) for x in entry["covered_knowledge_points"]])

        rubric_scores: dict[str, dict] = {}
        spreads: list[float] = []
        rwmj_rhos: list[float] = []
        for d in REQUIRED_DIMENSIONS:
            values = per_dim[d] or [60.0]
            spread = (max(values) - min(values)) if len(values) > 1 else 0.0
            if use_rwmj and len(values) >= 2:
                # RW-MJ expects [0,1]; the validator stores raw 0..100.
                unit = [max(0.0, min(1.0, float(v) / 100.0)) for v in values]
                agg = _rwmj_for(session_id, d)
                s_hat, rho, _dbg = agg.aggregate(unit)
                rubric_scores[d] = {"score": float(s_hat) * 100.0}
                rwmj_rhos.append(float(rho))
            else:
                mean = _trimmed_mean(values, trim)
                rubric_scores[d] = {"score": mean}
            spreads.append(spread)

        consistency = cross_judge_consistency(per_dim)
        agreement = max(0.0, 1.0 - (sum(spreads) / max(1, len(spreads))) / 100.0)

        aggregated.append({
            "rubric_scores": rubric_scores,
            "reasoning": _longest(reasonings),
            "strengths": _longest(strengths_pool),
            "gaps": _longest(gaps_pool),
            "covered_knowledge_points": _merge_coverage(coverage_pool),
        })
        panel_info.append({
            "judge_count": len(judge_outputs),
            "agreement": round(agreement, 3),
            "mean_spread": round(sum(spreads) / max(1, len(spreads)), 2),
            "consistency_ok": consistency.ok,
            "consistency_issues": consistency.issues[:3],
            "aggregator": "rwmj" if use_rwmj else "trimmed",
            "rwmj_rho": round(sum(rwmj_rhos) / max(1, len(rwmj_rhos)), 3) if rwmj_rhos else None,
        })

    return aggregated, panel_info


def _trimmed_mean(values: list[float], trim_frac: float) -> float:
    if not values:
        return 60.0
    if trim_frac <= 0 or len(values) < 4:
        return sum(values) / len(values)
    sorted_v = sorted(values)
    k = int(len(sorted_v) * trim_frac)
    sliced = sorted_v[k: len(sorted_v) - k] or sorted_v
    return sum(sliced) / len(sliced)


def _longest(items: list[str]) -> str:
    return max(items, key=len) if items else ""


def _merge_coverage(coverage_pool: list[list[str]]) -> list[str]:
    if not coverage_pool:
        return []
    counts: Counter[str] = Counter()
    for lst in coverage_pool:
        for x in set(lst):
            counts[x] += 1
    # Keep items mentioned by at least half the judges.
    threshold = max(1, len(coverage_pool) // 2)
    return [k for k, c in counts.items() if c >= threshold]


def _assemble_batch(
    questions: list[dict],
    items: list[dict],
    parsed_list: list[dict],
    *,
    consensus: list[dict] | None,
    judge_panel: list[dict] | None,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for idx, (q, item, entry) in enumerate(zip(questions, items, parsed_list)):
        if not isinstance(entry, dict):
            continue
        panel = (consensus or [None] * len(parsed_list))[idx]
        debug = (judge_panel or [None] * len(parsed_list))[idx]
        result = _assemble_llm_result(q, item, entry, panel=panel, debug=debug)
        if result:
            results[q.get("id")] = result
    return results


def _assemble_llm_result(
    q: dict,
    item: dict,
    parsed: dict,
    *,
    panel: dict | None = None,
    debug: dict | None = None,
) -> dict | None:
    """Build the final eval dict from a parsed LLM JSON entry (single or batch).

    When ``panel`` is provided we apply consensus-weighted calibration: high
    cross-judge agreement → trust the LLM more; low agreement → blend toward
    the raw weighted score.
    """
    try:
        s = get_settings()
        answer = (item.get("answer") or "").strip()
        follow_ups = item.get("follow_ups") or []
        combined_answer = " ".join([answer, *[(f.get("answer") or "") for f in follow_ups]]).strip()
        points = q.get("knowledge_points") or []

        raw_scores = parsed.get("rubric_scores") or {}
        sub_scores: dict[str, float] = {}
        for key in RUBRIC:
            entry = raw_scores.get(key) or {}
            raw = entry.get("score") if isinstance(entry, dict) else entry
            sub_scores[key] = _clamp(float(raw) if isinstance(raw, (int, float)) else 60.0)

        base = sum(sub_scores[k] * RUBRIC[k]["weight"] for k in RUBRIC)
        reliability = _reliability(combined_answer, sub_scores, item)
        legacy_calibrated = _calibrate(base, reliability, item)

        if s.calibration_enabled:
            calibrator = load_calibrator()
            agreement = float(panel.get("agreement")) if isinstance(panel, dict) and panel.get("agreement") is not None else None
            mapped_unit = calibrator.apply(legacy_calibrated / 100.0, consensus=agreement)
            calibrated = round(_clamp(mapped_unit * 100.0))
        else:
            calibrator = None
            calibrated = legacy_calibrated

        strongest_key = max(sub_scores, key=sub_scores.get)
        weakest_key = min(sub_scores, key=sub_scores.get)
        coverage = _infer_covered_points(parsed.get("covered_knowledge_points"), combined_answer, points)

        next_dir_raw = parsed.get("next_direction")
        next_direction = _normalise_next_direction(next_dir_raw, weakest_key, points)

        notes = [
            "采用 G-Eval/Prometheus 混合方案：LLM 先推理再打分，避免 verbosity bias。",
            "rubric 覆盖相关性、知识覆盖、证据具体性、逻辑推理、结构完整、复盘改进、追问响应七维度。",
            "最终分数经证据质量和完成度校准。",
        ]
        if calibrator is not None:
            notes.append(
                f"分数经 {calibrator.mode} 校准 (confidence={calibrator.confidence:.2f}, n={calibrator.fitted_pairs})。"
            )
        if isinstance(panel, dict):
            notes.append(
                f"多评委一致性 agreement={panel.get('agreement'):.2f}, spread={panel.get('mean_spread'):.1f}。"
            )

        return {
            "id": q.get("id"),
            "category": q.get("category"),
            "knowledge_points": q.get("knowledge_points", []),
            "score": calibrated,
            "strengths": parsed.get("strengths") or _strength_text(strongest_key, sub_scores[strongest_key], coverage),
            "gaps": parsed.get("gaps") or _gap_text(weakest_key, sub_scores[weakest_key], points, coverage),
            "llm_reasoning": parsed.get("reasoning", ""),
            "rubric_scores": {
                key: {"label": RUBRIC[key]["label"], "score": round(sub_scores[key]), "weight": RUBRIC[key]["weight"]}
                for key in RUBRIC
            },
            "evidence_quality": round(reliability * 100),
            "uncertainty": round((1 - reliability) * 100),
            "covered_knowledge_points": coverage,
            "next_direction": next_direction,
            "judge_panel": debug,
            "evaluation_notes": notes,
        }
    except Exception:
        return None


def _normalise_next_direction(raw: Any, weakest_key: str, points: list[str]) -> str:
    """Pin the LLM's free-text suggestion to a known category when possible."""
    text = str(raw or "").strip()
    if not text:
        # Heuristic fallback from the weakest rubric dimension.
        mapping = {
            "knowledge": "技术深度",
            "specificity": "项目经验",
            "reasoning": "系统设计",
            "completeness": "项目经验",
            "reflection": "学习能力",
            "follow_up": "沟通表达",
            "relevance": "技术深度",
        }
        cat = mapping.get(weakest_key, "技术深度")
        hint = f"建议下一题聚焦 {cat}"
        if points:
            hint += f"（围绕 {points[0]}）"
        return hint
    for cat in MEMORY_CATEGORIES:
        if cat in text:
            return text
    # Pull in the nearest category by simple keyword sniff.
    if any(k in text for k in ("架构", "扩展", "高并发", "分布式", "可观测")):
        cat = "系统设计"
    elif any(k in text for k in ("沟通", "对齐", "协作", "评审")):
        cat = "沟通表达"
    elif any(k in text for k in ("学习", "新技术", "调研", "前沿")):
        cat = "学习能力"
    elif any(k in text for k in ("项目", "上线", "复盘")):
        cat = "项目经验"
    else:
        cat = "技术深度"
    return f"{cat}：{text}"


def _llm_score_item(q: dict, item: dict) -> dict | None:
    """Single-question G-Eval/Prometheus fallback (used when batch parsing fails)."""
    try:
        from app.services.llm import chat, extract_json

        answer = (item.get("answer") or "").strip()
        follow_ups = item.get("follow_ups") or []
        follow_up_section = ""
        if follow_ups:
            follow_up_section = "\n\n追问与回答：\n" + "\n".join(
                f"  追问：{f.get('question', '')}\n  回答：{f.get('answer', '')}"
                for f in follow_ups
            )
        points = q.get("knowledge_points") or []
        user_msg = (
            f"题目类别：{q.get('category', '')}\n"
            f"考察意图：{q.get('intent', '')}\n"
            f"待考察知识点：{', '.join(points)}\n\n"
            f"面试题：{q.get('question', '')}\n\n"
            f"候选人主要回答：\n{answer}"
            f"{follow_up_section}"
        )
        llm = chat(temperature=0.1, max_tokens=1200)
        res = llm.invoke([SystemMessage(content=_EVAL_SYSTEM), HumanMessage(content=user_msg)])
        parsed = extract_json(res.content)
        if not isinstance(parsed, dict):
            return None
        return _assemble_llm_result(q, item, parsed)
    except Exception:
        return None


def _infer_covered_points(
    llm_list: Any,
    answer: str,
    points: list[str],
) -> list[str]:
    """Merge LLM-reported coverage with local soft-match as a sanity check."""
    if isinstance(llm_list, list):
        valid = [str(p) for p in llm_list if isinstance(p, str) and p in points]
        if valid:
            return valid
    # Fallback to local heuristic
    answer_tokens = _tokens(answer)
    return [p for p in points if _soft_contains(answer_tokens, p)]


# ---------------------------------------------------------------------------
# Local heuristic fallback (kept intact from original)
# ---------------------------------------------------------------------------

def _score_item(q: dict, item: dict | None) -> dict:
    if not item:
        return _missing(q)

    answer = (item.get("answer") or "").strip()
    follow_ups = item.get("follow_ups") or []
    combined_answer = " ".join([answer, *[(f.get("answer") or "") for f in follow_ups]]).strip()

    if _is_skipped(item, answer):
        return _empty_eval(q, "跳过未作答", "本题被跳过，缺少可验证证据。")

    if _is_off_topic(combined_answer):
        return _empty_eval(q, "回答与问题弱相关", "需要回到题目本身，围绕背景、方案、权衡和结果作答。", off_topic=True)

    context = _question_context(q)
    answer_tokens = _tokens(combined_answer)
    context_tokens = _tokens(context)
    knowledge_tokens = _tokens(" ".join(q.get("knowledge_points") or []))

    sub_scores = {
        "relevance":    _relevance(answer_tokens, context_tokens, combined_answer),
        "knowledge":    _knowledge(answer_tokens, knowledge_tokens, q.get("knowledge_points") or []),
        "specificity":  _specificity(combined_answer),
        "reasoning":    _reasoning(combined_answer),
        "completeness": _completeness(answer, follow_ups),
        "reflection":   _reflection(combined_answer),
        "follow_up":    _follow_up_score(follow_ups),
    }
    base = sum(sub_scores[k] * RUBRIC[k]["weight"] for k in RUBRIC)
    reliability = _reliability(combined_answer, sub_scores, item)
    calibrated = _calibrate(base, reliability, item)

    strongest_key = max(sub_scores, key=sub_scores.get)
    weakest_key = min(sub_scores, key=sub_scores.get)
    coverage = _covered_knowledge_points(combined_answer, q.get("knowledge_points") or [])

    return {
        "id": q.get("id"),
        "category": q.get("category"),
        "knowledge_points": q.get("knowledge_points", []),
        "score": calibrated,
        "strengths": _strength_text(strongest_key, sub_scores[strongest_key], coverage),
        "gaps": _gap_text(weakest_key, sub_scores[weakest_key], q.get("knowledge_points") or [], coverage),
        "rubric_scores": {
            key: {
                "label": RUBRIC[key]["label"],
                "score": round(value),
                "weight": RUBRIC[key]["weight"],
            }
            for key, value in sub_scores.items()
        },
        "evidence_quality": round(reliability * 100),
        "uncertainty": round((1 - reliability) * 100),
        "covered_knowledge_points": coverage,
        "evaluation_notes": [
            "采用多维 rubric 直接评分，减少单一总分偏差。",
            "用题目意图、知识点覆盖和回答证据密度做校准。",
            "追问回答会并入同一题证据链，但权重低于主回答。",
        ],
    }


def _question_context(q: dict) -> str:
    return " ".join([
        str(q.get("question") or ""),
        str(q.get("intent") or ""),
        str(q.get("category") or ""),
        " ".join(q.get("knowledge_points") or []),
    ])


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    ascii_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]{1,}", lowered)
    cjk = re.findall(r"[一-鿿]", lowered)
    cjk_bigrams = ["".join(cjk[i:i + 2]) for i in range(max(0, len(cjk) - 1))]
    tokens = ascii_words + cjk_bigrams
    return [t for t in tokens if t not in STOPWORDS and len(t.strip()) > 1]


def _coverage_ratio(answer_tokens: list[str], target_tokens: list[str]) -> float:
    if not target_tokens:
        return 0.55
    answer_set = set(answer_tokens)
    target = set(target_tokens)
    return len(answer_set & target) / max(1, len(target))


def _relevance(answer_tokens: list[str], context_tokens: list[str], answer: str) -> float:
    overlap = _coverage_ratio(answer_tokens, context_tokens)
    length_bonus = min(18, len(answer) / 10)
    return _clamp(38 + overlap * 48 + length_bonus)


def _knowledge(answer_tokens: list[str], knowledge_tokens: list[str], points: list[str]) -> float:
    if not points:
        return 68
    overlap = _coverage_ratio(answer_tokens, knowledge_tokens)
    explicit_hits = sum(1 for p in points if _soft_contains(answer_tokens, p))
    explicit_ratio = explicit_hits / len(points)
    return _clamp(35 + overlap * 35 + explicit_ratio * 30)


def _specificity(answer: str) -> float:
    numbers = len(re.findall(r"\d+|一|二|三|四|五|六|七|八|九|十", answer))
    markers = sum(1 for m in RESULT_MARKERS if m.lower() in answer.lower())
    nouns = len(set(_tokens(answer)))
    return _clamp(35 + min(20, numbers * 5) + min(22, markers * 5) + min(23, nouns / 3))


def _reasoning(answer: str) -> float:
    markers = sum(1 for m in REASONING_MARKERS if m.lower() in answer.lower())
    sentence_count = max(1, len(re.split(r"[。！？!?；;\n]", answer.strip())))
    structure = 10 if sentence_count >= 3 else 0
    return _clamp(40 + min(38, markers * 6) + structure + min(12, len(answer) / 35))


def _completeness(answer: str, follow_ups: list[dict]) -> float:
    length = len(answer)
    base = 28 + min(42, length / 4)
    if any(word in answer for word in ("背景", "目标", "方案", "结果", "难点", "权衡")):
        base += 12
    if follow_ups:
        base += min(18, 8 + len(" ".join(f.get("answer", "") for f in follow_ups)) / 20)
    return _clamp(base)


def _reflection(answer: str) -> float:
    markers = ("复盘", "不足", "改进", "如果", "下次", "风险", "教训", "监控", "回滚", "验证")
    hits = sum(1 for m in markers if m in answer)
    return _clamp(42 + min(42, hits * 9) + min(16, len(answer) / 60))


def _follow_up_score(follow_ups: list[dict]) -> float:
    if not follow_ups:
        return 62
    latest = (follow_ups[-1].get("answer") or "").strip()
    if _is_off_topic(latest):
        return 20
    return _clamp(55 + min(28, len(latest) / 5) + (12 if any(m in latest for m in REASONING_MARKERS) else 0))


def _reliability(answer: str, sub_scores: dict[str, float], item: dict) -> float:
    length_factor = min(1.0, len(answer) / 180)
    variance = _variance(list(sub_scores.values()))
    consistency = max(0.62, 1 - variance / 1400)
    speech = (item.get("speech_metrics") or {})
    speech_factor = 0.04 if speech.get("duration_ms") else 0
    return _clamp_float(0.42 + length_factor * 0.35 + consistency * 0.19 + speech_factor, 0.35, 0.98)


def _calibrate(base: float, reliability: float, item: dict) -> int:
    score = base * (0.82 + reliability * 0.18)
    if len((item.get("answer") or "").strip()) < 45:
        score -= 8
    if (item.get("speech_metrics") or {}).get("confidence", 1) < 0.55:
        score -= 3
    return round(_clamp(score, 0, 96))


def _covered_knowledge_points(answer: str, points: list[str]) -> list[str]:
    answer_tokens = _tokens(answer)
    return [p for p in points if _soft_contains(answer_tokens, p)]


def _soft_contains(answer_tokens: list[str], phrase: str) -> bool:
    phrase_tokens = _tokens(phrase)
    if not phrase_tokens:
        return False
    overlap = _coverage_ratio(answer_tokens, phrase_tokens)
    return overlap >= 0.28 or phrase.lower() in " ".join(answer_tokens)


def _strength_text(key: str, score: float, coverage: list[str]) -> str:
    label = RUBRIC[key]["label"]
    if coverage:
        return f"{label}表现较好，并覆盖了 {', '.join(coverage[:3])} 等知识点。"
    if score >= 75:
        return f"{label}表现较好，回答中能提供较清晰的事实和判断。"
    return "回答与题目有一定关联，具备继续追问和复盘的基础。"


def _gap_text(key: str, score: float, points: list[str], coverage: list[str]) -> str:
    label = RUBRIC[key]["label"]
    missing = [p for p in points if p not in coverage]
    if missing:
        return f"{label}仍需加强，建议补充 {', '.join(missing[:3])} 的具体机制、指标或案例。"
    if score < 60:
        return f"{label}证据不足，建议按「背景-方案-权衡-结果-复盘」展开。"
    return "可以继续补充量化结果、边界条件和个人贡献，让答案更可验证。"


def _empty_eval(q: dict, strengths: str, gaps: str, off_topic: bool = False) -> dict:
    return {
        "id": q.get("id"),
        "category": q.get("category"),
        "knowledge_points": q.get("knowledge_points", []),
        "score": 0,
        "strengths": strengths,
        "gaps": gaps,
        "rubric_scores": {key: {"label": RUBRIC[key]["label"], "score": 0, "weight": RUBRIC[key]["weight"]} for key in RUBRIC},
        "evidence_quality": 0,
        "uncertainty": 100,
        "covered_knowledge_points": [],
        "off_topic": off_topic,
    }


def _missing(q: dict) -> dict:
    return _empty_eval(q, "未覆盖", "本题没有作答记录，无法形成能力判断。")


def _is_skipped(item: dict, answer: str) -> bool:
    return bool(item.get("skipped") or answer.startswith("[跳过") or answer.startswith("[璺宠繃"))


def _is_off_topic(answer: str) -> bool:
    normalized = answer.strip().lower()
    if len(normalized) < 8:
        return True
    if any(marker in normalized for marker in OFF_TOPIC_MARKERS) and len(normalized) < 80:
        return True
    return False


def _variance(values: list[float]) -> float:
    if not values:
        return 0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
