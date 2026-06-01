"""Read persisted final reports."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.storage import sessions as store

router = APIRouter()


@router.get("/report/{session_id}")
def get_report(session_id: str):
    report = store.get_report(session_id)
    if report:
        return report

    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session 不存在")

    report = state.get("final_report")
    if not report:
        raise HTTPException(status_code=409, detail="报告尚未生成，请先调用 /finalize")

    store.save_report(session_id, state.get("user_id"), report)
    return report
