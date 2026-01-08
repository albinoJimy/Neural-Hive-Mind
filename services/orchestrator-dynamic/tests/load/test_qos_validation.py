"""
Testes de validação de QoS para IntelligentScheduler.

Valida que garantias de QoS são respeitadas sob carga:
- Priority scores respeitam pesos configurados
- EXACTLY_ONCE > AT_LEAST_ONCE > AT_MOST_ONCE
- SLA deadlines influenciam priorização
- Risk bands são respeitados
"""

import asyncio
import pytest
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import AsyncMock, MagicMock

from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.resource_allocator import ResourceAllocator
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def qos_test_config():
    """Config com pesos de prioridade explícitos."""
    config = MagicMock(spec=OrchestratorSettings)
    config.service_registry_cache_ttl_seconds = 60
    config.service_registry_timeout_seconds = 5
    # Pesos: risk 40%, qos 30%, sla 30%
    config.scheduler_priority_weights = {'risk': 0.4, 'qos': 0.3, 'sla': 0.3}
    config.enable_ml_enhanced_scheduling = False
    config.optimizer_forecast_horizon_minutes = 5
    config.CIRCUIT_BREAKER_ENABLED = False
    config.service_name = 'orchestrator-dynamic'
    return config


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock(spec=OrchestratorMetrics)
    return metrics


@pytest.fixture
def sample_workers() -> List[Dict[str, Any]]:
    """Workers mock."""
    return [
        {
            'agent_id': f'worker-{i:03d}',
            'agent_type': 'worker-agent',
            'score': 0.9,
            'capabilities': ['python', 'data-processing'],
            'status': 'HEALTHY',
        }
        for i in range(5)
    ]


def create_allocator(workers: List[Dict]) -> AsyncMock:
    """Cria ResourceAllocator mock."""
    allocator = AsyncMock(spec=ResourceAllocator)
    allocator.discover_workers = AsyncMock(return_value=workers)
    allocator.select_best_worker = MagicMock(return_value=workers[0] if workers else None)
    return allocator


def create_ticket(
    ticket_id: str,
    risk_band: str = 'normal',
    delivery_mode: str = 'AT_LEAST_ONCE',
    consistency: str = 'EVENTUAL',
    durability: str = 'PERSISTENT',
    deadline_hours: float = 1.0
) -> Dict[str, Any]:
    """Cria ticket com parâmetros específicos de QoS."""
    return {
        'ticket_id': ticket_id,
        'risk_band': risk_band,
        'qos': {
            'delivery_mode': delivery_mode,
            'consistency': consistency,
            'durability': durability
        },
        'sla': {
            'deadline': (datetime.utcnow() + timedelta(hours=deadline_hours)).isoformat(),
            'timeout_ms': int(deadline_hours * 3600000)
        },
        'required_capabilities': ['python', 'data-processing'],
        'namespace': 'default',
        'security_level': 'standard',
        'estimated_duration_ms': 1000,
        'created_at': datetime.utcnow().isoformat()
    }


