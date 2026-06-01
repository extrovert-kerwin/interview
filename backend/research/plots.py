"""Generate the paper's figures from the JSON experiment results.

Each figure is written twice: once as PDF (camera-ready) and once as PNG
(quick visual sanity-check). Reads from ``research/results/*.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = Path(__file__).parent / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "legend.fontsize": 9,
    "figure.dpi": 130,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

STRAT_COLOR = {
    "round_robin": "#888888",
    "thompson":    "#D97A2A",
    "linucb":      "#3D72B6",
    "irt_cat":     "#7AB55C",
    "ia_linucb":   "#B83C8B",
}
STRAT_LABEL = {
    "round_robin": "Round-robin",
    "thompson":    "Thompson",
    "linucb":      "LinUCB",
    "irt_cat":     "Max-Fisher CAT",
    "ia_linucb":   "IA-LinUCB (ours)",
}


def _save(fig, name: str) -> None:
    pdf = FIGURES_DIR / f"{name}.pdf"
    png = FIGURES_DIR / f"{name}.png"
    fig.savefig(pdf)
    fig.savefig(png)
    print(f"  wrote {pdf.name} + {png.name}")


def _short_label(d: dict) -> str:
    """Short axis label for a judge-reliability row, picking the most
    informative field for that aggregator."""
    agg = d.get("aggregator", "?")
    j = d.get("judge_count", 0)
    cal = d.get("calibration", "none")
    nice = {
        "single": f"single (J={j}, CoT={'Y' if d.get('use_cot') else 'N'})",
        "mean": "mean",
        "trimmed": f"trimmed t={d.get('outlier_trim', 0):.1f}",
        "single_cot": "1-judge CoT",
        "majority_vote": "majority-vote",
        "geval": "G-Eval",
        "poll": "PoLL",
        "self_cons": "self-consistency",
        "prometheus": "Prometheus-2",
        "ds": "Dawid-Skene",
        "mace": "MACE",
        "rwmj": "RW-MJ (ours)",
    }.get(agg, agg)
    if cal == "platt":
        nice = f"{nice}+Platt"
    return nice


# ---------------------------------------------------------------------------
# Fig 1 — judge-reliability ablation (two panels: homogeneous / heterogeneous)
# ---------------------------------------------------------------------------

def _plot_panel(ax, data, title):
    # Sort: keep ordering stable but put RW-MJ + Trimmed near the right for
    # the eye.  Drop the J=1 no-CoT row from the plot (still in tables).
    rows = [d for d in data if not (d["aggregator"] == "single" and d["judge_count"] == 1 and not d["use_cot"])]
    short = [_short_label(d) for d in rows]
    mae = [d["mae"] for d in rows]
    kappa = [d["kappa"] for d in rows]
    x = np.arange(len(short))
    w = 0.38
    colors = [
        "#B83C8B" if d["aggregator"] == "rwmj" else
        "#3D72B6" if d["aggregator"] == "trimmed" else
        "#9aa6b2"
        for d in rows
    ]
    bars1 = ax.bar(x - w / 2, mae, w, color=colors, edgecolor="black", linewidth=0.4, label="MAE")
    for b, v in zip(bars1, mae):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.001, f"{v:.03f}",
                ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("MAE")
    ax.set_ylim(0, max(mae) * 1.4)
    ax.set_xticks(x)
    ax.set_xticklabels(short, rotation=35, ha="right", fontsize=7.5)
    ax.set_title(title)
    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.set_ylim(min(kappa) * 0.96, 1.0)
    ax2.set_ylabel("κ")
    bars2 = ax2.bar(x + w / 2, kappa, w, color="#D97A2A", alpha=0.75, label="κ")
    for b, v in zip(bars2, kappa):
        ax2.text(b.get_x() + b.get_width() / 2, v + 0.002, f"{v:.02f}",
                 ha="center", va="bottom", fontsize=7)


def fig_judge_reliability() -> None:
    homo = json.loads((RESULTS_DIR / "exp_judge_reliability_homogeneous.json").read_text())
    hetero = json.loads((RESULTS_DIR / "exp_judge_reliability_heterogeneous.json").read_text())

    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.4))
    _plot_panel(axes[0], homo, "Homogeneous judge panel (independent noise, no per-judge bias)")
    _plot_panel(axes[1], hetero, "Heterogeneous panel (1 noisy + 1 moderately-biased judge)")
    fig.tight_layout()
    _save(fig, "fig_judge_reliability")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 2 — regret curves (all 5 strategies)
# ---------------------------------------------------------------------------

def fig_regret_curves() -> None:
    data = json.loads((RESULTS_DIR / "exp_policy_regret.json").read_text())
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    for d in data:
        curve = d["regret_curve"]
        xs = np.arange(1, len(curve) + 1)
        s = d["strategy"]
        ax.plot(xs, curve, marker="o", markersize=4,
                label=STRAT_LABEL.get(s, s),
                color=STRAT_COLOR.get(s),
                linewidth=2 if s in ("linucb", "ia_linucb") else 1.4,
                linestyle="-" if s != "ia_linucb" else "--")
    ax.axhline(0, color="black", linewidth=0.5, linestyle=":")
    ax.set_xlabel("Interview round t")
    ax.set_ylabel("Cumulative regret R(t)")
    ax.set_title("Selection-policy regret on synthetic candidates")
    ax.legend(frameon=False, ncol=2, fontsize=8.5)
    _save(fig, "fig_regret_curves")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 3 — ability-estimate convergence
# ---------------------------------------------------------------------------

def fig_ability_convergence() -> None:
    data = json.loads((RESULTS_DIR / "exp_policy_regret.json").read_text())
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    for d in data:
        curve = d["avg_ability_curve"]
        xs = np.arange(1, len(curve) + 1)
        s = d["strategy"]
        ax.plot(xs, curve, marker="s", markersize=3.5, linewidth=1.8,
                color=STRAT_COLOR.get(s),
                linestyle="-" if s != "ia_linucb" else "--",
                label=STRAT_LABEL.get(s, s))
    ax.set_xlabel("Interview round t")
    ax.set_ylabel("Estimated ability θ̂_t")
    ax.set_title("Ability-estimate trajectory (mean across candidates)")
    ax.legend(frameon=False, ncol=2, fontsize=8.5)
    _save(fig, "fig_ability_convergence")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 4 — joint adaptive grid (selector × difficulty)
# ---------------------------------------------------------------------------

def fig_joint_grid() -> None:
    data = json.loads((RESULTS_DIR / "exp_joint_policy.json").read_text())
    selectors = ["round_robin", "linucb", "ia_linucb"]
    difficulties = ["heuristic", "pi_control"]
    matrix_reward = np.full((len(selectors), len(difficulties)), np.nan)
    matrix_hit = np.full((len(selectors), len(difficulties)), np.nan)
    for d in data:
        if d["selector"] not in selectors:
            continue
        i = selectors.index(d["selector"])
        j = difficulties.index(d["difficulty"])
        matrix_reward[i, j] = d["avg_total_reward"]
        matrix_hit[i, j] = d["avg_target_hit_rate"]

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.4))
    fig.subplots_adjust(wspace=0.55)
    for ax, mat, title, fmt in [
        (axes[0], matrix_reward, "Avg. shaped reward", "{:.2f}"),
        (axes[1], matrix_hit,    "Target-difficulty hit rate", "{:.2f}"),
    ]:
        im = ax.imshow(mat, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(difficulties)))
        ax.set_xticklabels(["heuristic", "PI control"])
        ax.set_yticks(range(len(selectors)))
        ax.set_yticklabels(["round-robin", "LinUCB", "IA-LinUCB (ours)"])
        ax.set_title(title)
        finite = mat[np.isfinite(mat)]
        midpoint = finite.mean() if len(finite) else 0.0
        for i in range(len(selectors)):
            for j in range(len(difficulties)):
                v = mat[i, j]
                if np.isnan(v):
                    ax.text(j, i, "—", ha="center", va="center", color="black", fontsize=12)
                else:
                    ax.text(j, i, fmt.format(v), ha="center", va="center",
                            color="white" if v > midpoint else "black", fontsize=11)
        fig.colorbar(im, ax=ax, shrink=0.85, pad=0.04)
    _save(fig, "fig_joint_grid")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 5 — cross-dataset selector comparison
# ---------------------------------------------------------------------------

def fig_cross_dataset() -> None:
    data = json.loads((RESULTS_DIR / "exp_cross_dataset.json").read_text())
    datasets = sorted({d["dataset"] for d in data}, key=lambda s: ("balanced senior_heavy adversarial resume_mismatch".split()).index(s))
    strategies = ["round_robin", "thompson", "linucb", "irt_cat", "ia_linucb"]

    reward = np.full((len(datasets), len(strategies)), np.nan)
    rmse   = np.full((len(datasets), len(strategies)), np.nan)
    for d in data:
        i = datasets.index(d["dataset"])
        j = strategies.index(d["strategy"])
        reward[i, j] = d["avg_total_reward"]
        rmse[i, j]   = d["per_arm_ability_rmse"]

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 3.8))
    x = np.arange(len(datasets))
    w = 0.16
    for ax, mat, title, ylabel, fmt in [
        (axes[0], reward, "Average shaped reward (higher is better)", "Reward", "{:.2f}"),
        (axes[1], rmse,   "Per-arm ability RMSE (lower is better)",   "Per-arm RMSE", "{:.2f}"),
    ]:
        for j, s in enumerate(strategies):
            offset = (j - (len(strategies) - 1) / 2) * w
            ax.bar(x + offset, mat[:, j], w, color=STRAT_COLOR[s], label=STRAT_LABEL[s],
                   edgecolor="black", linewidth=0.3)
        ax.set_xticks(x)
        ax.set_xticklabels([d.replace("_", "-") for d in datasets], rotation=10)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
    axes[0].legend(frameon=False, fontsize=8, ncol=3, loc="lower center", bbox_to_anchor=(1.05, -0.35))
    fig.tight_layout()
    _save(fig, "fig_cross_dataset")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 6 — PSER termination tradeoff
# ---------------------------------------------------------------------------

def fig_pser_termination() -> None:
    data = json.loads((RESULTS_DIR / "exp_termination.json").read_text())
    rounds = [d["avg_rounds_used"] for d in data]
    rmse   = [d["avg_ability_rmse"] for d in data]
    reward = [d["avg_total_reward"] for d in data]
    labels = [d["rule"] for d in data]

    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    # Pareto-style scatter: rounds (x) vs ability RMSE (y), reward as size.
    sizes = [180 + 30 * (r - min(reward)) for r in reward]
    colors = ["#888888" if l == "fixed_budget" else "#B83C8B" for l in labels]
    ax.scatter(rounds, rmse, s=sizes, c=colors, alpha=0.85, edgecolor="black", linewidth=0.6)
    for r, e, lab in zip(rounds, rmse, labels):
        # Slight offset for label readability.
        offset = (0.4, 0.004) if lab == "fixed_budget" else (0.35, -0.002)
        ax.annotate(lab, xy=(r, e), xytext=(r + offset[0], e + offset[1]),
                    fontsize=8.5, ha="left")
    ax.set_xlabel("Average interview rounds used")
    ax.set_ylabel("Average ability RMSE (θ̂ vs θ*)")
    ax.set_title("PSER early stopping vs fixed-budget interview")
    ax.invert_yaxis()
    _save(fig, "fig_pser_termination")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 7 — baseline tuning sweeps
# ---------------------------------------------------------------------------

def fig_baseline_tuning() -> None:
    data = json.loads((RESULTS_DIR / "exp_baseline_tuning.json").read_text())
    trim = [(d["value"], d["mae"], d["kappa"]) for d in data if d["knob"] == "trimmed.trim"]
    ia   = [(d["value"], d["mae"]) for d in data if d["knob"] == "ia_linucb.alpha0"]
    gam  = [(d["value"], d["mae"]) for d in data if d["knob"] == "ia_linucb.gamma0"]
    trim.sort(); ia.sort(); gam.sort()

    n_panels = 2 + (1 if gam else 0)
    fig, axes = plt.subplots(1, n_panels, figsize=(4.7 * n_panels, 3.4))
    if trim:
        xs, mae, kap = zip(*trim)
        ax = axes[0]
        ax.plot(xs, mae, marker="o", color="#3D72B6", linewidth=2, label="MAE")
        ax.set_xlabel("Outlier trim fraction t")
        ax.set_ylabel("MAE", color="#3D72B6")
        ax.tick_params(axis="y", labelcolor="#3D72B6")
        ax.set_title("Trimmed-mean: trim-fraction sweep")
        ax2 = ax.twinx()
        ax2.spines["top"].set_visible(False)
        ax2.plot(xs, kap, marker="s", color="#D97A2A", linewidth=2, label="κ")
        ax2.set_ylabel("κ", color="#D97A2A")
        ax2.tick_params(axis="y", labelcolor="#D97A2A")

    if ia:
        xs, rw = zip(*ia)
        ax = axes[1]
        ax.plot(xs, rw, marker="o", color="#B83C8B", linewidth=2)
        ax.set_xlabel("Initial exploration weight α₀")
        ax.set_ylabel("Average shaped reward")
        ax.set_title("IA-LinUCB: α₀ sensitivity")
        best_x = xs[int(np.argmax(rw))]
        best_y = max(rw)
        ax.annotate(f"best α₀={best_x}", xy=(best_x, best_y),
                    xytext=(best_x + 0.1, best_y - 0.05),
                    arrowprops=dict(arrowstyle="->", color="#444"), fontsize=8.5)

    if gam:
        xs, rw = zip(*gam)
        ax = axes[2]
        ax.plot(xs, rw, marker="o", color="#4A8C4E", linewidth=2)
        ax.axvline(0.9, color="#888", linestyle=":", linewidth=1)
        ax.axvline(0.0, color="#BBB", linestyle="--", linewidth=1)
        ax.set_xlabel("Fisher-info weight γ₀")
        ax.set_ylabel("Average shaped reward")
        ax.set_title("IA-LinUCB: γ₀ sensitivity (γ₀=0 → vanilla LinUCB)")
        best_x = xs[int(np.argmax(rw))]
        best_y = max(rw)
        ax.annotate(f"best γ₀={best_x}", xy=(best_x, best_y),
                    xytext=(best_x - 0.55, best_y - 0.04),
                    arrowprops=dict(arrowstyle="->", color="#444"), fontsize=8.5)

    fig.tight_layout()
    _save(fig, "fig_baseline_tuning")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 8c — adversary-fraction degradation curves
# ---------------------------------------------------------------------------

def fig_adversary_sweep() -> None:
    data = json.loads((RESULTS_DIR / "exp_adversary_sweep.json").read_text())
    aggs = ["mean", "trimmed", "ds", "mace", "rwmj"]
    labels = {"mean": "Mean", "trimmed": "Trimmed (t=0.2)", "ds": "Dawid–Skene",
              "mace": "MACE", "rwmj": "RW-MJ (ours)"}
    colors = {"mean": "#9aa6b2", "trimmed": "#3D72B6", "ds": "#7AB55C",
              "mace": "#D97A2A", "rwmj": "#B83C8B"}

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6))
    for agg in aggs:
        rows = sorted([d for d in data if d["aggregator"] == agg], key=lambda d: d["n_adversaries"])
        xs = [d["n_adversaries"] for d in rows]
        mae = [d["mae"] for d in rows]
        bias = [d["bias"] for d in rows]
        axes[0].plot(xs, mae, marker="o", color=colors[agg], linewidth=2, label=labels[agg])
        axes[1].plot(xs, bias, marker="s", color=colors[agg], linewidth=2, label=labels[agg])

    axes[0].set_xticks([0, 1, 2, 3])
    axes[0].set_xlabel("Adversaries in 5-judge panel")
    axes[0].set_ylabel("MAE $\\downarrow$")
    axes[0].set_title("MAE vs adversary fraction")
    axes[0].legend(frameon=False, fontsize=8)

    axes[1].set_xticks([0, 1, 2, 3])
    axes[1].set_xlabel("Adversaries in 5-judge panel")
    axes[1].set_ylabel("Bias (signed)")
    axes[1].set_title("Aggregator bias vs adversary fraction")
    axes[1].axhline(0, color="black", linewidth=0.5, linestyle=":")
    axes[1].legend(frameon=False, fontsize=8)

    fig.tight_layout()
    _save(fig, "fig_adversary_sweep")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 8b — judge-count cost-quality curve
# ---------------------------------------------------------------------------

def fig_judge_count_sweep() -> None:
    data = json.loads((RESULTS_DIR / "exp_judge_count_sweep.json").read_text())
    panels = ["homogeneous", "heterogeneous"]
    aggs = ["trimmed", "rwmj"]
    colors = {"trimmed": "#3D72B6", "rwmj": "#B83C8B"}
    labels = {"trimmed": "Trimmed-mean", "rwmj": "RW-MJ (ours)"}

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.4))
    for ax, panel in zip(axes, panels):
        for agg in aggs:
            rows = sorted(
                [d for d in data if d["panel_type"] == panel and d["aggregator"] == agg],
                key=lambda d: d["judge_count"],
            )
            xs = [d["judge_count"] for d in rows]
            mae = [d["mae"] for d in rows]
            ax.plot(xs, mae, marker="o", color=colors[agg], linewidth=2, label=labels[agg])
            for x, y in zip(xs, mae):
                ax.text(x, y + 0.002, f"{y:.03f}", ha="center", va="bottom", fontsize=7,
                        color=colors[agg])
        ax.set_xticks([1, 3, 5, 7, 9])
        ax.set_xlabel("Judge-panel size $J$")
        ax.set_ylabel("MAE $\\downarrow$")
        ax.set_title(f"{panel.capitalize()} panel")
        ax.legend(frameon=False, fontsize=8.5)
        ax.set_ylim(bottom=0)
    fig.tight_layout()
    _save(fig, "fig_judge_count_sweep")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 8c — RW-MJ judge-bias convergence (calibration learning curves)
# ---------------------------------------------------------------------------

def fig_rwmj_convergence() -> None:
    data = json.loads((RESULTS_DIR / "exp_rwmj_convergence.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.4))
    palette = ["#3D72B6", "#7AB55C", "#D14A4A", "#D97A2A", "#8C4FB0"]
    for r in data:
        j = int(r["judge_idx"])
        true_b = float(r["true_bias"])
        true_n = float(r["true_noise"])
        traj_b = r["estimated_bias_traj"]
        traj_s = r["estimated_sigma_traj"]
        xs = list(range(1, len(traj_b) + 1))
        label = f"J{j} (true b={true_b:+.2f}, $\\sigma$={true_n:.2f})"
        axes[0].plot(xs, traj_b, color=palette[j % len(palette)], linewidth=1.6, label=label)
        axes[0].axhline(true_b, color=palette[j % len(palette)], linewidth=0.8,
                        linestyle="--", alpha=0.55)
        axes[1].plot(xs, traj_s, color=palette[j % len(palette)], linewidth=1.6, label=label)
        axes[1].axhline(true_n, color=palette[j % len(palette)], linewidth=0.8,
                        linestyle="--", alpha=0.55)

    axes[0].set_xlabel("Items observed")
    axes[0].set_ylabel("Estimated bias $\\hat\\mu_j$")
    axes[0].set_title("Per-judge bias estimate vs. items")
    axes[0].legend(frameon=False, fontsize=7, loc="upper right")
    axes[0].axhline(0, color="black", linewidth=0.4, linestyle=":")

    axes[1].set_xlabel("Items observed")
    axes[1].set_ylabel("Estimated noise $\\hat\\sigma_j$")
    axes[1].set_title("Per-judge noise estimate vs. items")
    axes[1].legend(frameon=False, fontsize=7, loc="upper right")
    axes[1].set_ylim(bottom=0)

    fig.tight_layout()
    _save(fig, "fig_rwmj_convergence")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Fig 8 — system architecture / agent message flow (vector schematic)
# ---------------------------------------------------------------------------

def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    ax.axis("off")
    nodes = [
        ("Resume\n+ Position",                          0.08, 0.60, 0.07, 0.10),
        ("Memory M_t\n(ability θ̂, coverage,\ngap set, η_t hints)",
                                                        0.30, 0.60, 0.10, 0.13),
        ("Selection π_θ\n(IA-LinUCB)",                  0.55, 0.85, 0.08, 0.10),
        ("Difficulty π_d\n(PI control)",                0.55, 0.35, 0.08, 0.10),
        ("LLM Interviewer",                              0.78, 0.60, 0.08, 0.08),
        ("Multi-judge LLM\n+ RW-MJ + Platt",            0.96, 0.60, 0.09, 0.10),
    ]
    box_xy: dict[str, tuple[float, float, float, float]] = {}
    for name, cx, cy, hw, hh in nodes:
        ax.add_patch(plt.Rectangle((cx - hw, cy - hh), 2 * hw, 2 * hh, fill=True,
                                   facecolor="#EEF2F7", edgecolor="#3D72B6", linewidth=1.4))
        ax.text(cx, cy, name, ha="center", va="center", fontsize=9)
        box_xy[name] = (cx, cy, hw, hh)

    def edge(src_name: str, dst_name: str, src_side: str = "right", dst_side: str = "left") -> None:
        sx, sy, shw, shh = box_xy[src_name]
        dx, dy, dhw, dhh = box_xy[dst_name]
        sides = {
            "right":  (sx + shw, sy),
            "left":   (sx - shw, sy),
            "top":    (sx, sy + shh),
            "bottom": (sx, sy - shh),
        }
        ssrc = sides[src_side]
        dsides = {
            "right":  (dx + dhw, dy),
            "left":   (dx - dhw, dy),
            "top":    (dx, dy + dhh),
            "bottom": (dx, dy - dhh),
        }
        sdst = dsides[dst_side]
        ax.annotate("", xy=sdst, xytext=ssrc,
                    arrowprops=dict(arrowstyle="-|>", color="#444", lw=1.2))

    edge("Resume\n+ Position", "Memory M_t\n(ability θ̂, coverage,\ngap set, η_t hints)")
    edge("Memory M_t\n(ability θ̂, coverage,\ngap set, η_t hints)", "Selection π_θ\n(IA-LinUCB)", "right", "bottom")
    edge("Memory M_t\n(ability θ̂, coverage,\ngap set, η_t hints)", "Difficulty π_d\n(PI control)", "right", "top")
    edge("Selection π_θ\n(IA-LinUCB)", "LLM Interviewer", "bottom", "top")
    edge("Difficulty π_d\n(PI control)", "LLM Interviewer", "top", "bottom")
    edge("LLM Interviewer", "Multi-judge LLM\n+ RW-MJ + Platt")

    ax.annotate(
        "", xy=(0.40, 0.18), xytext=(0.96, 0.18),
        arrowprops=dict(arrowstyle="-|>", color="#888", lw=1.0,
                        connectionstyle="arc3,rad=0.0"),
    )
    ax.plot([0.96, 0.96], [0.50, 0.18], color="#888", lw=1.0)
    ax.plot([0.40, 0.40], [0.18, 0.47], color="#888", lw=1.0)
    ax.annotate("", xy=(0.40, 0.47), xytext=(0.40, 0.18),
                arrowprops=dict(arrowstyle="-|>", color="#888", lw=1.0))
    ax.text(0.68, 0.13, "η_t feedback (gap text → memory)", color="#555",
            ha="center", va="center", fontsize=9, style="italic")

    ax.set_xlim(0, 1.08)
    ax.set_ylim(0.05, 1.02)
    ax.set_title("Agentic interview loop")
    _save(fig, "fig_architecture")
    plt.close(fig)


def main() -> None:
    print("[plots] generating figures ...")
    fig_judge_reliability()
    fig_regret_curves()
    fig_ability_convergence()
    fig_joint_grid()
    fig_cross_dataset()
    fig_pser_termination()
    fig_baseline_tuning()
    fig_judge_count_sweep()
    fig_adversary_sweep()
    fig_rwmj_convergence()
    fig_architecture()
    print(f"all figures in {FIGURES_DIR}")


if __name__ == "__main__":
    main()
