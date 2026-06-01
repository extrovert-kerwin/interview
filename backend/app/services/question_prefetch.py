"""Background prefetch for the next main interview question."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.agents.question_planner import generate_question
from app.storage import sessions as store

_EXECUTOR = ThreadPoolExecutor(max_workers=1)


def schedule_next_question(session_id: str) -> None:
    state = store.get(session_id)
    if not state:
        return

    plan = state.get("question_plan") or []
    target_total = int(state.get("target_total_questions") or 8)
    next_index = len(plan) + 1
    if next_index > target_total:
        return

    expected_id = f"q{next_index}"
    if state.get("prefetching_question_id") == expected_id:
        return
    prefetched = state.get("prefetched_question")
    if isinstance(prefetched, dict) and prefetched.get("id") == expected_id:
        return

    store.update(session_id, {"prefetching_question_id": expected_id}, event_type="question_prefetch_started")
    _EXECUTOR.submit(_prefetch, session_id, next_index, expected_id)


def _prefetch(session_id: str, index: int, expected_id: str) -> None:
    state = store.get(session_id)
    if not state:
        return
    try:
        question = generate_question(state, index)
        latest = store.get(session_id)
        if not latest:
            return
        plan = latest.get("question_plan") or []
        if len(plan) + 1 == index:
            store.update(session_id, {
                "prefetched_question": question,
                "prefetching_question_id": "",
            }, event_type="question_prefetched")
    except Exception:
        store.update(session_id, {"prefetching_question_id": ""}, event_type="question_prefetch_failed")
