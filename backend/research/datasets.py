"""Candidate dataset variants for cross-dataset experiments.

Real recruiting funnels are not a single distribution; different industries
and stages produce structurally different candidate pools. We define four
named datasets so the comparison tables can show that IA-LinUCB and RW-MJ
generalise rather than over-fit to one synthetic regime:

  * ``balanced``     — the default mixed-archetype pool (junior/backend/
    senior/balanced in 1:1:1:1 ratio).
  * ``senior_heavy`` — senior-skewed pool (1:1:1:5). Tests whether
    selectors over-explore on a population that is mostly strong.
  * ``adversarial``  — candidates with very narrow strengths (1 strong arm
    only) and noisy resume signals. Stresses ability estimation.
  * ``resume_mismatch`` — high resume-affinity but low actual ability;
    the standard LinUCB context will overweight resume and pick poorly.
    Designed to reward IA-LinUCB's Fisher info term.

Each dataset is a list of ``(archetype, CandidateProfile)`` tuples ready
to be consumed by ``run_episode``. The construction is deterministic given
the seed so cross-dataset numbers in the paper are reproducible.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from app.agents.memory import CATEGORIES
from research.simulator import CandidateProfile, sample_candidate


def _adversarial_candidate(rng: np.random.Generator) -> CandidateProfile:
    """Single very strong category, the rest very weak. Resume gives a
    misleading hint at a different category."""
    base = {c: float(np.clip(rng.beta(2, 6), 0.02, 0.35)) for c in CATEGORIES}
    strong = str(rng.choice(list(CATEGORIES)))
    base[strong] = float(np.clip(rng.beta(7, 2), 0.6, 0.95))
    # Resume hints at a different (random) category, not the actual strong one.
    decoy = str(rng.choice([c for c in CATEGORIES if c != strong]))
    align = {c: 0.2 for c in CATEGORIES}
    align[decoy] = 0.8
    return CandidateProfile(
        seed=int(rng.integers(0, 1_000_000)),
        abilities=base,
        verbosity=float(rng.uniform(0.3, 0.8)),
        resume_alignment=align,
    )


def _resume_mismatch_candidate(rng: np.random.Generator) -> CandidateProfile:
    """High resume affinity everywhere, modest actual ability everywhere."""
    base = {c: float(np.clip(rng.beta(3, 5), 0.1, 0.55)) for c in CATEGORIES}
    align = {c: float(rng.beta(7, 2)) for c in CATEGORIES}
    return CandidateProfile(
        seed=int(rng.integers(0, 1_000_000)),
        abilities=base,
        verbosity=float(rng.uniform(0.5, 0.9)),
        resume_alignment=align,
    )


def build_dataset(name: str, n: int, *, seed: int) -> list[tuple[str, CandidateProfile]]:
    rng = np.random.default_rng(seed)
    if name == "balanced":
        mix = ["balanced", "backend", "junior", "senior"] * ((n + 3) // 4)
        return [(arche, sample_candidate(rng, archetype=arche)) for arche in mix[:n]]
    if name == "senior_heavy":
        per = max(1, n // 8)
        mix = ["balanced"] * per + ["junior"] * per + ["backend"] * per + ["senior"] * (n - 3 * per)
        return [(arche, sample_candidate(rng, archetype=arche)) for arche in mix]
    if name == "adversarial":
        return [("adversarial", _adversarial_candidate(rng)) for _ in range(n)]
    if name == "resume_mismatch":
        return [("resume_mismatch", _resume_mismatch_candidate(rng)) for _ in range(n)]
    raise ValueError(f"unknown dataset {name}")


DATASETS = ("balanced", "senior_heavy", "adversarial", "resume_mismatch")
