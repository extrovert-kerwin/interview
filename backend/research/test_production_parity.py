"""Production-parity smoke test for the env-var toggles that route to the
two algorithms introduced in this paper (IA-LinUCB and RW-MJ).

The Reproducibility appendix claims that setting ``SELECTOR_STRATEGY=ia_linucb``
and ``JUDGE_AGGREGATOR=rwmj`` flips the live FastAPI code path to the same
modules exercised by the research harness. This script demonstrates that.

Run from the ``backend/`` directory:

    .venv_mac/bin/python -m research.test_production_parity

Exits non-zero on any failed assertion. Designed to be safe to run from
CI: it makes no network calls, no file writes, and no LLM calls. The
synthetic state is hand-built to be minimally sufficient for the dispatchers.
"""
from __future__ import annotations

import os
import sys
from typing import Any


def _clear_settings_cache() -> None:
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]


def check_selector_dispatch() -> dict[str, Any]:
    """Set SELECTOR_STRATEGY=ia_linucb, invoke the production selector, and
    verify that the debug payload identifies IA-LinUCB as the active branch."""
    os.environ["SELECTOR_STRATEGY"] = "ia_linucb"
    _clear_settings_cache()

    from app.services.bandit import select_category
    from app.agents.memory import CATEGORIES

    # Build a minimal InterviewState (TypedDict). The fields below match what
    # the bandit reads via app.agents.memory helpers.
    state: dict[str, Any] = {
        "session_id": "parity_check",
        "ability_estimate": 0.62,
        "score_window": [0.7, 0.65, 0.6, 0.75, 0.7],
        "per_topic_stats": {c: {"n": 1, "mean": 0.7, "last_seen": i,
                                "gaps": ["concept_x"]}
                            for i, c in enumerate(CATEGORIES[:5])},
        "coverage_count": {c: 1 for c in CATEGORIES[:5]},
        "gap_set": ["concept_x", "concept_y"],
        "next_direction_hints": ["probe deeper on system design"],
        "difficulty_trajectory": [0.6, 0.65, 0.7, 0.72, 0.7],
        "chapter_trajectory": list(CATEGORIES[:5]),
    }

    chosen, dbg = select_category(state, next_index=6, rounds_total=12)
    assert isinstance(chosen, str) and chosen, "selector returned empty category"
    strategy_field = str(dbg.get("strategy", "")).lower()
    assert "ia_linucb" in strategy_field or "ia-linucb" in strategy_field, (
        f"expected ia_linucb dispatch, got strategy={strategy_field!r} "
        f"(full debug payload: {dbg})"
    )
    return {"chosen": chosen, "strategy": strategy_field}


def check_aggregator_dispatch() -> dict[str, Any]:
    """Set JUDGE_AGGREGATOR=rwmj, run the production aggregator on synthetic
    judge outputs, and verify that the panel_info names the RW-MJ branch."""
    os.environ["JUDGE_AGGREGATOR"] = "rwmj"
    _clear_settings_cache()

    # Diagnostic: confirm settings actually picked up the env var.
    from app.config import get_settings
    _s = get_settings()
    from app.agents import evaluator as _ev
    assert str(_s.judge_aggregator).lower() == "rwmj", (
        f"settings.judge_aggregator did not pick up env var: {_s.judge_aggregator!r}"
    )
    assert _ev._RWMJ_AVAILABLE, "RW-MJ module did not import; check research.rw_multi_judge"

    from app.agents.evaluator import _aggregate_judges, REQUIRED_DIMENSIONS

    def _judge_output(scores: dict[str, float]) -> list[dict]:
        return [{
            "rubric_scores": {d: {"score": float(scores.get(d, 70.0))} for d in REQUIRED_DIMENSIONS},
            "reasoning": "synthetic",
            "strengths": "synthetic",
            "gaps": "synthetic",
        }]

    judge_outputs = [
        _judge_output({d: 80.0 for d in REQUIRED_DIMENSIONS}),
        _judge_output({d: 60.0 for d in REQUIRED_DIMENSIONS}),
        _judge_output({d: 95.0 for d in REQUIRED_DIMENSIONS}),
    ]

    aggregated, panel_info = _aggregate_judges(
        judge_outputs, n_questions=1, session_id="parity_check"
    )
    assert len(aggregated) == 1, "expected one aggregated entry"
    assert len(panel_info) == 1, "expected one panel-info entry"
    agg_name = str(panel_info[0].get("aggregator", "")).lower()
    assert agg_name == "rwmj", (
        f"expected aggregator=rwmj, got {agg_name!r} "
        f"(full panel_info: {panel_info[0]})"
    )
    return {
        "aggregator": agg_name,
        "rwmj_rho": panel_info[0].get("rwmj_rho"),
        "first_dim_score": aggregated[0]["rubric_scores"][REQUIRED_DIMENSIONS[0]]["score"],
    }


