import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Runtime configuration.

    All fields are read inside ``__init__`` from the live process environment
    so that changes to ``os.environ`` between calls to ``get_settings()`` (with
    ``cache_clear()``) actually take effect. This is what the paper's
    Reproducibility appendix promises for ``SELECTOR_STRATEGY`` and
    ``JUDGE_AGGREGATOR``.
    """

    def __init__(self) -> None:
        self.zhipuai_api_key: str = os.getenv("ZHIPUAI_API_KEY", "")
        self.zhipuai_model: str = os.getenv("ZHIPUAI_MODEL", "glm-4-plus")
        self.cors_origins: list[str] = [
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if o.strip()
        ]

        # ------------------------------------------------------------------
        # Ablation knobs (used by experiment harness; safe defaults for prod)
        # ------------------------------------------------------------------
        self.llm_multi_judge_count: int = _env_int("LLM_MULTI_JUDGE_COUNT", 1)
        self.llm_use_cot: bool = _env_bool("LLM_USE_COT", True)
        self.llm_judge_temperatures: list[float] = [
            float(x) for x in os.getenv("LLM_JUDGE_TEMPS", "0.1,0.4,0.7").split(",") if x.strip()
        ]
        self.judge_outlier_trim: float = _env_float("JUDGE_OUTLIER_TRIM", 0.0)
        self.judge_aggregator: str = os.getenv("JUDGE_AGGREGATOR", "trimmed")  # trimmed | rwmj
        self.calibration_enabled: bool = _env_bool("CALIBRATION_ENABLED", True)
        self.calibration_slope: float = _env_float("CALIBRATION_SLOPE", 1.0)
        self.calibration_intercept: float = _env_float("CALIBRATION_INTERCEPT", 0.0)
        self.consensus_floor: float = _env_float("CONSENSUS_FLOOR", 0.55)

        # Selection
        self.selector_strategy: str = os.getenv("SELECTOR_STRATEGY", "linucb")  # round_robin | linucb | thompson | ia_linucb
        self.bandit_alpha: float = _env_float("BANDIT_ALPHA", 1.0)
        self.bandit_lambda_coverage: float = _env_float("BANDIT_LAMBDA_COV", 0.4)
        self.bandit_lambda_gap: float = _env_float("BANDIT_LAMBDA_GAP", 0.6)
        self.bandit_lambda_resume: float = _env_float("BANDIT_LAMBDA_RESUME", 0.3)

        # Control
        self.difficulty_strategy: str = os.getenv("DIFFICULTY_STRATEGY", "pi_control")  # heuristic | pi_control
        self.difficulty_target: float = _env_float("DIFFICULTY_TARGET", 0.70)
        self.difficulty_kp: float = _env_float("DIFFICULTY_KP", 1.4)
        self.difficulty_ki: float = _env_float("DIFFICULTY_KI", 0.3)

        # Memory feedback loop
        self.eta_hint_enabled: bool = _env_bool("ETA_HINT_ENABLED", True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
