"""Bayesian weight recalibration for the ensemble.

Each base model's weight per market is treated as a posterior updated from
its realized log-loss: exponentiated-gradient (multiplicative weights) with a
learning rate, which is the online-Bayes update for a log-loss dealer. Weights
never hit zero, so a cold model can recover.
"""
from __future__ import annotations

import math


def clip_probability(p: float, eps: float = 1e-4) -> float:
    return min(max(p, eps), 1 - eps)


def log_loss_single(probability: float, outcome: int) -> float:
    p = clip_probability(probability)
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def brier_single(probability: float, outcome: int) -> float:
    return (probability - outcome) ** 2


def update_weights(
    weights: dict[str, float],
    model_probs: dict[str, float],
    outcome: int,
    learning_rate: float = 0.15,
    floor: float = 0.02,
) -> dict[str, float]:
    """Multiplicative-weights update from one settled prediction."""
    updated: dict[str, float] = {}
    for name, w in weights.items():
        if name in model_probs:
            loss = log_loss_single(model_probs[name], outcome)
            updated[name] = w * math.exp(-learning_rate * loss)
        else:
            updated[name] = w
    total = sum(updated.values()) or 1.0
    normalized = {k: max(v / total, floor) for k, v in updated.items()}
    renorm = sum(normalized.values())
    return {k: v / renorm for k, v in normalized.items()}


def blend(model_probs: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted logit-space blend — better calibrated than linear averaging."""
    num = 0.0
    den = 0.0
    for name, p in model_probs.items():
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        p = clip_probability(p)
        num += w * math.log(p / (1 - p))
        den += w
    if den == 0:
        return sum(model_probs.values()) / max(len(model_probs), 1)
    logit = num / den
    return 1.0 / (1.0 + math.exp(-logit))


def beta_shrink(rate: float, opportunities: float, prior_rate: float, prior_strength: float = 60.0) -> float:
    """Beta-binomial shrinkage: stabilizes small-sample player rates toward league prior."""
    alpha = prior_rate * prior_strength + rate * opportunities
    beta = (1 - prior_rate) * prior_strength + (1 - rate) * opportunities
    return alpha / (alpha + beta)
