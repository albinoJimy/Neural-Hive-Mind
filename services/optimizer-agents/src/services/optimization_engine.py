import random
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from src.config.settings import get_settings
from src.models.optimization_event import Adjustment, CausalAnalysis, OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis

logger = structlog.get_logger()


class OptimizationEngine:
    """
    Núcleo do Optimization Engine com Reinforcement Learning + Contextual Bandits.

    Implementa Q-learning para seleção de ações de otimização, com epsilon-greedy
    para balancear exploração/exploração.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

        # Q-table: dict[state_hash][action] -> Q-value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        # Reward history
        self.reward_history: List[Tuple[str, str, float]] = []

        # Hyperparameters RL
        self.learning_rate = self.settings.learning_rate
        self.exploration_rate = self.settings.exploration_rate
        self.discount_factor = self.settings.discount_factor

        # Action space (tipos de otimização)
        self.action_space = [
            OptimizationType.WEIGHT_RECALIBRATION,
            OptimizationType.SLO_ADJUSTMENT,
            OptimizationType.HEURISTIC_UPDATE,
            OptimizationType.POLICY_CHANGE,
        ]

        logger.info(
            "optimization_engine_initialized",
            learning_rate=self.learning_rate,
            exploration_rate=self.exploration_rate,
            discount_factor=self.discount_factor,
        )

    def analyze_opportunity(self, insight: Dict) -> List[OptimizationHypothesis]:
        """
        Analisar insight e identificar oportunidades de otimização.

        Args:
            insight: Insight do Analyst Agents

        Returns:
            Lista de hipóteses de otimização
        """
        try:
            hypotheses = []

            # Extrair métricas relevantes do insight
            metrics = insight.get("metrics", {})
            entity = insight.get("related_entities", [{}])[0]
            component = entity.get("entity_id", "unknown")

            # Mapear estado atual
            state = self._extract_state(metrics)
            state_hash = self._hash_state(state)

            # Identificar ações candidatas baseado no tipo de insight
            insight_type = insight.get("insight_type", "")
            if "OPERATIONAL" in insight_type or "ANOMALY" in insight_type:
                # Para insights operacionais/anomalias, considerar ajustes de SLO e recalibração
                candidate_actions = [
                    OptimizationType.WEIGHT_RECALIBRATION,
                    OptimizationType.SLO_ADJUSTMENT,
                ]
            elif "STRATEGIC" in insight_type:
                # Para insights estratégicos, considerar mudanças de política
                candidate_actions = [OptimizationType.POLICY_CHANGE, OptimizationType.HEURISTIC_UPDATE]
            else:
                # Default: considerar todos
                candidate_actions = self.action_space

            # Gerar hipóteses para cada ação candidata
            for action in candidate_actions:
                hypothesis = self.generate_hypothesis(state, action, component, metrics, insight)
                if hypothesis and hypothesis.validate_feasibility():
                    hypotheses.append(hypothesis)

            logger.info(
                "opportunities_analyzed",
                insight_id=insight.get("insight_id"),
                hypotheses_generated=len(hypotheses),
                component=component,
            )

            return hypotheses

        except Exception as e:
            logger.error("opportunity_analysis_failed", insight_id=insight.get("insight_id"), error=str(e))
            return []

    def generate_hypothesis(
        self, state: Dict, action: OptimizationType, component: str, metrics: Dict, context: Dict
    ) -> Optional[OptimizationHypothesis]:
        """
        Gerar hipótese de otimização usando RL.

        Args:
            state: Estado atual do sistema
            action: Tipo de otimização
            component: Componente alvo
            metrics: Métricas atuais
            context: Contexto adicional

        Returns:
            Hipótese de otimização
        """
        try:
            state_hash = self._hash_state(state)

            # Obter Q-value para esta ação no estado atual
            q_value = self.q_table[state_hash][action.value]

            # Calcular expected improvement baseado em Q-value (normalizar para 0-1)
            expected_improvement = min(max(q_value, 0.0), 1.0)

            # Estimar risco baseado em variância histórica
            risk_score = self._estimate_risk(action, component)

            # Calcular confidence baseado em número de observações
            confidence_score = self._calculate_confidence(state_hash, action)

            # Gerar ajustes propostos
            proposed_adjustments = self._generate_adjustments(action, component, metrics)

            # Calcular métricas alvo
            target_metrics = self._calculate_target_metrics(metrics, expected_improvement)

            # Gerar texto da hipótese
            hypothesis_text = self._generate_hypothesis_text(action, component, expected_improvement)

            # Criar hipótese
            hypothesis = OptimizationHypothesis(
                hypothesis_id=str(uuid.uuid4()),
                hypothesis_text=hypothesis_text,
                target_component=component,
                optimization_type=action,
                proposed_adjustments=proposed_adjustments,
                expected_improvement=expected_improvement,
                confidence_score=confidence_score,
                risk_score=risk_score,
                baseline_metrics=metrics,
                target_metrics=target_metrics,
                priority=self._calculate_priority(expected_improvement, risk_score),
                requires_experiment=risk_score > 0.3,  # Experimentos para mudanças de risco médio/alto
                metadata={
                    "state_hash": state_hash,
                    "q_value": q_value,
                    "context_id": context.get("correlation_id", ""),
                },
            )

            logger.debug(
                "hypothesis_generated",
                hypothesis_id=hypothesis.hypothesis_id,
                action=action.value,
                expected_improvement=expected_improvement,
                risk=risk_score,
            )

            return hypothesis

        except Exception as e:
            logger.error("hypothesis_generation_failed", action=action.value, component=component, error=str(e))
            return None

    def select_action(self, state: Dict) -> OptimizationType:
        """
        Selecionar ação usando política epsilon-greedy.

        Args:
            state: Estado atual

        Returns:
            Tipo de otimização selecionado
        """
        state_hash = self._hash_state(state)

        # Epsilon-greedy: com probabilidade epsilon, explorar (ação aleatória)
        if random.random() < self.exploration_rate:
            action = random.choice(self.action_space)
            logger.debug("action_selected_exploration", action=action.value, epsilon=self.exploration_rate)
        else:
            # Exploitar: selecionar ação com maior Q-value
            q_values = self.q_table[state_hash]
            if q_values:
                action_str = max(q_values, key=q_values.get)
                action = OptimizationType(action_str)
            else:
                # Se Q-table vazio para este estado, explorar
                action = random.choice(self.action_space)

            logger.debug("action_selected_exploitation", action=action.value)

        return action

    def calculate_reward(self, optimization_event, post_metrics: Dict) -> float:
        """
        Calcular recompensa baseado em melhoria observada.

        Reward = improvement_percentage - (risk_score * penalty_factor)

        Args:
            optimization_event: Evento de otimização aplicada
            post_metrics: Métricas após otimização

        Returns:
            Recompensa (pode ser negativa)
        """
        try:
            improvement = optimization_event.improvement_percentage
            risk = optimization_event.causal_analysis.confidence  # Usar inverso da confiança como penalização

            # Penalidade por risco
            penalty_factor = 0.2
            reward = improvement - ((1.0 - risk) * penalty_factor)

            # Penalizar se degradação
            if improvement < 0:
                reward = improvement * 2.0  # Penalidade dobrada

            # Bonificar se melhoria excedeu expectativa
            expected = optimization_event.metadata.get("expected_improvement", 0.0)
            if improvement > expected * 1.2:  # 20% acima do esperado
                reward += 0.1  # Bônus

            logger.debug(
                "reward_calculated",
                optimization_id=optimization_event.optimization_id,
                improvement=improvement,
                reward=reward,
            )

            return reward

        except Exception as e:
            logger.error(
                "reward_calculation_failed", optimization_id=optimization_event.optimization_id, error=str(e)
            )
            return 0.0

    def update_q_table(self, state: Dict, action: OptimizationType, reward: float, next_state: Dict):
        """
        Atualizar Q-table usando Q-learning.

        Q(s,a) = Q(s,a) + α * [r + γ * max(Q(s',a')) - Q(s,a)]

        Args:
            state: Estado atual
            action: Ação tomada
            reward: Recompensa recebida
            next_state: Próximo estado
        """
        try:
            state_hash = self._hash_state(state)
            next_state_hash = self._hash_state(next_state)

            # Q-value atual
            current_q = self.q_table[state_hash][action.value]

            # Max Q-value do próximo estado
            next_q_values = self.q_table[next_state_hash]
            max_next_q = max(next_q_values.values()) if next_q_values else 0.0

            # Q-learning update
            new_q = current_q + self.learning_rate * (reward + self.discount_factor * max_next_q - current_q)

            self.q_table[state_hash][action.value] = new_q

            # Salvar no histórico
            self.reward_history.append((state_hash, action.value, reward))

            logger.info(
                "q_table_updated",
                state_hash=state_hash[:8],
                action=action.value,
                old_q=current_q,
                new_q=new_q,
                reward=reward,
            )

        except Exception as e:
            logger.error("q_table_update_failed", error=str(e))

    # Helper methods

    def _extract_state(self, metrics: Dict) -> Dict:
        """Extrair features de estado relevantes."""
        return {
            "divergence": metrics.get("divergence", 0.0),
            "confidence": metrics.get("confidence", 0.0),
            "latency_p95": metrics.get("latency_p95", 0.0),
            "error_rate": metrics.get("error_rate", 0.0),
            "slo_compliance": metrics.get("slo_compliance", 1.0),
        }

    def _hash_state(self, state: Dict) -> str:
        """Gerar hash do estado para indexação na Q-table."""
        # Discretizar métricas contínuas em bins
        discretized = []
        for key in sorted(state.keys()):
            value = state[key]
            # Bins de 0.1
            bin_value = round(value * 10) / 10
            discretized.append(f"{key}:{bin_value}")

        return "|".join(discretized)

    def _estimate_risk(self, action: OptimizationType, component: str) -> float:
        """Estimar risco da ação baseado em histórico."""
        # Calcular variância de rewards para esta ação
        action_rewards = [r for s, a, r in self.reward_history if a == action.value]

        if len(action_rewards) >= 3:
            variance = np.var(action_rewards)
            # Normalizar variância para score de risco 0-1
            risk = min(variance * 2, 1.0)
        else:
            # Sem histórico suficiente, assumir risco médio
            risk = 0.5

        return risk

    def _calculate_confidence(self, state_hash: str, action: OptimizationType) -> float:
        """Calcular confiança baseado em número de observações."""
        observations = sum(1 for s, a, r in self.reward_history if s == state_hash and a == action.value)

        # Função sigmoide para mapear observações para confiança
        confidence = 1.0 / (1.0 + np.exp(-0.1 * (observations - 10)))
        return confidence

    def _generate_adjustments(self, action: OptimizationType, component: str, metrics: Dict) -> List[Adjustment]:
        """Gerar ajustes propostos baseado no tipo de otimização."""
        adjustments = []

        if action == OptimizationType.WEIGHT_RECALIBRATION:
            # Exemplo: ajustar peso de especialista
            adjustments.append(
                Adjustment(
                    parameter_name="technical_specialist_weight",
                    old_value="0.20",
                    new_value="0.25",
                    justification="Aumentar peso do especialista técnico para reduzir divergência",
                )
            )
        elif action == OptimizationType.SLO_ADJUSTMENT:
            # Exemplo: ajustar SLO de latência
            current_slo = metrics.get("slo_target_latency", 1000)
            new_slo = current_slo * 0.9  # Reduzir 10%
            adjustments.append(
                Adjustment(
                    parameter_name="latency_p95_slo",
                    old_value=str(current_slo),
                    new_value=str(new_slo),
                    justification="Reduzir SLO de latência baseado em performance observada",
                )
            )

        return adjustments

    def _calculate_target_metrics(self, baseline: Dict, improvement: float) -> Dict:
        """Calcular métricas alvo baseado em melhoria esperada."""
        target = {}
        for key, value in baseline.items():
            if "error" in key or "divergence" in key:
                # Métricas a serem reduzidas
                target[key] = value * (1.0 - improvement)
            elif "compliance" in key or "confidence" in key:
                # Métricas a serem aumentadas
                target[key] = min(value * (1.0 + improvement), 1.0)
            else:
                target[key] = value

        return target

    def _calculate_priority(self, expected_improvement: float, risk_score: float) -> int:
        """Calcular prioridade (1-5)."""
        # Prioridade = f(improvement, risco)
        score = expected_improvement * (1.0 - risk_score)

        if score > 0.8:
            return 5  # Crítico
        elif score > 0.6:
            return 4  # Alto
        elif score > 0.4:
            return 3  # Médio
        elif score > 0.2:
            return 2  # Baixo
        else:
            return 1  # Muito baixo

    def _generate_hypothesis_text(self, action: OptimizationType, component: str, improvement: float) -> str:
        """Gerar texto descritivo da hipótese."""
        improvement_pct = improvement * 100

        if action == OptimizationType.WEIGHT_RECALIBRATION:
            return f"Recalibrar pesos do {component} pode melhorar consenso em {improvement_pct:.1f}%"
        elif action == OptimizationType.SLO_ADJUSTMENT:
            return f"Ajustar SLOs do {component} pode melhorar compliance em {improvement_pct:.1f}%"
        elif action == OptimizationType.HEURISTIC_UPDATE:
            return f"Atualizar heurísticas do {component} pode melhorar performance em {improvement_pct:.1f}%"
        elif action == OptimizationType.POLICY_CHANGE:
            return f"Mudar política do {component} pode melhorar eficiência em {improvement_pct:.1f}%"
        else:
            return f"Otimizar {component} pode melhorar métricas em {improvement_pct:.1f}%"

    def get_q_table_size(self) -> int:
        """Retornar tamanho da Q-table."""
        return len(self.q_table)

    def get_exploration_rate(self) -> float:
        """Retornar taxa de exploração atual."""
        return self.exploration_rate

    def decay_exploration_rate(self, decay_factor: float = 0.99):
        """Decay da taxa de exploração ao longo do tempo."""
        self.exploration_rate *= decay_factor
        # Mínimo de 5% de exploração
        self.exploration_rate = max(self.exploration_rate, 0.05)
