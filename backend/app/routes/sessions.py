"""Session REST routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.graph import (
    agent_pipeline,
    continue_graph,
    finalize_graph,
    next_question_graph,
    setup_graph,
)
from app.services.question_prefetch import schedule_next_question
from app.services.resume_loader import load_resume
from app.routes.users import require_user
from app.storage import sessions as store

router = APIRouter()


class AnswerIn(BaseModel):
    answer: str
    speech_metrics: dict | None = None


class AnalyticsIn(BaseModel):
    kind: str
    payload: dict


def _public_question(q: dict) -> dict:
    return {
        "id": q.get("id"),
        "category": q.get("category"),
        "intent": q.get("intent", ""),
        "knowledge_points": q.get("knowledge_points", []),
        "question": q.get("question", ""),
    }


def _snapshot(session_id: str, state: dict) -> dict:
    return {
        "session_id": session_id,
        "profile": state.get("resume_profile"),
        "question_plan": [_public_question(q) for q in state.get("question_plan", [])],
        "pending_question": state.get("pending_question", ""),
        "pending_kind": state.get("pending_kind", "main"),
        "current_q_index": state.get("current_q_index", 0),
        "total_questions": state.get("target_total_questions", 8),
        "stage": state.get("stage"),
        "qa_history": state.get("qa_history", []),
        "agents": agent_pipeline(),
        "last_active_agent": state.get("last_active_agent"),
    }


def _step_response(state: dict) -> dict:
    return {
        "pending_question": state.get("pending_question", ""),
        "pending_kind": state.get("pending_kind", "main"),
        "question_plan": [_public_question(q) for q in state.get("question_plan", [])],
        "current_q_index": state.get("current_q_index", 0),
        "total_questions": state.get("target_total_questions", 8),
        "stage": state.get("stage"),
        "last_active_agent": state.get("last_active_agent"),
        "done": state.get("stage") == "evaluating",
    }


@router.post("/sessions")
async def create_session(
    resume: UploadFile = File(...),
    position: str = Form("通用工程师"),
    difficulty: str = Form("mid"),
    user_id: str | None = Form(None),
    authorization: str | None = Header(None),
):
    blob = await resume.read()
    try:
        text = load_resume(resume.filename or "resume", blob)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not text.strip():
        raise HTTPException(status_code=400, detail="简历内容为空，请检查文件")

    session_id = uuid.uuid4().hex[:12]
    if authorization:
        user = require_user(authorization)
    else:
        user = store.ensure_user(user_id)
    init_state = {
        "session_id": session_id,
        "user_id": user["id"],
        "resume_text": text,
        "position": position,
        "difficulty": difficulty,
        "stage": "parsing",
        "qa_history": [],
        "evaluations": [],
        "target_total_questions": 8,
    }

    try:
        result = setup_graph.invoke(init_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"setup 失败: {e}")

    store.save(session_id, result, event_type="session_created")
    schedule_next_question(session_id)
    return _snapshot(session_id, result)


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session 不存在")
    return _snapshot(session_id, state)


@router.post("/sessions/{session_id}/answer")
def submit_answer(session_id: str, payload: AnswerIn):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session 不存在")

    plan = state.get("question_plan") or []
    idx = state.get("current_q_index", 0)
    if idx >= len(plan):
        raise HTTPException(status_code=400, detail="当前没有可回答的题目")

    q = plan[idx]
    history = list(state.get("qa_history") or [])
    pending_kind = state.get("pending_kind", "main")

    if pending_kind == "follow_up" and history and history[-1].get("q_id") == q["id"]:
        history[-1].setdefault("follow_ups", []).append({
            "question": state.get("pending_question", ""),
            "answer": payload.answer,
            "speech_metrics": payload.speech_metrics,
        })
    else:
        history.append({
            "q_id": q["id"],
            "category": q["category"],
            "intent": q.get("intent", ""),
            "knowledge_points": q.get("knowledge_points", []),
            "question": q["question"],
            "answer": payload.answer,
            "speech_metrics": payload.speech_metrics,
            "follow_ups": [],
        })

    state["qa_history"] = history
    state["pending_question"] = ""
    store.save(session_id, state, event_type="answer_recorded")

    try:
        result = continue_graph.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"continue 失败: {e}")

    merged = {**state, **result}
    store.save(session_id, merged, event_type="answer_processed")
    if merged.get("stage") == "interviewing" and merged.get("pending_kind") == "main":
        schedule_next_question(session_id)
    return _step_response(merged)


@router.post("/sessions/{session_id}/skip")
def skip_question(session_id: str):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session 不存在")

    plan = state.get("question_plan") or []
    idx = state.get("current_q_index", 0)
    target_total = state.get("target_total_questions", 8)
    if idx >= target_total:
        raise HTTPException(status_code=400, detail="所有题目已完成")

    history = list(state.get("qa_history") or [])
    q = plan[idx] if idx < len(plan) else None
    if q:
        if state.get("pending_kind") == "follow_up" and history and history[-1].get("q_id") == q["id"]:
            history[-1].setdefault("follow_ups", []).append({
                "question": state.get("pending_question", ""),
                "answer": "[跳过追问]",
                "skipped": True,
            })
        elif not any(item.get("q_id") == q["id"] for item in history):
            history.append({
                "q_id": q["id"],
                "category": q["category"],
                "intent": q.get("intent", ""),
                "knowledge_points": q.get("knowledge_points", []),
                "question": q["question"],
                "answer": "[跳过本题]",
                "follow_ups": [],
                "skipped": True,
            })

    next_idx = idx + 1
    state.update({
        "qa_history": history,
        "current_q_index": next_idx,
        "follow_up_count": 0,
        "pending_question": "",
        "pending_kind": "main",
        "stage": "evaluating" if next_idx >= target_total else "planning",
    })

    if state["stage"] == "evaluating":
        store.save(session_id, state, event_type="question_skipped_done")
        return _step_response(state)

    try:
        result = next_question_graph.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"skip 失败: {e}")

    merged = {**state, **result}
    store.save(session_id, merged, event_type="question_skipped")
    if merged.get("stage") == "interviewing" and merged.get("pending_kind") == "main":
        schedule_next_question(session_id)
    return _step_response(merged)


@router.post("/sessions/{session_id}/finalize")
def finalize(session_id: str):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session 不存在")

    try:
        result = finalize_graph.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"finalize 失败: {e}")

    merged = {**state, **result}
    report = merged.get("final_report")
    store.save(session_id, merged, event_type="report_generated")
    if report:
        store.save_report(session_id, merged.get("user_id"), report)
    return {
        "stage": merged.get("stage"),
        "last_active_agent": merged.get("last_active_agent"),
        "report_ready": bool(report),
    }


@router.post("/sessions/{session_id}/analytics")
def record_analytics(session_id: str, payload: AnalyticsIn):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session 不存在")
    key = f"{payload.kind}_metrics"
    existing = list(state.get(key) or [])
    existing.append(payload.payload)
    state[key] = existing[-200:]
    store.save(session_id, state, event_type=f"{payload.kind}_analytics")
    return {"ok": True}
