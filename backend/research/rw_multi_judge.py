"""Reliability-Weighted Multi-Judge (RW-MJ).

The production aggregator (`app.agents.evaluator._aggregate_judges`) takes a
*trimmed mean* over each rubric dimension and treats every judge as equally
credible. That is a sensible robust starting point but throws away two
signals we actually have:

  * **systematic bias** — some LLM judges over-rate niceness, some
    over-rate specificity. A constant bias should be subtracted, not
    trimmed.
  * **per-item competence** — a judge's variance is heterogeneous across
    questions. CoT-prompted strong models are sharper on reasoning items;
    weaker models drift on long answers.

RW-MJ is an *online* MACE/Dawid-Skene-flavoured aggregator that maintains a
running competence ``c_j ∈ [0, 1]`` per judge and a running additive bias
``mu_j`` per judge, both updated per item using a small EM step:

    Inference (E-step, per item):
        s_hat = weighted_mean( s_{j,t} - mu_j,  weights = c_j / (sigma_j^2 + eps) )
    Update (M-step, exponential moving average):
        mu_j      ←  (1 - rho_mu) * mu_j    + rho_mu * (s_{j,t} - s_hat)
        sigma_j^2 ←  (1 - rho_var) * sigma_j^2 + rho_var * (s_{j,t} - mu_j - s_hat)^2
        c_j       ←  clip( exp(-lambda * sigma_j^2),  0.05,  1.0 )

This is essentially a streaming approximation of MACE (Hovy et al. 2013)
where the competence parameter is recovered from a one-pass exponential
moving average of squared residuals. We add a Dawid-Skene-style *posterior
agreement* signal by also reporting ``rho_t``, the consensus weight on the
winning posterior. The dispatch downstream (validator + calibration) is
unchanged.

The class is judge-count agnostic: a panel of 1 collapses to the identity
aggregator, so the experiment harness can run J ∈ {1, 3, 5} through the
same code path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class JudgeState:
    mu: float = 0.0          # additive bias estimate
    sigma2: float = 0.04     # squared error (init = 0.2^2)
    n: int = 0


@dataclass
class RWMJConfig:
    rho_mu: float = 0.04      # EMA rate for bias (small — bias is regularised toward zero)
    rho_shrink: float = 0.06  # extra L2-style pull of mu_j toward 0 each step
    rho_var: float = 0.25     # EMA rate for variance
    lambda_c: float = 12.0    # competence sharpening (sigma^2 → competence)
    min_c: float = 0.03       # floor so a bad judge never gets zeroed out entirely
    eps: float = 1e-3         # numerical safety
    cold_n: int = 3           # treat first `cold_n` items as warm-up (equal w)
    median_anchor: bool = True  # use cross-judge median as warm-up anchor


@dataclass
class RWMJAggregator:
    """Stateful aggregator. Maintains one ``JudgeState`` per judge index."""
    judges: dict[int, JudgeState] = field(default_factory=dict)
    cfg: RWMJConfig = field(default_factory=RWMJConfig)

    def _state(self, j: int) -> JudgeState:
        if j not in self.judges:
            self.judges[j] = JudgeState()
        return self.judges[j]

    def competence(self, j: int) -> float:
        st = self._state(j)
        c = math.exp(-self.cfg.lambda_c * st.sigma2)
        return max(self.cfg.min_c, min(1.0, c))

    def aggregate(self, scores: list[float]) -> tuple[float, float, dict]:
        """Aggregate raw judge scores in [0,1] for a single item.

        Returns ``(s_hat, rho_t, debug)`` where ``rho_t`` is the
        consensus-weight share of the winning judge (proxy for posterior
        sharpness; high = tight, low = spread).
        """
        cfg = self.cfg
        n_judges = len(scores)
        if n_judges == 0:
            return 0.5, 0.0, {"judges": 0}
        if n_judges == 1:
            j_idx = 0
            st = self._state(j_idx)
            s_corr = float(scores[0]) - st.mu
            return float(max(0.0, min(1.0, s_corr))), 1.0, {"judges": 1}

        # ---------- E-step (1): cold-start posterior is the median, which
        # is robust to a single noisy/biased judge. We use it both as the
        # output for the first few items AND as the M-step anchor while
        # variances haven't separated. After ``cold_n`` items we switch to
        # inverse-variance weighted mean of bias-corrected scores.
        sorted_scores = sorted(scores)
        median_score = float(sorted_scores[n_judges // 2]) if n_judges % 2 else (
            float(sorted_scores[n_judges // 2 - 1] + sorted_scores[n_judges // 2]) / 2.0
        )

        warming = any(self._state(j).n < cfg.cold_n for j in range(n_judges))
        ws = []
        cs = []
        scs = []
        for j, s in enumerate(scores):
            st = self._state(j)
            c = self.competence(j)
            w = c / (st.sigma2 + cfg.eps)
            ws.append(w)
            cs.append(c)
            scs.append(float(s) - st.mu)
        W = sum(ws) or cfg.eps
        s_hat_iv = sum(w * sc for w, sc in zip(ws, scs)) / W

        if warming and cfg.median_anchor:
            # Trust the median while reliabilities haven't separated.
            s_hat = float(max(0.0, min(1.0, median_score)))
        else:
            s_hat = float(max(0.0, min(1.0, s_hat_iv)))

        # ---------- M-step: EMA updates per judge against the chosen anchor.
        anchor = s_hat
        for j, s in enumerate(scores):
            st = self._state(j)
            resid = float(s) - st.mu - anchor
            # Variance EMA, faster during warm-up so weights separate.
            rho_v = cfg.rho_var * (1.5 if warming else 1.0)
            st.sigma2 = (1.0 - rho_v) * st.sigma2 + rho_v * resid * resid
            st.sigma2 = max(1e-4, st.sigma2)
            # Bias EMA, shrunk toward 0 to avoid drift (closes the
            # Dawid-Skene identifiability gap when biases are small).
            target_mu = float(s) - anchor
            st.mu = (1.0 - cfg.rho_mu - cfg.rho_shrink) * st.mu + cfg.rho_mu * target_mu
            st.n += 1

        w_max = max(ws)
        rho_t = float(w_max / (W + cfg.eps))
        return s_hat, rho_t, {
            "competences": [round(c, 3) for c in cs],
            "biases": [round(self._state(j).mu, 3) for j in range(n_judges)],
            "sigmas": [round(math.sqrt(self._state(j).sigma2), 3) for j in range(n_judges)],
            "weights": [round(w / W, 3) for w in ws],
            "anchor_mode": "median" if (warming and cfg.median_anchor) else "iv",
        }


# ---------------------------------------------------------------------------
# Convenience helpers used by the experiment harness so the simulator can
# plug RW-MJ in where it currently uses ``JudgePanel.score(...)``.
# ---------------------------------------------------------------------------

def aggregate_per_dim(
    per_dim_scores: dict[str, list[float]],
    rubric_weights: dict[str, float],
    agg: RWMJAggregator,
) -> tuple[float, float, dict]:
    """Run RW-MJ per rubric dimension and combine with rubric weights.

    Returns the unit-scale aggregated score in [0,1], the mean consensus
    weight across dimensions, and a debug dict mirroring the simulator's
    existing ``score(...)`` interface so plots/figures stay consistent.
    """
    per_dim_hat: dict[str, float] = {}
    rhos: list[float] = []
    debug: dict = {}
    for dim, raw in per_dim_scores.items():
        # Scores come in on 0..100; RW-MJ expects 0..1.
        unit = [max(0.0, min(1.0, float(x) / 100.0)) for x in raw]
        s_hat, rho, dbg = agg.aggregate(unit)
        per_dim_hat[dim] = s_hat
        rhos.append(rho)
        debug[dim] = dbg
    s_overall = sum(per_dim_hat[d] * rubric_weights[d] for d in per_dim_hat)
    return float(s_overall), float(sum(rhos) / max(1, len(rhos))), debug
