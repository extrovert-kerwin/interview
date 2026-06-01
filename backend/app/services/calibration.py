"""Score calibration for the hybrid judge.

We expose two calibration modes:
  * ``linear``  — affine map ``y = slope * x + intercept`` configured from env.
  * ``platt``   — logistic recalibration trained on (raw, human) pairs.

When no calibration data is present, the linear mode degenerates to the
identity, which keeps the original raw-score behaviour for existing sessions.
The fitted Platt coefficients are stored in a small JSON file so the
experiment harness can swap in new calibrations without code changes.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Iterable

from app.config import get_settings


_CALIB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "calibration.json")


@dataclass
class Calibrator:
    mode: str = "linear"
    slope: float = 1.0
    intercept: float = 0.0
    a: float = 1.0  # platt coefficient on raw score (logit slope)
    b: float = 0.0  # platt bias
    confidence: float = 0.0
    consensus_floor: float = 0.55
    fitted_pairs: int = 0
    meta: dict = field(default_factory=dict)

    def apply(self, raw_unit: float, consensus: float | None = None) -> float:
        x = max(0.0, min(1.0, float(raw_unit)))
        if self.mode == "platt":
            z = self.a * (x - 0.5) + self.b
            y = 1.0 / (1.0 + math.exp(-z))
        else:
            y = self.slope * x + self.intercept
        y = max(0.0, min(1.0, y))
        if consensus is not None:
            c = max(0.0, min(1.0, float(consensus)))
            blend = self.consensus_floor + (1 - self.consensus_floor) * c
            y = blend * y + (1 - blend) * x
        return y


def _resolve_path() -> str:
    return os.path.abspath(_CALIB_PATH)


def load_calibrator() -> Calibrator:
    """Load from JSON if present, otherwise fall back to env-driven linear."""
    s = get_settings()
    path = _resolve_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return Calibrator(
                mode=str(data.get("mode", "linear")),
                slope=float(data.get("slope", 1.0)),
                intercept=float(data.get("intercept", 0.0)),
                a=float(data.get("a", 1.0)),
                b=float(data.get("b", 0.0)),
                confidence=float(data.get("confidence", 0.0)),
                consensus_floor=s.consensus_floor,
                fitted_pairs=int(data.get("fitted_pairs", 0)),
                meta=dict(data.get("meta", {})),
            )
        except Exception:
            pass
    return Calibrator(
        mode="linear",
        slope=s.calibration_slope,
        intercept=s.calibration_intercept,
        consensus_floor=s.consensus_floor,
    )


def save_calibrator(c: Calibrator) -> str:
    path = _resolve_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "mode": c.mode,
        "slope": c.slope,
        "intercept": c.intercept,
        "a": c.a,
        "b": c.b,
        "confidence": c.confidence,
        "fitted_pairs": c.fitted_pairs,
        "meta": c.meta,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def fit_platt(raw_scores: Iterable[float], human_scores: Iterable[float]) -> Calibrator:
    """Fit a 2-parameter logistic recalibration via gradient descent."""
    xs = [max(0.0, min(1.0, float(x))) for x in raw_scores]
    ys = [max(0.0, min(1.0, float(y))) for y in human_scores]
    n = min(len(xs), len(ys))
    if n < 5:
        return load_calibrator()
    xs, ys = xs[:n], ys[:n]
    a, b = 1.0, 0.0
    lr = 0.3
    for _ in range(500):
        ga, gb = 0.0, 0.0
        for x, y in zip(xs, ys):
            z = a * (x - 0.5) + b
            p = 1.0 / (1.0 + math.exp(-z))
            err = p - y
            ga += err * (x - 0.5)
            gb += err
        a -= lr * ga / n
        b -= lr * gb / n
    # Closed-form linear baseline for diagnostics.
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    var = sum((x - mx) ** 2 for x in xs) / n or 1e-6
    slope = cov / var
    intercept = my - slope * mx
    # Reliability as Pearson r^2.
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n) or 1e-6
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n) or 1e-6
    r = cov / (sx * sy)
    return Calibrator(
        mode="platt",
        slope=slope,
        intercept=intercept,
        a=a,
        b=b,
        confidence=max(0.0, min(1.0, r ** 2)),
        consensus_floor=get_settings().consensus_floor,
        fitted_pairs=n,
        meta={"r": r, "slope_linear": slope, "intercept_linear": intercept},
    )
