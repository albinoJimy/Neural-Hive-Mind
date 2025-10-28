import structlog
import numpy as np
from typing import List, Dict, Tuple, Optional
from scipy import stats
import networkx as nx

logger = structlog.get_logger()


class CausalAnalyzer:
    """Analisador de relações causa-efeito"""

    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    async def analyze_causal_relationship(
        self,
        cause: str,
        effect: str,
        data: Dict
    ) -> Dict:
        """Analisar relação causal entre eventos e métricas"""
        try:
            time_series = data.get('time_series', [])
            if not time_series or len(time_series) < 10:
                return {'causal': False, 'reason': 'insufficient_data'}

            # Extrair séries temporais
            cause_values = [item.get(cause, 0) for item in time_series]
            effect_values = [item.get(effect, 0) for item in time_series]

            if not cause_values or not effect_values:
                return {'causal': False, 'reason': 'missing_values'}

            # Granger Causality Test
            granger_result = self._granger_causality_test(cause_values, effect_values)

            # Calcular correlação com lag
            lag_correlation = self._calculate_lag_correlation(cause_values, effect_values)

            # Determinar causalidade
            is_causal = granger_result['p_value'] < 0.05 and abs(lag_correlation['correlation']) > 0.5

            result = {
                'causal': is_causal,
                'strength': abs(lag_correlation['correlation']),
                'confidence': 1 - granger_result['p_value'],
                'lag': lag_correlation['lag'],
                'granger_p_value': granger_result['p_value'],
                'method': 'granger_causality'
            }

            logger.info(
                'causal_relationship_analyzed',
                cause=cause,
                effect=effect,
                is_causal=is_causal,
                strength=result['strength']
            )

            return result

        except Exception as e:
            logger.error('analyze_causal_relationship_failed', error=str(e))
            return {'causal': False, 'error': str(e)}

    def _granger_causality_test(
        self,
        cause_series: List[float],
        effect_series: List[float],
        max_lag: int = 5
    ) -> Dict:
        """Teste de Granger Causality"""
        try:
            # Implementação simplificada usando correlação com lag
            best_p_value = 1.0
            best_lag = 0

            for lag in range(1, min(max_lag, len(cause_series) // 4)):
                if lag >= len(cause_series):
                    break

                # Série causa com lag vs série efeito
                cause_lagged = cause_series[:-lag] if lag > 0 else cause_series
                effect_current = effect_series[lag:]

                if len(cause_lagged) != len(effect_current):
                    continue

                # Correlação de Pearson
                if len(cause_lagged) >= 3:
                    correlation, p_value = stats.pearsonr(cause_lagged, effect_current)

                    if p_value < best_p_value:
                        best_p_value = p_value
                        best_lag = lag

            return {
                'p_value': best_p_value,
                'best_lag': best_lag
            }

        except Exception as e:
            logger.error('granger_causality_test_failed', error=str(e))
            return {'p_value': 1.0, 'best_lag': 0}

    def _calculate_lag_correlation(
        self,
        cause_series: List[float],
        effect_series: List[float],
        max_lag: int = 10
    ) -> Dict:
        """Calcular correlação com lag ótimo"""
        try:
            best_correlation = 0.0
            best_lag = 0

            for lag in range(max_lag):
                if lag >= len(cause_series):
                    break

                cause_lagged = cause_series[:-lag] if lag > 0 else cause_series
                effect_current = effect_series[lag:]

                if len(cause_lagged) != len(effect_current) or len(cause_lagged) < 2:
                    continue

                correlation, _ = stats.pearsonr(cause_lagged, effect_current)

                if abs(correlation) > abs(best_correlation):
                    best_correlation = correlation
                    best_lag = lag

            return {
                'correlation': best_correlation,
                'lag': best_lag
            }

        except Exception as e:
            logger.error('calculate_lag_correlation_failed', error=str(e))
            return {'correlation': 0.0, 'lag': 0}

    async def build_causal_graph(
        self,
        events: List[Dict],
        time_window: Dict
    ) -> Dict:
        """Construir grafo causal (DAG)"""
        try:
            # Criar grafo direcionado
            G = nx.DiGraph()

            # Adicionar nós (eventos)
            for event in events:
                event_id = event.get('event_id', event.get('id', ''))
                if event_id:
                    G.add_node(event_id, **event)

            # Adicionar arestas baseadas em timestamps
            sorted_events = sorted(events, key=lambda x: x.get('timestamp', 0))

            for i, event1 in enumerate(sorted_events):
                event1_id = event1.get('event_id', event1.get('id', ''))
                event1_ts = event1.get('timestamp', 0)

                for event2 in sorted_events[i+1:]:
                    event2_id = event2.get('event_id', event2.get('id', ''))
                    event2_ts = event2.get('timestamp', 0)

                    # Se evento2 ocorre após evento1, pode haver causalidade
                    time_diff = event2_ts - event1_ts

                    # Janela de causalidade: até 60 segundos
                    if 0 < time_diff <= 60000:
                        # Adicionar aresta com peso baseado na proximidade temporal
                        weight = 1.0 / (1.0 + time_diff / 1000.0)
                        G.add_edge(event1_id, event2_id, weight=weight, time_diff=time_diff)

            # Verificar se é DAG (sem ciclos)
            is_dag = nx.is_directed_acyclic_graph(G)

            result = {
                'graph': {
                    'nodes': list(G.nodes()),
                    'edges': [
                        {
                            'source': u,
                            'target': v,
                            'weight': data.get('weight', 0),
                            'time_diff': data.get('time_diff', 0)
                        }
                        for u, v, data in G.edges(data=True)
                    ]
                },
                'is_dag': is_dag,
                'num_nodes': G.number_of_nodes(),
                'num_edges': G.number_of_edges()
            }

            logger.info('causal_graph_built', nodes=result['num_nodes'], edges=result['num_edges'])
            return result

        except Exception as e:
            logger.error('build_causal_graph_failed', error=str(e))
            return {'graph': {}, 'is_dag': False}

    async def find_root_causes(self, effect: str, graph: Dict) -> List[str]:
        """Encontrar causas raiz para um efeito"""
        try:
            # Reconstruir grafo NetworkX
            G = nx.DiGraph()

            for edge in graph.get('edges', []):
                G.add_edge(edge['source'], edge['target'], weight=edge.get('weight', 1.0))

            if effect not in G.nodes():
                return []

            # Encontrar todos os predecessores (nós que levam ao efeito)
            predecessors = list(nx.ancestors(G, effect))

            # Filtrar apenas as causas raiz (nós sem predecessores)
            root_causes = [
                node for node in predecessors
                if G.in_degree(node) == 0
            ]

            logger.info('root_causes_found', effect=effect, count=len(root_causes))
            return root_causes

        except Exception as e:
            logger.error('find_root_causes_failed', error=str(e))
            return []

    async def calculate_causal_effect(
        self,
        cause: str,
        effect: str,
        data: Dict
    ) -> float:
        """Calcular efeito causal (magnitude)"""
        try:
            time_series = data.get('time_series', [])
            if not time_series:
                return 0.0

            cause_values = [item.get(cause, 0) for item in time_series]
            effect_values = [item.get(effect, 0) for item in time_series]

            if not cause_values or not effect_values or len(cause_values) < 2:
                return 0.0

            # Regressão linear simples: effect = a + b * cause
            cause_arr = np.array(cause_values)
            effect_arr = np.array(effect_values)

            # Calcular coeficiente de regressão (slope)
            slope, intercept, r_value, p_value, std_err = stats.linregress(cause_arr, effect_arr)

            # O slope indica a magnitude do efeito causal
            # (quanto o efeito muda quando a causa muda em 1 unidade)
            causal_effect = slope

            logger.info(
                'causal_effect_calculated',
                cause=cause,
                effect=effect,
                magnitude=causal_effect,
                r_squared=r_value**2
            )

            return float(causal_effect)

        except Exception as e:
            logger.error('calculate_causal_effect_failed', error=str(e))
            return 0.0

    async def detect_confounders(
        self,
        cause: str,
        effect: str,
        data: Dict
    ) -> List[str]:
        """Detectar variáveis confundidoras"""
        try:
            time_series = data.get('time_series', [])
            confounders = data.get('confounders', [])

            if not time_series or not confounders:
                return []

            detected_confounders = []

            cause_values = [item.get(cause, 0) for item in time_series]
            effect_values = [item.get(effect, 0) for item in time_series]

            for confounder in confounders:
                confounder_values = [item.get(confounder, 0) for item in time_series]

                if not confounder_values or len(confounder_values) < 3:
                    continue

                # Correlação do confounder com causa
                corr_cause, p_cause = stats.pearsonr(confounder_values, cause_values)

                # Correlação do confounder com efeito
                corr_effect, p_effect = stats.pearsonr(confounder_values, effect_values)

                # Se confounder está correlacionado com ambos, pode ser confundidor
                if abs(corr_cause) > 0.5 and abs(corr_effect) > 0.5:
                    detected_confounders.append(confounder)

            logger.info('confounders_detected', count=len(detected_confounders))
            return detected_confounders

        except Exception as e:
            logger.error('detect_confounders_failed', error=str(e))
            return []

    async def generate_causal_explanation(
        self,
        cause: str,
        effect: str,
        chain: List[str]
    ) -> str:
        """Gerar explicação causal em linguagem natural"""
        try:
            if not chain:
                return f'{cause} causa {effect} diretamente.'

            explanation = f'{cause} '

            for i, node in enumerate(chain):
                if i == 0:
                    explanation += f'leva a {node}, '
                elif i == len(chain) - 1:
                    explanation += f'o que finalmente resulta em {effect}.'
                else:
                    explanation += f'que causa {node}, '

            return explanation

        except Exception as e:
            logger.error('generate_causal_explanation_failed', error=str(e))
            return ''
