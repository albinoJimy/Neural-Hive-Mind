"""
Unit tests para a filtragem de outliers de duração (Task 9 da spec
caminho-real-first-class).

Durações anómalas (timeouts, 300s sobre mediana de ~3s) destroem o R² do
DurationPredictor — em dados reais R²=-37 com outliers vs ~0.6 sem. A filtragem
IQR é aplicada no train_model antes do split.
"""

import numpy as np
from src.ml.duration_predictor import DurationPredictor


class TestFilterDurationOutliers:
    def test_removes_extreme_outliers(self):
        # 40 durações ~3s + 3 outliers extremos (300s)
        y = np.array([3000.0] * 20 + [4000.0] * 20 + [300000.0, 305000.0, 310000.0])
        X = np.arange(len(y)).reshape(-1, 1).astype(float)
        Xf, yf, removed = DurationPredictor._filter_duration_outliers(X, y, 3.0)
        assert removed == 3
        assert yf.max() < 300000.0
        assert len(Xf) == len(yf) == len(y) - 3

    def test_disabled_when_multiplier_zero(self):
        y = np.array([1.0, 2.0, 3.0, 1000000.0])
        X = np.arange(4).reshape(-1, 1).astype(float)
        Xf, yf, removed = DurationPredictor._filter_duration_outliers(X, y, 0.0)
        assert removed == 0
        assert len(yf) == 4

    def test_no_filter_below_four_samples(self):
        y = np.array([1.0, 2.0, 9999.0])
        X = np.arange(3).reshape(-1, 1).astype(float)
        _, yf, removed = DurationPredictor._filter_duration_outliers(X, y, 3.0)
        assert removed == 0
        assert len(yf) == 3

    def test_no_filter_when_iqr_zero(self):
        # todas iguais → IQR=0 → não filtra
        y = np.array([5000.0] * 10)
        X = np.arange(10).reshape(-1, 1).astype(float)
        _, yf, removed = DurationPredictor._filter_duration_outliers(X, y, 3.0)
        assert removed == 0
        assert len(yf) == 10

    def test_safeguard_does_not_remove_majority(self):
        # distribuição bimodal extrema: não deve esvaziar o dataset
        y = np.array([1.0] * 10 + [100000.0] * 10)
        X = np.arange(20).reshape(-1, 1).astype(float)
        _, yf, removed = DurationPredictor._filter_duration_outliers(X, y, 0.1)
        # mantém pelo menos metade
        assert len(yf) >= 10
