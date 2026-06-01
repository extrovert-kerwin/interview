"""Run the controlled experiments reported in the paper.

The harness sweeps four orthogonal axes (paper §5):

  * judge aggregator  : single | mean | trimmed | linear-cal | Platt
                        | Dawid-Skene (offline) | MACE (offline) | RW-MJ (online, ours)
  * selection policy  : round_robin | thompson | LinUCB | IRT-CAT | IA-LinUCB (ours)
                        (+ an oracle reference for the regret denominator)
  * difficulty rule   : heuristic vs PI controller
  * termination rule  : fixed budget vs PSER credible-interval stop

For each configuration we run N synthetic candidates across A archetypes
and aggregate the reliability / regret / coverage metrics defined in §5.
Results land in ``research/results/*.json``; figures land in
``research/figures/*.pdf`` and ``*.png``.

Run directly: ``python -m research.experiments``.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.services.calibration import Calibrator, fit_platt
from research.baselines.dawid_skene import dawid_skene_gaussian
from research.baselines.irt_cat import selector as irt_cat_selector
from research.baselines.llm_judges import (
    geval as judge_geval,
    majority_vote as judge_majority,
    poll_jury as judge_poll,
    prometheus2_style as judge_prometheus,
    self_consistency_cot as judge_selfcons,
    single_judge_cot as judge_single,
)
from research.baselines.mace import mace_continuous
from research.baselines.pser_stop import PSERConfig, fisher, should_stop
from research.datasets import DATASETS, build_dataset
from research.ia_linucb import IALinUCBConfig, selector as ia_linucb_selector
from research.rw_multi_judge import RWMJAggregator, RWMJConfig, aggregate_per_dim
from research.simulator import (
    CATEGORIES,
    EpisodeConfig,
    EpisodeTrace,
    RUBRIC_KEYS,
    RUBRIC_WEIGHTS,
    fit_calibrator_from_pool,
    make_judge_panel,
    oracle_selector,
    run_episode,
    sample_candidate,
    simulate_answer_quality,
)

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent / "figures"
RESULTS_DIR.mkdir(exist_ok=True)
FIGURES_DIR.mkdir(exist_ok=True)

ARCHETYPES = ("balanced", "backend", "junior", "senior")
SEED = 20260530


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def cohens_kappa_from_pairs(preds: list[float], targets: list[float], *, n_bins: int = 4) -> float:
    """Linearly-weighted κ on quantised scores."""
    if not preds:
        return 0.0
    p_bins = np.clip((np.array(preds) * n_bins).astype(int), 0, n_bins - 1)
    t_bins = np.clip((np.array(targets) * n_bins).astype(int), 0, n_bins - 1)
    cm = np.zeros((n_bins, n_bins))
    for p, t in zip(p_bins, t_bins):
        cm[int(p), int(t)] += 1
    n = cm.sum()
    if n == 0:
        return 0.0
    weights = np.array([[((i - j) ** 2) / ((n_bins - 1) ** 2) for j in range(n_bins)] for i in range(n_bins)])
    row = cm.sum(1) / n
    col = cm.sum(0) / n
    expected = np.outer(row, col) * n
    num = (weights * cm).sum()
    den = (weights * expected).sum()
    if den == 0:
        return 1.0
    return float(1.0 - num / den)


def bootstrap_ci(values: list[float] | np.ndarray, *, n_boot: int = 2000, alpha: float = 0.05,
                 seed: int = SEED) -> tuple[float, float]:
    """Percentile bootstrap CI on the sample mean. Returns (lo, hi)."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    n = arr.size
    means = rng.choice(arr, size=(n_boot, n), replace=True).mean(axis=1)
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1.0 - alpha / 2))
    return (lo, hi)


def regret_per_round(trace_actor: EpisodeTrace, trace_oracle: EpisodeTrace) -> list[float]:
    cum_actor, cum_oracle = 0.0, 0.0
    out = []
    for a, o in zip(trace_actor.rewards, trace_oracle.rewards):
        cum_actor += a
        cum_oracle += o
        out.append(cum_oracle - cum_actor)
    return out


# ---------------------------------------------------------------------------
# Experiment 1 — judge reliability ablation (J × CoT × calibration ×
# aggregator). Includes our RW-MJ and the Dawid-Skene / MACE baselines.
# ---------------------------------------------------------------------------

@dataclass
class JudgeResult:
    name: str
    aggregator: str          # single | mean | trimmed | linear | platt | ds | mace | rwmj
    judge_count: int
    use_cot: bool
    outlier_trim: float
    calibration: str
    mae: float
    rmse: float
    bias: float
    kappa: float
    agreement: float
    judge_seconds_per_q: float
    panel_type: str = "homogeneous"
    mae_ci95: tuple[float, float] = (0.0, 0.0)
    bias_ci95: tuple[float, float] = (0.0, 0.0)


def _calibrator_for(name: str, rng: np.random.Generator, judge_count: int, use_cot: bool) -> Calibrator:
    if name == "none":
        return Calibrator(mode="linear", slope=1.0, intercept=0.0)
    if name == "linear":
        c = fit_calibrator_from_pool(rng, judge_count=max(1, judge_count), use_cot=use_cot)
        c.mode = "linear"
        return c
    return fit_calibrator_from_pool(rng, judge_count=max(1, judge_count), use_cot=use_cot)


def _aggregate_single(per_dim: dict[str, list[float]], idx: int = 0) -> float:
    return sum((per_dim[d][idx] / 100.0) * RUBRIC_WEIGHTS[d] for d in RUBRIC_KEYS)


def _aggregate_mean(per_dim: dict[str, list[float]]) -> float:
    return sum((sum(per_dim[d]) / max(1, len(per_dim[d])) / 100.0) * RUBRIC_WEIGHTS[d] for d in RUBRIC_KEYS)


def _aggregate_trimmed(per_dim: dict[str, list[float]], trim: float = 0.2) -> float:
    out = 0.0
    for d in RUBRIC_KEYS:
        scores = sorted(per_dim[d])
        if trim > 0 and len(scores) >= 4:
            cut = int(len(scores) * trim)
            scores = scores[cut: len(scores) - cut] or scores
        out += (sum(scores) / max(1, len(scores)) / 100.0) * RUBRIC_WEIGHTS[d]
    return out


