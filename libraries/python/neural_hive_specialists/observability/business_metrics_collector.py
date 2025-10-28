"""
BusinessMetricsCollector: Coleta métricas de negócio correlacionando opiniões com decisões de consenso.

Responsável por:
- Consultar opiniões do ledger e decisões de consenso
- Correlacionar via opinion_id
- Calcular métricas de concordância, FP/FN, precision/recall, F1
- Calcular valor de negócio gerado
- Atualizar métricas Prometheus
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import structlog
import asyncio
from collections import defaultdict
import time

logger = structlog.get_logger(__name__)


class BusinessMetricsCollector:
    """Coleta métricas de negócio correlacionando opiniões com decisões de consenso."""

    def __init__(self, config: Dict[str, Any], metrics_registry: Dict[str, Any]):
        """
        Inicializa coletor de business metrics.

        Args:
            config: Configuração do sistema
            metrics_registry: Registry de SpecialistMetrics para todos os especialistas
        """
        self.config = config
        self.metrics_registry = metrics_registry

        # Configurações de MongoDB
        self.ledger_uri = config.get('mongodb_uri')
        self.ledger_database = config.get('mongodb_database', 'neural_hive')
        self.ledger_collection_name = config.get('mongodb_opinions_collection', 'specialist_opinions')

        self.consensus_uri = config.get('consensus_mongodb_uri', self.ledger_uri)
        self.consensus_database = config.get('consensus_mongodb_database', 'neural_hive')
        self.consensus_collection_name = config.get('consensus_collection_name', 'consensus_decisions')
        self.consensus_timestamp_field = config.get('consensus_timestamp_field', 'timestamp')

        # Configurações de business metrics
        self.enable_business_metrics = config.get('enable_business_metrics', True)
        self.window_hours = config.get('business_metrics_window_hours', 24)
        self.enable_business_value_tracking = config.get('enable_business_value_tracking', False)
        self.execution_ticket_api_url = config.get('execution_ticket_api_url')

        # Clients MongoDB (lazy initialization)
        self._ledger_client: Optional[MongoClient] = None
        self._consensus_client: Optional[MongoClient] = None

        # Cache de resultados (5 minutos)
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: float = 0
        self._cache_ttl: int = 300  # 5 minutos

        logger.info(
            "BusinessMetricsCollector initialized",
            window_hours=self.window_hours,
            enable_business_value=self.enable_business_value_tracking
        )

    @property
    def ledger_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB do ledger."""
        if self._ledger_client is None:
            self._ledger_client = MongoClient(
                self.ledger_uri,
                serverSelectionTimeoutMS=5000
            )
        return self._ledger_client

    @property
    def consensus_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB do consensus."""
        if self._consensus_client is None:
            self._consensus_client = MongoClient(
                self.consensus_uri,
                serverSelectionTimeoutMS=5000
            )
        return self._consensus_client

    @property
    def ledger_collection(self):
        """Retorna collection de opiniões do ledger."""
        db = self.ledger_client[self.ledger_database]
        return db[self.ledger_collection_name]

    @property
    def consensus_collection(self):
        """Retorna collection de decisões de consenso."""
        db = self.consensus_client[self.consensus_database]
        return db[self.consensus_collection_name]

    def collect_business_metrics(self, window_hours: Optional[int] = None) -> Dict[str, Any]:
        """
        Coleta métricas de negócio para janela de tempo especificada.

        Args:
            window_hours: Janela de tempo em horas (default: self.window_hours)

        Returns:
            Dicionário com estatísticas de coleta
        """
        if not self.enable_business_metrics:
            logger.info("Business metrics collection disabled")
            return {'status': 'disabled'}

        # Verificar cache
        current_time = time.time()
        if current_time - self._cache_timestamp < self._cache_ttl and self._cache:
            logger.debug("Using cached business metrics", cache_age_seconds=current_time - self._cache_timestamp)
            return self._cache

        start_time = time.time()
        window_hours = window_hours or self.window_hours

        try:
            logger.info("Starting business metrics collection", window_hours=window_hours)

            # 1. Buscar opiniões e decisões
            opinions = self._fetch_opinions(window_hours)
            decisions = self._fetch_consensus_decisions(window_hours)

            logger.info(
                "Data fetched",
                opinions_count=len(opinions),
                decisions_count=len(decisions)
            )

            if not opinions or not decisions:
                logger.warning("No data to process", opinions=len(opinions), decisions=len(decisions))
                return {'status': 'no_data', 'opinions': len(opinions), 'decisions': len(decisions)}

            # 2. Correlacionar opiniões com decisões
            correlations = self._correlate_opinions_with_decisions(opinions, decisions)

            logger.info("Correlations created", total_correlations=len(correlations))

            # 3. Calcular métricas por especialista
            metrics_by_specialist = defaultdict(lambda: {
                'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0,
                'total': 0, 'correlations': []
            })

            for corr in correlations:
                specialist_type = corr['specialist_type']
                category = corr['category']

                if category in ['tp', 'tn', 'fp', 'fn']:
                    metrics_by_specialist[specialist_type][category] += 1

                metrics_by_specialist[specialist_type]['total'] += 1
                metrics_by_specialist[specialist_type]['correlations'].append(corr)

            # 4. Calcular métricas derivadas e atualizar Prometheus
            for specialist_type, confusion_matrix in metrics_by_specialist.items():
                derived_metrics = self._calculate_derived_metrics(confusion_matrix)
                self._update_prometheus_metrics(specialist_type, confusion_matrix, derived_metrics)

            # 4.5. Calcular métricas de A/B test por variante (se aplicável)
            ab_test_metrics = self._calculate_ab_test_metrics(correlations)
            if ab_test_metrics:
                self._update_ab_test_prometheus_metrics(ab_test_metrics)
                logger.info(
                    "A/B test metrics calculated",
                    variants_processed=len(ab_test_metrics)
                )

            # 5. Calcular valor de negócio (se habilitado)
            if self.enable_business_value_tracking and self.execution_ticket_api_url:
                plan_ids = [d.get('plan_id') for d in decisions if d.get('plan_id')]
                if plan_ids:
                    execution_outcomes = self._fetch_execution_outcomes(plan_ids)
                    business_value = self._calculate_business_value(correlations, execution_outcomes)

                    for specialist_type, value in business_value.items():
                        if specialist_type in self.metrics_registry:
                            self.metrics_registry[specialist_type].increment_business_value(value)

            duration = time.time() - start_time

            result = {
                'status': 'success',
                'window_hours': window_hours,
                'opinions_processed': len(opinions),
                'decisions_processed': len(decisions),
                'correlations_created': len(correlations),
                'specialists_updated': len(metrics_by_specialist),
                'duration_seconds': duration
            }

            # Atualizar cache
            self._cache = result
            self._cache_timestamp = current_time

            logger.info(
                "Business metrics collection completed",
                **result
            )

            return result

        except Exception as e:
            logger.error(
                "Error collecting business metrics",
                error=str(e),
                exc_info=True
            )
            return {'status': 'error', 'error': str(e)}

    def _fetch_opinions(self, window_hours: int) -> List[Dict]:
        """
        Busca opiniões do ledger para janela de tempo especificada.

        Args:
            window_hours: Janela de tempo em horas

        Returns:
            Lista de opiniões
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)

            query = {
                'evaluated_at': {'$gte': cutoff_time},
                'opinion_id': {'$exists': True}
            }

            opinions = list(self.ledger_collection.find(query))

            logger.debug(
                "Opinions fetched",
                count=len(opinions),
                window_hours=window_hours
            )

            return opinions

        except PyMongoError as e:
            logger.error("Error fetching opinions", error=str(e))
            return []

    def _fetch_consensus_decisions(self, window_hours: int) -> List[Dict]:
        """
        Busca decisões de consenso para janela de tempo especificada.

        Args:
            window_hours: Janela de tempo em horas

        Returns:
            Lista de decisões
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)

            query = {
                self.consensus_timestamp_field: {'$gte': cutoff_time},
                'specialist_votes': {'$exists': True}
            }

            decisions = list(self.consensus_collection.find(query))

            logger.debug(
                "Consensus decisions fetched",
                count=len(decisions),
                window_hours=window_hours
            )

            return decisions

        except PyMongoError as e:
            logger.error("Error fetching consensus decisions", error=str(e))
            return []

    def _correlate_opinions_with_decisions(
        self,
        opinions: List[Dict],
        decisions: List[Dict]
    ) -> List[Dict]:
        """
        Correlaciona opiniões com decisões de consenso via opinion_id.

        Args:
            opinions: Lista de opiniões
            decisions: Lista de decisões

        Returns:
            Lista de correlações com categoria (tp, tn, fp, fn)
        """
        # Criar índice de opiniões por opinion_id
        opinions_by_id = {
            op.get('opinion_id'): op
            for op in opinions
            if op.get('opinion_id')
        }

        correlations = []

        for decision in decisions:
            final_decision = decision.get('final_decision', '').upper()
            specialist_votes = decision.get('specialist_votes', [])

            for vote in specialist_votes:
                opinion_id = vote.get('opinion_id')
                if not opinion_id or opinion_id not in opinions_by_id:
                    continue

                opinion = opinions_by_id[opinion_id]
                specialist_recommendation = vote.get('recommendation', '').lower()
                specialist_type = vote.get('specialist_type')

                # Classificar como TP/TN/FP/FN
                category = self._classify_prediction(
                    specialist_recommendation,
                    final_decision
                )

                # Extrair variante A/B da opinião, se disponível
                ab_test_variant = opinion.get('opinion', {}).get('metadata', {}).get('ab_test_variant')

                correlation_data = {
                    'opinion_id': opinion_id,
                    'specialist_type': specialist_type,
                    'specialist_recommendation': specialist_recommendation,
                    'final_decision': final_decision,
                    'category': category,
                    'plan_id': decision.get('plan_id'),
                    'decision_id': decision.get('_id')
                }

                # Incluir informação completa da opinião para acesso aos metadados de A/B test
                if ab_test_variant:
                    correlation_data['opinion'] = opinion

                correlations.append(correlation_data)

        logger.debug(
            "Opinions correlated with decisions",
            total_correlations=len(correlations)
        )

        return correlations

    def _classify_prediction(
        self,
        specialist_recommendation: str,
        final_decision: str
    ) -> str:
        """
        Classifica predição como TP, TN, FP ou FN.

        Args:
            specialist_recommendation: Recomendação do especialista
            final_decision: Decisão final do consenso

        Returns:
            Categoria: 'tp', 'tn', 'fp', 'fn', ou 'unknown'
        """
        # Normalizar strings
        spec_rec = specialist_recommendation.lower().strip()
        final_dec = final_decision.upper().strip()

        # Mapeamento de recomendações para positivo/negativo
        positive_recommendations = ['approve', 'approved', 'accept']
        negative_recommendations = ['reject', 'rejected', 'deny']

        spec_is_positive = spec_rec in positive_recommendations
        spec_is_negative = spec_rec in negative_recommendations

        final_is_positive = final_dec in ['APPROVE', 'APPROVED', 'ACCEPT']
        final_is_negative = final_dec in ['REJECT', 'REJECTED', 'DENY']

        # Ignorar recomendações de review ou conditional
        if spec_rec in ['review_required', 'conditional']:
            return 'unknown'

        # Classificar
        if spec_is_positive and final_is_positive:
            return 'tp'  # True Positive
        elif spec_is_negative and final_is_negative:
            return 'tn'  # True Negative
        elif spec_is_positive and final_is_negative:
            return 'fp'  # False Positive
        elif spec_is_negative and final_is_positive:
            return 'fn'  # False Negative
        else:
            return 'unknown'

    def _calculate_derived_metrics(self, confusion_matrix: Dict) -> Dict[str, float]:
        """
        Calcula métricas derivadas da confusion matrix.

        Args:
            confusion_matrix: Dict com 'tp', 'tn', 'fp', 'fn'

        Returns:
            Dict com métricas derivadas
        """
        tp = confusion_matrix['tp']
        tn = confusion_matrix['tn']
        fp = confusion_matrix['fp']
        fn = confusion_matrix['fn']

        total = tp + tn + fp + fn

        if total == 0:
            return {
                'agreement_rate': 0.0,
                'fp_rate': 0.0,
                'fn_rate': 0.0,
                'precision': 0.0,
                'recall': 0.0,
                'f1_score': 0.0
            }

        # Agreement Rate (concordância)
        agreement_rate = (tp + tn) / total if total > 0 else 0.0

        # False Positive Rate
        fp_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        # False Negative Rate
        fn_rate = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        # Precision
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

        # Recall
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        # F1 Score
        f1_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return {
            'agreement_rate': agreement_rate,
            'fp_rate': fp_rate,
            'fn_rate': fn_rate,
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score
        }

    def _update_prometheus_metrics(
        self,
        specialist_type: str,
        confusion_matrix: Dict,
        derived_metrics: Dict
    ):
        """
        Atualiza métricas Prometheus para especialista.

        Args:
            specialist_type: Tipo do especialista
            confusion_matrix: Confusion matrix
            derived_metrics: Métricas derivadas
        """
        if specialist_type not in self.metrics_registry:
            logger.warning(
                "Specialist not in metrics registry",
                specialist_type=specialist_type
            )
            return

        metrics = self.metrics_registry[specialist_type]

        # Atualizar confusion matrix counters
        metrics.business_true_positives_total.labels(specialist_type).inc(confusion_matrix['tp'])
        metrics.business_true_negatives_total.labels(specialist_type).inc(confusion_matrix['tn'])
        metrics.business_false_positives_total.labels(specialist_type).inc(confusion_matrix['fp'])
        metrics.business_false_negatives_total.labels(specialist_type).inc(confusion_matrix['fn'])

        # Atualizar métricas derivadas (gauges)
        metrics.set_consensus_agreement_rate(derived_metrics['agreement_rate'])
        metrics.set_false_positive_rate(derived_metrics['fp_rate'])
        metrics.set_false_negative_rate(derived_metrics['fn_rate'])
        metrics.set_precision_score(derived_metrics['precision'])
        metrics.set_recall_score(derived_metrics['recall'])
        metrics.set_f1_score(derived_metrics['f1_score'])

        # Atualizar timestamp
        metrics.update_business_metrics_timestamp()

        logger.debug(
            "Prometheus metrics updated",
            specialist_type=specialist_type,
            **derived_metrics
        )

    def _fetch_execution_outcomes(self, plan_ids: List[str]) -> Dict[str, str]:
        """
        Busca status de execução de tickets da Execution Ticket API.

        Args:
            plan_ids: Lista de IDs de planos

        Returns:
            Dict mapeando plan_id para status ('COMPLETED', 'FAILED', etc)
        """
        if not self.execution_ticket_api_url:
            logger.debug("execution_ticket_api_url not configured, skipping execution outcomes fetch")
            return {}

        if not plan_ids:
            return {}

        try:
            import requests

            # Endpoint para buscar múltiplos tickets por plan_ids
            url = f"{self.execution_ticket_api_url}/api/v1/tickets/by-plans"

            # Timeout de 10 segundos
            response = requests.post(
                url,
                json={'plan_ids': plan_ids},
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            if response.status_code == 200:
                tickets_data = response.json()
                outcomes = {}

                # Mapear plan_id para status de execução
                for ticket in tickets_data.get('tickets', []):
                    plan_id = ticket.get('plan_id')
                    status = ticket.get('status', 'UNKNOWN').upper()

                    if plan_id:
                        outcomes[plan_id] = status

                logger.debug(
                    "Execution outcomes fetched",
                    total_plan_ids=len(plan_ids),
                    outcomes_found=len(outcomes)
                )

                return outcomes

            else:
                logger.warning(
                    "Failed to fetch execution outcomes",
                    status_code=response.status_code,
                    reason=response.text[:200]
                )
                return {}

        except requests.exceptions.Timeout:
            logger.error(
                "Timeout fetching execution outcomes",
                timeout_seconds=10
            )
            return {}

        except requests.exceptions.RequestException as e:
            logger.error(
                "Error fetching execution outcomes",
                error=str(e),
                api_url=self.execution_ticket_api_url
            )
            return {}

        except Exception as e:
            logger.error(
                "Unexpected error fetching execution outcomes",
                error=str(e),
                exc_info=True
            )
            return {}

    def _calculate_business_value(
        self,
        correlations: List[Dict],
        execution_outcomes: Dict[str, str]
    ) -> Dict[str, float]:
        """
        Calcula valor de negócio gerado por especialista.

        Args:
            correlations: Lista de correlações
            execution_outcomes: Status de execução por plan_id

        Returns:
            Dict mapeando specialist_type para valor gerado
        """
        business_value = defaultdict(float)

        for corr in correlations:
            # Contar apenas aprovações que foram executadas com sucesso
            if (
                corr['category'] == 'tp' and
                corr['final_decision'] == 'APPROVE'
            ):
                plan_id = corr.get('plan_id')
                if plan_id and execution_outcomes.get(plan_id) == 'COMPLETED':
                    specialist_type = corr['specialist_type']
                    business_value[specialist_type] += 1.0

        logger.debug(
            "Business value calculated",
            business_value=dict(business_value)
        )

        return dict(business_value)

    def _calculate_ab_test_metrics(self, correlations: List[Dict]) -> Dict[str, Dict]:
        """
        Calcula métricas de A/B test por variante.

        Filtra correlações que têm metadata de A/B test e agrupa por variante
        para calcular confusion matrix e métricas derivadas separadamente.

        Args:
            correlations: Lista de correlações entre opiniões e decisões

        Returns:
            Dict de métricas por variante {specialist_type: {variant: metrics}}
        """
        # Filtrar correlações com A/B test metadata
        ab_test_correlations = [
            corr for corr in correlations
            if corr.get('opinion', {}).get('metadata', {}).get('ab_test_variant')
        ]

        if not ab_test_correlations:
            logger.debug("Nenhuma correlação com A/B test metadata encontrada")
            return {}

        # Agrupar por specialist_type e variante
        metrics_by_variant = defaultdict(lambda: defaultdict(lambda: {
            'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0,
            'total': 0, 'correlations': []
        }))

        for corr in ab_test_correlations:
            specialist_type = corr['specialist_type']
            variant = corr['opinion']['metadata']['ab_test_variant']
            category = corr['category']

            if category in ['tp', 'tn', 'fp', 'fn']:
                metrics_by_variant[specialist_type][variant][category] += 1

            metrics_by_variant[specialist_type][variant]['total'] += 1
            metrics_by_variant[specialist_type][variant]['correlations'].append(corr)

        # Calcular métricas derivadas para cada variante
        result = {}
        for specialist_type, variants in metrics_by_variant.items():
            result[specialist_type] = {}
            for variant, confusion_matrix in variants.items():
                derived_metrics = self._calculate_derived_metrics(confusion_matrix)
                result[specialist_type][variant] = {
                    'confusion_matrix': confusion_matrix,
                    'derived_metrics': derived_metrics
                }

        logger.info(
            "A/B test metrics calculated",
            specialist_types=list(result.keys()),
            total_variants=sum(len(v) for v in result.values())
        )

        return result

    def _update_ab_test_prometheus_metrics(self, ab_test_metrics: Dict[str, Dict]):
        """
        Atualiza métricas Prometheus de A/B test.

        Args:
            ab_test_metrics: Métricas por specialist_type e variante
        """
        for specialist_type, variants in ab_test_metrics.items():
            if specialist_type not in self.metrics_registry:
                logger.warning(
                    "Specialist type not in metrics registry",
                    specialist_type=specialist_type
                )
                continue

            metrics = self.metrics_registry[specialist_type]

            for variant, variant_data in variants.items():
                derived = variant_data['derived_metrics']
                confusion = variant_data['confusion_matrix']

                # Atualizar agreement rate
                metrics.set_ab_test_variant_agreement(
                    variant,
                    derived['agreement_rate']
                )

                # Atualizar sample size
                metrics.set_ab_test_sample_size(
                    variant,
                    confusion['total']
                )

                logger.debug(
                    "A/B test Prometheus metrics updated",
                    specialist_type=specialist_type,
                    variant=variant,
                    agreement_rate=derived['agreement_rate'],
                    sample_size=confusion['total']
                )

        # Calcular significância estatística se ambas variantes presentes
        for specialist_type, variants in ab_test_metrics.items():
            if 'model_a' in variants and 'model_b' in variants:
                significance = self._calculate_statistical_significance(
                    variants['model_a'],
                    variants['model_b']
                )

                logger.info(
                    "Statistical significance calculated",
                    specialist_type=specialist_type,
                    p_value=significance.get('p_value'),
                    is_significant=significance.get('is_significant'),
                    winner=significance.get('winner')
                )

    def _calculate_statistical_significance(
        self,
        variant_a_data: Dict,
        variant_b_data: Dict
    ) -> Dict[str, Any]:
        """
        Calcula significância estatística entre variantes A e B.

        Usa chi-square test para comparar confusion matrices.

        Args:
            variant_a_data: Dados da variante A
            variant_b_data: Dados da variante B

        Returns:
            Dict com p_value, is_significant, winner
        """
        try:
            from scipy.stats import chi2_contingency

            # Montar tabela de contingência
            confusion_a = variant_a_data['confusion_matrix']
            confusion_b = variant_b_data['confusion_matrix']

            # [[tp_a, fn_a], [tp_b, fn_b]]
            contingency_table = [
                [confusion_a['tp'], confusion_a['fn']],
                [confusion_b['tp'], confusion_b['fn']]
            ]

            # Executar chi-square test
            chi2, p_value, dof, expected = chi2_contingency(contingency_table)

            is_significant = p_value < 0.05

            # Determinar vencedor baseado em agreement rate
            agreement_a = variant_a_data['derived_metrics']['agreement_rate']
            agreement_b = variant_b_data['derived_metrics']['agreement_rate']

            if is_significant:
                winner = 'model_b' if agreement_b > agreement_a else 'model_a'
            else:
                winner = None

            return {
                'p_value': float(p_value),
                'chi2': float(chi2),
                'is_significant': is_significant,
                'winner': winner,
                'agreement_a': agreement_a,
                'agreement_b': agreement_b
            }

        except ImportError:
            logger.warning("scipy not available, cannot calculate statistical significance")
            return {
                'p_value': None,
                'is_significant': False,
                'winner': None,
                'error': 'scipy_not_installed'
            }
        except Exception as e:
            logger.error(
                "Error calculating statistical significance",
                error=str(e)
            )
            return {
                'p_value': None,
                'is_significant': False,
                'winner': None,
                'error': str(e)
            }

    def close(self):
        """Fecha conexões MongoDB."""
        if self._ledger_client:
            self._ledger_client.close()
        if self._consensus_client:
            self._consensus_client.close()

        logger.info("BusinessMetricsCollector connections closed")