def check_ia_linucb_unavailable_is_explicit() -> dict[str, Any]:
    """Simulate the slim-deploy case where research.ia_linucb is missing and
    verify the production selector reports the downgrade in its debug payload.
    Reviewer-facing claim: silent fall-back to LinUCB would mislead operators
    who set ``SELECTOR_STRATEGY=ia_linucb`` and read trace logs."""
    os.environ["SELECTOR_STRATEGY"] = "ia_linucb"
    _clear_settings_cache()

    from app.services import bandit as _bandit
    from app.agents.memory import CATEGORIES

    # Force the lazy resolution to "unavailable" by pinning the cache flag.
    # The dispatcher consults _resolve_ia_linucb() which short-circuits on a
    # non-None cached flag, so setting it False here cleanly simulates the
    # slim-deploy case where research.ia_linucb is not on the import path.
    saved_flag = _bandit._IA_LINUCB_AVAILABLE
    saved_select = _bandit._select_ia_linucb
    saved_cfg = _bandit._IALinUCBConfig
    try:
        _bandit._IA_LINUCB_AVAILABLE = False
        _bandit._select_ia_linucb = None
        _bandit._IALinUCBConfig = None

        state: dict[str, Any] = {
            "session_id": "parity_check_fallback",
            "ability_estimate": 0.55,
            "score_window": [0.6, 0.65, 0.7],
            "per_topic_stats": {c: {"n": 1, "mean": 0.6, "last_seen": i, "gaps": []}
                                for i, c in enumerate(CATEGORIES[:5])},
            "coverage_count": {c: 1 for c in CATEGORIES[:5]},
            "gap_set": [],
            "next_direction_hints": [],
            "difficulty_trajectory": [0.6, 0.6, 0.6],
            "chapter_trajectory": list(CATEGORIES[:3]),
        }
        chosen, dbg = _bandit.select_category(state, next_index=4, rounds_total=12)
        assert isinstance(chosen, str) and chosen
        assert dbg.get("strategy") == "linucb", (
            f"expected strategy=linucb after fallback, got {dbg.get('strategy')!r}"
        )
        assert dbg.get("requested_strategy") == "ia_linucb", (
            f"expected requested_strategy=ia_linucb, got {dbg.get('requested_strategy')!r} "
            f"(full debug payload: {dbg})"
        )
        assert "fell_back" in str(dbg.get("dispatch_note", "")), (
            f"expected dispatch_note to mention fallback, got "
            f"{dbg.get('dispatch_note')!r}"
        )
        return {"requested": dbg.get("requested_strategy"),
                "actual": dbg.get("strategy"),
                "note": dbg.get("dispatch_note")}
    finally:
        _bandit._IA_LINUCB_AVAILABLE = saved_flag
        _bandit._select_ia_linucb = saved_select
        _bandit._IALinUCBConfig = saved_cfg


def check_healthz_algorithms() -> dict[str, Any]:
    """Verify that GET /healthz/algorithms reports the live env-var-toggled
    configuration. Reads via FastAPI TestClient so no real HTTP server is
    started; this exercises the same dispatch code an operator hits."""
    os.environ["SELECTOR_STRATEGY"] = "ia_linucb"
    os.environ["JUDGE_AGGREGATOR"] = "rwmj"
    _clear_settings_cache()

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/healthz/algorithms")
    assert resp.status_code == 200, f"unexpected status {resp.status_code}"
    body = resp.json()
    assert body["selector_strategy"] == "ia_linucb", (
        f"healthz reports selector_strategy={body['selector_strategy']!r}, "
        f"expected 'ia_linucb' (env vars not picked up?)"
    )
    assert body["judge_aggregator"] == "rwmj", (
        f"healthz reports judge_aggregator={body['judge_aggregator']!r}, "
        f"expected 'rwmj'"
    )
    assert body["modules"]["ia_linucb_available"], "ia_linucb module not importable in app context"
    assert body["modules"]["rwmj_available"], "rwmj module not importable in app context"
    return body


def main() -> int:
    print("[parity] checking SELECTOR_STRATEGY=ia_linucb routes through production selector ...")
    sel_info = check_selector_dispatch()
    print(f"  OK — chose category={sel_info['chosen']!r}, strategy={sel_info['strategy']!r}")

    print("[parity] checking JUDGE_AGGREGATOR=rwmj routes through production aggregator ...")
    agg_info = check_aggregator_dispatch()
    print(f"  OK — aggregator={agg_info['aggregator']!r}, "
          f"rho={agg_info['rwmj_rho']}, first_dim_score={agg_info['first_dim_score']:.2f}")

    print("[parity] checking GET /healthz/algorithms reflects live env-var dispatch ...")
    hz = check_healthz_algorithms()
    print(f"  OK — selector={hz['selector_strategy']!r}, "
          f"aggregator={hz['judge_aggregator']!r}, modules={hz['modules']}")

    print("[parity] checking ia_linucb-requested-but-unavailable downgrade is loud ...")
    fb = check_ia_linucb_unavailable_is_explicit()
    print(f"  OK — requested={fb['requested']!r}, actual={fb['actual']!r}, "
          f"note={fb['note']!r}")

    print("[parity] all checks passed — env-var toggles dispatch to the paper's research modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