class TestQoSDeliveryModeOrdering:
    """Testes de ordenação por delivery_mode."""

    @pytest.mark.asyncio
    async def test_exactly_once_higher_than_at_least_once(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida EXACTLY_ONCE > AT_LEAST_ONCE em priority score."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        # Tickets idênticos exceto delivery_mode
        exactly_once_scores = []
        at_least_once_scores = []

        for i in range(50):
            ticket_eo = create_ticket(f'eo-{i}', delivery_mode='EXACTLY_ONCE')
            ticket_al = create_ticket(f'al-{i}', delivery_mode='AT_LEAST_ONCE')

            result_eo = await scheduler.schedule_ticket(ticket_eo)
            result_al = await scheduler.schedule_ticket(ticket_al)

            exactly_once_scores.append(
                result_eo.get('allocation_metadata', {}).get('priority_score', 0)
            )
            at_least_once_scores.append(
                result_al.get('allocation_metadata', {}).get('priority_score', 0)
            )

        avg_eo = statistics.mean(exactly_once_scores)
        avg_al = statistics.mean(at_least_once_scores)

        assert avg_eo > avg_al, \
            f'EXACTLY_ONCE ({avg_eo:.4f}) deve ter score maior que AT_LEAST_ONCE ({avg_al:.4f})'

        print(f'\n[QoS Delivery Mode Ordering]')
        print(f'  EXACTLY_ONCE média: {avg_eo:.4f}')
        print(f'  AT_LEAST_ONCE média: {avg_al:.4f}')
        print(f'  Diferença: {avg_eo - avg_al:.4f}')

    @pytest.mark.asyncio
    async def test_at_least_once_higher_than_at_most_once(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida AT_LEAST_ONCE > AT_MOST_ONCE em priority score."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        at_least_once_scores = []
        at_most_once_scores = []

        for i in range(50):
            ticket_al = create_ticket(f'al-{i}', delivery_mode='AT_LEAST_ONCE')
            ticket_am = create_ticket(f'am-{i}', delivery_mode='AT_MOST_ONCE')

            result_al = await scheduler.schedule_ticket(ticket_al)
            result_am = await scheduler.schedule_ticket(ticket_am)

            at_least_once_scores.append(
                result_al.get('allocation_metadata', {}).get('priority_score', 0)
            )
            at_most_once_scores.append(
                result_am.get('allocation_metadata', {}).get('priority_score', 0)
            )

        avg_al = statistics.mean(at_least_once_scores)
        avg_am = statistics.mean(at_most_once_scores)

        assert avg_al > avg_am, \
            f'AT_LEAST_ONCE ({avg_al:.4f}) deve ter score maior que AT_MOST_ONCE ({avg_am:.4f})'

        print(f'\n[QoS Delivery Mode Ordering]')
        print(f'  AT_LEAST_ONCE média: {avg_al:.4f}')
        print(f'  AT_MOST_ONCE média: {avg_am:.4f}')
        print(f'  Diferença: {avg_al - avg_am:.4f}')

    @pytest.mark.asyncio
    async def test_full_delivery_mode_ordering(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida ordenação completa: EXACTLY_ONCE > AT_LEAST_ONCE > AT_MOST_ONCE."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        scores = {'EXACTLY_ONCE': [], 'AT_LEAST_ONCE': [], 'AT_MOST_ONCE': []}

        for i in range(100):
            for mode in scores.keys():
                ticket = create_ticket(f'{mode}-{i}', delivery_mode=mode)
                result = await scheduler.schedule_ticket(ticket)
                score = result.get('allocation_metadata', {}).get('priority_score', 0)
                scores[mode].append(score)

        avg_scores = {mode: statistics.mean(s) for mode, s in scores.items()}

        assert avg_scores['EXACTLY_ONCE'] > avg_scores['AT_LEAST_ONCE'] > avg_scores['AT_MOST_ONCE'], \
            f'Ordenação incorreta: {avg_scores}'

        print(f'\n[Ordenação Completa de Delivery Mode]')
        for mode in ['EXACTLY_ONCE', 'AT_LEAST_ONCE', 'AT_MOST_ONCE']:
            print(f'  {mode}: {avg_scores[mode]:.4f}')


class TestQoSConsistencyImpact:
    """Testes de impacto de consistency no QoS."""

    @pytest.mark.asyncio
    async def test_strong_consistency_higher_than_eventual(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida STRONG > EVENTUAL em priority score."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        strong_scores = []
        eventual_scores = []

        for i in range(50):
            ticket_strong = create_ticket(f'strong-{i}', consistency='STRONG')
            ticket_eventual = create_ticket(f'eventual-{i}', consistency='EVENTUAL')

            result_strong = await scheduler.schedule_ticket(ticket_strong)
            result_eventual = await scheduler.schedule_ticket(ticket_eventual)

            strong_scores.append(
                result_strong.get('allocation_metadata', {}).get('priority_score', 0)
            )
            eventual_scores.append(
                result_eventual.get('allocation_metadata', {}).get('priority_score', 0)
            )

        avg_strong = statistics.mean(strong_scores)
        avg_eventual = statistics.mean(eventual_scores)

        assert avg_strong > avg_eventual, \
            f'STRONG ({avg_strong:.4f}) deve ter score maior que EVENTUAL ({avg_eventual:.4f})'

        print(f'\n[QoS Consistency Impact]')
        print(f'  STRONG média: {avg_strong:.4f}')
        print(f'  EVENTUAL média: {avg_eventual:.4f}')
        print(f'  Diferença: {avg_strong - avg_eventual:.4f}')


class TestRiskBandPrioritization:
    """Testes de priorização por risk_band."""

    @pytest.mark.asyncio
    async def test_risk_band_ordering_under_load(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida ordenação: critical > high > normal > low."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        risk_bands = ['critical', 'high', 'normal', 'low']
        scores = {rb: [] for rb in risk_bands}

        # 100 tickets por risk band
        for i in range(100):
            for rb in risk_bands:
                ticket = create_ticket(f'{rb}-{i}', risk_band=rb)
                result = await scheduler.schedule_ticket(ticket)
                score = result.get('allocation_metadata', {}).get('priority_score', 0)
                scores[rb].append(score)

        avg_scores = {rb: statistics.mean(s) for rb, s in scores.items()}

        # Validar ordenação
        assert avg_scores['critical'] > avg_scores['high'], \
            f'critical ({avg_scores["critical"]:.4f}) > high ({avg_scores["high"]:.4f})'
        assert avg_scores['high'] > avg_scores['normal'], \
            f'high ({avg_scores["high"]:.4f}) > normal ({avg_scores["normal"]:.4f})'
        assert avg_scores['normal'] > avg_scores['low'], \
            f'normal ({avg_scores["normal"]:.4f}) > low ({avg_scores["low"]:.4f})'

        print(f'\n[Risk Band Ordering]')
        for rb in risk_bands:
            print(f'  {rb}: {avg_scores[rb]:.4f}')

    @pytest.mark.asyncio
    async def test_risk_band_weight_contribution(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida que risk_band contribui 40% do score conforme configurado."""
        priority_calc = PriorityCalculator(qos_test_config)

        # Risk weights esperados
        expected_weights = {
            'critical': 1.0,
            'high': 0.7,
            'normal': 0.5,
            'low': 0.3
        }

        for risk_band, expected_weight in expected_weights.items():
            ticket = create_ticket(f'{risk_band}-test', risk_band=risk_band)
            actual_weight = priority_calc._calculate_risk_weight(risk_band)

            assert actual_weight == expected_weight, \
                f'{risk_band}: esperado {expected_weight}, obtido {actual_weight}'

        print(f'\n[Risk Band Weights]')
        for rb, weight in expected_weights.items():
            print(f'  {rb}: {weight}')


class TestSLAUrgencyPrioritization:
    """Testes de priorização por urgência de SLA."""

    @pytest.mark.asyncio
    async def test_deadline_urgency_impact(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida que tickets próximos do deadline têm prioridade maior."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        # Tickets com diferentes deadlines
        urgency_levels = {
            'relaxed': 24.0,    # 24 horas
            'normal': 1.0,      # 1 hora
            'urgent': 0.1,      # 6 minutos
        }

        scores = {level: [] for level in urgency_levels}

        for i in range(50):
            for level, hours in urgency_levels.items():
                ticket = create_ticket(f'{level}-{i}', deadline_hours=hours)
                result = await scheduler.schedule_ticket(ticket)
                score = result.get('allocation_metadata', {}).get('priority_score', 0)
                scores[level].append(score)

        avg_scores = {level: statistics.mean(s) for level, s in scores.items()}

        # Urgent deve ter score maior (deadline mais próximo)
        assert avg_scores['urgent'] >= avg_scores['normal'], \
            f'urgent ({avg_scores["urgent"]:.4f}) >= normal ({avg_scores["normal"]:.4f})'

        print(f'\n[SLA Urgency Impact]')
        for level in ['urgent', 'normal', 'relaxed']:
            print(f'  {level}: {avg_scores[level]:.4f}')


class TestCombinedQoSFactors:
    """Testes de combinação de fatores de QoS."""

    @pytest.mark.asyncio
    async def test_combined_qos_priority_ordering(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida priorização combinando múltiplos fatores."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        # Ticket de alta prioridade
        high_priority_ticket = create_ticket(
            'high-priority',
            risk_band='critical',
            delivery_mode='EXACTLY_ONCE',
            consistency='STRONG',
            deadline_hours=0.1
        )

        # Ticket de baixa prioridade
        low_priority_ticket = create_ticket(
            'low-priority',
            risk_band='low',
            delivery_mode='AT_MOST_ONCE',
            consistency='EVENTUAL',
            deadline_hours=24.0
        )

        result_high = await scheduler.schedule_ticket(high_priority_ticket)
        result_low = await scheduler.schedule_ticket(low_priority_ticket)

        score_high = result_high.get('allocation_metadata', {}).get('priority_score', 0)
        score_low = result_low.get('allocation_metadata', {}).get('priority_score', 0)

        assert score_high > score_low, \
            f'High priority ({score_high:.4f}) deve ser > low priority ({score_low:.4f})'

        # Diferença significativa esperada
        difference = score_high - score_low
        assert difference > 0.3, \
            f'Diferença deve ser > 0.3, obtido: {difference:.4f}'

        print(f'\n[Combined QoS Factors]')
        print(f'  High priority score: {score_high:.4f}')
        print(f'  Low priority score: {score_low:.4f}')
        print(f'  Diferença: {difference:.4f}')

    @pytest.mark.asyncio
    async def test_mixed_qos_load_distribution(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida distribuição sob carga com QoS misto."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        # Gerar 200 tickets com QoS variado
        tickets = []
        risk_bands = ['critical', 'high', 'normal', 'low']
        delivery_modes = ['EXACTLY_ONCE', 'AT_LEAST_ONCE', 'AT_MOST_ONCE']

        for i in range(200):
            ticket = create_ticket(
                f'mixed-{i}',
                risk_band=risk_bands[i % 4],
                delivery_mode=delivery_modes[i % 3]
            )
            tickets.append(ticket)

        # Processar concorrentemente
        async def process(ticket):
            result = await scheduler.schedule_ticket(ticket)
            return result.get('allocation_metadata', {}).get('priority_score', 0)

        scores = await asyncio.gather(*[process(t) for t in tickets])

        # Estatísticas de distribuição
        mean_score = statistics.mean(scores)
        stdev_score = statistics.stdev(scores)
        min_score = min(scores)
        max_score = max(scores)

        # Validar distribuição razoável
        assert min_score > 0, 'Todos scores devem ser > 0'
        assert max_score <= 1.0, 'Todos scores devem ser <= 1.0'
        assert stdev_score > 0.05, f'Deve haver variação nos scores, stdev: {stdev_score:.4f}'

        print(f'\n[Mixed QoS Load Distribution]')
        print(f'  Tickets: 200')
        print(f'  Média: {mean_score:.4f}')
        print(f'  Desvio Padrão: {stdev_score:.4f}')
        print(f'  Min: {min_score:.4f}')
        print(f'  Max: {max_score:.4f}')


class TestQoSWeightsValidation:
    """Testes de validação de pesos de QoS."""

    @pytest.mark.asyncio
    async def test_qos_weight_30_percent_contribution(
        self,
        qos_test_config,
        mock_metrics,
        sample_workers
    ):
        """Valida que QoS contribui aproximadamente 30% do score total."""
        priority_calc = PriorityCalculator(qos_test_config)
        allocator = create_allocator(sample_workers)

        scheduler = IntelligentScheduler(
            config=qos_test_config,
            metrics=mock_metrics,
            priority_calculator=priority_calc,
            resource_allocator=allocator
        )

        # Tickets com mesmo risk_band e SLA, variando apenas QoS
        ticket_max_qos = create_ticket(
            'max-qos',
            risk_band='normal',
            delivery_mode='EXACTLY_ONCE',
            consistency='STRONG',
            durability='PERSISTENT'
        )

        ticket_min_qos = create_ticket(
            'min-qos',
            risk_band='normal',
            delivery_mode='AT_MOST_ONCE',
            consistency='EVENTUAL',
            durability='EPHEMERAL'
        )

        result_max = await scheduler.schedule_ticket(ticket_max_qos)
        result_min = await scheduler.schedule_ticket(ticket_min_qos)

        score_max = result_max.get('allocation_metadata', {}).get('priority_score', 0)
        score_min = result_min.get('allocation_metadata', {}).get('priority_score', 0)

        # Diferença deve ser aproximadamente 30% * (max_qos_weight - min_qos_weight)
        # max_qos_weight = 1.0 * 1.0 * 1.0 = 1.0
        # min_qos_weight = 0.5 * 0.85 * 0.8 = 0.34
        # Contribuição esperada: 0.3 * (1.0 - 0.34) = 0.198
        expected_diff_approx = 0.3 * (1.0 - 0.34)
        actual_diff = score_max - score_min

        # Tolerância de 20%
        assert abs(actual_diff - expected_diff_approx) < 0.05, \
            f'Diferença ({actual_diff:.4f}) deve ser próxima de {expected_diff_approx:.4f}'

        print(f'\n[QoS Weight Validation]')
        print(f'  Score max QoS: {score_max:.4f}')
        print(f'  Score min QoS: {score_min:.4f}')
        print(f'  Diferença real: {actual_diff:.4f}')
        print(f'  Diferença esperada: ~{expected_diff_approx:.4f}')