def run_judge_reliability(
    *,
    n_candidates: int = 80,
    rounds: int = 10,
    configs: list[dict] | None = None,
    panel_type: str = "homogeneous",
    write_results: bool = True,
    panel_kwargs: dict | None = None,
) -> list[JudgeResult]:
    """Cross-aggregator comparison covering classical aggregators (single,
    mean, trimmed-mean), LLM-recipe baselines (G-Eval, PoLL/jury, majority
    vote, self-consistency CoT, Prometheus-2-style reference grounding),
    EM-style baselines (Dawid-Skene, MACE), and our RW-MJ.

    ``panel_type`` selects the well-controlled (``homogeneous``) or
    stress-test (``heterogeneous``) regime.
    """
    if configs is None:
        configs = [
            # Single-judge / no-aggregation baselines
            {"agg": "single",        "j": 1, "cot": False, "trim": 0.0, "cal": "none"},
            {"agg": "single",        "j": 1, "cot": True,  "trim": 0.0, "cal": "none"},
            # Classical aggregators
            {"agg": "mean",          "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "trimmed",       "j": 5, "cot": True,  "trim": 0.2, "cal": "none"},
            {"agg": "trimmed",       "j": 5, "cot": True,  "trim": 0.2, "cal": "platt"},
            # LLM-as-judge recipe baselines (paper §3)
            {"agg": "single_cot",    "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "majority_vote", "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "geval",         "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "poll",          "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "self_cons",     "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "prometheus",    "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            # EM-style statistical baselines
            {"agg": "ds",            "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "mace",          "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            # Ours
            {"agg": "rwmj",          "j": 5, "cot": True,  "trim": 0.0, "cal": "none"},
            {"agg": "rwmj",          "j": 5, "cot": True,  "trim": 0.0, "cal": "platt"},
        ]

    results: list[JudgeResult] = []
    rng_master = np.random.default_rng(SEED)

    for cfg_row in configs:
        agg = cfg_row["agg"]
        j = cfg_row["j"]
        cot = cfg_row["cot"]
        trim = cfg_row["trim"]
        cal_name = cfg_row["cal"]

        cal_rng = np.random.default_rng(SEED + 991)
        calibrator = _calibrator_for(cal_name, cal_rng, j, cot)

        preds_unit: list[float] = []
        truth_unit: list[float] = []
        agreements: list[float] = []
        timings: list[float] = []

        # For Dawid-Skene/MACE we collect all (item, judge) scores per
        # candidate then run a single batched estimator at the end of the
        # candidate's interview — that's the offline regime they target.
        # RW-MJ is *per-session* online: one fresh aggregator per candidate
        # because the panel reseeding produces a different set of judges.
        for c_idx in range(n_candidates):
            arche = ARCHETYPES[c_idx % len(ARCHETYPES)]
            cand = sample_candidate(rng_master, archetype=arche)
            rng = np.random.default_rng(int(cand.seed) + 2026)
            panel = make_judge_panel(
                rng, j=j, use_cot=cot, panel_type=panel_type,
                **(panel_kwargs or {}),
            )
            rwmj = RWMJAggregator(cfg=RWMJConfig()) if agg == "rwmj" else None

            # Collect per-item ground-truth + raw judge matrix (averaged
            # over rubric dims so we have shape (T, J) for DS / MACE).
            ground = []
            raw_judge_TJ: list[list[float]] = []
            cross_agree = []
            t0 = time.perf_counter()
            for t in range(rounds):
                q = simulate_answer_quality(cand, CATEGORIES[t % len(CATEGORIES)], 0.55, rng=rng)
                _, per_dim, agreement = panel.score(q, rng=rng, outlier_trim=0.0)
                ground.append(q)
                cross_agree.append(agreement)
                # average per rubric dim then average across dims → one number per judge
                per_judge = [
                    sum(per_dim[d][k] * RUBRIC_WEIGHTS[d] for d in RUBRIC_KEYS) / 100.0
                    for k in range(j)
                ]
                raw_judge_TJ.append(per_judge)
                # Aggregate this item
                if agg == "single":
                    s = _aggregate_single(per_dim, idx=0)
                elif agg == "mean":
                    s = _aggregate_mean(per_dim)
                elif agg == "trimmed":
                    s = _aggregate_trimmed(per_dim, trim=trim)
                elif agg == "single_cot":
                    s = judge_single(per_dim, RUBRIC_WEIGHTS)
                elif agg == "majority_vote":
                    s = judge_majority(per_dim, RUBRIC_WEIGHTS)
                elif agg == "geval":
                    s = judge_geval(per_dim, RUBRIC_WEIGHTS, rng=rng)
                elif agg == "poll":
                    s = judge_poll(per_dim, RUBRIC_WEIGHTS)
                elif agg == "self_cons":
                    s = judge_selfcons(per_dim, RUBRIC_WEIGHTS, rng=rng)
                elif agg == "prometheus":
                    s = judge_prometheus(per_dim, RUBRIC_WEIGHTS)
                elif agg == "rwmj":
                    s, rho, _dbg = aggregate_per_dim(per_dim, RUBRIC_WEIGHTS, rwmj)  # type: ignore[arg-type]
                else:
                    # DS / MACE — placeholder, filled after the batch loop.
                    s = 0.0
                online_aggs = {"single", "mean", "trimmed", "single_cot", "majority_vote",
                               "geval", "poll", "self_cons", "prometheus", "rwmj"}
                if agg in online_aggs:
                    cal_unit = calibrator.apply(s, consensus=agreement if j > 1 else None)
                    preds_unit.append(cal_unit)
                    truth_unit.append(q)

            elapsed = time.perf_counter() - t0
            timings.append(elapsed / max(1, rounds))
            agreements.extend(cross_agree)

            # Offline aggregators: now we have shape (T, J) per dim summary.
            if agg == "ds":
                res = dawid_skene_gaussian(raw_judge_TJ)
                for q, p in zip(ground, res.posterior.tolist()):
                    cal_unit = calibrator.apply(float(p), consensus=None)
                    preds_unit.append(cal_unit)
                    truth_unit.append(q)
            elif agg == "mace":
                res = mace_continuous(raw_judge_TJ)
                for q, p in zip(ground, res.posterior.tolist()):
                    cal_unit = calibrator.apply(float(p), consensus=None)
                    preds_unit.append(cal_unit)
                    truth_unit.append(q)

        preds = np.array(preds_unit)
        truth = np.array(truth_unit)
        mae = float(np.mean(np.abs(preds - truth))) if len(preds) else 0.0
        rmse = float(math.sqrt(np.mean((preds - truth) ** 2))) if len(preds) else 0.0
        bias = float(np.mean(preds - truth)) if len(preds) else 0.0
        kappa = cohens_kappa_from_pairs(preds.tolist(), truth.tolist(), n_bins=5)
        if len(preds):
            abs_err = np.abs(preds - truth)
            signed_err = preds - truth
            mae_ci = bootstrap_ci(abs_err)
            bias_ci = bootstrap_ci(signed_err)
        else:
            mae_ci = (0.0, 0.0)
            bias_ci = (0.0, 0.0)
        results.append(JudgeResult(
            name=f"{agg.upper()}_J{j}_CoT={cot}_cal={cal_name}_{panel_type}",
            aggregator=agg,
            judge_count=j,
            use_cot=cot,
            outlier_trim=trim,
            calibration=cal_name,
            mae=mae,
            rmse=rmse,
            bias=bias,
            kappa=kappa,
            agreement=float(np.mean(agreements)) if agreements else 1.0,
            judge_seconds_per_q=float(statistics.median(timings)) if timings else 0.0,
            panel_type=panel_type,
            mae_ci95=mae_ci,
            bias_ci95=bias_ci,
        ))

    if write_results:
        out = [asdict(r) for r in results]
        out_path = RESULTS_DIR / f"exp_judge_reliability_{panel_type}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        # Keep the historical filename pointing at the homogeneous run for
        # backwards compat with the existing plotting code.
        if panel_type == "homogeneous":
            (RESULTS_DIR / "exp_judge_reliability.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return results


# ---------------------------------------------------------------------------
# Experiment 2 — selection policy regret + coverage. Now includes IRT-CAT
# (BanditCAT-style baseline) and IA-LinUCB (ours).
# ---------------------------------------------------------------------------

@dataclass
class PolicyResult:
    strategy: str
    avg_total_reward: float
    avg_final_regret: float
    avg_coverage_entropy: float
    regret_curve: list[float]
    avg_ability_curve: list[float]
    per_archetype_reward: dict[str, float]
    per_archetype_regret: dict[str, float] = field(default_factory=dict)
    paired_t_vs_linucb: float | None = None      # paired t-test p-value
    ability_rmse: float = 0.0                    # |theta_hat_T - true_mean|
    per_arm_ability_rmse: float = 0.0            # RMSE over arms × candidates
    regret_ci95: tuple[float, float] = (0.0, 0.0)  # 95% bootstrap CI on avg_final_regret
    reward_ci95: tuple[float, float] = (0.0, 0.0)  # 95% bootstrap CI on avg_total_reward


def _override_for(strategy: str) -> Callable | None:
    if strategy == "ia_linucb":
        return ia_linucb_selector(IALinUCBConfig())
    if strategy == "irt_cat":
        return irt_cat_selector()
    return None


def run_policy_regret(
    *,
    n_candidates_per_arche: int = 25,
    rounds: int = 12,
    strategies: tuple[str, ...] = ("round_robin", "thompson", "linucb", "irt_cat", "ia_linucb"),
    judge_count: int = 3,
    use_cot: bool = True,
    calibrator: Calibrator | None = None,
) -> list[PolicyResult]:
    if calibrator is None:
        calibrator = fit_calibrator_from_pool(
            np.random.default_rng(SEED + 7),
            judge_count=judge_count,
            use_cot=use_cot,
        )

    rng_master = np.random.default_rng(SEED + 17)
    candidates: list[tuple[str, Any]] = []
    for arche in ARCHETYPES:
        for _ in range(n_candidates_per_arche):
            candidates.append((arche, sample_candidate(rng_master, archetype=arche)))

    results: list[PolicyResult] = []
    # Store per-candidate total rewards for paired t-test later.
    rewards_by_strategy: dict[str, list[float]] = {s: [] for s in strategies}

    for strategy in strategies:
        rewards_curves: list[list[float]] = []
        regret_curves: list[list[float]] = []
        ability_curves: list[list[float]] = []
        coverage_entropies: list[float] = []
        per_arche_reward: dict[str, list[float]] = {a: [] for a in ARCHETYPES}
        per_arche_regret: dict[str, list[float]] = {a: [] for a in ARCHETYPES}
        ability_errs: list[float] = []

        override = _override_for(strategy)

        per_arm_errs: list[float] = []
        for arche, cand in candidates:
            rng = np.random.default_rng(int(cand.seed))
            internal_strategy = strategy if override is None else "linucb"  # LinUCB book-keeping
            cfg = EpisodeConfig(
                strategy=internal_strategy,
                use_cot=use_cot,
                judge_count=judge_count,
                outlier_trim=0.15,
                calibrator=calibrator,
                rounds=rounds,
            )
            trace = run_episode(cand, cfg, rng=rng, selector_override=override)
            # Per-arm ability RMSE: compare topic_mean_hat (from memory)
            # against the true latent θ_arm for each arm we visited.
            visited = set(trace.arms)
            for arm in visited:
                # The simulator's per_topic_stats is internal to run_episode;
                # we recover topic_mean_hat by averaging the calibrated scores
                # for that arm across the trajectory.
                idxs = [i for i, a in enumerate(trace.arms) if a == arm]
                if not idxs:
                    continue
                topic_hat = float(np.mean([trace.calibrated_scores[i] for i in idxs]))
                true_theta = cand.abilities[arm]
                per_arm_errs.append(abs(topic_hat - true_theta))

            rng_o = np.random.default_rng(int(cand.seed) + 1)
            oracle_cfg = EpisodeConfig(
                strategy="round_robin",
                use_cot=use_cot,
                judge_count=judge_count,
                outlier_trim=0.15,
                calibrator=calibrator,
                rounds=rounds,
            )
            oracle_trace = run_episode(
                cand, oracle_cfg, rng=rng_o,
                selector_override=oracle_selector(cand),
            )

            rewards_curves.append(trace.rewards)
            regret_curves.append(regret_per_round(trace, oracle_trace))
            ability_curves.append(trace.ability_traj)
            coverage_entropies.append(trace.coverage_entropy())
            per_arche_reward[arche].append(trace.total_reward())
            per_arche_regret[arche].append(regret_curves[-1][-1])
            true_mean_ability = float(np.mean(list(cand.abilities.values())))
            ability_errs.append(abs(trace.ability_traj[-1] - true_mean_ability))
            rewards_by_strategy[strategy].append(trace.total_reward())

        rewards_arr = np.array(rewards_curves)
        regret_arr = np.array(regret_curves)
        ability_arr = np.array(ability_curves)

        per_session_final_regret = regret_arr[:, -1]
        per_session_total_reward = rewards_arr.sum(axis=1)
        regret_ci = bootstrap_ci(per_session_final_regret)
        reward_ci = bootstrap_ci(per_session_total_reward)

        results.append(PolicyResult(
            strategy=strategy,
            avg_total_reward=float(per_session_total_reward.mean()),
            avg_final_regret=float(per_session_final_regret.mean()),
            avg_coverage_entropy=float(np.mean(coverage_entropies)),
            regret_curve=regret_arr.mean(axis=0).tolist(),
            avg_ability_curve=ability_arr.mean(axis=0).tolist(),
            per_archetype_reward={a: float(np.mean(v)) if v else 0.0 for a, v in per_arche_reward.items()},
            per_archetype_regret={a: float(np.mean(v)) if v else 0.0 for a, v in per_arche_regret.items()},
            ability_rmse=float(np.sqrt(np.mean(np.array(ability_errs) ** 2))),
            per_arm_ability_rmse=float(np.sqrt(np.mean(np.array(per_arm_errs) ** 2))) if per_arm_errs else 0.0,
            regret_ci95=regret_ci,
            reward_ci95=reward_ci,
        ))

    # Paired t-test vs LinUCB for each new strategy (uses scipy if available).
    try:
        from scipy import stats as _scs  # type: ignore
        base = np.array(rewards_by_strategy["linucb"])
        for res in results:
            arr = np.array(rewards_by_strategy[res.strategy])
            if len(arr) == len(base) and res.strategy != "linucb":
                t, p = _scs.ttest_rel(arr, base)
                res.paired_t_vs_linucb = float(p)
    except Exception:
        pass

    out = [asdict(r) for r in results]
    (RESULTS_DIR / "exp_policy_regret.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return results


# ---------------------------------------------------------------------------
# Experiment 3 — joint adaptive policy (selector × difficulty), now
# including IA-LinUCB.
# ---------------------------------------------------------------------------

@dataclass
class JointResult:
    selector: str
    difficulty: str
    avg_total_reward: float
    avg_calibration_mae: float
    avg_target_hit_rate: float
    avg_coverage_entropy: float
    reward_ci95: tuple[float, float] = (0.0, 0.0)
    mae_ci95: tuple[float, float] = (0.0, 0.0)
    hit_rate_ci95: tuple[float, float] = (0.0, 0.0)


def run_joint_policy(
    *,
    n_candidates_per_arche: int = 20,
    rounds: int = 12,
    judge_count: int = 3,
    use_cot: bool = True,
    target: float = 0.7,
) -> list[JointResult]:
    calibrator = fit_calibrator_from_pool(
        np.random.default_rng(SEED + 31),
        judge_count=judge_count,
        use_cot=use_cot,
    )

    rng_master = np.random.default_rng(SEED + 41)
    candidates = []
    for arche in ARCHETYPES:
        for _ in range(n_candidates_per_arche):
            candidates.append(sample_candidate(rng_master, archetype=arche))

    grid = [
        ("round_robin", "heuristic"),
        ("round_robin", "pi_control"),
        ("linucb",      "heuristic"),
        ("linucb",      "pi_control"),
        ("ia_linucb",   "pi_control"),
    ]
    results: list[JointResult] = []
    for selector, difficulty in grid:
        os.environ["SELECTOR_STRATEGY"] = selector if selector != "ia_linucb" else "linucb"
        os.environ["DIFFICULTY_STRATEGY"] = difficulty
        from app.config import get_settings
        get_settings.cache_clear()  # type: ignore[attr-defined]
        get_settings()

        override = _override_for(selector)
        rewards, mae_vals, hits, ents = [], [], [], []
        for cand in candidates:
            rng = np.random.default_rng(int(cand.seed) + 91)
            cfg = EpisodeConfig(
                strategy=selector if override is None else "linucb",
                use_cot=use_cot,
                judge_count=judge_count,
                outlier_trim=0.15,
                calibrator=calibrator,
                rounds=rounds,
                difficulty_strategy=difficulty,
            )
            trace = run_episode(cand, cfg, rng=rng, selector_override=override)
            rewards.append(trace.total_reward())
            mae_vals.append(trace.calibration_mae())
            hits.append(float(np.mean(np.abs(np.array(trace.true_scores) - target) < 0.15)))
            ents.append(trace.coverage_entropy())

        results.append(JointResult(
            selector=selector,
            difficulty=difficulty,
            avg_total_reward=float(np.mean(rewards)),
            avg_calibration_mae=float(np.mean(mae_vals)),
            avg_target_hit_rate=float(np.mean(hits)),
            avg_coverage_entropy=float(np.mean(ents)),
            reward_ci95=bootstrap_ci(rewards),
            mae_ci95=bootstrap_ci(mae_vals),
            hit_rate_ci95=bootstrap_ci(hits),
        ))

    out = [asdict(r) for r in results]
    (RESULTS_DIR / "exp_joint_policy.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return results


# ---------------------------------------------------------------------------
# Experiment 3b — cross-dataset policy comparison
# ---------------------------------------------------------------------------

@dataclass
class CrossDatasetResult:
    dataset: str
    strategy: str
    avg_total_reward: float
    avg_final_regret: float
    per_arm_ability_rmse: float
    n_candidates: int
    reward_ci95: tuple[float, float] = (0.0, 0.0)
    regret_ci95: tuple[float, float] = (0.0, 0.0)


def run_cross_dataset_policy(
    *,
    n_per_dataset: int = 80,
    rounds: int = 12,
    strategies: tuple[str, ...] = ("round_robin", "thompson", "linucb", "irt_cat", "ia_linucb"),
    judge_count: int = 3,
    use_cot: bool = True,
) -> list[CrossDatasetResult]:
    calibrator = fit_calibrator_from_pool(
        np.random.default_rng(SEED + 53),
        judge_count=judge_count,
        use_cot=use_cot,
    )

    out: list[CrossDatasetResult] = []
    for ds_name in DATASETS:
        candidates = build_dataset(ds_name, n_per_dataset, seed=SEED + hash(ds_name) % 100_000)
        for strategy in strategies:
            override = _override_for(strategy)
            rewards: list[float] = []
            regrets: list[float] = []
            arm_errs: list[float] = []
            for _arche, cand in candidates:
                rng = np.random.default_rng(int(cand.seed))
                internal = strategy if override is None else "linucb"
                cfg = EpisodeConfig(
                    strategy=internal,
                    use_cot=use_cot,
                    judge_count=judge_count,
                    outlier_trim=0.15,
                    calibrator=calibrator,
                    rounds=rounds,
                )
                trace = run_episode(cand, cfg, rng=rng, selector_override=override)
                rng_o = np.random.default_rng(int(cand.seed) + 1)
                oracle_trace = run_episode(
                    cand,
                    EpisodeConfig(strategy="round_robin", use_cot=use_cot,
                                  judge_count=judge_count, outlier_trim=0.15,
                                  calibrator=calibrator, rounds=rounds),
                    rng=rng_o, selector_override=oracle_selector(cand),
                )
                rewards.append(trace.total_reward())
                regrets.append(regret_per_round(trace, oracle_trace)[-1])
                visited = set(trace.arms)
                for arm in visited:
                    idxs = [i for i, a in enumerate(trace.arms) if a == arm]
                    topic_hat = float(np.mean([trace.calibrated_scores[i] for i in idxs]))
                    arm_errs.append(abs(topic_hat - cand.abilities[arm]))

            out.append(CrossDatasetResult(
                dataset=ds_name,
                strategy=strategy,
                avg_total_reward=float(np.mean(rewards)),
                avg_final_regret=float(np.mean(regrets)),
                per_arm_ability_rmse=float(np.sqrt(np.mean(np.array(arm_errs) ** 2))) if arm_errs else 0.0,
                n_candidates=len(candidates),
                reward_ci95=bootstrap_ci(rewards),
                regret_ci95=bootstrap_ci(regrets),
            ))

    (RESULTS_DIR / "exp_cross_dataset.json").write_text(
        json.dumps([asdict(r) for r in out], indent=2, ensure_ascii=False)
    )
    return out


# ---------------------------------------------------------------------------
# Experiment 3c — baseline parameter sweep (sanity-check tuning)
# ---------------------------------------------------------------------------

@dataclass
class TuneResult:
    knob: str
    value: float
    mae: float
    kappa: float
    bias: float


def run_baseline_tuning(
    *,
    n_candidates: int = 40,
    rounds: int = 10,
) -> list[TuneResult]:
    """Trim-fraction sweep on trimmed mean + alpha sweep on LinUCB.

    Demonstrates that the baselines we compare against are themselves
    tuned, not naive defaults. We report the best operating point for
    each, which is what feeds the comparison tables.
    """
    out: list[TuneResult] = []
    rng_master = np.random.default_rng(SEED + 91)
    for trim in (0.0, 0.10, 0.20, 0.30, 0.40):
        cfg_local = [{"agg": "trimmed", "j": 5, "cot": True, "trim": trim, "cal": "none"}]
        res = run_judge_reliability(n_candidates=n_candidates, rounds=rounds,
                                    configs=cfg_local, panel_type="heterogeneous",
                                    write_results=False)
        x = res[0]
        out.append(TuneResult(knob="trimmed.trim", value=trim, mae=x.mae,
                              kappa=x.kappa, bias=x.bias))

    # Note: LinUCB alpha is a runtime setting; we sweep IA-LinUCB's alpha0
    # which is the comparable knob.
    from research.ia_linucb import IALinUCBConfig
    calibrator = fit_calibrator_from_pool(
        np.random.default_rng(SEED + 93), judge_count=3, use_cot=True
    )
    rng_master = np.random.default_rng(SEED + 95)
    cands = build_dataset("balanced", 40, seed=SEED + 95)
    for alpha0 in (0.4, 0.8, 1.0, 1.4, 2.0):
        rewards = []
        for _arche, cand in cands:
            rng = np.random.default_rng(int(cand.seed))
            override = ia_linucb_selector(IALinUCBConfig(alpha0=alpha0))
            cfg = EpisodeConfig(strategy="linucb", use_cot=True, judge_count=3,
                                outlier_trim=0.15, calibrator=calibrator, rounds=12)
            trace = run_episode(cand, cfg, rng=rng, selector_override=override)
            rewards.append(trace.total_reward())
        out.append(TuneResult(knob="ia_linucb.alpha0", value=alpha0,
                              mae=float(np.mean(rewards)), kappa=0.0, bias=0.0))

    # IA-LinUCB Fisher-weight sensitivity: gamma0 controls how strongly the
    # selector prefers items with high item-information at the current ability
    # estimate. gamma0=0.0 collapses to vanilla LinUCB, providing a sanity
    # floor; we want to show the default gamma0=0.9 sits in a flat reward
    # neighborhood (not a sharp peak that would betray over-tuning).
    rng_master = np.random.default_rng(SEED + 97)
    cands = build_dataset("balanced", 40, seed=SEED + 97)
    for gamma0 in (0.0, 0.3, 0.6, 0.9, 1.2, 1.5):
        rewards = []
        for _arche, cand in cands:
            rng = np.random.default_rng(int(cand.seed))
            override = ia_linucb_selector(IALinUCBConfig(gamma0=gamma0))
            cfg = EpisodeConfig(strategy="linucb", use_cot=True, judge_count=3,
                                outlier_trim=0.15, calibrator=calibrator, rounds=12)
            trace = run_episode(cand, cfg, rng=rng, selector_override=override)
            rewards.append(trace.total_reward())
        out.append(TuneResult(knob="ia_linucb.gamma0", value=gamma0,
                              mae=float(np.mean(rewards)), kappa=0.0, bias=0.0))

    (RESULTS_DIR / "exp_baseline_tuning.json").write_text(
        json.dumps([asdict(r) for r in out], indent=2, ensure_ascii=False)
    )
    return out


# ---------------------------------------------------------------------------
# Experiment 3d — judge-count sweep (J ∈ {1,3,5,7,9}) for trimmed-mean +
# RW-MJ on both homogeneous and heterogeneous panels. Reports MAE / κ /
# per-question judge cost so the J=5 default has a defensible cost-quality
# curve, not an unjustified pick.
# ---------------------------------------------------------------------------

@dataclass
class JudgeCountResult:
    aggregator: str
    panel_type: str
    judge_count: int
    mae: float
    rmse: float
    bias: float
    kappa: float
    judge_seconds_per_q: float


def run_judge_count_sweep(
    *,
    n_candidates: int = 60,
    rounds: int = 10,
    j_values: tuple[int, ...] = (1, 3, 5, 7, 9),
    aggregators: tuple[str, ...] = ("trimmed", "rwmj"),
    panel_types: tuple[str, ...] = ("homogeneous", "heterogeneous"),
) -> list[JudgeCountResult]:
    """Cost-quality curve for J ∈ {1,3,5,7,9} under both trimmed-mean and
    RW-MJ, on both panel regimes. Single-judge (J=1) is the natural floor
    because there is nothing to aggregate.
    """
    out: list[JudgeCountResult] = []
    for panel_type in panel_types:
        for agg in aggregators:
            for j in j_values:
                if agg == "trimmed":
                    trim = 0.0 if j < 4 else 0.2
                    cfg_row = {"agg": "trimmed", "j": j, "cot": True, "trim": trim, "cal": "none"}
                elif agg == "rwmj":
                    if j < 2:
                        # RW-MJ degenerates to a single judge — report the
                        # single-judge baseline so the curve has the same
                        # x-axis as trimmed-mean.
                        cfg_row = {"agg": "single", "j": 1, "cot": True, "trim": 0.0, "cal": "none"}
                    else:
                        cfg_row = {"agg": "rwmj", "j": j, "cot": True, "trim": 0.0, "cal": "none"}
                else:
                    continue
                res = run_judge_reliability(
                    n_candidates=n_candidates, rounds=rounds,
                    configs=[cfg_row], panel_type=panel_type, write_results=False,
                )
                x = res[0]
                out.append(JudgeCountResult(
                    aggregator=agg, panel_type=panel_type, judge_count=j,
                    mae=x.mae, rmse=x.rmse, bias=x.bias, kappa=x.kappa,
                    judge_seconds_per_q=x.judge_seconds_per_q,
                ))

    (RESULTS_DIR / "exp_judge_count_sweep.json").write_text(
        json.dumps([asdict(r) for r in out], indent=2, ensure_ascii=False)
    )
    return out


# ---------------------------------------------------------------------------
# Experiment 3e — adversary-fraction sweep: vary how many of the J=5 judges
# are heavily biased + noisy and measure aggregator MAE. Shows when each
# aggregator breaks: trimmed-mean fails when the adversary count exceeds the
# trim budget; DS/MACE/RW-MJ should degrade more gracefully because they
# learn per-judge weights.
# ---------------------------------------------------------------------------

@dataclass
class AdvSweepResult:
    aggregator: str
    n_adversaries: int
    mae: float
    rmse: float
    bias: float
    kappa: float
    mae_ci95: tuple[float, float] = (0.0, 0.0)
    bias_ci95: tuple[float, float] = (0.0, 0.0)


def run_adversary_sweep(
    *,
    n_candidates: int = 60,
    rounds: int = 10,
    j: int = 5,
    n_adv_values: tuple[int, ...] = (0, 1, 2, 3),
    aggregators: tuple[str, ...] = ("mean", "trimmed", "ds", "mace", "rwmj"),
) -> list[AdvSweepResult]:
    """Aggregator degradation curves as the adversary count goes 0→3 of J=5
    judges. The trimmed-mean uses ``trim=0.2`` (drops 1 per side); RW-MJ /
    DS / MACE learn per-judge weights and should track better when
    adversaries exceed the symmetric-trim budget.
    """
    out: list[AdvSweepResult] = []
    for n_adv in n_adv_values:
        for agg in aggregators:
            cfg_row = {
                "agg": agg,
                "j": j,
                "cot": True,
                "trim": 0.2 if agg == "trimmed" else 0.0,
                "cal": "none",
            }
            res = run_judge_reliability(
                n_candidates=n_candidates, rounds=rounds,
                configs=[cfg_row], panel_type="adversarial",
                panel_kwargs={"n_adversaries": n_adv},
                write_results=False,
            )
            x = res[0]
            out.append(AdvSweepResult(
                aggregator=agg, n_adversaries=n_adv,
                mae=x.mae, rmse=x.rmse, bias=x.bias, kappa=x.kappa,
                mae_ci95=x.mae_ci95, bias_ci95=x.bias_ci95,
            ))

    (RESULTS_DIR / "exp_adversary_sweep.json").write_text(
        json.dumps([asdict(r) for r in out], indent=2, ensure_ascii=False)
    )
    return out


# ---------------------------------------------------------------------------
# Experiment 3f — aggregator wall-clock latency. Measures end-to-end aggregate
# time for a 10-round, J=5 session under each aggregator. RW-MJ is online
# per-question; DS/MACE are batched at session end. Single-judge trimmed
# is the baseline floor (literally a sum over 5 numbers per dim).
# ---------------------------------------------------------------------------

@dataclass
class LatencyResult:
    aggregator: str
    rounds: int
    judge_count: int
    median_ms_per_session: float
    p95_ms_per_session: float
    sessions_measured: int


def run_latency_benchmark(
    *,
    n_sessions: int = 200,
    rounds: int = 10,
    j: int = 5,
    aggregators: tuple[str, ...] = ("mean", "trimmed", "ds", "mace", "rwmj"),
) -> list[LatencyResult]:
    """Wall-clock cost of each aggregator on a synthetic J=5, 10-round
    panel. We strip out the simulator's quality sampling and just feed
    the aggregators raw judge scores so the timing is the aggregator
    itself, not the upstream pipeline."""
    rng = np.random.default_rng(SEED + 991)
    # Pre-generate a panel of synthetic scores so all aggregators see the
    # same workload — fairness matters more than realism for a latency
    # benchmark.
    sessions: list[list[list[float]]] = []
    for _ in range(n_sessions):
        sess: list[list[float]] = []
        for _t in range(rounds):
            sess.append(np.clip(rng.normal(0.6, 0.15, size=j), 0.0, 1.0).tolist())
        sessions.append(sess)

    out: list[LatencyResult] = []
    for agg in aggregators:
        times_ms: list[float] = []
        for sess_scores in sessions:
            t0 = time.perf_counter()
            if agg == "rwmj":
                a = RWMJAggregator(cfg=RWMJConfig())
                for item in sess_scores:
                    a.aggregate(item)
            elif agg == "trimmed":
                for item in sess_scores:
                    sorted_v = sorted(item)
                    k = int(len(sorted_v) * 0.2)
                    sliced = sorted_v[k:len(sorted_v) - k] or sorted_v
                    _s = sum(sliced) / len(sliced)
            elif agg == "mean":
                for item in sess_scores:
                    _s = sum(item) / len(item)
            elif agg == "ds":
                # Dawid-Skene is offline-only: pay it at session end.
                dawid_skene_gaussian(sess_scores)
            elif agg == "mace":
                mace_continuous(sess_scores)
            times_ms.append((time.perf_counter() - t0) * 1000.0)
        times_ms.sort()
        median = times_ms[len(times_ms) // 2]
        p95 = times_ms[min(len(times_ms) - 1, int(0.95 * len(times_ms)))]
        out.append(LatencyResult(
            aggregator=agg, rounds=rounds, judge_count=j,
            median_ms_per_session=float(median),
            p95_ms_per_session=float(p95),
            sessions_measured=len(times_ms),
        ))

    (RESULTS_DIR / "exp_latency_benchmark.json").write_text(
        json.dumps([asdict(r) for r in out], indent=2, ensure_ascii=False)
    )
    return out


# ---------------------------------------------------------------------------
# Experiment 4 — termination rule (fixed budget vs PSER credible-interval)
# ---------------------------------------------------------------------------

@dataclass
class TerminationResult:
    rule: str
    avg_rounds_used: float
    avg_total_reward: float
    avg_ability_rmse: float
    se_threshold: float
    stop_reason_dist: dict[str, float]
    rounds_ci95: tuple[float, float] = (0.0, 0.0)
    rmse_ci95: tuple[float, float] = (0.0, 0.0)
    reward_ci95: tuple[float, float] = (0.0, 0.0)


def run_termination(
    *,
    n_candidates_per_arche: int = 15,
    rounds_cap: int = 16,
    judge_count: int = 3,
    use_cot: bool = True,
    se_thresholds: tuple[float, ...] = (0.30, 0.22, 0.18),
) -> list[TerminationResult]:
    calibrator = fit_calibrator_from_pool(
        np.random.default_rng(SEED + 71),
        judge_count=judge_count,
        use_cot=use_cot,
    )
    rng_master = np.random.default_rng(SEED + 73)
    candidates = []
    for arche in ARCHETYPES:
        for _ in range(n_candidates_per_arche):
            candidates.append(sample_candidate(rng_master, archetype=arche))

    results: list[TerminationResult] = []
    # Always include fixed-budget baseline.
    for se_thr in (None,) + se_thresholds:
        rounds_used: list[int] = []
        rewards: list[float] = []
        ability_errs: list[float] = []
        reasons: dict[str, int] = {}

        cfg_pser = PSERConfig(se_threshold=se_thr if se_thr is not None else 0.0,
                              max_rounds=rounds_cap)

        for cand in candidates:
            rng = np.random.default_rng(int(cand.seed) + 33)
            override = ia_linucb_selector(IALinUCBConfig())
            cfg = EpisodeConfig(
                strategy="linucb",
                use_cot=use_cot,
                judge_count=judge_count,
                outlier_trim=0.15,
                calibrator=calibrator,
                rounds=rounds_cap,
            )
            trace = run_episode(cand, cfg, rng=rng, selector_override=override)

            if se_thr is None:
                # Fixed-budget run: keep all rounds.
                rounds_used.append(rounds_cap)
                rewards.append(trace.total_reward())
                reasons["fixed_budget"] = reasons.get("fixed_budget", 0) + 1
            else:
                info_sum = 0.0
                cov: dict[str, int] = {}
                stopped_at = rounds_cap
                stop_reason = "max_rounds"
                for t in range(1, rounds_cap + 1):
                    arm = trace.arms[t - 1]
                    cov[arm] = cov.get(arm, 0) + 1
                    info_sum += fisher(trace.ability_traj[t - 1], trace.difficulties[t - 1],
                                       k=cfg_pser.k_irt)
                    stop, dbg = should_stop(round_idx=t, info_sum=info_sum,
                                            per_arm_coverage=cov, cfg=cfg_pser)
                    if stop:
                        stopped_at = t
                        stop_reason = dbg["reason"]
                        break
                rounds_used.append(stopped_at)
                rewards.append(sum(trace.rewards[:stopped_at]))
                reasons[stop_reason] = reasons.get(stop_reason, 0) + 1

            true_mean = float(np.mean(list(cand.abilities.values())))
            idx_for_ab = min(len(trace.ability_traj), rounds_used[-1]) - 1
            ability_errs.append(abs(trace.ability_traj[idx_for_ab] - true_mean))

        total = sum(reasons.values()) or 1
        # Bootstrap CIs on the per-candidate quantities. rmse_ci95 is
        # bootstrapped on the squared errors so the percentile reflects the
        # sampling distribution of the RMSE itself (sqrt of bootstrapped mean).
        sq_errs = np.asarray(ability_errs, dtype=float) ** 2
        if sq_errs.size:
            rng_ci = np.random.default_rng(SEED + 81)
            boots = rng_ci.choice(sq_errs, size=(2000, sq_errs.size), replace=True).mean(axis=1)
            rmse_ci = (float(np.sqrt(np.quantile(boots, 0.025))),
                       float(np.sqrt(np.quantile(boots, 0.975))))
        else:
            rmse_ci = (0.0, 0.0)
        results.append(TerminationResult(
            rule="fixed_budget" if se_thr is None else f"pser_se<={se_thr}",
            avg_rounds_used=float(np.mean(rounds_used)),
            avg_total_reward=float(np.mean(rewards)),
            avg_ability_rmse=float(np.sqrt(np.mean(np.array(ability_errs) ** 2))),
            se_threshold=float(se_thr) if se_thr is not None else 0.0,
            stop_reason_dist={k: round(v / total, 3) for k, v in reasons.items()},
            rounds_ci95=bootstrap_ci(rounds_used),
            rmse_ci95=rmse_ci,
            reward_ci95=bootstrap_ci(rewards),
        ))

    out = [asdict(r) for r in results]
    (RESULTS_DIR / "exp_termination.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return results


# ---------------------------------------------------------------------------
# Experiment — RW-MJ judge-bias convergence (calibration quality)
# ---------------------------------------------------------------------------

@dataclass
class RWMJConvergenceResult:
    judge_idx: int
    true_bias: float
    true_noise: float
    estimated_bias_traj: list[float]
    estimated_sigma_traj: list[float]
    final_bias_err: float
    final_competence: float


def run_rwmj_convergence(
    *,
    n_items: int = 200,
    seed: int = SEED + 4242,
    true_biases: tuple[float, ...] = (0.0, 0.0, 0.15, -0.10, 0.0),
    true_noises: tuple[float, ...] = (0.05, 0.05, 0.05, 0.05, 0.18),
) -> list[RWMJConvergenceResult]:
    """Inject judges with KNOWN bias / noise; check that RW-MJ recovers them.

    Each round draws a synthetic ground-truth quality ``q_t`` ~ U[0.2, 0.8]
    and emits ``score_jt = clip(q_t + bias_j + N(0, noise_j), 0, 1)`` for
    each judge. RW-MJ sees only the scores and is expected to learn
    bias_j on its own. We log the bias / sigma trajectories so we can plot
    the calibration learning curve.
    """
    rng = np.random.default_rng(seed)
    J = len(true_biases)
    assert len(true_noises) == J
    rwmj = RWMJAggregator(cfg=RWMJConfig())
    bias_trajs: list[list[float]] = [[] for _ in range(J)]
    sigma_trajs: list[list[float]] = [[] for _ in range(J)]

    for _t in range(n_items):
        q = float(rng.uniform(0.2, 0.8))
        raw_scores = [
            float(np.clip(q + true_biases[k] + rng.normal(0.0, true_noises[k]), 0.0, 1.0))
            for k in range(J)
        ]
        rwmj.aggregate(raw_scores)
        for k in range(J):
            st = rwmj.judges.get(k)
            bias_trajs[k].append(float(st.mu) if st else 0.0)
            sigma_trajs[k].append(float(math.sqrt(st.sigma2)) if st else 0.0)

    results: list[RWMJConvergenceResult] = []
    for k in range(J):
        final_b = bias_trajs[k][-1] if bias_trajs[k] else 0.0
        results.append(RWMJConvergenceResult(
            judge_idx=k,
            true_bias=float(true_biases[k]),
            true_noise=float(true_noises[k]),
            estimated_bias_traj=bias_trajs[k],
            estimated_sigma_traj=sigma_trajs[k],
            final_bias_err=float(abs(final_b - true_biases[k])),
            final_competence=float(rwmj.competence(k)),
        ))

    (RESULTS_DIR / "exp_rwmj_convergence.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)
    )
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("[exp 1a/4] judge reliability ablation — HOMOGENEOUS panel ...")
    r1a = run_judge_reliability(n_candidates=80, rounds=10, panel_type="homogeneous")
    for x in r1a:
        print(f"  {x.name:55s} MAE={x.mae:.3f} κ={x.kappa:.3f} bias={x.bias:+.3f}")

    print("[exp 1b/4] judge reliability ablation — HETEROGENEOUS panel ...")
    r1 = run_judge_reliability(n_candidates=80, rounds=10, panel_type="heterogeneous")
    for x in r1:
        print(f"  {x.name:55s} MAE={x.mae:.3f} κ={x.kappa:.3f} bias={x.bias:+.3f}")

    print("[exp 2/4] policy regret / coverage (incl. IRT-CAT, IA-LinUCB) ...")
    r2 = run_policy_regret(n_candidates_per_arche=25, rounds=12)
    for x in r2:
        p = f"p={x.paired_t_vs_linucb:.3f}" if x.paired_t_vs_linucb is not None else "—"
        print(f"  {x.strategy:14s} reward={x.avg_total_reward:.2f} regret={x.avg_final_regret:.2f} "
              f"H={x.avg_coverage_entropy:.2f} ab.RMSE={x.ability_rmse:.3f}  {p}")

    print("[exp 3/6] joint adaptive policy ...")
    r3 = run_joint_policy(n_candidates_per_arche=20, rounds=12)
    for x in r3:
        print(f"  {x.selector:12s} + {x.difficulty:10s} reward={x.avg_total_reward:.2f} "
              f"MAE={x.avg_calibration_mae:.3f} hit={x.avg_target_hit_rate:.2f}")

    print("[exp 4/6] cross-dataset policy comparison ...")
    r3b = run_cross_dataset_policy(n_per_dataset=60, rounds=12)
    for x in r3b:
        print(f"  ds={x.dataset:18s} {x.strategy:12s} reward={x.avg_total_reward:.2f} "
              f"regret={x.avg_final_regret:.2f} arm.RMSE={x.per_arm_ability_rmse:.3f}")

    print("[exp 5/7] baseline tuning sweep ...")
    r3c = run_baseline_tuning(n_candidates=40, rounds=10)
    for x in r3c:
        print(f"  {x.knob:24s} = {x.value:.2f}  metric={x.mae:.3f}")

    print("[exp 6/9] judge-count sweep (J ∈ {1,3,5,7,9}) ...")
    r3d = run_judge_count_sweep(n_candidates=60, rounds=10)
    for x in r3d:
        print(f"  panel={x.panel_type:13s} agg={x.aggregator:8s} J={x.judge_count} "
              f"MAE={x.mae:.3f} κ={x.kappa:.3f}")

    print("[exp 7/9] adversary-fraction sweep (J=5, 0..3 biased) ...")
    r3e = run_adversary_sweep(n_candidates=60, rounds=10)
    for x in r3e:
        print(f"  n_adv={x.n_adversaries} agg={x.aggregator:8s} MAE={x.mae:.3f} "
              f"κ={x.kappa:.3f} bias={x.bias:+.3f}")

    print("[exp 8/9] aggregator latency benchmark ...")
    r3f = run_latency_benchmark(n_sessions=500, rounds=10, j=5)
    for x in r3f:
        print(f"  {x.aggregator:8s} median={x.median_ms_per_session:.3f}ms "
              f"p95={x.p95_ms_per_session:.3f}ms")

    print("[exp 9/10] RW-MJ judge-bias convergence ...")
    r3g = run_rwmj_convergence(n_items=200)
    for x in r3g:
        print(f"  J{x.judge_idx}: true b={x.true_bias:+.3f} n={x.true_noise:.2f}  "
              f"est b={x.estimated_bias_traj[-1]:+.3f} (err {x.final_bias_err:.3f}) "
              f"comp={x.final_competence:.3f}")

    print("[exp 10/10] PSER termination ...")
    r4 = run_termination(n_candidates_per_arche=15, rounds_cap=16)
    for x in r4:
        print(f"  {x.rule:18s} rounds={x.avg_rounds_used:.1f} reward={x.avg_total_reward:.2f} "
              f"ab.RMSE={x.avg_ability_rmse:.3f} reasons={x.stop_reason_dist}")

    summary = {
        "judge_reliability_homogeneous":   [asdict(x) for x in r1a],
        "judge_reliability_heterogeneous": [asdict(x) for x in r1],
        "policy_regret":     [asdict(x) for x in r2],
        "joint_policy":      [asdict(x) for x in r3],
        "cross_dataset":     [asdict(x) for x in r3b],
        "baseline_tuning":   [asdict(x) for x in r3c],
        "judge_count_sweep": [asdict(x) for x in r3d],
        "adversary_sweep":   [asdict(x) for x in r3e],
        "latency_benchmark": [asdict(x) for x in r3f],
        "rwmj_convergence":  [asdict(x) for x in r3g],
        "termination":       [asdict(x) for x in r4],
    }
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"wrote {RESULTS_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
