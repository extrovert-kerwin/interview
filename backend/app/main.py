from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import report, sessions, users
from app.storage.sessions import init_db

settings = get_settings()

app = FastAPI(
    title="AI Interview System",
    version="0.1.0",
    description="Single-agent AI interview service with local tools",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "model": settings.zhipuai_model,
        "llm_configured": bool(settings.zhipuai_api_key),
    }


@app.get("/healthz/algorithms")
def healthz_algorithms() -> dict:
    """Report the algorithm dispatch table actually in effect.

    Reads settings fresh (not the module-level binding) so an operator can
    verify env-var toggles after restart without running the parity test.
    Also reports whether the research-side modules backing the paper's
    IA-LinUCB and RW-MJ implementations are importable in this process---
    if False, the env-var toggle would silently fall back to the baseline.
    """
    live = get_settings()
    # Read availability from the same flags the live dispatch path uses, so
    # this endpoint reflects exactly what a request would see rather than
    # re-importing and possibly disagreeing with it. _resolve_ia_linucb() is
    # idempotent and forces the lazy resolution if it has not run yet.
    try:
        from app.services.bandit import _resolve_ia_linucb
        ia_linucb_available = bool(_resolve_ia_linucb())
    except Exception:
        ia_linucb_available = False
    try:
        from app.agents.evaluator import _RWMJ_AVAILABLE
        rwmj_available = bool(_RWMJ_AVAILABLE)
    except Exception:
        rwmj_available = False
    return {
        "selector_strategy": live.selector_strategy,
        "difficulty_strategy": live.difficulty_strategy,
        "judge_aggregator": live.judge_aggregator,
        "llm_multi_judge_count": live.llm_multi_judge_count,
        "calibration_enabled": live.calibration_enabled,
        "eta_hint_enabled": live.eta_hint_enabled,
        "modules": {
            "ia_linucb_available": ia_linucb_available,
            "rwmj_available": rwmj_available,
        },
    }


app.include_router(sessions.router, prefix="/api")
app.include_router(report.router, prefix="/api")
app.include_router(users.router, prefix="/api")


@app.on_event("startup")
def startup() -> None:
    init_db()
