"""
Multi-Signal Workflow Classifier

Implementação do IWorkflowClassifier que usa múltiplos sinais
ponderados para decidir entre ORCHESTRATION e GENERATION.

Precisão esperada: 80-85%
"""

import asyncio
from typing import Dict, Any
from datetime import datetime

from neural_hive_context.interfaces import IWorkflowClassifier
from neural_hive_context.models import (
    RichContext,
    WorkflowClassification,
    WorkflowType,
    IntentContext,
    SystemContext,
)


class MultiSignalWorkflowClassifier(IWorkflowClassifier):
    """
    Classificador de workflow baseado em múltiplos sinais ponderados.

    Sinais e Pesos:
    - system_context (40%): Estado do sistema, serviços afetados
    - affected_services (25%): Quantidade de serviços impactados
    - pii_detection (15%): Presença de dados sensíveis
    - user_input (10%): Keywords e explicitação do usuário
    - semantic (10%): Similaridade semântica (quando disponível)

    Thresholds:
    - score >= 0.65: Auto-route para workflow decidido
    - score < 0.50: Requer revisão humana
    - 0.50 <= score < 0.65: Zone intermediária, usa heurística
    """

    # Pesos dos sinais (soma = 1.0)
    SIGNAL_WEIGHTS: Dict[str, float] = {
        "system_context": 0.30,
        "affected_services": 0.25,
        "pii_detection": 0.20,
        "user_input": 0.25,  # Aumentado para dar mais peso às keywords
        "semantic": 0.00,  # Desabilitado até features semânticas disponíveis
    }

    # Keywords que indicam geração
    GENERATION_KEYWORDS = {
        "gerar", "gere", "generate", "criar", "create",
        "escrever", "escreva", "write", "produzir", "build",
        "relatório", "report", "código", "code", "script"
    }

    # Keywords que indicam orquestração
    ORCHESTRATION_KEYWORDS = {
        "analisar", "análise", "analise", "analyze", "examinar",
        "investigar", "diagnosticar", "coordenar", "coordenação",
        "aprovar", "validate", "validar"
    }

    def __init__(self, pii_detector=None):
        """
        Inicializa o classificador.

        Args:
            pii_detector: Opcional, detector de PII para sinal PII
        """
        self.pii_detector = pii_detector

    async def classify(self, context: RichContext) -> WorkflowClassification:
        """
        Classifica o workflow baseado no RichContext.

        Args:
            context: RichContext com todas as dimensões

        Returns:
            WorkflowClassification com decisão e justificativa
        """
        signals = await self._extract_all_signals(context)
        score = self._calculate_weighted_score(signals)
        workflow_type = self._determine_workflow(score, signals)
        confidence = self._calculate_confidence(signals)
        reasoning = self._build_reasoning(signals, workflow_type, score)

        return WorkflowClassification(
            workflow_type=workflow_type,
            confidence=confidence,
            reasoning=reasoning,
            signals=signals,
            raw_score=score,
        )

    async def _extract_all_signals(self, context: RichContext) -> Dict[str, Any]:
        """Extrai todos os sinais do contexto em paralelo."""
        signals = {}

        # Sinais síncronos (rápidos)
        signals["system_context"] = self._extract_system_context_signal(context)
        signals["affected_services"] = self._extract_affected_services_signal(context)
        signals["user_input"] = self._extract_user_input_signal(context)

        # Sinal PII (se detector disponível)
        if self.pii_detector:
            signals["pii_detection"] = await self._extract_pii_signal(context)
        else:
            signals["pii_detection"] = 0.0

        # Sinal semântico (quando disponível)
        signals["semantic"] = self._extract_semantic_signal(context)

        return signals

    def _extract_system_context_signal(self, context: RichContext) -> float:
        """
        Sinal do contexto do sistema.

        Mais workflows ativos = favor ORCHESTRATION (coordenação)
        Recursos altos = favor ORCHESTRATION
        """
        system = context.system

        # Workflow count signal
        workflow_signal = min(system.active_workflows / 10.0, 1.0)

        # Resource utilization signal
        util_values = list(system.resource_utilization.values())

        # Base signal quando sem dados - neutro
        if system.active_workflows == 0 and not util_values:
            return 0.5  # Neutro quando sem informações

        if util_values:
            avg_util = sum(util_values) / len(util_values)
            util_signal = avg_util / 100.0
            # Combinar: mais atividade = orquestração
            return (workflow_signal * 0.6 + util_signal * 0.4)
        else:
            # Sem dados de utilização, usa apenas workflow signal
            return workflow_signal

    def _extract_affected_services_signal(self, context: RichContext) -> float:
        """
        Sinal de serviços afetados.

        Mais serviços = ORCHESTRATION (coordenação necessária)
        0-1 serviço = pode ser GENERATION
        """
        count = len(context.system.affected_services)

        if count == 0:
            return 0.5  # Neutro
        elif count == 1:
            return 0.3  # Levemente favor GENERATION
        elif count <= 3:
            return 0.6  # Levemente favor ORCHESTRATION
        else:
            return 0.9  # Fortemente favor ORCHESTRATION

    def _extract_user_input_signal(self, context: RichContext) -> float:
        """
        Sinal do input do usuário baseado em keywords.

        Keywords de geração = favor GENERATION (score menor)
        Keywords de orquestração = favor ORCHESTRATION (score maior)
        """
        text = context.intent.raw_text.lower()
        words = set(text.split())

        # Conta keywords
        gen_count = len(words & self.GENERATION_KEYWORDS)
        orch_count = len(words & self.ORCHESTRATION_KEYWORDS)

        if gen_count > orch_count:
            # Keywords de geração = score baixo (favor generation)
            return max(0.2, 0.5 - gen_count * 0.2)
        elif orch_count > gen_count:
            # Keywords de orquestração = score alto (favor orchestration)
            return min(0.9, 0.5 + orch_count * 0.2)
        else:
            return 0.5  # Neutro

    async def _extract_pii_signal(self, context: RichContext) -> float:
        """
        Sinal PII.

        Presença de PII = ORCHESTRATION (requer aprovação humana)

        Returns:
            0.0 (sem PII, favor generation) a 1.0 (PII crítico, favor orchestration)
        """
        if not self.pii_detector:
            return 0.0

        result = self.pii_detector.detect(context.intent.raw_text)

        if not result.has_pii:
            return 0.0

        # Mapeamento de risk level para sinal
        risk_mapping = {
            "none": 0.0,
            "low": 0.3,
            "medium": 0.6,
            "high": 0.85,
            "critical": 1.0,
        }

        return risk_mapping.get(result.risk_level, 0.5)

    def _extract_semantic_signal(self, context: RichContext) -> float:
        """
        Sinal semântico (quando disponível).

        Usa features semânticas do intent se disponíveis.
        """
        features = context.intent.semantic_features

        if not features:
            return 0.5  # Neutro se não disponível

        # Se tiver similaridade com generation/orchestration
        gen_sim = features.get("similarity_generation", 0.5)
        orch_sim = features.get("similarity_orchestration", 0.5)

        # Retorna score baseado na diferença
        if gen_sim > orch_sim:
            return 1.0 - gen_sim  # Invertido: menor = favor generation
        else:
            return orch_sim

    def _calculate_weighted_score(self, signals: Dict[str, Any]) -> float:
        """Calcula score ponderado dos sinais."""
        total = 0.0
        for name, weight in self.SIGNAL_WEIGHTS.items():
            value = signals.get(name, 0.5)
            total += value * weight
        return round(total, 3)

    def _determine_workflow(
        self, score: float, signals: Dict[str, Any]
    ) -> WorkflowType:
        """
        Determina workflow baseado no score.

        score < 0.45: GENERATION
        score >= 0.45: ORCHESTRATION (threshold ajustado para mais sensibilidade)
        """
        return (
            WorkflowType.ORCHESTRATION if score >= 0.45 else WorkflowType.GENERATION
        )

    def _calculate_confidence(self, signals: Dict[str, Any]) -> float:
        """
        Calcula confiança da classificação.

        Confiança baseada em:
        - Consistência dos sinais
        - Força dos sinais individuais
        """
        # Variância dos sinais (menor = mais confiança)
        values = list(signals.values())
        if len(values) < 2:
            return 0.5

        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)

        # Menor variância = maior confiança
        base_confidence = max(0.5, 1.0 - variance)

        # Ajusta baseado em sinais fortes
        strong_signals = sum(1 for v in values if v >= 0.8 or v <= 0.2)
        if strong_signals >= 3:
            base_confidence = min(0.95, base_confidence + 0.15)

        return round(min(0.95, base_confidence), 3)

    def _build_reasoning(
        self, signals: Dict[str, Any], workflow_type: WorkflowType, score: float
    ) -> str:
        """Construi explicação em linguagem natural."""
        parts = []

        # Workflow type
        workflow_name = "Orquestração" if workflow_type == WorkflowType.ORCHESTRATION else "Geração"
        parts.append(f"Workflow de {workflow_name.lower()} selecionado")

        # Sinais principais
        if signals.get("affected_services", 0) > 0.7:
            parts.append("múltiplos serviços afetados")
        elif signals.get("affected_services", 0) < 0.3:
            parts.append("serviço único ou focado")

        if signals.get("pii_detection", 0) > 0.5:
            parts.append("dados sensíveis detectados")

        if signals.get("user_input", 0) < 0.4:
            parts.append("intenção de criação/geração")
        elif signals.get("user_input", 0) > 0.6:
            parts.append("intenção de análise/coordenação")

        return ". ".join(parts) + "."
