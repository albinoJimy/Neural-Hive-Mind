# -*- coding: utf-8 -*-
"""
Calculadora de Tamanho de Amostra para testes A/B.

Fornece funcoes para calcular o tamanho de amostra necessario
para atingir significancia estatistica desejada.
"""

import math
from dataclasses import dataclass
from typing import Optional

from scipy import stats
import structlog

logger = structlog.get_logger()


@dataclass
class SampleSizeResult:
    """Resultado do calculo de tamanho de amostra."""
    sample_size_per_group: int
    total_sample_size: int
    mde: float  # Minimum Detectable Effect
    alpha: float
    power: float
    baseline_metric: float
    effect_type: str  # "absolute" ou "relative"


@dataclass
class DurationEstimate:
    """Estimativa de duracao do experimento."""
    estimated_days: float
    estimated_hours: float
    sample_size_per_group: int
    traffic_rate_per_hour: float
    traffic_split: float


class SampleSizeCalculator:
    """
    Calculadora de tamanho de amostra para testes A/B.

    Fornece calculos para:
    - Metricas continuas (latencia, tempo de resposta)
    - Metricas binarias (taxa de conversao, taxa de erro)
    - Estimativa de duracao baseada em trafego
    """

    @staticmethod
    def calculate_for_continuous(
        baseline_mean: float,
        mde: float,
        std_dev: float,
        alpha: float = 0.05,
        power: float = 0.80,
        one_sided: bool = False,
    ) -> SampleSizeResult:
        """
        Calcular tamanho de amostra para metrica continua.

        Usa formula para teste t de duas amostras:
        n = 2 * ((z_alpha + z_beta) * std_dev / mde)^2

        Args:
            baseline_mean: Media baseline (controle)
            mde: Minimum Detectable Effect (diferenca absoluta desejada)
            std_dev: Desvio padrao estimado
            alpha: Nivel de significancia (default 0.05)
            power: Power estatistico (1 - beta, default 0.80)
            one_sided: Teste unilateral (default False = bilateral)

        Returns:
            Resultado com tamanho de amostra por grupo
        """
        if mde <= 0:
            raise ValueError("MDE deve ser maior que zero")
        if std_dev <= 0:
            raise ValueError("Desvio padrao deve ser maior que zero")
        if not 0 < alpha < 1:
            raise ValueError("Alpha deve estar entre 0 e 1")
        if not 0 < power < 1:
            raise ValueError("Power deve estar entre 0 e 1")

        # Calcular z-scores
        if one_sided:
            z_alpha = stats.norm.ppf(1 - alpha)
        else:
            z_alpha = stats.norm.ppf(1 - alpha / 2)

        z_beta = stats.norm.ppf(power)

        # Formula do tamanho de amostra
        n = 2 * ((z_alpha + z_beta) * std_dev / mde) ** 2

        # Arredondar para cima
        n_per_group = int(math.ceil(n))

        logger.debug(
            "sample_size_calculated_continuous",
            baseline_mean=baseline_mean,
            mde=mde,
            std_dev=std_dev,
            alpha=alpha,
            power=power,
            n_per_group=n_per_group,
        )

        return SampleSizeResult(
            sample_size_per_group=n_per_group,
            total_sample_size=n_per_group * 2,
            mde=mde,
            alpha=alpha,
            power=power,
            baseline_metric=baseline_mean,
            effect_type="absolute",
        )

    @staticmethod
    def calculate_for_continuous_relative(
        baseline_mean: float,
        mde_percentage: float,
        std_dev: float,
        alpha: float = 0.05,
        power: float = 0.80,
        one_sided: bool = False,
    ) -> SampleSizeResult:
        """
        Calcular tamanho de amostra para metrica continua com MDE relativo.

        Args:
            baseline_mean: Media baseline (controle)
            mde_percentage: Melhoria minima desejada em porcentagem (ex: 0.05 = 5%)
            std_dev: Desvio padrao estimado
            alpha: Nivel de significancia
            power: Power estatistico

        Returns:
            Resultado com tamanho de amostra por grupo
        """
        # Converter MDE relativo para absoluto
        mde_absolute = baseline_mean * mde_percentage

        result = SampleSizeCalculator.calculate_for_continuous(
            baseline_mean=baseline_mean,
            mde=mde_absolute,
            std_dev=std_dev,
            alpha=alpha,
            power=power,
            one_sided=one_sided,
        )

        # Ajustar effect_type
        result.effect_type = "relative"

        return result

    @staticmethod
    def calculate_for_binary(
        baseline_rate: float,
        mde: float,
        alpha: float = 0.05,
        power: float = 0.80,
        one_sided: bool = False,
    ) -> SampleSizeResult:
        """
        Calcular tamanho de amostra para metrica binaria.

        Usa formula para diferenca de proporcoes:
        n = (z_alpha * sqrt(2*p_avg*(1-p_avg)) + z_beta * sqrt(p1*(1-p1) + p2*(1-p2)))^2 / (p2-p1)^2

        Args:
            baseline_rate: Taxa baseline (ex: 0.10 = 10%)
            mde: Minimum Detectable Effect como diferenca absoluta
                 (ex: se baseline=0.10 e mde=0.01, detecta mudanca para 0.11)
            alpha: Nivel de significancia
            power: Power estatistico

        Returns:
            Resultado com tamanho de amostra por grupo
        """
        if not 0 < baseline_rate < 1:
            raise ValueError("Baseline rate deve estar entre 0 e 1")
        if mde <= 0:
            raise ValueError("MDE deve ser maior que zero")

        p1 = baseline_rate
        p2 = baseline_rate + mde  # Taxa esperada no tratamento

        if p2 >= 1:
            p2 = 0.99  # Cap em 99%

        p_avg = (p1 + p2) / 2

        # Calcular z-scores
        if one_sided:
            z_alpha = stats.norm.ppf(1 - alpha)
        else:
            z_alpha = stats.norm.ppf(1 - alpha / 2)

        z_beta = stats.norm.ppf(power)

        # Formula de tamanho de amostra para proporcoes
        term1 = z_alpha * math.sqrt(2 * p_avg * (1 - p_avg))
        term2 = z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
        n = ((term1 + term2) ** 2) / ((p2 - p1) ** 2)

        n_per_group = int(math.ceil(n))

        logger.debug(
            "sample_size_calculated_binary",
            baseline_rate=baseline_rate,
            mde=mde,
            alpha=alpha,
            power=power,
            n_per_group=n_per_group,
        )

        return SampleSizeResult(
            sample_size_per_group=n_per_group,
            total_sample_size=n_per_group * 2,
            mde=mde,
            alpha=alpha,
            power=power,
            baseline_metric=baseline_rate,
            effect_type="absolute",
        )

    @staticmethod
    def calculate_for_binary_relative(
        baseline_rate: float,
        mde_percentage: float,
        alpha: float = 0.05,
        power: float = 0.80,
        one_sided: bool = False,
    ) -> SampleSizeResult:
        """
        Calcular tamanho de amostra para metrica binaria com MDE relativo.

        Args:
            baseline_rate: Taxa baseline (ex: 0.10 = 10%)
            mde_percentage: Melhoria minima desejada em porcentagem
                           (ex: 0.10 = 10% de melhoria, de 0.10 para 0.11)
            alpha: Nivel de significancia
            power: Power estatistico

        Returns:
            Resultado com tamanho de amostra por grupo
        """
        # Converter MDE relativo para absoluto
        mde_absolute = baseline_rate * mde_percentage

        result = SampleSizeCalculator.calculate_for_binary(
            baseline_rate=baseline_rate,
            mde=mde_absolute,
            alpha=alpha,
            power=power,
            one_sided=one_sided,
        )

        result.effect_type = "relative"

        return result

    @staticmethod
    def estimate_duration(
        sample_size_per_group: int,
        traffic_rate_per_hour: float,
        traffic_split: float = 0.5,
    ) -> DurationEstimate:
        """
        Estimar duracao do experimento baseado em trafego.

        Args:
            sample_size_per_group: Tamanho de amostra necessario por grupo
            traffic_rate_per_hour: Taxa de trafego por hora
            traffic_split: Proporcao de trafego para o experimento (0 a 1)

        Returns:
            Estimativa de duracao em dias e horas
        """
        if traffic_rate_per_hour <= 0:
            raise ValueError("Taxa de trafego deve ser maior que zero")
        if not 0 < traffic_split <= 1:
            raise ValueError("Traffic split deve estar entre 0 e 1")

        # Trafego efetivo para o experimento
        effective_rate = traffic_rate_per_hour * traffic_split

        # Total de amostras necessarias (ambos os grupos)
        total_samples = sample_size_per_group * 2

        # Horas necessarias
        hours_needed = total_samples / effective_rate

        # Dias necessarios
        days_needed = hours_needed / 24

        logger.debug(
            "duration_estimated",
            sample_size_per_group=sample_size_per_group,
            traffic_rate=traffic_rate_per_hour,
            traffic_split=traffic_split,
            estimated_hours=hours_needed,
            estimated_days=days_needed,
        )

        return DurationEstimate(
            estimated_days=days_needed,
            estimated_hours=hours_needed,
            sample_size_per_group=sample_size_per_group,
            traffic_rate_per_hour=traffic_rate_per_hour,
            traffic_split=traffic_split,
        )

    @staticmethod
    def validate_sample_size(
        current_sample: int,
        required_sample: int,
    ) -> dict:
        """
        Validar se amostra atual e suficiente.

        Args:
            current_sample: Tamanho atual da amostra
            required_sample: Tamanho necessario calculado

        Returns:
            Dict com is_sufficient e percentual completado
        """
        is_sufficient = current_sample >= required_sample
        percentage_complete = (current_sample / required_sample * 100) if required_sample > 0 else 0

        return {
            "is_sufficient": is_sufficient,
            "current_sample": current_sample,
            "required_sample": required_sample,
            "percentage_complete": min(percentage_complete, 100),
            "samples_remaining": max(0, required_sample - current_sample),
        }

    @staticmethod
    def recommend_mde(
        baseline_value: float,
        metric_type: str = "continuous",
        business_impact: str = "medium",
    ) -> dict:
        """
        Recomendar MDE baseado em valor baseline e impacto de negocio.

        Args:
            baseline_value: Valor baseline da metrica
            metric_type: "continuous" ou "binary"
            business_impact: "low", "medium", "high"

        Returns:
            Dict com MDE recomendado e justificativa
        """
        # Tabela de MDEs recomendados por impacto
        impact_factors = {
            "low": 0.02,     # 2% de melhoria
            "medium": 0.05,  # 5% de melhoria
            "high": 0.10,    # 10% de melhoria
        }

        factor = impact_factors.get(business_impact, 0.05)

        if metric_type == "continuous":
            mde_absolute = baseline_value * factor
            mde_relative = factor
        else:  # binary
            mde_absolute = baseline_value * factor
            mde_relative = factor

        return {
            "mde_absolute": mde_absolute,
            "mde_relative": mde_relative,
            "baseline": baseline_value,
            "business_impact": business_impact,
            "justification": f"MDE de {factor*100:.0f}% para impacto {business_impact}",
        }
