"""MACE-style competence-weighted aggregator (Hovy et al., 2013).

Original MACE is for discrete labels with a "spam" prior. The
continuous-score variant we report estimates a per-judge competence
``c_j ∈ [0, 1]``: with probability ``c_j`` the judge reports the true
value plus Gaussian noise, with probability ``1 - c_j`` they sample an
uninformative value. The MAP weight for posterior aggregation is

    w_j  ∝   c_j / (sigma_j^2 + eps)

We estimate ``(c_j, sigma_j^2)`` with one full pass of coordinate ascent on
a batch of T items (offline baseline). For the online RW-MJ variant see
``research.rw_multi_judge``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class MACEResult:
    posterior: np.ndarray   # (T,)
    competence: np.ndarray  # (J,)
    sigmas: np.ndarray      # (J,)


def mace_continuous(
    judge_matrix: Iterable[Iterable[float]],
    *,
    n_iter: int = 30,
    lambda_c: float = 8.0,
) -> MACEResult:
    X = np.asarray(judge_matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] == 0 or X.shape[0] == 0:
        return MACEResult(posterior=np.array([]), competence=np.zeros(0), sigmas=np.ones(0))

    T, J = X.shape
    competence = np.full(J, 0.7)
    sigmas = np.full(J, 0.2)

    for _ in range(n_iter):
        w = competence / (sigmas ** 2 + 1e-6)
        posterior = (X @ w) / (w.sum() + 1e-9)
        resid = X - posterior[:, None]
        sigmas = np.sqrt(np.mean(resid ** 2, axis=0) + 1e-6)
        competence = np.exp(-lambda_c * sigmas ** 2)
        competence = np.clip(competence, 0.05, 1.0)

    return MACEResult(posterior=np.clip(posterior, 0.0, 1.0),
                      competence=competence, sigmas=sigmas)
