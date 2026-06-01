"""Build a structured final interview report.

The final decision uses weighted evidence aggregation rather than a plain mean:
question score, rubric reliability, knowledge coverage, completion, and audio /
video signals are fused into a calibrated interview score.

Narrative sections (summary, strengths, gaps, next_steps) are synthesized by
an LLM using the per-question evaluations as grounding evidence, producing more
specific and personalized text than template strings. Falls back to templates
if the LLM call fails.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import InterviewState

# ---------------------------------------------------------------------------
# LLM narrative synthesis
# ---------------------------------------------------------------------------

_NARRATIVE_SYSTEM = """\
你是一位专业的招聘评估顾问，根据面试评估数据撰写候选人报告。

要求：
- 每条优势/不足都必须有具体题目或维度作为依据，不允许空泛表述
- 下一步建议必须具体可操作（具体知识点、练习方法）
- 不要使用"非常"、"很好"等模糊褒义词
- 用第三人称描述候选人表现，直接陈述事实

输出严格 JSON（不输出其他文字）：
{
  "summary": "2-3句综合评语，提及最突出的优点和最主要的不足",
  "strengths": ["优势1（引用具体题目或维度）", "优势2", "优势3"],
  "gaps": ["不足1（引用具体题目或维度）", "不足2", "不足3"],
  "next_steps": ["建议1（具体知识点/练习方法）", "建议2", "建议3", "建议4"]
}"""

DIMENSIONS = ["技术深度", "项目经验", "系统设计", "沟通表达", "学习能力"]
DIMENSION_WEIGHTS = {
    "技术深度": 1.18,
    "项目经验": 1.08,
    "系统设计": 1.12,
    "沟通表达": 0.92,
    "学习能力": 0.88,
}


def _llm_narrative(
    overall: int,
    completion: dict,
    dimensions: dict,
    evaluations: list[dict],
    knowledge_coverage: dict,
    profile: dict,
    position: str,
) -> dict | None:
    """Call LLM once to synthesize grounded narrative sections."""
    try:
        from app.services.llm import chat, extract_json

        # Compact evidence for the LLM — include reasoning from LLM evaluations if present
        per_q = []
        for ev in evaluations:
            entry: dict[str, Any] = {
                "category": ev.get("category"),
                "score": ev.get("score", 0),
                "strengths": ev.get("strengths", ""),
                "gaps": ev.get("gaps", ""),
            }
            if ev.get("llm_reasoning"):
                entry["reasoning"] = ev["llm_reasoning"]
            per_q.append(entry)

        user_msg = (
            f"目标岗位：{position}\n"
            f"综合得分：{overall}\n"
            f"维度得分：{json.dumps(dimensions, ensure_ascii=False)}\n"
            f"完成情况：有效作答 {completion.get('answered', 0)} 题，"
            f"跳过 {completion.get('skipped', 0)} 题\n"
            f"知识点覆盖分：{knowledge_coverage.get('overall_score', 0)}\n\n"
            f"逐题评估摘要：\n{json.dumps(per_q, ensure_ascii=False, indent=2)}"
        )

        llm = chat(temperature=0.4, max_tokens=1200)
        res = llm.invoke([SystemMessage(content=_NARRATIVE_SYSTEM), HumanMessage(content=user_msg)])
        parsed = extract_json(res.content)
        if not isinstance(parsed, dict):
            return None
        # Validate required keys
        if not all(k in parsed for k in ("summary", "strengths", "gaps", "next_steps")):
            return None
        # Ensure list fields are lists
        for k in ("strengths", "gaps", "next_steps"):
            if not isinstance(parsed[k], list):
                parsed[k] = [str(parsed[k])]
        return parsed
    except Exception:
        return None


def build_report(state: InterviewState) -> InterviewState:
    evaluations = state.get("evaluations") or []
    history = state.get("qa_history") or []
    plan = state.get("question_plan") or []
    profile = state.get("resume_profile") or {}
    position = state.get("position", "")

    completion = _completion_summary(history, state.get("target_total_questions", 8))
    speech_summary = _speech_summary(history, state.get("audio_metrics") or [])
    video_summary = _video_summary(state.get("video_metrics") or [])
    knowledge_coverage = _knowledge_coverage(plan, history, evaluations)
    dimensions = _dimension_scores(evaluations)
    dimension_details = _dimension_details(dimensions, evaluations, history)
    overall = _overall_score(evaluations, completion, knowledge_coverage, speech_summary, video_summary)
    weakest = sorted(evaluations, key=lambda ev: ev.get("score", 0))[:2]
    strongest = sorted(evaluations, key=lambda ev: ev.get("score", 0), reverse=True)[:2]
    methodology = _evaluation_methodology(evaluations, completion, knowledge_coverage)

    # LLM-synthesized narrative (falls back to template functions)
    narrative = _llm_narrative(overall, completion, dimensions, evaluations, knowledge_coverage, profile, position)

    summary = narrative["summary"] if narrative else _summary(overall, completion, speech_summary, video_summary, knowledge_coverage)
    strengths = narrative["strengths"] if narrative else _strengths(strongest, completion, dimension_details, speech_summary, video_summary, knowledge_coverage)
    gaps = narrative["gaps"] if narrative else _gaps(weakest, completion, dimension_details, speech_summary, video_summary, knowledge_coverage)
    next_steps = narrative["next_steps"] if narrative else _next_steps(weakest, completion, dimension_details, speech_summary, video_summary, knowledge_coverage)

    report = {
        "overall_score": overall,
        "recommendation": _recommend(overall, completion),
        "summary": summary,
        "strengths": strengths,
        "gaps": gaps,
        "next_steps": next_steps,
        "risk_flags": _risk_flags(overall, completion, speech_summary, video_summary, dimension_details, knowledge_coverage),
        "communication_analysis": {
            "text": _text_analysis(history, evaluations),
            "audio": _audio_analysis(speech_summary),
            "video": _video_analysis(video_summary),
            "metrics": speech_summary,
            "video_metrics": video_summary,
            "audio_dimensions": _audio_dimensions(speech_summary),
            "video_dimensions": _video_dimensions(video_summary),
        },
        "knowledge_coverage": knowledge_coverage,
        "evaluation_methodology": methodology,
        "dimensions": dimensions,
        "dimension_details": dimension_details,
        "completion": completion,
        "interview_trace": _interview_trace(history, evaluations),
        "per_question": evaluations,
        "qa_history": history,
        "profile": profile,
        "position": position,
    }

    return {"final_report": report, "stage": "done", "last_active_agent": "InterviewAgent"}


def _overall_score(evaluations: list[dict], completion: dict, knowledge: dict, speech: dict, video: dict) -> int:
    answered = [ev for ev in evaluations if ev.get("score", 0) > 0]
    if not answered:
        return 0

    weighted_total = 0.0
    weight_sum = 0.0
    for ev in evaluations:
        score = float(ev.get("score", 0) or 0)
        category = _normalize_category(ev.get("category"))
        reliability = max(0.35, min(1.0, (ev.get("evidence_quality", 60) or 60) / 100))
        category_weight = DIMENSION_WEIGHTS.get(category, 1.0)
        weight = reliability * category_weight
        weighted_total += score * weight
        weight_sum += weight

    base = weighted_total / weight_sum if weight_sum else 0
    coverage_adj = ((knowledge.get("overall_score") or 0) - 65) * 0.10
    completion_adj = (completion.get("completion_rate") or 0) * 6 - 4
    communication_adj = _communication_adjustment(speech, video)
    skip_penalty = min(completion.get("skipped", 0) * 3.5, 16)
    uncertainty_penalty = _avg([ev.get("uncertainty") for ev in evaluations if isinstance(ev.get("uncertainty"), (int, float))])
    uncertainty_adj = -min(7, (uncertainty_penalty or 0) / 14)

    return round(_clip(base + coverage_adj + completion_adj + communication_adj + uncertainty_adj - skip_penalty))


def _dimension_scores(evaluations: list[dict]) -> dict[str, int]:
    bucket: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for ev in evaluations:
        category = _normalize_category(ev.get("category"))
        score = int(ev.get("score", 0) or 0)
        reliability = max(0.35, min(1.0, (ev.get("evidence_quality", 60) or 60) / 100))
        bucket[category].append((score, reliability))
    result = {}
    for dim in DIMENSIONS:
        rows = bucket.get(dim, [])
        if not rows:
            result[dim] = 0
            continue
        total = sum(score * weight for score, weight in rows)
        weights = sum(weight for _, weight in rows)
        result[dim] = round(total / weights) if weights else 0
    return result


def _dimension_details(dimensions: dict[str, int], evaluations: list[dict], history: list[dict]) -> list[dict[str, Any]]:
    evidence_by_dim: dict[str, list[dict]] = defaultdict(list)
    skipped_by_dim: dict[str, int] = defaultdict(int)
    for item in history:
        category = _normalize_category(item.get("category"))
        if _is_skipped(item):
            skipped_by_dim[category] += 1
        elif item.get("answer"):
            evidence_by_dim[category].append(item)

    details = []
    for dim in DIMENSIONS:
        score = dimensions.get(dim, 0)
        related = [ev for ev in evaluations if _normalize_category(ev.get("category")) == dim]
        strengths = [ev.get("strengths") for ev in related if ev.get("strengths")]
        gaps = [ev.get("gaps") for ev in related if ev.get("gaps")]
        uncertainty = _avg([ev.get("uncertainty") for ev in related if isinstance(ev.get("uncertainty"), (int, float))])
        details.append({
            "name": dim,
            "score": score,
            "level": _score_level(score),
            "evidence_count": len(evidence_by_dim.get(dim, [])),
            "skipped_count": skipped_by_dim.get(dim, 0),
            "insight": _dimension_insight(dim, score, strengths, gaps, skipped_by_dim.get(dim, 0), uncertainty),
        })
    return details


def _completion_summary(history: list[dict], target_total: int) -> dict:
    skipped = sum(1 for h in history if _is_skipped(h))
    answered = sum(1 for h in history if h.get("answer") and not _is_skipped(h))
    return {
        "answered": answered,
        "skipped": skipped,
        "total_seen": len(history),
        "target_total": target_total,
        "follow_ups": sum(len(h.get("follow_ups") or []) for h in history),
        "completion_rate": round(answered / target_total, 2) if target_total else 0,
    }


def _speech_summary(history: list[dict], audio_metrics: list[dict]) -> dict:
    answer_metrics = [item.get("speech_metrics") for item in history if isinstance(item.get("speech_metrics"), dict)]
    durations = [m.get("duration_ms", 0) / 1000 for m in answer_metrics if m.get("duration_ms")]
    confidences = [m.get("confidence") for m in answer_metrics if isinstance(m.get("confidence"), (int, float))]
    lengths = [m.get("transcript_length", 0) for m in answer_metrics]
    total_minutes = sum(durations) / 60 if durations else 0
    volume_values = [m.get("avg_volume") for m in audio_metrics if isinstance(m.get("avg_volume"), (int, float))]
    peak_values = [m.get("peak_volume") for m in audio_metrics if isinstance(m.get("peak_volume"), (int, float))]
    silence_values = [m.get("silence_rate") for m in audio_metrics if isinstance(m.get("silence_rate"), (int, float))]
    stability_values = [m.get("volume_stability") for m in audio_metrics if isinstance(m.get("volume_stability"), (int, float))]

    silence_rate = _avg(silence_values)
    stability = _avg(stability_values)
    wpm = round(sum(lengths) / total_minutes, 1) if total_minutes else None
    fluency = _fluency_score(confidences, silence_rate, stability, wpm)
    nervous = _audio_nervousness(silence_rate, stability, _avg(volume_values), wpm)
    confidence_score = _confidence_score(confidences, fluency)

    return {
        "voice_answer_count": len(answer_metrics),
        "audio_sample_count": len(audio_metrics),
        "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        "avg_confidence": round(_avg(confidences), 2) if confidences else None,
        "avg_words_per_minute": wpm,
        "avg_volume": round(_avg(volume_values), 3) if volume_values else None,
        "peak_volume": round(max(peak_values), 3) if peak_values else None,
        "silence_rate": round(silence_rate, 2) if silence_rate is not None else None,
        "volume_stability": round(stability, 2) if stability is not None else None,
        "fluency_score": fluency,
        "nervousness_score": nervous,
        "confidence_score": confidence_score,
        "pace_label": _pace_label(wpm),
    }


def _video_summary(metrics: list[dict]) -> dict:
    if not metrics:
        return {"sample_count": 0}
    presence_values = [m.get("presence") for m in metrics if isinstance(m.get("presence"), bool)]
    brightness_values = [m.get("brightness") for m in metrics if isinstance(m.get("brightness"), (int, float))]
    motion_values = [m.get("motion_proxy") for m in metrics if isinstance(m.get("motion_proxy"), (int, float))]
    face_values = [m.get("face_count") for m in metrics if isinstance(m.get("face_count"), (int, float))]
    attention_values = [m.get("attention_score") for m in metrics if isinstance(m.get("attention_score"), (int, float))]
    center_values = [m.get("centered") for m in metrics if isinstance(m.get("centered"), bool)]
    presence_rate = sum(1 for v in presence_values if v) / len(presence_values) if presence_values else None
    center_rate = sum(1 for v in center_values if v) / len(center_values) if center_values else None
    motion_avg = _avg(motion_values)
    brightness_avg = _avg(brightness_values)
    attention = round(_avg(attention_values)) if attention_values else None
    nervous = _video_nervousness(motion_avg, presence_rate, center_rate)
    return {
        "sample_count": len(metrics),
        "presence_rate": round(presence_rate, 2) if presence_rate is not None else None,
        "avg_brightness": round(brightness_avg, 1) if brightness_avg is not None else None,
        "avg_motion_proxy": round(motion_avg, 1) if motion_avg is not None else None,
        "avg_face_count": round(_avg(face_values), 2) if face_values else None,
        "avg_attention_score": attention,
        "center_rate": round(center_rate, 2) if center_rate is not None else None,
        "lighting_quality": _lighting_quality(brightness_avg),
        "motion_quality": _motion_quality(motion_avg),
        "visual_nervousness_score": nervous,
        "presence_score": round((presence_rate or 0) * 100) if presence_rate is not None else None,
        "framing_score": round((center_rate or 0) * 100) if center_rate is not None else None,
        "lighting_score": _lighting_score(brightness_avg),
    }


def _knowledge_coverage(plan: list[dict], history: list[dict], evaluations: list[dict]) -> dict:
    eval_by_id = {ev.get("id"): ev for ev in evaluations}
    history_by_id = {item.get("q_id"): item for item in history}
    buckets: dict[str, dict[str, Any]] = {}

    for q in plan:
        qid = q.get("id")
        points = q.get("knowledge_points") or []
        item = history_by_id.get(qid, {})
        ev = eval_by_id.get(qid, {})
        answered = bool(item.get("answer")) and not _is_skipped(item)
        score = int(ev.get("score", 0) or 0)
        covered_points = set(ev.get("covered_knowledge_points") or [])
        for point in points:
            name = str(point).strip()
            if not name:
                continue
            bucket = buckets.setdefault(name, {
                "name": name,
                "planned_count": 0,
                "answered_count": 0,
                "covered_count": 0,
                "score_total": 0,
                "questions": [],
            })
            bucket["planned_count"] += 1
            if answered:
                bucket["answered_count"] += 1
                bucket["score_total"] += score
            if name in covered_points:
                bucket["covered_count"] += 1
            bucket["questions"].append({
                "id": qid,
                "category": q.get("category"),
                "answered": answered,
                "covered": name in covered_points,
                "score": score,
            })

    items = []
    for bucket in buckets.values():
        planned = bucket["planned_count"]
        answered = bucket["answered_count"]
        covered = bucket["covered_count"]
        avg_score = round(bucket["score_total"] / answered) if answered else 0
        answer_rate = answered / planned if planned else 0
        explicit_rate = covered / planned if planned else 0
        coverage_rate = round(max(answer_rate * 0.55, explicit_rate), 2)
        coverage_score = round(explicit_rate * 45 + answer_rate * 25 + avg_score * 0.30) if planned else 0
        items.append({
            "name": bucket["name"],
            "planned_count": planned,
            "answered_count": answered,
            "coverage_rate": coverage_rate,
            "avg_score": avg_score,
            "coverage_score": round(_clip(coverage_score)),
            "level": _knowledge_level(coverage_score),
            "questions": bucket["questions"],
        })

    total_planned = sum(item["planned_count"] for item in items)
    total_answered = sum(item["answered_count"] for item in items)
    overall_rate = round(total_answered / total_planned, 2) if total_planned else 0
    overall_score = round(sum(item["coverage_score"] for item in items) / len(items)) if items else 0
    strongest = sorted(items, key=lambda x: (x["coverage_score"], x["answered_count"]), reverse=True)[:4]
    weakest = sorted(items, key=lambda x: (x["coverage_score"], x["answered_count"]))[:4]
    return {
        "overall_score": overall_score,
        "coverage_rate": overall_rate,
        "planned_points": len(items),
        "answered_points": sum(1 for item in items if item["answered_count"] > 0),
        "summary": _knowledge_summary(overall_score, overall_rate, strongest, weakest),
        "items": sorted(items, key=lambda x: x["coverage_score"], reverse=True),
        "strongest": strongest,
        "weakest": weakest,
    }


def _evaluation_methodology(evaluations: list[dict], completion: dict, knowledge: dict) -> dict:
    avg_reliability = _avg([ev.get("evidence_quality") for ev in evaluations if isinstance(ev.get("evidence_quality"), (int, float))])
    avg_uncertainty = _avg([ev.get("uncertainty") for ev in evaluations if isinstance(ev.get("uncertainty"), (int, float))])
    return {
        "name": "Rubric-Calibrated Interview Evaluation",
        "version": "2026.05-local",
        "summary": "每题先按细粒度 rubric 评分，再用证据质量、知识点覆盖、完成率和音视频信号做最终校准。",
        "principles": [
            "G-Eval 思路：把开放回答拆成相关性、知识覆盖、证据、推理、完整度等维度。",
            "Prometheus 思路：每道题使用岗位和知识点定制 rubric，而不是只给一个笼统分数。",
            "MT-Bench 思路：追问回答并入同一题的多轮证据链，并对低证据答案提高不确定性。",
        ],
        "calibration": {
            "avg_evidence_quality": round(avg_reliability or 0),
            "avg_uncertainty": round(avg_uncertainty or 0),
            "completion_rate": completion.get("completion_rate", 0),
            "knowledge_score": knowledge.get("overall_score", 0),
        },
    }


def _audio_dimensions(metrics: dict) -> list[dict[str, Any]]:
    if not metrics.get("voice_answer_count") and not metrics.get("audio_sample_count"):
        return []
    return [
        _detail("流畅度", metrics.get("fluency_score"), "综合语速、停顿、音量稳定和识别置信度。"),
        _detail("紧张程度", _inverse(metrics.get("nervousness_score")), "分数越低代表长停顿、音量波动或语速异常越明显。"),
        _detail("语速节奏", _pace_score(metrics.get("avg_words_per_minute")), f"当前节奏：{metrics.get('pace_label') or '暂无'}。"),
        _detail("停顿控制", _inverse_rate(metrics.get("silence_rate")), "静音占比越低，回答连续性越好。"),
        _detail("音量稳定", _percent_score(metrics.get("volume_stability")), "评估麦克风音量是否忽大忽小。"),
        _detail("作答自信", metrics.get("confidence_score"), "结合 ASR 置信度、流畅度和音量表现估算。"),
    ]


def _video_dimensions(metrics: dict) -> list[dict[str, Any]]:
    if not metrics.get("sample_count"):
        return []
    return [
        _detail("出镜稳定", metrics.get("presence_score"), "候选人持续出现在画面中的比例。"),
        _detail("画面居中", metrics.get("framing_score"), "面部或主体是否处于较合适的位置。"),
        _detail("光线质量", metrics.get("lighting_score"), f"当前判断：{metrics.get('lighting_quality') or '暂无'}。"),
        _detail("动作稳定", _inverse_motion(metrics.get("avg_motion_proxy")), f"当前动作状态：{metrics.get('motion_quality') or '暂无'}。"),
        _detail("视觉紧张程度", _inverse(metrics.get("visual_nervousness_score")), "分数越低代表动作波动、离框或画面不稳定更明显。"),
        _detail("专注观感", metrics.get("avg_attention_score"), "综合出镜、居中、光线和动作稳定性。"),
    ]


def _summary(overall: int, completion: dict, speech: dict, video: dict, knowledge: dict) -> str:
    voice = "已采集语音样本" if speech.get("voice_answer_count") or speech.get("audio_sample_count") else "未采集语音样本"
    video_text = "已采集视频状态样本" if video.get("sample_count") else "未采集视频状态样本"
    return (
        f"本次面试综合得分 {overall}。候选人有效作答 {completion['answered']} 题，"
        f"跳过 {completion['skipped']} 题，追问 {completion['follow_ups']} 次；知识点覆盖度 {knowledge.get('overall_score', 0)}。"
        f"{voice}，{video_text}。报告采用 rubric 校准算法，综合文本证据、知识点、完成度、语音流畅度和视频专注观感。"
    )


def _strengths(strongest: list[dict], completion: dict, details: list[dict], speech: dict, video: dict, knowledge: dict) -> list[str]:
    items = []
    for item in knowledge.get("strongest") or []:
        if item.get("coverage_score", 0) >= 70:
            items.append(f"知识点 {item['name']} 覆盖较好，覆盖分 {item['coverage_score']}。")
    if speech.get("fluency_score") and speech["fluency_score"] >= 75:
        items.append("语音表达较流畅，停顿和音量稳定性支持较好的面试沟通观感。")
    if video.get("avg_attention_score") and video["avg_attention_score"] >= 75:
        items.append("视频出镜和画面状态稳定，远程面试呈现较自然。")
    for detail in sorted(details, key=lambda d: d["score"], reverse=True):
        if detail["score"] >= 70:
            items.append(f"{detail['name']}：{detail['insight']}")
    for ev in strongest:
        if ev.get("score", 0) > 0:
            items.append(f"{ev.get('category', '能力表现')}：{ev.get('strengths') or '回答具备一定信息量。'}")
    if completion["answered"] > 0:
        items.append("能够完成有效作答，具备继续深挖项目细节和复盘表现的基础。")
    return _dedupe(items)[:5] or ["本次有效作答较少，暂未形成稳定优势判断。"]


def _gaps(weakest: list[dict], completion: dict, details: list[dict], speech: dict, video: dict, knowledge: dict) -> list[str]:
    items = []
    if completion["skipped"] > 0:
        items.append(f"跳过 {completion['skipped']} 题，导致部分能力维度缺少可验证证据。")
    for item in knowledge.get("weakest") or []:
        if item.get("coverage_score", 100) < 60:
            items.append(f"知识点 {item['name']} 覆盖不足，建议补充真实项目中的机制、指标和边界条件。")
    if speech.get("nervousness_score") is not None and speech["nervousness_score"] >= 60:
        items.append("语音侧紧张代理偏高，建议练习短句分层表达，减少长停顿和音量波动。")
    if video.get("visual_nervousness_score") is not None and video["visual_nervousness_score"] >= 60:
        items.append("视频侧动作或出镜稳定性存在波动，建议调整坐姿、摄像头高度和光线。")
    for detail in details:
        if detail["score"] < 60 or detail["skipped_count"] > 0:
            items.append(f"{detail['name']}：{detail['insight']}")
    for ev in weakest:
        items.append(f"{ev.get('category', '能力短板')}：{ev.get('gaps') or '需要补充更具体的方案、权衡和结果。'}")
    return _dedupe(items)[:5]


def _next_steps(weakest: list[dict], completion: dict, details: list[dict], speech: dict, video: dict, knowledge: dict) -> list[str]:
    lowest = min(details, key=lambda d: d["score"], default=None)
    steps = ["把低分题按“背景-目标-方案-权衡-结果-复盘”重写一版，补充数据、规模、难点和个人贡献。"]
    weak_points = [item["name"] for item in (knowledge.get("weakest") or [])[:3]]
    if weak_points:
        steps.append(f"优先补齐前沿知识点：{', '.join(weak_points)}，每个知识点准备一个真实项目例子。")
    if completion["skipped"] > 0:
        steps.append("优先补答跳过题，避免关键维度没有证据。")
    if speech.get("nervousness_score") is not None and speech["nervousness_score"] >= 60:
        steps.append("语音训练：每题先用 10 秒列三点，再用 90 秒稳定展开，减少沉默和重复。")
    if video.get("visual_nervousness_score") is not None and video["visual_nervousness_score"] >= 60:
        steps.append("视频训练：固定摄像头，保持脸部居中，回答时减少大幅晃动。")
    if lowest:
        steps.append(f"下一轮重点训练“{lowest['name']}”：准备一个可复用案例，并练习 2 分钟结构化表达。")
    if weakest:
        steps.append(f"复盘最低分题目“{weakest[0].get('category', '综合能力')}”，把回答从结论扩展到过程和取舍。")
    return _dedupe(steps)[:6]


def _risk_flags(overall: int, completion: dict, speech: dict, video: dict, details: list[dict], knowledge: dict) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if completion["skipped"] >= 2:
        flags.append({"level": "high", "title": "跳题偏多", "detail": "多道题缺少作答证据，真实面试中会显著影响判断稳定性。"})
    if overall < 55:
        flags.append({"level": "high", "title": "综合得分偏低", "detail": "当前回答在技术细节或结构完整度上仍需明显加强。"})
    if knowledge.get("overall_score", 0) < 55:
        flags.append({"level": "medium", "title": "知识点覆盖不足", "detail": knowledge.get("summary", "待考察知识点缺少充分覆盖。")})
    for detail in details:
        if detail["score"] < 50:
            flags.append({"level": "medium", "title": f"{detail['name']}证据不足", "detail": detail["insight"]})
    if not speech.get("voice_answer_count") and not speech.get("audio_sample_count"):
        flags.append({"level": "low", "title": "缺少语音样本", "detail": "无法评估语速、停顿、音量稳定性和紧张程度。"})
    elif speech.get("nervousness_score") is not None and speech["nervousness_score"] >= 70:
        flags.append({"level": "medium", "title": "语音紧张程度偏高", "detail": "长停顿、音量波动或语速异常较明显，建议加强口头表达节奏训练。"})
    if not video.get("sample_count"):
        flags.append({"level": "low", "title": "缺少视频样本", "detail": "无法评估出镜稳定、画面居中、光线和动作波动。"})
    elif video.get("visual_nervousness_score") is not None and video["visual_nervousness_score"] >= 70:
        flags.append({"level": "medium", "title": "视频紧张代理偏高", "detail": "动作波动或出镜不稳定较明显，远程面试前建议调试环境和坐姿。"})
    return flags[:8]


def _text_analysis(history: list[dict], evaluations: list[dict]) -> str:
    answered = [h for h in history if h.get("answer") and not _is_skipped(h)]
    avg = round(sum(ev.get("score", 0) for ev in evaluations) / len(evaluations)) if evaluations else 0
    return f"共记录 {len(answered)} 条有效文本回答，逐题平均得分 {avg}。文本侧重点看相关性、知识覆盖、证据具体性、推理链、结构完整度和追问响应。"


def _audio_analysis(metrics: dict) -> str:
    if not metrics.get("voice_answer_count") and not metrics.get("audio_sample_count"):
        return "本次没有浏览器语音或音量样本，无法进行音频侧分析。"
    return (
        f"本次包含 {metrics.get('voice_answer_count', 0)} 条 ASR 作答、{metrics.get('audio_sample_count', 0)} 个音量采样窗口。"
        f"流畅度 {metrics.get('fluency_score') if metrics.get('fluency_score') is not None else '-'}，"
        f"紧张程度 {metrics.get('nervousness_score') if metrics.get('nervousness_score') is not None else '-'}，"
        f"语速 {metrics.get('avg_words_per_minute') or '-'} 字/分钟（{metrics.get('pace_label') or '-'}），"
        f"静音占比 {metrics.get('silence_rate') if metrics.get('silence_rate') is not None else '-'}，"
        f"音量稳定 {metrics.get('volume_stability') if metrics.get('volume_stability') is not None else '-'}。"
    )


def _video_analysis(metrics: dict) -> str:
    if not metrics.get("sample_count"):
        return "本次没有开启视频分析，无法评估出镜状态和神情稳定性。"
    return (
        f"本次采集 {metrics['sample_count']} 个视频样本。"
        f"专注观感 {metrics.get('avg_attention_score') if metrics.get('avg_attention_score') is not None else '-'}，"
        f"视觉紧张程度 {metrics.get('visual_nervousness_score') if metrics.get('visual_nervousness_score') is not None else '-'}，"
        f"出镜率 {metrics.get('presence_rate') if metrics.get('presence_rate') is not None else '-'}，"
        f"居中率 {metrics.get('center_rate') if metrics.get('center_rate') is not None else '-'}，"
        f"光线 {metrics.get('lighting_quality') or '-'}，动作 {metrics.get('motion_quality') or '-'}。"
    )


def _interview_trace(history: list[dict], evaluations: list[dict]) -> dict:
    return {
        "main_questions_seen": len(history),
        "evaluated_questions": len(evaluations),
        "skipped_questions": sum(1 for h in history if _is_skipped(h)),
        "follow_up_answers": sum(len(h.get("follow_ups") or []) for h in history),
        "categories_seen": sorted({h.get("category") for h in history if h.get("category")}),
    }


def _knowledge_level(score: int | float) -> str:
    if score >= 85:
        return "覆盖充分"
    if score >= 70:
        return "覆盖较好"
    if score >= 50:
        return "部分覆盖"
    if score > 0:
        return "覆盖不足"
    return "未覆盖"


def _normalize_category(category: Any) -> str:
    text = str(category or "")
    if text in DIMENSIONS:
        return text
    if any(token in text for token in ("技术", "算法", "模型", "深度")):
        return "技术深度"
    if any(token in text for token in ("项目", "经验", "履历")):
        return "项目经验"
    if any(token in text for token in ("系统", "架构", "设计")):
        return "系统设计"
    if any(token in text for token in ("沟通", "表达", "协作")):
        return "沟通表达"
    if any(token in text for token in ("学习", "成长", "复盘")):
        return "学习能力"
    return "技术深度"


def _knowledge_summary(overall: int, rate: float, strongest: list[dict], weakest: list[dict]) -> str:
    strong_text = "、".join(item["name"] for item in strongest[:2]) or "暂无明显优势知识点"
    weak_text = "、".join(item["name"] for item in weakest[:2]) or "暂无明显缺口"
    return (
        f"本次预设知识点覆盖度 {overall}，作答覆盖率 {round(rate * 100)}%。"
        f"覆盖相对较好的方向是 {strong_text}；后续建议补强 {weak_text}。"
    )


def _recommend(score: int, completion: dict) -> str:
    if completion.get("answered", 0) == 0:
        return "不推荐"
    if score >= 85:
        return "强烈推荐"
    if score >= 70:
        return "推荐"
    if score >= 55:
        return "待定"
    return "不推荐"


def _score_level(score: int) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "需观察"
    if score > 0:
        return "薄弱"
    return "缺少证据"


def _dimension_insight(dim: str, score: int, strengths: list[str], gaps: list[str], skipped: int, uncertainty: float | None) -> str:
    suffix = f"平均不确定性约 {round(uncertainty)}。" if uncertainty is not None and uncertainty >= 45 else ""
    if skipped:
        return f"该维度有 {skipped} 次跳过，证据链不完整；建议补充具体案例。{suffix}"
    if score >= 75 and strengths:
        return f"{strengths[0]}{suffix}"
    if gaps:
        return f"{gaps[0]}{suffix}"
    if score >= 75:
        return f"该维度表现稳定，回答中能提供较清晰的事实和判断。{suffix}"
    if score >= 55:
        return f"具备基础表现，但还需要更多细节、指标和方案权衡来支撑判断。{suffix}"
    return f"{dim} 的有效证据偏少，需要补充项目背景、关键难点、方案选择和结果。{suffix}"


def _detail(name: str, score: int | float | None, insight: str) -> dict[str, Any]:
    rounded = None if score is None else round(_clip(score))
    return {"name": name, "score": rounded, "level": _score_level(rounded or 0), "insight": insight}


def _communication_adjustment(speech: dict, video: dict) -> float:
    values = []
    if speech.get("fluency_score") is not None:
        values.append((speech["fluency_score"] - 65) * 0.04)
    if speech.get("nervousness_score") is not None:
        values.append((45 - speech["nervousness_score"]) * 0.025)
    if video.get("avg_attention_score") is not None:
        values.append((video["avg_attention_score"] - 65) * 0.03)
    if video.get("visual_nervousness_score") is not None:
        values.append((45 - video["visual_nervousness_score"]) * 0.02)
    return max(-5, min(5, sum(values)))


def _fluency_score(confidences: list[float], silence_rate: float | None, stability: float | None, wpm: float | None) -> int | None:
    if not confidences and silence_rate is None and stability is None and wpm is None:
        return None
    score = 72
    if confidences:
        score += round(((_avg(confidences) or 0.7) - 0.7) * 30)
    if silence_rate is not None:
        score -= round(max(0, silence_rate - 0.28) * 70)
    if stability is not None:
        score += round((stability - 0.55) * 18)
    if wpm is not None and (wpm < 90 or wpm > 260):
        score -= 8
    return round(_clip(score))


def _audio_nervousness(silence_rate: float | None, stability: float | None, avg_volume: float | None, wpm: float | None) -> int | None:
    if silence_rate is None and stability is None and avg_volume is None and wpm is None:
        return None
    score = 20
    if silence_rate is not None:
        score += max(0, silence_rate - 0.2) * 90
    if stability is not None:
        score += max(0, 0.58 - stability) * 55
    if avg_volume is not None and avg_volume < 0.025:
        score += 14
    if wpm is not None and (wpm < 80 or wpm > 280):
        score += 12
    return round(_clip(score))


def _video_nervousness(motion: float | None, presence_rate: float | None, center_rate: float | None) -> int | None:
    if motion is None and presence_rate is None and center_rate is None:
        return None
    score = 18
    if motion is not None:
        score += min(45, motion * 1.8)
    if presence_rate is not None:
        score += max(0, 0.86 - presence_rate) * 38
    if center_rate is not None:
        score += max(0, 0.75 - center_rate) * 28
    return round(_clip(score))


def _confidence_score(confidences: list[float], fluency: int | None) -> int | None:
    if not confidences and fluency is None:
        return None
    base = ((_avg(confidences) or 0.72) * 100) if confidences else 72
    if fluency is not None:
        base = base * 0.55 + fluency * 0.45
    return round(_clip(base))


def _pace_label(wpm: float | None) -> str | None:
    if wpm is None:
        return None
    if wpm < 90:
        return "偏慢"
    if wpm > 260:
        return "偏快"
    return "适中"


def _pace_score(wpm: float | None) -> int | None:
    if wpm is None:
        return None
    if 110 <= wpm <= 220:
        return 88
    if 90 <= wpm <= 260:
        return 72
    return 48


def _inverse(value: int | float | None) -> int | None:
    return None if value is None else round(_clip(100 - value))


def _inverse_rate(value: float | None) -> int | None:
    return None if value is None else round(_clip((1 - value) * 100))


def _percent_score(value: float | None) -> int | None:
    return None if value is None else round(_clip(value * 100))


def _inverse_motion(value: float | None) -> int | None:
    if value is None:
        return None
    return round(_clip(100 - min(value * 3.2, 100)))


def _lighting_score(value: float | None) -> int | None:
    if value is None:
        return None
    if 65 <= value <= 185:
        return 90
    if 45 <= value <= 210:
        return 72
    return 45


def _lighting_quality(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 45:
        return "偏暗"
    if value > 210:
        return "过亮"
    return "合适"


def _motion_quality(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 8:
        return "稳定"
    if value < 22:
        return "轻微波动"
    return "波动偏大"


def _is_skipped(item: dict) -> bool:
    answer = str(item.get("answer", ""))
    return bool(item.get("skipped") or answer.startswith("[跳过") or answer.startswith("[璺宠繃"))


def _avg(values: list[float | int | None]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    return sum(clean) / len(clean) if clean else None


def _clip(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
