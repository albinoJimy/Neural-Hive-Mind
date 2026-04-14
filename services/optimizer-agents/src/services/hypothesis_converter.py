"""Conversor de OptimizationHypothesis para HypothesisCreate do hypothesis-library."""

from typing import Any

import structlog

from src.models.optimization_hypothesis import OptimizationHypothesis

# Importar HypothesisPriority para validacao
try:
    from services.hypothesis_library.src.models.hypothesis import HypothesisPriority
except ImportError:
    # Fallback para quando hypothesis-library nao esta no path
    from enum import Enum

    class _HypothesisPriority(str, Enum):  # noqa: UP042 (kept for Python 3.12 compat)
        """Niveis de prioridade (fallback)."""

        CRITICAL = "CRITICAL"
        HIGH = "HIGH"
        MEDIUM = "MEDIUM"
        LOW = "LOW"

    HypothesisPriority = _HypothesisPriority  # type: ignore[misc,assignment]


logger = structlog.get_logger()


class HypothesisConverter:
    """
    Conversor de hipoteses de otimizacao para o formato do hypothesis-library.

    Responsavel por transformar objetos OptimizationHypothesis do optimizer-agents
    em dicionarios compativeis com o schema HypothesisCreate do hypothesis-library,
    permitindo a integracao entre os dois servicos.
    """

    # Mapeamento de prioridade (optimizer: 1-5 int → hypothesis-library: CRITICAL/.../LOW)
    PRIORITY_MAPPING = {
        1: HypothesisPriority.CRITICAL,
        2: HypothesisPriority.HIGH,
        3: HypothesisPriority.MEDIUM,
        4: HypothesisPriority.LOW,
        5: HypothesisPriority.LOW,
    }

    # Comprimento maximo para o campo title (200 caracteres)
    MAX_TITLE_LENGTH = 200

    # Autor padrao para hipoteses geradas automaticamente
    DEFAULT_AUTHOR = "optimizer-agents"

    def __init__(self, default_author: str | None = None):
        """
        Inicializar conversor.

        Args:
            default_author: Autor padrao para hipoteses (default: "optimizer-agents")
        """
        self.default_author = default_author or self.DEFAULT_AUTHOR
        logger.info("hypothesis_converter_initialized", default_author=self.default_author)

    def to_hypothesis_create(self, hypothesis: OptimizationHypothesis) -> dict[str, Any]:
        """
        Converter OptimizationHypothesis para dicionario compativel com HypothesisCreate.

        Args:
            hypothesis: Hipotese de otimizacao a ser convertida

        Returns:
            Dicionario com campos compativeis com HypothesisCreate do hypothesis-library

        Raises:
            ValueError: Se campos obrigatorios estiverem invalidos
        """
        try:
            # Validar campos obrigatorios
            self._validate_hypothesis(hypothesis)

            # Extrair metricas (uniao de baseline e target metrics)
            metrics = self._map_metrics(hypothesis)

            # Mapear prioridade
            priority = self._map_priority(hypothesis.priority)

            # Gerar titulo com limite de caracteres
            title = self._generate_title(hypothesis)

            # Gerar descricao detalhada
            description = self._generate_description(hypothesis)

            # Gerar background/contexto
            background = self._generate_background(hypothesis)

            # Gerar expected outcome
            expected_outcome = self._generate_expected_outcome(hypothesis)

            # Gerar tags (incluir tipo de otimizacao)
            tags = self._generate_tags(hypothesis)

            # Enriquecer metadata com informacoes do optimizer
            enriched_metadata = self._enrich_metadata(hypothesis)

            hypothesis_create = {
                "title": title,
                "description": description,
                "background": background,
                "expected_outcome": expected_outcome,
                "metrics": metrics,
                "baseline_metrics": hypothesis.baseline_metrics,
                "target_metrics": hypothesis.target_metrics,
                "priority": (
                    priority.value if isinstance(priority, HypothesisPriority) else priority
                ),
                "author": self.default_author,
                "reviewers": [],  # Hipoteses automaticas nao tem revisores iniciais
                "tags": tags,
                "requires_experiment": hypothesis.requires_experiment,
                "auto_approve": False,  # Hipoteses automaticas requerem revisao
                "metadata": enriched_metadata,
            }

            logger.info(
                "hypothesis_converted",
                hypothesis_id=hypothesis.hypothesis_id,
                title=title[:50],
                priority=priority,
                metrics_count=len(metrics),
            )

            return hypothesis_create

        except Exception as e:
            logger.error(
                "hypothesis_conversion_failed",
                hypothesis_id=hypothesis.hypothesis_id,
                error=str(e),
            )
            raise ValueError(f"Failed to convert hypothesis: {str(e)}") from e

    def _validate_hypothesis(self, hypothesis: OptimizationHypothesis) -> None:
        """
        Validar campos obrigatorios da hipotese.

        Args:
            hypothesis: Hipotese a ser validada

        Raises:
            ValueError: Se campos obrigatorios estiverem ausentes ou invalidos
        """
        if not hypothesis.hypothesis_text or not hypothesis.hypothesis_text.strip():
            raise ValueError("hypothesis_text is required and cannot be empty")

        if not hypothesis.target_component or not hypothesis.target_component.strip():
            raise ValueError("target_component is required")

        if not hypothesis.baseline_metrics:
            raise ValueError("baseline_metrics is required")

        if not hypothesis.target_metrics:
            raise ValueError("target_metrics is required")

        if not 1 <= hypothesis.priority <= 5:
            raise ValueError("priority must be between 1 and 5")

    def _map_priority(self, optimizer_priority: int) -> str | HypothesisPriority:
        """
        Mapear prioridade do optimizer para prioridade do hypothesis-library.

        Args:
            optimizer_priority: Prioridade do optimizer (1-5, onde 1 e a maior)

        Returns:
            HypothesisPriority correspondente (CRITICAL, HIGH, MEDIUM, LOW)

        Raises:
            ValueError: Se prioridade estiver fora do range valido
        """
        if optimizer_priority not in self.PRIORITY_MAPPING:
            logger.warning(
                "invalid_priority_falling_back_to_medium",
                priority=optimizer_priority,
            )
            return HypothesisPriority.MEDIUM

        return self.PRIORITY_MAPPING[optimizer_priority]

    def _map_metrics(self, hypothesis: OptimizationHypothesis) -> list[str]:
        """
        Extrair lista de metricas unicas de baseline e target.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Lista de nomes de metricas (sem duplicatas)
        """
        baseline_keys = set(hypothesis.baseline_metrics.keys())
        target_keys = set(hypothesis.target_metrics.keys())

        # Uniao de todas as metricas mencionadas
        all_metrics = sorted(baseline_keys | target_keys)

        logger.debug(
            "metrics_mapped",
            hypothesis_id=hypothesis.hypothesis_id,
            metrics_count=len(all_metrics),
        )

        return all_metrics

    def _generate_title(self, hypothesis: OptimizationHypothesis) -> str:
        """
        Gerar titulo para hipotese com limite de caracteres.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Titulo truncado para MAX_TITLE_LENGTH caracteres
        """
        # Formato: "[Tipo] Componente: Resumo da hipotese"
        optimization_type_label = hypothesis.optimization_type.value.replace("_", " ").title()

        title = f"[{optimization_type_label}] {hypothesis.target_component}: {hypothesis.hypothesis_text}"

        # Truncar se necessario
        if len(title) > self.MAX_TITLE_LENGTH:
            title = title[: self.MAX_TITLE_LENGTH - 3] + "..."

        return title

    def _generate_description(self, hypothesis: OptimizationHypothesis) -> str:
        """
        Gerar descricao detalhada da hipotese.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Descricao detalhada com informacoes sobre ajustes propostos
        """
        description_parts = [
            f"**Tipo de Otimizacao:** {hypothesis.optimization_type.value}",
            f"**Componente Alvo:** {hypothesis.target_component}",
            "",
            "**Ajustes Propostos:**",
        ]

        for adj in hypothesis.proposed_adjustments:
            description_parts.append(f"- {adj.parameter_name}: {adj.old_value} → {adj.new_value}")
            if adj.justification:
                description_parts.append(f"  Justificativa: {adj.justification}")

        # Adicionar informacoes de confianca e risco
        description_parts.extend(
            [
                "",
                f"**Melhoria Esperada:** {hypothesis.expected_improvement:.1%}",
                f"**Confianca:** {hypothesis.confidence_score:.1%}",
                f"**Risco:** {hypothesis.risk_score:.1%}",
            ]
        )

        # Adicionar evidencia causal se disponivel
        if hypothesis.causal_evidence:
            description_parts.extend(
                [
                    "",
                    "**Analise Causal:**",
                    f"- Metodo: {hypothesis.causal_evidence.method}",
                ]
            )
            if hypothesis.causal_evidence.root_cause:
                description_parts.append(f"- Causa Raiz: {hypothesis.causal_evidence.root_cause}")
            if hypothesis.causal_evidence.contributing_factors:
                description_parts.append(
                    f"- Fatores Contribuintes: {', '.join(hypothesis.causal_evidence.contributing_factors)}"
                )

        return "\n".join(description_parts)

    def _generate_background(self, hypothesis: OptimizationHypothesis) -> str:
        """
        Gerar contexto/background para a hipotese.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Contexto da hipotese
        """
        background_parts = [
            "Esta hipotese de otimizacao foi gerada automaticamente pelo Optimizer Agents.",
            "",
            "**Metricas Baseline Atuais:**",
        ]

        for metric, value in hypothesis.baseline_metrics.items():
            background_parts.append(f"- {metric}: {value}")

        background_parts.extend(
            [
                "",
                "**Metricas Alvo:**",
            ]
        )

        for metric, value in hypothesis.target_metrics.items():
            baseline = hypothesis.baseline_metrics.get(metric, 0)
            diff_pct = ((value - baseline) / baseline * 100) if baseline > 0 else 0
            direction = "aumento" if value > baseline else "reducao"
            background_parts.append(f"- {metric}: {value} ({direction} de {abs(diff_pct):.1f}%)")

        return "\n".join(background_parts)

    def _generate_expected_outcome(self, hypothesis: OptimizationHypothesis) -> str:
        """
        Gerar descricao do resultado esperado.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Descricao do resultado esperado
        """
        outcome_parts = [
            "Apos a aplicacao desta otimizacao, espera-se:",
            "",
        ]

        for metric, target in hypothesis.target_metrics.items():
            baseline = hypothesis.baseline_metrics.get(metric, 0)
            if baseline > 0:
                improvement = ((target - baseline) / baseline) * 100
                outcome_parts.append(
                    f"- {metric}: {baseline} → {target} ({improvement:+.1f}% de mudanca)"
                )
            else:
                outcome_parts.append(f"- {metric}: {target} (baseline indisponivel)")

        outcome_parts.extend(
            [
                "",
                f"Com {hypothesis.confidence_score:.1%} de confianca e risco estimado de {hypothesis.risk_score:.1%}.",
            ]
        )

        return "\n".join(outcome_parts)

    def _generate_tags(self, hypothesis: OptimizationHypothesis) -> list[str]:
        """
        Gerar tags para categorizacao da hipotese.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Lista de tags
        """
        tags = [
            hypothesis.optimization_type.value.lower(),
            f"component:{hypothesis.target_component.lower()}",
            "auto-generated",
        ]

        # Adicionar tag baseada na prioridade
        if hypothesis.priority == 1:
            tags.append("critical")
        elif hypothesis.priority == 2:
            tags.append("high-priority")

        # Adicionar tag baseada no nivel de risco
        if hypothesis.risk_score > 0.7:
            tags.append("high-risk")
        elif hypothesis.risk_score < 0.3:
            tags.append("low-risk")

        # Adicionar tags de metricas (ate 5 metricas principais)
        for metric in list(hypothesis.target_metrics.keys())[:5]:
            tags.append(f"metric:{metric.lower()}")

        return tags

    def _enrich_metadata(self, hypothesis: OptimizationHypothesis) -> dict[str, Any]:
        """
        Enriquecer metadata com informacoes originais do optimizer.

        Args:
            hypothesis: Hipotese de otimizacao

        Returns:
            Metadata enriquecida com campos adicionais
        """
        # Preservar metadata original e adicionar campos especificos do optimizer
        enriched_metadata = hypothesis.metadata.copy() if hypothesis.metadata else {}

        # Adicionar identificadores do optimizer
        enriched_metadata.update(
            {
                "optimizer_hypothesis_id": hypothesis.hypothesis_id,
                "optimizer_source": "optimizer-agents",
                "optimization_type": hypothesis.optimization_type.value,
                "confidence_score": hypothesis.confidence_score,
                "risk_score": hypothesis.risk_score,
                "expected_improvement": hypothesis.expected_improvement,
            }
        )

        # Adicionar informacoes de ajustes propostos
        if hypothesis.proposed_adjustments:
            enriched_metadata["proposed_adjustments"] = [
                {
                    "parameter": adj.parameter_name,
                    "old_value": adj.old_value,
                    "new_value": adj.new_value,
                }
                for adj in hypothesis.proposed_adjustments
            ]

        # Adicionar informacoes de analise causal se disponivel
        if hypothesis.causal_evidence:
            enriched_metadata["causal_analysis"] = {
                "method": hypothesis.causal_evidence.method,
                "root_cause": hypothesis.causal_evidence.root_cause,
                "confidence": hypothesis.causal_evidence.confidence_score,
                "effect_size": hypothesis.causal_evidence.effect_size,
            }

        return enriched_metadata
