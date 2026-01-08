# -*- coding: utf-8 -*-
"""
Modulo de Analise Estatistica para testes A/B.

Implementa testes estatisticos para validacao de experimentos:
- t-test para dados normais
- Mann-Whitney U para dados nao-normais
- Chi-square para metricas binarias
- Analise Bayesiana com priors informativos
- Intervalos de confianca via bootstrap
- Correcao para testes multiplos
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from scipy.stats import shapiro, ttest_ind, mannwhitneyu, chi2_contingency

import structlog

logger = structlog.get_logger()


@dataclass
class ContinuousMetricResult:
    """Resultado de analise para metrica continua."""
    metric_name: str
    test_used: str
    p_value: float
    statistically_significant: bool
    effect_size: float  # Cohen's d
    effect_size_interpretation: str  # small, medium, large
    control_mean: float
    treatment_mean: float
    control_std: float
    treatment_std: float
    confidence_interval_95: Tuple[float, float]
    sample_size_control: int
    sample_size_treatment: int
    normality_test_control_p: float
    normality_test_treatment_p: float


@dataclass
class BinaryMetricResult:
    """Resultado de analise para metrica binaria."""
    metric_name: str
    p_value: float
    statistically_significant: bool
    relative_risk: float
    odds_ratio: float
    control_rate: float
    treatment_rate: float
    control_successes: int
    control_total: int
    treatment_successes: int
    treatment_total: int
    confidence_interval_95: Tuple[float, float]


@dataclass
class BayesianResult:
    """Resultado de analise Bayesiana."""
    metric_name: str
    posterior_mean_control: float
    posterior_mean_treatment: float
    posterior_std_control: float
    posterior_std_treatment: float
    credible_interval_95_control: Tuple[float, float]
    credible_interval_95_treatment: Tuple[float, float]
    probability_of_superiority: float  # P(treatment > control)
    expected_lift: float  # (treatment - control) / control


class StatisticalAnalyzer:
    """
    Analisador estatistico para testes A/B.

    Fornece analise frequentista e Bayesiana para metricas
    continuas e binarias.
    """

    def __init__(self, alpha: float = 0.05):
        """
        Inicializar analisador.

        Args:
            alpha: Nivel de significancia (default 0.05)
        """
        self.alpha = alpha

    def analyze_continuous_metric(
        self,
        control_data: List[float],
        treatment_data: List[float],
        metric_name: str = "metric",
    ) -> ContinuousMetricResult:
        """
        Analisar metrica continua.

        Verifica normalidade e escolhe teste apropriado:
        - Se normal: t-test independente
        - Se nao-normal: Mann-Whitney U test

        Args:
            control_data: Dados do grupo controle
            treatment_data: Dados do grupo tratamento
            metric_name: Nome da metrica

        Returns:
            Resultado com p-value, effect size e interpretacao
        """
        control_arr = np.array(control_data)
        treatment_arr = np.array(treatment_data)

        # Calcular estatisticas descritivas
        control_mean = float(np.mean(control_arr))
        treatment_mean = float(np.mean(treatment_arr))
        control_std = float(np.std(control_arr, ddof=1)) if len(control_arr) > 1 else 0.0
        treatment_std = float(np.std(treatment_arr, ddof=1)) if len(treatment_arr) > 1 else 0.0

        # Testar normalidade (Shapiro-Wilk)
        # Shapiro requer n >= 3
        normality_p_control = 0.0
        normality_p_treatment = 0.0

        if len(control_arr) >= 3:
            try:
                _, normality_p_control = shapiro(control_arr[:5000])  # Limite Shapiro
            except Exception:
                normality_p_control = 0.0

        if len(treatment_arr) >= 3:
            try:
                _, normality_p_treatment = shapiro(treatment_arr[:5000])
            except Exception:
                normality_p_treatment = 0.0

        # Verificar se ambos sao normais (p > 0.05)
        is_normal = (normality_p_control > 0.05) and (normality_p_treatment > 0.05)

        # Escolher teste apropriado
        if is_normal:
            # t-test independente
            stat, p_value = ttest_ind(control_arr, treatment_arr, equal_var=False)
            test_used = "welch_t_test"
        else:
            # Mann-Whitney U test (nao-parametrico)
            try:
                stat, p_value = mannwhitneyu(
                    control_arr, treatment_arr, alternative="two-sided"
                )
                test_used = "mann_whitney_u"
            except Exception:
                # Fallback para t-test se Mann-Whitney falhar
                stat, p_value = ttest_ind(control_arr, treatment_arr, equal_var=False)
                test_used = "welch_t_test_fallback"

        # Calcular effect size (Cohen's d)
        pooled_std = self._pooled_std(control_arr, treatment_arr)
        if pooled_std > 0:
            cohens_d = (treatment_mean - control_mean) / pooled_std
        else:
            cohens_d = 0.0

        effect_interpretation = self._interpret_cohens_d(cohens_d)

        # Intervalo de confianca para diferenca de medias
        ci_lower, ci_upper = self._confidence_interval_difference(
            control_arr, treatment_arr
        )

        return ContinuousMetricResult(
            metric_name=metric_name,
            test_used=test_used,
            p_value=float(p_value),
            statistically_significant=p_value < self.alpha,
            effect_size=float(cohens_d),
            effect_size_interpretation=effect_interpretation,
            control_mean=control_mean,
            treatment_mean=treatment_mean,
            control_std=control_std,
            treatment_std=treatment_std,
            confidence_interval_95=(ci_lower, ci_upper),
            sample_size_control=len(control_arr),
            sample_size_treatment=len(treatment_arr),
            normality_test_control_p=float(normality_p_control),
            normality_test_treatment_p=float(normality_p_treatment),
        )

    def analyze_binary_metric(
        self,
        control_successes: int,
        control_total: int,
        treatment_successes: int,
        treatment_total: int,
        metric_name: str = "conversion",
    ) -> BinaryMetricResult:
        """
        Analisar metrica binaria usando chi-square test.

        Args:
            control_successes: Numero de sucessos no controle
            control_total: Total de observacoes no controle
            treatment_successes: Numero de sucessos no tratamento
            treatment_total: Total de observacoes no tratamento
            metric_name: Nome da metrica

        Returns:
            Resultado com p-value, relative risk e odds ratio
        """
        # Construir tabela de contingencia
        control_failures = control_total - control_successes
        treatment_failures = treatment_total - treatment_successes

        contingency_table = [
            [control_successes, control_failures],
            [treatment_successes, treatment_failures],
        ]

        # Chi-square test
        try:
            chi2, p_value, dof, expected = chi2_contingency(contingency_table)
        except Exception:
            p_value = 1.0

        # Calcular taxas
        control_rate = control_successes / control_total if control_total > 0 else 0.0
        treatment_rate = treatment_successes / treatment_total if treatment_total > 0 else 0.0

        # Relative Risk (RR)
        if control_rate > 0:
            relative_risk = treatment_rate / control_rate
        else:
            relative_risk = float("inf") if treatment_rate > 0 else 1.0

        # Odds Ratio (OR)
        odds_control = control_successes / control_failures if control_failures > 0 else float("inf")
        odds_treatment = treatment_successes / treatment_failures if treatment_failures > 0 else float("inf")

        if odds_control > 0 and odds_control != float("inf"):
            odds_ratio = odds_treatment / odds_control
        else:
            odds_ratio = float("inf") if odds_treatment > 0 else 1.0

        # Intervalo de confianca para diferenca de proporcoes
        ci_lower, ci_upper = self._proportion_ci(
            control_rate, control_total, treatment_rate, treatment_total
        )

        return BinaryMetricResult(
            metric_name=metric_name,
            p_value=float(p_value),
            statistically_significant=p_value < self.alpha,
            relative_risk=float(relative_risk) if not math.isinf(relative_risk) else 999.0,
            odds_ratio=float(odds_ratio) if not math.isinf(odds_ratio) else 999.0,
            control_rate=float(control_rate),
            treatment_rate=float(treatment_rate),
            control_successes=control_successes,
            control_total=control_total,
            treatment_successes=treatment_successes,
            treatment_total=treatment_total,
            confidence_interval_95=(ci_lower, ci_upper),
        )

    def bayesian_analysis(
        self,
        control_data: List[float],
        treatment_data: List[float],
        metric_name: str = "metric",
        prior_mean: float = 0.0,
        prior_std: float = 1.0,
    ) -> BayesianResult:
        """
        Analise Bayesiana com priors informativos.

        Usa conjugate priors (Normal-Normal) para calcular:
        - Distribuicoes posteriores
        - Intervalos de credibilidade 95%
        - Probabilidade de superioridade do tratamento

        Args:
            control_data: Dados do grupo controle
            treatment_data: Dados do grupo tratamento
            metric_name: Nome da metrica
            prior_mean: Media do prior
            prior_std: Desvio padrao do prior

        Returns:
            Resultado Bayesiano com probabilidade de superioridade
        """
        control_arr = np.array(control_data)
        treatment_arr = np.array(treatment_data)

        # Calcular posterior para controle
        posterior_control = self._calculate_posterior(
            control_arr, prior_mean, prior_std
        )

        # Calcular posterior para tratamento
        posterior_treatment = self._calculate_posterior(
            treatment_arr, prior_mean, prior_std
        )

        # Calcular probabilidade de superioridade via Monte Carlo
        n_samples = 10000
        samples_control = np.random.normal(
            posterior_control["mean"],
            posterior_control["std"],
            n_samples,
        )
        samples_treatment = np.random.normal(
            posterior_treatment["mean"],
            posterior_treatment["std"],
            n_samples,
        )

        probability_of_superiority = float(np.mean(samples_treatment > samples_control))

        # Expected lift
        if posterior_control["mean"] != 0:
            expected_lift = (
                (posterior_treatment["mean"] - posterior_control["mean"])
                / abs(posterior_control["mean"])
            )
        else:
            expected_lift = 0.0

        return BayesianResult(
            metric_name=metric_name,
            posterior_mean_control=posterior_control["mean"],
            posterior_mean_treatment=posterior_treatment["mean"],
            posterior_std_control=posterior_control["std"],
            posterior_std_treatment=posterior_treatment["std"],
            credible_interval_95_control=posterior_control["ci_95"],
            credible_interval_95_treatment=posterior_treatment["ci_95"],
            probability_of_superiority=probability_of_superiority,
            expected_lift=float(expected_lift),
        )

    def calculate_confidence_intervals(
        self,
        data: List[float],
        confidence_level: float = 0.95,
        n_bootstrap: int = 1000,
    ) -> Tuple[float, float]:
        """
        Calcular intervalos de confianca via bootstrap.

        Util para metricas nao-parametricas onde
        suposicoes normais nao se aplicam.

        Args:
            data: Dados para calcular CI
            confidence_level: Nivel de confianca (default 0.95)
            n_bootstrap: Numero de amostras bootstrap

        Returns:
            Tuple com (lower_bound, upper_bound)
        """
        data_arr = np.array(data)

        if len(data_arr) < 2:
            mean = float(np.mean(data_arr)) if len(data_arr) > 0 else 0.0
            return (mean, mean)

        # Bootstrap
        bootstrap_means = []
        for _ in range(n_bootstrap):
            sample = np.random.choice(data_arr, size=len(data_arr), replace=True)
            bootstrap_means.append(np.mean(sample))

        bootstrap_means = np.array(bootstrap_means)

        # Percentis
        alpha = 1 - confidence_level
        lower = float(np.percentile(bootstrap_means, (alpha / 2) * 100))
        upper = float(np.percentile(bootstrap_means, (1 - alpha / 2) * 100))

        return (lower, upper)

    def multiple_testing_correction(
        self,
        p_values: List[float],
        method: str = "bonferroni",
    ) -> List[float]:
        """
        Aplicar correcao para testes multiplos.

        Args:
            p_values: Lista de p-values
            method: Metodo de correcao ("bonferroni" ou "benjamini_hochberg")

        Returns:
            Lista de p-values corrigidos
        """
        if not p_values:
            return []

        try:
            from statsmodels.stats.multitest import multipletests

            rejected, corrected_pvals, _, _ = multipletests(
                p_values, alpha=self.alpha, method="bonferroni" if method == "bonferroni" else "fdr_bh"
            )
            return list(corrected_pvals)
        except ImportError:
            # Fallback para correcao manual de Bonferroni
            n = len(p_values)
            return [min(p * n, 1.0) for p in p_values]

    # Metodos auxiliares

    def _pooled_std(self, arr1: np.ndarray, arr2: np.ndarray) -> float:
        """Calcular desvio padrao pooled."""
        n1, n2 = len(arr1), len(arr2)
        if n1 + n2 <= 2:
            return 0.0

        var1 = np.var(arr1, ddof=1) if n1 > 1 else 0.0
        var2 = np.var(arr2, ddof=1) if n2 > 1 else 0.0

        pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
        return float(np.sqrt(pooled_var))

    def _interpret_cohens_d(self, d: float) -> str:
        """Interpretar Cohen's d."""
        d_abs = abs(d)
        if d_abs < 0.2:
            return "negligible"
        elif d_abs < 0.5:
            return "small"
        elif d_abs < 0.8:
            return "medium"
        else:
            return "large"

    def _confidence_interval_difference(
        self,
        arr1: np.ndarray,
        arr2: np.ndarray,
        confidence: float = 0.95,
    ) -> Tuple[float, float]:
        """Calcular CI para diferenca de medias."""
        mean_diff = float(np.mean(arr2) - np.mean(arr1))

        n1, n2 = len(arr1), len(arr2)
        if n1 < 2 or n2 < 2:
            return (mean_diff, mean_diff)

        se1 = np.std(arr1, ddof=1) / np.sqrt(n1)
        se2 = np.std(arr2, ddof=1) / np.sqrt(n2)
        se_diff = np.sqrt(se1**2 + se2**2)

        # t-critico
        df = n1 + n2 - 2
        t_crit = stats.t.ppf((1 + confidence) / 2, df)

        margin = t_crit * se_diff

        return (float(mean_diff - margin), float(mean_diff + margin))

    def _proportion_ci(
        self,
        p1: float,
        n1: int,
        p2: float,
        n2: int,
        confidence: float = 0.95,
    ) -> Tuple[float, float]:
        """Calcular CI para diferenca de proporcoes."""
        diff = p2 - p1

        if n1 == 0 or n2 == 0:
            return (diff, diff)

        se = np.sqrt((p1 * (1 - p1) / n1) + (p2 * (1 - p2) / n2))
        z = stats.norm.ppf((1 + confidence) / 2)
        margin = z * se

        return (float(diff - margin), float(diff + margin))

    def _calculate_posterior(
        self,
        data: np.ndarray,
        prior_mean: float,
        prior_std: float,
    ) -> Dict:
        """Calcular distribuicao posterior (Normal-Normal conjugate)."""
        n = len(data)
        if n == 0:
            return {
                "mean": prior_mean,
                "std": prior_std,
                "ci_95": (
                    prior_mean - 1.96 * prior_std,
                    prior_mean + 1.96 * prior_std,
                ),
            }

        data_mean = float(np.mean(data))
        data_std = float(np.std(data, ddof=1)) if n > 1 else prior_std

        # Precisoes
        prior_precision = 1 / (prior_std ** 2) if prior_std > 0 else 0.01
        data_precision = n / (data_std ** 2) if data_std > 0 else 0.01

        # Posterior
        posterior_precision = prior_precision + data_precision
        posterior_mean = (
            (prior_precision * prior_mean + data_precision * data_mean)
            / posterior_precision
        )
        posterior_std = 1 / np.sqrt(posterior_precision)

        # Intervalo de credibilidade 95%
        ci_lower = posterior_mean - 1.96 * posterior_std
        ci_upper = posterior_mean + 1.96 * posterior_std

        return {
            "mean": float(posterior_mean),
            "std": float(posterior_std),
            "ci_95": (float(ci_lower), float(ci_upper)),
        }
