"""Trainable model zoo: Random Forest, XGBoost, LightGBM, CatBoost, neural net,
stacking meta-learner and an online SGD learner. Gradient-boosting libraries are
optional at runtime — if an import fails the zoo substitutes sklearn's
GradientBoosting so the engine keeps producing all model votes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from xgboost import XGBClassifier

    HAS_XGB = True
except ImportError:  # pragma: no cover
    HAS_XGB = False

try:
    from lightgbm import LGBMClassifier

    HAS_LGBM = True
except ImportError:  # pragma: no cover
    HAS_LGBM = False

try:
    from catboost import CatBoostClassifier

    HAS_CATBOOST = True
except ImportError:  # pragma: no cover
    HAS_CATBOOST = False

MODEL_NAMES = [
    "random_forest",
    "xgboost",
    "lightgbm",
    "catboost",
    "neural_net",
    "online_sgd",
    "elo",
    "monte_carlo",
]
TRAINABLE = ["random_forest", "xgboost", "lightgbm", "catboost", "neural_net", "online_sgd"]
MIN_TRAIN_SAMPLES = 120


class Classifier(Protocol):  # pragma: no cover - typing only
    def fit(self, X: Any, y: Any) -> Any: ...
    def predict_proba(self, X: Any) -> Any: ...


def _build_estimators() -> dict[str, Classifier]:
    zoo: dict[str, Classifier] = {
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=5, n_jobs=-1),
        "neural_net": MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=600, early_stopping=True),
        "online_sgd": SGDClassifier(loss="log_loss", alpha=1e-4, warm_start=True),
    }
    zoo["xgboost"] = (
        XGBClassifier(n_estimators=350, max_depth=5, learning_rate=0.05, subsample=0.85,
                      colsample_bytree=0.85, eval_metric="logloss")
        if HAS_XGB
        else GradientBoostingClassifier(n_estimators=300, max_depth=4, learning_rate=0.05)
    )
    zoo["lightgbm"] = (
        LGBMClassifier(n_estimators=400, num_leaves=31, learning_rate=0.05, subsample=0.85, verbose=-1)
        if HAS_LGBM
        else GradientBoostingClassifier(n_estimators=350, max_depth=3, learning_rate=0.06)
    )
    zoo["catboost"] = (
        CatBoostClassifier(iterations=400, depth=5, learning_rate=0.05, verbose=False, allow_writing_files=False)
        if HAS_CATBOOST
        else GradientBoostingClassifier(n_estimators=250, max_depth=5, learning_rate=0.04)
    )
    return zoo


class MarketModelBundle:
    """All trainable models + scaler + stacking meta-learner for one market family."""

    def __init__(self, market_family: str) -> None:
        self.market_family = market_family
        self.scaler = StandardScaler()
        self.estimators = _build_estimators()
        self.meta = LogisticRegression(max_iter=500)
        self.feature_names: list[str] = []
        self.trained = False
        self.train_samples = 0

    # ── training ────────────────────────────────────────────────────────────
    def fit(self, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> dict[str, float]:
        if len(y) < MIN_TRAIN_SAMPLES or len(np.unique(y)) < 2:
            logger.info("skipping training: not enough samples", extra={"market": self.market_family, "n": len(y)})
            return {}
        self.feature_names = feature_names
        Xs = self.scaler.fit_transform(X)
        base_preds = np.zeros((len(y), len(TRAINABLE)))
        scores: dict[str, float] = {}
        split = int(len(y) * 0.8)
        for i, name in enumerate(TRAINABLE):
            est = self.estimators[name]
            est.fit(Xs[:split], y[:split])
            holdout = est.predict_proba(Xs[split:])[:, 1]
            eps = 1e-6
            ll = float(-np.mean(y[split:] * np.log(holdout + eps) + (1 - y[split:]) * np.log(1 - holdout + eps)))
            scores[name] = ll
            est.fit(Xs, y)  # refit on all data after scoring
            base_preds[:, i] = est.predict_proba(Xs)[:, 1]
        self.meta.fit(base_preds, y)
        self.trained = True
        self.train_samples = len(y)
        return scores

    def partial_fit_online(self, X: np.ndarray, y: np.ndarray) -> None:
        """Daily online update for the SGD member without full retraining."""
        if not self.trained:
            return
        Xs = self.scaler.transform(X)
        sgd: SGDClassifier = self.estimators["online_sgd"]  # type: ignore[assignment]
        sgd.partial_fit(Xs, y, classes=np.array([0, 1]))

    # ── inference ───────────────────────────────────────────────────────────
    def predict_members(self, x: np.ndarray) -> dict[str, float]:
        """Per-model probability votes for one feature vector."""
        if not self.trained:
            return {}
        Xs = self.scaler.transform(x.reshape(1, -1))
        votes: dict[str, float] = {}
        for name in TRAINABLE:
            try:
                votes[name] = float(self.estimators[name].predict_proba(Xs)[0, 1])
            except Exception:  # noqa: BLE001 — a failed member must not kill the vote
                continue
        return votes

    def predict_stacked(self, member_votes: dict[str, float]) -> float | None:
        if not self.trained or len(member_votes) < len(TRAINABLE):
            return None
        ordered = np.array([[member_votes[n] for n in TRAINABLE]])
        return float(self.meta.predict_proba(ordered)[0, 1])

    # ── persistence ─────────────────────────────────────────────────────────
    def _path(self) -> Path:
        store = Path(settings.MODELS_STORE_DIR)
        store.mkdir(parents=True, exist_ok=True)
        return store / f"bundle_{self.market_family}.joblib"

    def save(self) -> None:
        joblib.dump(
            {
                "scaler": self.scaler,
                "estimators": self.estimators,
                "meta": self.meta,
                "feature_names": self.feature_names,
                "trained": self.trained,
                "train_samples": self.train_samples,
            },
            self._path(),
        )

    def load(self) -> bool:
        path = self._path()
        if not os.path.exists(path):
            return False
        try:
            data = joblib.load(path)
            self.scaler = data["scaler"]
            self.estimators = data["estimators"]
            self.meta = data["meta"]
            self.feature_names = data["feature_names"]
            self.trained = data["trained"]
            self.train_samples = data.get("train_samples", 0)
            return True
        except Exception:  # noqa: BLE001 — corrupted artifact ⇒ retrain from scratch
            logger.warning("failed loading model bundle", extra={"market": self.market_family})
            return False
