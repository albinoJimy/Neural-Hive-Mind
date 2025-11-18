"""
Scheduling Optimizer usando Reinforcement Learning (Q-learning).

Otimiza políticas de agendamento através de ações como escalonamento de workers,
ajuste de prioridades e balanceamento de carga.
"""

import asyncio
import logging
import pickle
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class SchedulingAction(str, Enum):
    """Ações de otimização de agendamento disponíveis."""
    INCREASE_WORKER_POOL = "INCREASE_WORKER_POOL"
    DECREASE_WORKER_POOL = "DECREASE_WORKER_POOL"
    ADJUST_PRIORITY_WEIGHTS = "ADJUST_PRIORITY_WEIGHTS"
    PREEMPTIVE_SCALING = "PREEMPTIVE_SCALING"
    LOAD_BALANCING_RECONFIG = "LOAD_BALANCING_RECONFIG"
    NO_ACTION = "NO_ACTION"


class SchedulingOptimizer:
    """
    Otimizador de agendamento usando Q-learning.

    Aprende política ótima de agendamento através de interações com o ambiente,
    buscando maximizar SLA compliance, eficiência de recursos e throughput.
    """

    def __init__(
        self,
        optimization_engine,
        experiment_manager,
        orchestrator_client,
        mongodb_client,
        redis_client,
        model_registry,
        metrics,
        config: Dict
    ):
        """
        Args:
            optimization_engine: Engine Q-learning existente
            experiment_manager: Gerenciador de experimentos A/B
            orchestrator_client: Cliente gRPC para orquestrador
            mongodb_client: Cliente MongoDB para persistência
            redis_client: Cliente Redis para caching
            model_registry: Registro MLflow para políticas
            metrics: Instância de métricas Prometheus
            config: Configuração (epsilon, learning rate, discount factor)
        """
        self.optimization_engine = optimization_engine
        self.experiment_manager = experiment_manager
        self.orchestrator = orchestrator_client
        self.mongodb = mongodb_client
        self.redis = redis_client
        self.model_registry = model_registry
        self.metrics = metrics
        self.config = config

        # Q-table: state_hash -> {action -> Q-value}
        self.q_table: Dict[str, Dict[SchedulingAction, float]] = {}

        # Hiperparâmetros RL
        self.epsilon = config.get('ml_scheduling_epsilon', 0.1)  # Exploração
        self.learning_rate = config.get('ml_scheduling_learning_rate', 0.01)
        self.discount_factor = config.get('ml_scheduling_discount_factor', 0.95)

        # Histórico recente para análise
        self.recent_states: List[Dict] = []
        self.recent_actions: List[SchedulingAction] = []
        self.recent_rewards: List[float] = []

        # Contador de atualizações para snapshot periódico
        self.update_counter = 0
        self.snapshot_interval = 100

        self._initialized = False

    async def initialize(self) -> None:
        """Carrega Q-table do MLflow ou MongoDB."""
        if self._initialized:
            return

        logger.info("Inicializando SchedulingOptimizer...")

        try:
            # Tentar carregar política do MLflow
            policy_data = await self.model_registry.load_scheduling_policy()

            if policy_data:
                self.q_table = policy_data['q_table']
                logger.info(f"Q-table carregada com {len(self.q_table)} estados")
            else:
                logger.info("Nenhuma política existente, iniciando Q-table vazia")
                self.q_table = {}

            self._initialized = True

        except Exception as e:
            logger.error(f"Erro ao inicializar SchedulingOptimizer: {e}")
            raise

    async def optimize_scheduling(
        self,
        current_state: Dict,
        load_forecast: Optional[Dict] = None
    ) -> Dict:
        """
        Gera recomendação de otimização de agendamento.

        Args:
            current_state: Estado atual (load, utilization, queue_depth, sla_compliance)
            load_forecast: Previsão de carga futura (opcional, melhora decisões)

        Returns:
            Dict com:
                - action: Ação recomendada (SchedulingAction)
                - justification: Razão para a ação
                - expected_improvement: Ganho esperado em SLA compliance
                - risk_score: Risco da ação (0-1)
                - confidence: Confiança na recomendação (0-1)
        """
        start_time = datetime.utcnow()

        try:
            # Enriquecer estado com previsão de carga
            enriched_state = self._enrich_state_with_forecast(current_state, load_forecast)

            # Hash do estado para lookup na Q-table
            state_hash = self._hash_state(enriched_state)

            # Selecionar ação (epsilon-greedy)
            action = self._select_action(state_hash)

            # Estimar melhoria esperada
            expected_improvement = self._estimate_improvement(enriched_state, action)

            # Calcular risco
            risk_score = self._calculate_action_risk(enriched_state, action)

            # Calcular confiança (baseado em experiência com este estado)
            confidence = self._calculate_confidence(state_hash)

            # Justificativa baseada em heurísticas
            justification = self._generate_justification(enriched_state, action, load_forecast)

            result = {
                'action': action.value,
                'justification': justification,
                'expected_improvement': expected_improvement,
                'risk_score': risk_score,
                'confidence': confidence,
                'state_hash': state_hash,
                'timestamp': datetime.utcnow().isoformat()
            }

            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_scheduling_optimization(action.value, duration, expected_improvement)

            logger.info(f"Recomendação: {action.value} (confiança={confidence:.2f}, risco={risk_score:.2f})")
            return result

        except Exception as e:
            logger.error(f"Erro ao otimizar agendamento: {e}")
            raise

    async def generate_scheduling_hypothesis(
        self,
        state: Dict,
        action: SchedulingAction
    ) -> Dict:
        """
        Gera hipótese de otimização para teste A/B.

        Args:
            state: Estado atual
            action: Ação a testar

        Returns:
            Dict com hipótese formatada para ExperimentManager
        """
        hypothesis = {
            'optimization_type': 'scheduling',
            'action': action.value,
            'state_snapshot': state,
            'predicted_metrics': {
                'sla_improvement': self._estimate_improvement(state, action),
                'resource_efficiency_delta': self._estimate_resource_delta(action),
                'throughput_change': self._estimate_throughput_change(action),
            },
            'implementation_details': self._get_implementation_details(action),
            'rollback_criteria': {
                'sla_degradation_threshold': 0.05,  # 5% piora
                'duration_increase_threshold': 0.10,  # 10% aumento
                'error_rate_threshold': 0.02,  # 2% erros
            }
        }

        return hypothesis

    async def evaluate_scheduling_policy(
        self,
        policy_id: str,
        duration_seconds: int
    ) -> Dict:
        """
        Avalia política de agendamento via experimento A/B.

        Args:
            policy_id: ID da política a avaliar
            duration_seconds: Duração do teste

        Returns:
            Dict com resultados da avaliação
        """
        logger.info(f"Avaliando política {policy_id} por {duration_seconds}s")

        try:
            # Usar ExperimentManager para A/B test
            experiment_result = await self.experiment_manager.run_experiment(
                experiment_name=f"scheduling_policy_{policy_id}",
                duration_seconds=duration_seconds,
                metrics_to_track=['sla_compliance', 'avg_duration', 'throughput']
            )

            # Analisar resultados
            evaluation = {
                'policy_id': policy_id,
                'duration': duration_seconds,
                'metrics': experiment_result.get('metrics', {}),
                'success': experiment_result.get('success', False),
                'recommendation': 'promote' if experiment_result.get('success') else 'rollback'
            }

            return evaluation

        except Exception as e:
            logger.error(f"Erro ao avaliar política: {e}")
            return {'success': False, 'error': str(e)}

    async def update_policy(self, reward: float, next_state: Dict) -> None:
        """
        Atualiza Q-table com base em recompensa recebida.

        Args:
            reward: Recompensa obtida pela ação tomada
            next_state: Estado resultante da ação
        """
        try:
            if not self.recent_states or not self.recent_actions:
                logger.warning("Sem estado/ação anterior para atualizar")
                return

            # Estado e ação anteriores
            prev_state = self.recent_states[-1]
            prev_action = self.recent_actions[-1]
            state_hash = self._hash_state(prev_state)

            # Inicializar estado se não existir
            if state_hash not in self.q_table:
                self.q_table[state_hash] = {action: 0.0 for action in SchedulingAction}

            # Q-value atual
            current_q = self.q_table[state_hash][prev_action]

            # Max Q-value do próximo estado
            next_state_hash = self._hash_state(next_state)
            if next_state_hash in self.q_table:
                max_next_q = max(self.q_table[next_state_hash].values())
            else:
                max_next_q = 0.0

            # Q-learning update: Q(s,a) = Q(s,a) + α[r + γ·max(Q(s',a')) - Q(s,a)]
            new_q = current_q + self.learning_rate * (
                reward + self.discount_factor * max_next_q - current_q
            )

            self.q_table[state_hash][prev_action] = new_q

            # Registrar recompensa
            self.recent_rewards.append(reward)
            if len(self.recent_rewards) > 1000:
                self.recent_rewards = self.recent_rewards[-1000:]

            # Métricas
            self.metrics.record_policy_update(reward, new_q)

            # Snapshot periódico
            self.update_counter += 1
            if self.update_counter % self.snapshot_interval == 0:
                await self._save_q_table_snapshot()

            logger.debug(f"Q-table atualizada: state={state_hash[:8]}, action={prev_action.value}, Q={new_q:.4f}")

        except Exception as e:
            logger.error(f"Erro ao atualizar política: {e}")

    def _select_action(self, state_hash: str) -> SchedulingAction:
        """
        Seleciona ação usando epsilon-greedy.

        Args:
            state_hash: Hash do estado atual

        Returns:
            Ação selecionada
        """
        # Exploração com probabilidade epsilon
        if np.random.random() < self.epsilon:
            action = np.random.choice(list(SchedulingAction))
            logger.debug(f"Ação exploratória: {action.value}")
            return action

        # Exploração: escolher ação com maior Q-value
        if state_hash in self.q_table and self.q_table[state_hash]:
            best_action = max(self.q_table[state_hash].items(), key=lambda x: x[1])[0]
            logger.debug(f"Ação gulosa: {best_action.value}")
            return best_action

        # Estado nunca visto: ação padrão
        return SchedulingAction.NO_ACTION

    def _hash_state(self, state: Dict) -> str:
        """
        Cria hash do estado para indexação na Q-table.

        Discretiza valores contínuos em bins para reduzir espaço de estados.
        """
        # Discretizar carga (bins: baixa, média, alta, crítica)
        load = state.get('current_load', 0)
        load_bin = 'low' if load < 50 else 'medium' if load < 100 else 'high' if load < 200 else 'critical'

        # Discretizar utilização
        utilization = state.get('worker_utilization', 0)
        util_bin = 'low' if utilization < 0.5 else 'medium' if utilization < 0.8 else 'high'

        # Discretizar depth de fila
        queue = state.get('queue_depth', 0)
        queue_bin = 'low' if queue < 10 else 'medium' if queue < 50 else 'high'

        # Discretizar SLA compliance
        sla = state.get('sla_compliance', 1.0)
        sla_bin = 'critical' if sla < 0.8 else 'warning' if sla < 0.95 else 'good'

        # Tendência de carga (se forecast disponível)
        trend = state.get('load_trend', 'stable')

        # Concatenar
        state_str = f"{load_bin}_{util_bin}_{queue_bin}_{sla_bin}_{trend}"

        return state_str

    def _enrich_state_with_forecast(
        self,
        current_state: Dict,
        load_forecast: Optional[Dict]
    ) -> Dict:
        """Enriquece estado atual com previsão de carga."""
        enriched = current_state.copy()

        if load_forecast and 'forecast' in load_forecast:
            # Calcular tendência de carga (próxima hora vs atual)
            current_load = current_state.get('current_load', 0)
            future_points = load_forecast['forecast'][:60]  # Próxima hora

            if future_points:
                avg_future_load = np.mean([p['ticket_count'] for p in future_points])
                if avg_future_load > current_load * 1.2:
                    enriched['load_trend'] = 'increasing'
                elif avg_future_load < current_load * 0.8:
                    enriched['load_trend'] = 'decreasing'
                else:
                    enriched['load_trend'] = 'stable'

                enriched['predicted_peak'] = max(p['ticket_count'] for p in future_points)
            else:
                enriched['load_trend'] = 'stable'
        else:
            enriched['load_trend'] = 'stable'

        return enriched

    def _calculate_scheduling_reward(
        self,
        metrics_before: Dict,
        metrics_after: Dict
    ) -> float:
        """
        Calcula recompensa baseado em métricas antes/depois.

        Componentes:
        - SLA compliance improvement (peso 0.5)
        - Resource efficiency (peso 0.3)
        - Throughput increase (peso 0.2)
        """
        # SLA compliance delta
        sla_before = metrics_before.get('sla_compliance', 0)
        sla_after = metrics_after.get('sla_compliance', 0)
        sla_reward = (sla_after - sla_before) * 0.5

        # Eficiência de recursos (throughput / utilização)
        efficiency_before = metrics_before.get('throughput', 0) / max(metrics_before.get('utilization', 1), 0.01)
        efficiency_after = metrics_after.get('throughput', 0) / max(metrics_after.get('utilization', 1), 0.01)
        efficiency_reward = ((efficiency_after - efficiency_before) / max(efficiency_before, 1)) * 0.3

        # Throughput delta
        throughput_before = metrics_before.get('throughput', 0)
        throughput_after = metrics_after.get('throughput', 0)
        throughput_reward = ((throughput_after - throughput_before) / max(throughput_before, 1)) * 0.2

        total_reward = sla_reward + efficiency_reward + throughput_reward

        # Normalizar para [-1, 1]
        total_reward = max(-1.0, min(1.0, total_reward))

        return total_reward

    def _estimate_improvement(self, state: Dict, action: SchedulingAction) -> float:
        """
        Estima melhoria esperada em SLA compliance.

        Baseado em Q-values e heurísticas.
        """
        state_hash = self._hash_state(state)

        # Se temos Q-value para este estado/ação
        if state_hash in self.q_table and action in self.q_table[state_hash]:
            q_value = self.q_table[state_hash][action]
            # Normalizar Q-value para [0, 1]
            improvement = max(0, min(1, (q_value + 1) / 2))
        else:
            # Heurísticas baseadas em ação
            improvement = {
                SchedulingAction.INCREASE_WORKER_POOL: 0.15,
                SchedulingAction.PREEMPTIVE_SCALING: 0.20,
                SchedulingAction.ADJUST_PRIORITY_WEIGHTS: 0.10,
                SchedulingAction.LOAD_BALANCING_RECONFIG: 0.12,
                SchedulingAction.DECREASE_WORKER_POOL: -0.05,
                SchedulingAction.NO_ACTION: 0.0,
            }.get(action, 0.0)

        return improvement

    def _calculate_action_risk(self, state: Dict, action: SchedulingAction) -> float:
        """
        Calcula risco da ação (0=seguro, 1=perigoso).

        Ações disruptivas têm risco maior.
        """
        base_risk = {
            SchedulingAction.INCREASE_WORKER_POOL: 0.2,
            SchedulingAction.DECREASE_WORKER_POOL: 0.4,  # Mais arriscado
            SchedulingAction.ADJUST_PRIORITY_WEIGHTS: 0.3,
            SchedulingAction.PREEMPTIVE_SCALING: 0.25,
            SchedulingAction.LOAD_BALANCING_RECONFIG: 0.35,
            SchedulingAction.NO_ACTION: 0.0,
        }.get(action, 0.5)

        # Aumentar risco se SLA já crítico
        if state.get('sla_compliance', 1.0) < 0.8:
            base_risk *= 1.5

        return min(1.0, base_risk)

    def _calculate_confidence(self, state_hash: str) -> float:
        """
        Calcula confiança na recomendação baseado em experiência.

        Alta confiança se já visitamos este estado muitas vezes.
        """
        if state_hash not in self.q_table:
            return 0.1  # Baixa confiança em estado novo

        # Contar visitas a este estado (proxy: soma de Q-values absolutos)
        q_values = list(self.q_table[state_hash].values())
        visit_proxy = sum(abs(q) for q in q_values)

        # Normalizar para [0, 1]
        confidence = min(1.0, visit_proxy / 10.0)

        return max(0.1, confidence)

    def _generate_justification(
        self,
        state: Dict,
        action: SchedulingAction,
        load_forecast: Optional[Dict]
    ) -> str:
        """Gera justificativa textual para a ação recomendada."""
        justifications = {
            SchedulingAction.INCREASE_WORKER_POOL: (
                f"Alta utilização ({state.get('worker_utilization', 0):.1%}) e fila crescente "
                f"({state.get('queue_depth', 0)} tickets). Aumentar workers reduzirá latência."
            ),
            SchedulingAction.DECREASE_WORKER_POOL: (
                f"Baixa utilização ({state.get('worker_utilization', 0):.1%}) detectada. "
                f"Reduzir workers economiza recursos sem impactar SLA."
            ),
            SchedulingAction.PREEMPTIVE_SCALING: (
                f"Pico de carga previsto ({load_forecast.get('metadata', {}).get('predicted_peak', 0)} tickets). "
                f"Escalonamento proativo evitará degradação de SLA."
            ),
            SchedulingAction.ADJUST_PRIORITY_WEIGHTS: (
                f"SLA compliance abaixo do alvo ({state.get('sla_compliance', 0):.1%}). "
                f"Rebalancear prioridades pode melhorar atendimento."
            ),
            SchedulingAction.LOAD_BALANCING_RECONFIG: (
                f"Distribuição de carga desbalanceada detectada. "
                f"Reconfigurar balanceamento otimizará uso de recursos."
            ),
            SchedulingAction.NO_ACTION: (
                f"Sistema operando dentro dos parâmetros ótimos "
                f"(SLA={state.get('sla_compliance', 0):.1%}, utilização={state.get('worker_utilization', 0):.1%})."
            ),
        }

        return justifications.get(action, "Otimização recomendada pelo modelo de RL.")

    def _estimate_resource_delta(self, action: SchedulingAction) -> float:
        """Estima mudança em eficiência de recursos."""
        return {
            SchedulingAction.INCREASE_WORKER_POOL: -0.1,  # Usa mais recursos
            SchedulingAction.DECREASE_WORKER_POOL: 0.15,  # Libera recursos
            SchedulingAction.LOAD_BALANCING_RECONFIG: 0.08,
            SchedulingAction.PREEMPTIVE_SCALING: -0.05,
            SchedulingAction.ADJUST_PRIORITY_WEIGHTS: 0.03,
            SchedulingAction.NO_ACTION: 0.0,
        }.get(action, 0.0)

    def _estimate_throughput_change(self, action: SchedulingAction) -> float:
        """Estima mudança em throughput."""
        return {
            SchedulingAction.INCREASE_WORKER_POOL: 0.2,
            SchedulingAction.PREEMPTIVE_SCALING: 0.15,
            SchedulingAction.LOAD_BALANCING_RECONFIG: 0.1,
            SchedulingAction.ADJUST_PRIORITY_WEIGHTS: 0.05,
            SchedulingAction.DECREASE_WORKER_POOL: -0.1,
            SchedulingAction.NO_ACTION: 0.0,
        }.get(action, 0.0)

    def _get_implementation_details(self, action: SchedulingAction) -> Dict:
        """Retorna detalhes de implementação para cada ação."""
        return {
            SchedulingAction.INCREASE_WORKER_POOL: {
                'target_workers': '+20%',
                'ramp_up_time': '2m',
                'health_check_delay': '30s'
            },
            SchedulingAction.DECREASE_WORKER_POOL: {
                'target_workers': '-15%',
                'graceful_shutdown': True,
                'drain_timeout': '5m'
            },
            SchedulingAction.ADJUST_PRIORITY_WEIGHTS: {
                'high_priority_boost': 1.3,
                'low_priority_reduction': 0.7,
            },
            SchedulingAction.PREEMPTIVE_SCALING: {
                'trigger_lead_time': '10m',
                'scale_factor': 1.5,
            },
            SchedulingAction.LOAD_BALANCING_RECONFIG: {
                'algorithm': 'weighted_round_robin',
                'rebalance_interval': '1m',
            },
            SchedulingAction.NO_ACTION: {},
        }.get(action, {})

    async def _save_q_table_snapshot(self) -> None:
        """Persiste Q-table no MongoDB e MLflow."""
        try:
            # Calcular métricas da política
            avg_reward = np.mean(self.recent_rewards) if self.recent_rewards else 0.0
            policy_metrics = {
                'average_reward': avg_reward,
                'states_explored': len(self.q_table),
                'updates_count': self.update_counter,
            }

            # Salvar no MLflow
            await self.model_registry.save_scheduling_policy(
                q_table=self.q_table,
                metrics=policy_metrics
            )

            # Também salvar no MongoDB para redundância
            await self.mongodb.db.scheduling_policies.update_one(
                {'policy_id': 'current'},
                {
                    '$set': {
                        'q_table_snapshot': pickle.dumps(self.q_table).hex(),
                        'metrics': policy_metrics,
                        'updated_at': datetime.utcnow(),
                    }
                },
                upsert=True
            )

            logger.info(f"Q-table snapshot salvo (estados={len(self.q_table)}, avg_reward={avg_reward:.3f})")

        except Exception as e:
            logger.error(f"Erro ao salvar snapshot: {e}")
