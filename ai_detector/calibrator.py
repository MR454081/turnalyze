"""
Calibration utilities for AI detector probabilities.

Supports Platt scaling (logistic calibration) and simple
temperature scaling. Saves/loads calibration objects via joblib.
"""
import os
import json
import joblib
import numpy as np
from typing import Optional, Tuple


def fit_platt_scaling(
    val_logits: np.ndarray,
    val_labels: np.ndarray,
) -> "LogisticCalibrator":
    """
    Fit Platt scaling on validation logits.

    Parameters
    ----------
    val_logits : np.ndarray
        Raw logits from the validation set (before softmax).
    val_labels : np.ndarray
        Binary labels (0=human, 1=AI).

    Returns
    -------
    LogisticCalibrator
        Fitted calibrator.
    """
    calibrator = LogisticCalibrator()
    calibrator.fit(val_logits, val_labels)
    return calibrator


class LogisticCalibrator:
    """
    Platt scaling / logistic calibration for binary classifiers.

    Maps raw model logits through a logistic regression
    with a single feature (the raw logit).
    """

    def __init__(self):
        self.a = 1.0
        self.b = 0.0
        self.fitted = False

    def fit(self, logits: np.ndarray, labels: np.ndarray):
        """
        Fit calibration parameters on raw logits.

        Uses scikit-learn's LogisticRegression with a single
        feature (the raw logit).
        """
        from sklearn.linear_model import LogisticRegression

        logits = np.asarray(logits, dtype=np.float64).reshape(-1, 1)
        labels = np.asarray(labels, dtype=np.int64)

        lr = LogisticRegression(C=1.0, solver="lbfgs")
        lr.fit(logits, labels)

        self.a = float(lr.coef_[0][0])
        self.b = float(lr.intercept_[0])
        self.fitted = True
        return self

    def transform(self, logits: np.ndarray) -> np.ndarray:
        """
        Apply calibration to raw logits.

        Returns calibrated probabilities in [0, 1].
        """
        if not self.fitted:
            return 1.0 / (1.0 + np.exp(-np.asarray(logits, dtype=np.float64)))

        logits = np.asarray(logits, dtype=np.float64).reshape(-1, 1)
        calibrated_logits = self.a * logits + self.b
        calibrated = 1.0 / (1.0 + np.exp(-calibrated_logits))
        return np.clip(calibrated, 0.0, 1.0).flatten()

    def save(self, path: str):
        """Save calibrator to disk."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {"a": self.a, "b": self.b, "fitted": self.fitted}
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> Optional["LogisticCalibrator"]:
        """Load calibrator from disk."""
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        cal = cls()
        cal.a = float(data.get("a", 1.0))
        cal.b = float(data.get("b", 0.0))
        cal.fitted = bool(data.get("fitted", False))
        return cal
