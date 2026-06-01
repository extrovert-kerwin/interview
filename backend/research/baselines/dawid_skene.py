"""Dawid-Skene (1979) EM aggregator for multi-judge scoring.

The original Dawid-Skene model is defined over discrete labels and
estimates a confusion matrix per annotator. For our continuous rubric
scores in [0,1] we use the natural Gaussian relaxation:

    s_{j,t} = mu_j + true_t + eps_{j,t},      eps_{j,t} ~ N(0, sigma_j^2)

Closed-form ML estimates after T items:

    mu_j     = mean_t( s_{j,t} - true_hat_t )
    sigma_j^2 = mean_t( (s_{j,t} - mu_j - true_hat_t)^2 )
    true_hat_t = sum_j ( (s_{j,t} - mu_j) / sigma_j^2 ) / sum_j ( 1/sigma_j^2 )

We iterate E and M steps until either convergence or 25 iterations, then
return the posterior mean per item. Used as an *offline* baseline against
RW-MJ: it gets to see the full batch of judge scores at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class DSResult:
    posterior: np.ndarray      # shape (T,)
    biases: np.ndarray         # shape (J,)
    sigmas: np.ndarray         # shape (J,)


def dawid_skene_gaussian(judge_matrix: Iterable[Iterable[float]], *, max_iter: int = 25, tol: float = 1e-4) -> DSResult:
    """``judge_matrix`` is shape (T, J): each row is one item's judge scores."""
    X = np.asarray(judge_matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] == 0:
        return DSResult(posterior=X.mean(axis=1) if X.size else np.array([]),
                        biases=np.zeros(0), sigmas=np.ones(0))
    T, J = X.shape
    biases = np.zeros(J)
    sigmas = np.full(J, 0.2)
    posterior = X.mean(axis=1)

    for _ in range(max_iter):
        w = 1.0 / (sigmas ** 2 + 1e-6)
        new_post = ((X - biases) @ w) / (w.sum() + 1e-9)
        new_biases = (X - new_post[:, None]).mean(axis=0)
        resid = X - new_biases - new_post[:, None]
        new_sigmas = np.sqrt(np.mean(resid ** 2, axis=0) + 1e-6)
        if (np.max(np.abs(new_post - posterior)) < tol and
                np.max(np.abs(new_biases - biases)) < tol):
            posterior, biases, sigmas = new_post, new_biases, new_sigmas
            break
        posterior, biases, sigmas = new_post, new_biases, new_sigmas

    return DSResult(posterior=np.clip(posterior, 0.0, 1.0), biases=biases, sigmas=sigmas)
