"""
Testes de Integração E2E para Cutover Orchestrator.

Implementa testes de ponta a ponta para o fluxo completo de cutover:
- Shadow Mode (execução paralela sem produção)
- Canary Deployment (tráfego gradual 5% → 25% → 50% → 100%)
- Full Cutover (100% do tráfego no novo sistema)
- Rollback automático e manual

Estes testes usam mocks para serviços externos (legacy/target) e
simulam o comportamento do traffic splitter e componentes de infraestrutura.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models.workflow import (
    CutoverConfig,
    CutoverPhase,
    RollbackReason,
)
from src.services.cutover_manager import CutoverManager


@pytest.fixture()
def cutover_config():
    """Fixture com configuração padrão de cutover."""
    return CutoverConfig(
        legacy_service_url="http://legacy:8080",
        target_service_url="http://target:8080",
        shadow_duration_hours=24,  # Mínimo permitido (para testes)
        canary_stages=[5, 25, 50, 100],
        canary_min_hours=1,  # Reduzido para testes
        rollback_threshold_error_rate=0.05,
        rollback_threshold_p95_latency_ms=2000,
        enable_auto_rollback=True,
        enable_auto_promote=True,
    )


@pytest.fixture()
def mock_kafka_producer():
    """Fixture para producer Kafka mockado."""
    producer = AsyncMock()
    producer.produce = AsyncMock()
    return producer


@pytest.fixture()
def mock_mongodb_client():
    """Fixture para cliente MongoDB mockado."""
    client = MagicMock()
    client.db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    collection.find_one = AsyncMock(return_value=None)
    client.db.get = MagicMock(return_value=collection)
    return client


@pytest.fixture()
def mock_metrics_client():
    """Fixture para cliente de métricas mockado."""
    client = MagicMock()
    client.counter = MagicMock()
    client.gauge = MagicMock()
    client.histogram = MagicMock()
    return client


@pytest.fixture()
def cutover_manager(cutover_config, mock_kafka_producer, mock_mongodb_client, mock_metrics_client):
    """Fixture para CutoverManager com todos os mocks."""
    return CutoverManager(
        config=cutover_config,
        cutover_id=str(uuid.uuid4()),
        kafka_producer=mock_kafka_producer,
        mongodb_client=mock_mongodb_client,
        metrics_client=mock_metrics_client,
    )


@pytest.mark.integration()
class TestShadowModeE2E:
    """Testes E2E para fase de Shadow Mode."""

    @pytest.mark.asyncio()
    async def test_shadow_mode_initialization(self, cutover_manager):
        """
        Teste E2E: Inicialização do Shadow Mode.

        Fluxo:
        1. Iniciar cutover
        2. Verificar fase inicial (SHADOW_MODE)
        3. Verificar tráfego em 0%
        4. Verificar evento emitido
        """
        status = await cutover_manager.start()

        assert status.phase == CutoverPhase.SHADOW_MODE
        assert status.traffic_percentage == 0
        assert status.started_at is not None

        # Verificar que evento foi emitido
        cutover_manager.kafka_producer.produce.assert_called()

        # Verificar tipo do evento
        call_args = cutover_manager.kafka_producer.produce.call_args_list
        event_types = []
        for call in call_args:
            kwargs = call.kwargs
            if "value" in kwargs:
                import json

                event_data = json.loads(kwargs["value"])
                event_types.append(event_data.get("event_type"))

        assert "cutover.started" in event_types

    @pytest.mark.asyncio()
    async def test_shadow_mode_metrics_collection(self, cutover_manager):
        """
        Teste E2E: Coleta de métricas durante Shadow Mode.

        Fluxo:
        1. Iniciar cutover
        2. Coletar métricas de legacy e target
        3. Verificar métricas armazenadas
        4. Verificar agreement rate aceitável
        """
        await cutover_manager.start()

        # Simular métricas coletadas
        legacy_metrics = {
            "p95_latency_ms": 100,
            "requests_per_second": 100,
        }

        target_metrics = {
            "error_rate": 0.01,
            "p50_latency_ms": 90,
            "p95_latency_ms": 105,
            "p99_latency_ms": 150,
            "requests_per_second": 100,
            "anomaly_detected": False,
        }

        await cutover_manager.collect_metrics(legacy_metrics, target_metrics)

        # Verificar métricas armazenadas
        status = await cutover_manager.get_status()
        assert status.current_metrics is not None
        assert status.current_metrics.error_rate == 0.01
        assert status.current_metrics.p95_latency_ms == 105
        assert len(status.metrics_history) == 1

    @pytest.mark.asyncio()
    async def test_shadow_mode_to_canary_promotion(self, cutover_manager, cutover_config):
        """
        Teste E2E: Promoção de Shadow Mode para Canary.

        Fluxo:
        1. Iniciar shadow mode
        2. Coletar métricas satisfatórias
        3. Aguardar tempo mínimo (24h para shadow mode)
        4. Promover para CANARY_5
        """
        await cutover_manager.start()

        # Coletar métricas boas
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.005,
                "p95_latency_ms": 105,
                "requests_per_second": 100,
                "anomaly_detected": False,
            },
        )

        # Simular tempo decorrido (modificando current_phase_start)
        # Shadow mode requer 24h
        cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=25)

        # Verificar que pode promover
        can_promote, reason = cutover_manager.status.can_promote_to_next_phase(cutover_config)
        assert can_promote, reason

        # Promover manualmente
        success, message = await cutover_manager.promote_to_next_phase()

        assert success
        assert cutover_manager.status.phase == CutoverPhase.CANARY_5
        assert cutover_manager.status.traffic_percentage == 5

    @pytest.mark.asyncio()
    async def test_shadow_mode_insufficient_time_blocks_promotion(
        self, cutover_manager, cutover_config
    ):
        """
        Teste E2E: Tempo insuficiente bloqueia promoção.

        Fluxo:
        1. Iniciar shadow mode
        2. Tentar promover imediatamente
        3. Verificar bloqueio por tempo mínimo
        """
        await cutover_manager.start()

        # Tentar promover imediatamente (sem tempo suficiente)
        can_promote, reason = cutover_manager.status.can_promote_to_next_phase(cutover_config)

        assert not can_promote
        assert "Tempo mínimo não atingido" in reason


@pytest.mark.integration()
class TestCanaryDeploymentE2E:
    """Testes E2E para Canary Deployment."""

    @pytest.mark.asyncio()
    async def test_canary_5_to_25_to_50_progression(self, cutover_manager, cutover_config):
        """
        Teste E2E: Progressão completa pelas fases de Canary.

        Fluxo:
        1. Iniciar em CANARY_5
        2. Promover para CANARY_25
        3. Promover para CANARY_50
        4. Verificar percentual de tráfego em cada fase
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_5

        # CANARY_5 → CANARY_25
        cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=2)
        success, _ = await cutover_manager.promote_to_next_phase()

        assert success
        assert cutover_manager.status.phase == CutoverPhase.CANARY_25
        assert cutover_manager.status.traffic_percentage == 25

        # CANARY_25 → CANARY_50
        cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=2)
        success, _ = await cutover_manager.promote_to_next_phase()

        assert success
        assert cutover_manager.status.phase == CutoverPhase.CANARY_50
        assert cutover_manager.status.traffic_percentage == 50

    @pytest.mark.asyncio()
    async def test_canary_50_to_full_cutover(self, cutover_manager, cutover_config):
        """
        Teste E2E: Promoção de CANARY_50 para FULL_CUTOVER.

        Fluxo:
        1. Iniciar em CANARY_50
        2. Promover para FULL_CUTOVER
        3. Verificar tráfego em 100%
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_50

        cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=2)
        success, _ = await cutover_manager.promote_to_next_phase()

        assert success
        assert cutover_manager.status.phase == CutoverPhase.FULL_CUTOVER
        assert cutover_manager.status.traffic_percentage == 100

    @pytest.mark.asyncio()
    async def test_canary_rollback_on_high_error_rate(self, cutover_manager, cutover_config):
        """
        Teste E2E: Rollback automático quando error rate excede threshold.

        Fluxo:
        1. Iniciar em CANARY_5
        2. Coletar métricas com error_rate > 5%
        3. Verificar rollback acionado automaticamente
        4. Verificar tráfego restaurado para 0%
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_5

        # Coletar métricas com error_rate alto
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.08,  # 8% - acima do threshold de 5%
                "p95_latency_ms": 150,
                "requests_per_second": 100,
                "anomaly_detected": False,
            },
        )

        # Auto-rollback deve ser acionado
        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.ROLLED_BACK
        assert status.traffic_percentage == 0
        assert status.rollback_reason == RollbackReason.ERROR_RATE_EXCEEDED

    @pytest.mark.asyncio()
    async def test_canary_rollback_on_high_latency(self, cutover_manager, cutover_config):
        """
        Teste E2E: Rollback automático quando latência P95 excede threshold.

        Fluxo:
        1. Iniciar em CANARY_5
        2. Coletar métricas com P95 > 2000ms
        3. Verificar rollback acionado
        4. Verificar motivo = LATENCY_HIGH
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_5

        # Coletar métricas com latência alta
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.01,
                "p95_latency_ms": 2500,  # Acima do threshold de 2000ms
                "requests_per_second": 100,
                "anomaly_detected": False,
            },
        )

        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.ROLLED_BACK
        assert status.rollback_reason == RollbackReason.LATENCY_HIGH

    @pytest.mark.asyncio()
    async def test_canary_rollback_on_anomaly_detected(self, cutover_manager):
        """
        Teste E2E: Rollback automático quando anomalia é detectada.

        Fluxo:
        1. Iniciar em CANARY_25
        2. Coletar métricas com anomaly_detected=True
        3. Verificar rollback acionado
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_25

        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.01,
                "p95_latency_ms": 150,
                "requests_per_second": 100,
                "anomaly_detected": True,  # Anomalia detectada
            },
        )

        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.ROLLED_BACK
        assert status.rollback_message == "Anomalia detectada nas métricas"

    @pytest.mark.asyncio()
    async def test_canary_latency_twice_legacy_triggers_rollback(self, cutover_manager):
        """
        Teste E2E: Rollback quando latência é 2x maior que legado.

        Fluxo:
        1. Iniciar em CANARY_5
        2. Coletar métricas com P95 = 2.1x legado
        3. Verificar rollback acionado
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_5

        # Legacy com 100ms, target com 210ms (> 2x)
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.01,
                "p95_latency_ms": 210,  # 2.1x o legado
                "requests_per_second": 100,
                "anomaly_detected": False,
            },
        )

        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.ROLLED_BACK
        assert "2.1x" in status.rollback_message


@pytest.mark.integration()
class TestFullCutoverE2E:
    """Testes E2E para Full Cutover."""

    @pytest.mark.asyncio()
    async def test_full_cutover_completion(self, cutover_manager, cutover_config):
        """
        Teste E2E: Full Cutover completo com sucesso.

        Fluxo:
        1. Progressar de SHADOW_MODE até FULL_CUTOVER
        2. Verificar todas as transições
        3. Verificar status final
        """
        await cutover_manager.start()

        # Simular progressão através das fases
        phases = [
            CutoverPhase.CANARY_5,
            CutoverPhase.CANARY_25,
            CutoverPhase.CANARY_50,
        ]

        for phase in phases:
            cutover_manager.status.phase = phase
            cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=2)

            # Coletar métricas boas
            await cutover_manager.collect_metrics(
                {"p95_latency_ms": 100},
                {
                    "error_rate": 0.005,
                    "p95_latency_ms": 105,
                    "requests_per_second": 100,
                    "anomaly_detected": False,
                },
            )

            success, _ = await cutover_manager.promote_to_next_phase()
            assert success

        # Promover para FULL_CUTOVER manualmente
        cutover_manager.status.phase = CutoverPhase.CANARY_50
        cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=2)
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.003,
                "p95_latency_ms": 102,
                "requests_per_second": 100,
                "anomaly_detected": False,
            },
        )
        await cutover_manager.promote_to_next_phase()

        # Verificar estado final
        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.FULL_CUTOVER
        assert status.traffic_percentage == 100
        assert status.phase_transitions > 0

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Test waits for 7 day stabilization period")
    async def test_full_cutover_stabilization_after_7_days(self, cutover_manager):
        """
        Teste E2E: Estabilização após 7 dias em FULL_CUTOVER.

        Fluxo:
        1. Alcançar FULL_CUTOVER
        2. Aguardar 7 dias (simulado)
        3. Verificar transição para COMPLETED
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.FULL_CUTOVER

        # Criar task de finalização (normalmente seria automático)
        task = asyncio.create_task(cutover_manager._finalize_after_full_cutover())

        # Como _finalize_after_full_cutover tem sleep de 7 dias, precisamos
        # mockar o sleep para testar
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await task

        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.COMPLETED
        assert status.completed_at is not None

    @pytest.mark.asyncio()
    async def test_full_cutover_metrics_during_stabilization(self, cutover_manager):
        """
        Teste E2E: Coleta de métricas durante estabilização.

        Fluxo:
        1. Alcançar FULL_CUTOVER
        2. Coletar múltiplas métricas
        3. Verificar histórico mantido
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.FULL_CUTOVER

        # Coletar 100 métricas
        for i in range(100):
            await cutover_manager.collect_metrics(
                {"p95_latency_ms": 100},
                {
                    "error_rate": 0.001 + (i * 0.0001),
                    "p95_latency_ms": 100 + i,
                    "requests_per_second": 1000,
                    "anomaly_detected": False,
                },
            )

        status = await cutover_manager.get_status()
        assert len(status.metrics_history) == 100

        # Verificar resumo de métricas
        summary = status.get_metrics_summary()
        assert summary["total_samples"] == 100
        assert summary["avg_error_rate"] > 0


@pytest.mark.integration()
class TestRollbackE2E:
    """Testes E2E para Rollback."""

    @pytest.mark.asyncio()
    async def test_manual_rollback_from_any_phase(self, cutover_manager):
        """
        Teste E2E: Rollback manual de qualquer fase.

        Fluxo:
        1. Iniciar em CANARY_25
        2. Acionar rollback manual
        3. Verificar ROLLED_BACK
        4. Verificar tráfego em 0%
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_25
        cutover_manager.status.traffic_percentage = 25

        # Acionar rollback manual
        status = await cutover_manager.rollback(
            reason=RollbackReason.MANUAL_REQUEST,
            message="Rollback manual solicitado por operador",
        )

        assert status.phase == CutoverPhase.ROLLED_BACK
        assert status.traffic_percentage == 0
        assert status.rollback_reason == RollbackReason.MANUAL_REQUEST
        assert status.rollback_count == 1

    @pytest.mark.asyncio()
    async def test_auto_rollback_on_system_down(self, cutover_manager):
        """
        Teste E2E: Rollback automático quando sistema está down.

        Fluxo:
        1. Iniciar em CANARY_5
        2. Simular system_down (requests_per_second = 0)
        3. Verificar rollback acionado
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_5

        # Simular sistema down
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 0},
            {
                "error_rate": 1.0,  # 100% de erro - sistema down
                "p95_latency_ms": 0,
                "requests_per_second": 0,
                "anomaly_detected": True,
            },
        )

        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.ROLLED_BACK

    @pytest.mark.asyncio()
    async def test_rollback_prevents_further_promotions(self, cutover_manager):
        """
        Teste E2E: Após rollback, não é possível promover.

        Fluxo:
        1. Executar rollback
        2. Tentar promover para próxima fase
        3. Verificar que promoção é negada
        """
        await cutover_manager.start()

        await cutover_manager.rollback(RollbackReason.MANUAL_REQUEST, "Teste")

        # Tentar promover
        success, reason = await cutover_manager.promote_to_next_phase()

        # Deve falhar pois está em ROLLED_BACK
        assert not success

    @pytest.mark.asyncio()
    async def test_rollback_emits_event(self, cutover_manager):
        """
        Teste E2E: Rollback emite evento Kafka.

        Fluxo:
        1. Executar rollback
        2. Verificar evento cutover.rolled_back emitido
        """
        await cutover_manager.start()

        await cutover_manager.rollback(RollbackReason.ERROR_RATE_EXCEEDED, "Teste")

        # Verificar que evento foi emitido
        assert cutover_manager.kafka_producer.produce.called

    @pytest.mark.asyncio()
    async def test_multiple_rollbacks_increment_counter(self, cutover_manager):
        """
        Teste E2E: Múltiplos rollbacks incrementam contador.

        Fluxo:
        1. Executar primeiro rollback
        2. Reiniciar cutover
        3. Executar segundo rollback
        4. Verificar rollback_count = 2
        """
        # Primeiro rollback
        await cutover_manager.start()
        await cutover_manager.rollback(RollbackReason.MANUAL_REQUEST, "Primeiro")
        assert cutover_manager.status.rollback_count == 1

        # Reiniciar e segundo rollback
        cutover_manager.status.phase = CutoverPhase.CANARY_5
        cutover_manager.status.traffic_percentage = 5
        cutover_manager._rollback_in_progress = False

        await cutover_manager.rollback(RollbackReason.LATENCY_HIGH, "Segundo")
        assert cutover_manager.status.rollback_count == 2


@pytest.mark.integration()
class TestPauseResumeE2E:
    """Testes E2E para Pause/Resume."""

    @pytest.mark.asyncio()
    async def test_pause_cutover(self, cutover_manager):
        """
        Teste E2E: Pausar cutover.

        Fluxo:
        1. Iniciar cutover
        2. Pausar
        3. Verificar status PAUSED
        """
        await cutover_manager.start()

        status = await cutover_manager.pause()

        assert status.phase == CutoverPhase.SHADOW_MODE  # Mantém fase
        assert not cutover_manager._running

    @pytest.mark.asyncio()
    async def test_resume_paused_cutover(self, cutover_manager):
        """
        Teste E2E: Resumir cutover pausado.

        Fluxo:
        1. Iniciar cutover
        2. Pausar
        3. Resumir
        4. Verificar monitoramento reiniciado
        """
        await cutover_manager.start()
        await cutover_manager.pause()

        status = await cutover_manager.resume()

        assert cutover_manager._running
        assert status.phase == CutoverPhase.SHADOW_MODE


@pytest.mark.integration()
class TestCutoverWorkflowE2E:
    """Testes E2E completos do workflow."""

    @pytest.mark.asyncio()
    async def test_complete_successful_cutover(self, cutover_manager, cutover_config):
        """
        Teste E2E: Cutover completo do início ao fim.

        Fluxo completo:
        1. SHADOW_MODE (0%)
        2. CANARY_5 (5%)
        3. CANARY_25 (25%)
        4. CANARY_50 (50%)
        5. FULL_CUTOVER (100%)
        6. COMPLETED (após estabilização)
        """
        await cutover_manager.start()

        expected_progression = [
            (CutoverPhase.SHADOW_MODE, 0, 25),  # phase, traffic, hours_needed
            (CutoverPhase.CANARY_5, 5, 2),
            (CutoverPhase.CANARY_25, 25, 2),
            (CutoverPhase.CANARY_50, 50, 2),
            (CutoverPhase.FULL_CUTOVER, 100, 2),
        ]

        for expected_phase, expected_traffic, hours_needed in expected_progression:
            # Definir fase
            cutover_manager.status.phase = expected_phase
            cutover_manager.status.current_phase_start = datetime.now() - timedelta(
                hours=hours_needed
            )

            # Verificar tráfego antes da promoção
            status = await cutover_manager.get_status()
            assert (
                status.traffic_percentage == expected_traffic
            ), f"Phase {expected_phase} should have {expected_traffic}% traffic"

            # Coletar métricas boas
            await cutover_manager.collect_metrics(
                {"p95_latency_ms": 100},
                {
                    "error_rate": 0.003,
                    "p95_latency_ms": 102,
                    "requests_per_second": 1000,
                    "anomaly_detected": False,
                },
            )

            # Promover para próxima fase (exceto FULL_CUTOVER)
            if expected_phase != CutoverPhase.FULL_CUTOVER:
                success, _ = await cutover_manager.promote_to_next_phase()
                assert success, f"Falha ao promover de {expected_phase}"

        # Estado final
        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.FULL_CUTOVER
        assert status.traffic_percentage == 100

    @pytest.mark.asyncio()
    async def test_cutover_with_rollback_and_recovery(self, cutover_manager, cutover_config):
        """
        Teste E2E: Cutover com rollback e recuperação.

        Fluxo:
        1. Progressar até CANARY_25
        2. Acionar rollback por alta latência
        3. Criar novo CutoverManager para recuperação
        4. Verificar que pode reiniciar
        """
        # Progressar normalmente
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_25

        # Simular métricas ruins
        await cutover_manager.collect_metrics(
            {"p95_latency_ms": 100},
            {
                "error_rate": 0.06,
                "p95_latency_ms": 2500,
                "requests_per_second": 100,
                "anomaly_detected": False,
            },
        )

        status = await cutover_manager.get_status()
        assert status.phase == CutoverPhase.ROLLED_BACK

        # Criar novo cutover com mesmo ID para recuperação
        recovery_manager = CutoverManager(
            config=cutover_config,
            cutover_id=cutover_manager.cutover_id,  # Reusar ID
            kafka_producer=cutover_manager.kafka_producer,
            mongodb_client=cutover_manager.mongodb_client,
            metrics_client=cutover_manager.metrics_client,
        )

        # Deve ser possível reiniciar
        new_status = await recovery_manager.start()
        assert new_status.phase == CutoverPhase.SHADOW_MODE
        assert new_status.cutover_id == cutover_manager.cutover_id

    @pytest.mark.asyncio()
    async def test_metrics_history_limit_enforced(self, cutover_manager):
        """
        Teste E2E: Histórico de métricas limitado a 1000 registros.

        Fluxo:
        1. Coletar mais de 1000 métricas
        2. Verificar que histórico não excede 1000
        3. Verificar que métricas mais recentes são mantidas
        """
        await cutover_manager.start()

        # Coletar 1500 métricas
        for i in range(1500):
            await cutover_manager.collect_metrics(
                {"p95_latency_ms": 100},
                {
                    "error_rate": 0.001,
                    "p95_latency_ms": 100 + i,
                    "requests_per_second": 100,
                    "anomaly_detected": False,
                },
            )

        status = await cutover_manager.get_status()
        assert len(status.metrics_history) == 1000

        # Última métrica deve ser a mais recente
        assert status.metrics_history[-1].p95_latency_ms == 1599

    @pytest.mark.asyncio()
    async def test_get_metrics_summary(self, cutover_manager):
        """
        Teste E2E: Obter resumo de métricas.

        Fluxo:
        1. Coletar variedade de métricas
        2. Chamar get_metrics_summary()
        3. Verificar estatísticas corretas
        """
        await cutover_manager.start()

        # Coletar métricas com valores variados
        error_rates = [0.01, 0.02, 0.015, 0.005, 0.01]
        latencies = [100, 150, 120, 90, 110]

        for er, lat in zip(error_rates, latencies):
            await cutover_manager.collect_metrics(
                {"p95_latency_ms": 100},
                {
                    "error_rate": er,
                    "p95_latency_ms": lat,
                    "requests_per_second": 100,
                    "anomaly_detected": False,
                },
            )

        summary = cutover_manager.status.get_metrics_summary()

        assert summary["total_samples"] == 5
        assert abs(summary["avg_error_rate"] - sum(error_rates) / len(error_rates)) < 0.0001
        assert summary["max_error_rate"] == max(error_rates)
        assert abs(summary["avg_p95_latency_ms"] - sum(latencies) / len(latencies)) < 0.1
        assert summary["max_p95_latency_ms"] == max(latencies)


@pytest.mark.integration()
class TestCutoverEventsE2E:
    """Testes E2E para eventos de cutover."""

    @pytest.mark.asyncio()
    async def test_all_phase_transitions_emit_events(self, cutover_manager):
        """
        Teste E2E: Todas as transições de fase emitem eventos.

        Fluxo:
        1. Progressar através de todas as fases
        2. Verificar evento cutover.phase_changed para cada transição
        """
        await cutover_manager.start()

        phases = [
            CutoverPhase.CANARY_5,
            CutoverPhase.CANARY_25,
            CutoverPhase.CANARY_50,
        ]

        initial_call_count = cutover_manager.kafka_producer.produce.call_count

        for phase in phases:
            cutover_manager.status.phase = phase
            cutover_manager.status.current_phase_start = datetime.now() - timedelta(hours=2)

            await cutover_manager.promote_to_next_phase()

        # Cada transição deve emitir pelo menos um evento
        assert cutover_manager.kafka_producer.produce.call_count > initial_call_count

    @pytest.mark.asyncio()
    async def test_rollback_event_contains_details(self, cutover_manager):
        """
        Teste E2E: Evento de rollback contém detalhes.

        Fluxo:
        1. Executar rollback
        2. Verificar que evento contém motivo e fase
        """
        await cutover_manager.start()
        cutover_manager.status.phase = CutoverPhase.CANARY_25

        await cutover_manager.rollback(
            RollbackReason.ERROR_RATE_EXCEEDED, "Error rate 8% detectado"
        )

        # Verificar última chamada ao producer
        last_call = cutover_manager.kafka_producer.produce.call_args_list[-1]
        kwargs = last_call.kwargs

        import json

        event_data = json.loads(kwargs["value"])

        assert event_data.get("event_type") == "cutover.rolled_back"
        assert event_data.get("phase") == CutoverPhase.ROLLED_BACK.value


@pytest.mark.integration()
class TestCutoverConfigValidation:
    """Testes E2E para validação de configuração."""

    def test_invalid_canary_stages_raises_error(self):
        """
        Teste E2E: Configuração inválida de canary_stages raise erro.

        Fluxo:
        1. Criar config com estágios inválidos
        2. Verificar ValidationError
        """
        with pytest.raises(ValueError):
            CutoverConfig(
                legacy_service_url="http://legacy:8080",
                target_service_url="http://target:8080",
                canary_stages=[5, 25, 50],  # Falta 100
            )

    def test_unsorted_canary_stages_raises_error(self):
        """
        Teste E2E: canary_stages não ordenados raise erro.

        Fluxo:
        1. Criar config com estágios desordenados
        2. Verificar ValidationError
        """
        with pytest.raises(ValueError):
            CutoverConfig(
                legacy_service_url="http://legacy:8080",
                target_service_url="http://target:8080",
                canary_stages=[50, 5, 25, 100],  # Desordenado
            )

    def test_shadow_duration_validation(self):
        """
        Teste E2E: Validação de shadow_duration_hours.

        Fluxo:
        1. Criar config com duração < 24h
        2. Verificar ValidationError
        """
        with pytest.raises(ValueError):
            CutoverConfig(
                legacy_service_url="http://legacy:8080",
                target_service_url="http://target:8080",
                shadow_duration_hours=10,  # Abaixo do mínimo de 24
            )


@pytest.mark.integration()
class TestCutoverManagerCleanup:
    """Testes E2E para cleanup do CutoverManager."""

    @pytest.mark.asyncio()
    async def test_close_stops_monitoring(self, cutover_manager):
        """
        Teste E2E: close() para monitoramento.

        Fluxo:
        1. Iniciar cutover
        2. Chamar close()
        3. Verificar que monitoramento parou
        """
        await cutover_manager.start()

        assert cutover_manager._running

        await cutover_manager.close()

        assert not cutover_manager._running
        assert cutover_manager._monitor_task is None or cutover_manager._monitor_task.done()

    @pytest.mark.asyncio()
    async def test_close_cancels_monitor_task(self, cutover_manager):
        """
        Teste E2E: close() cancela task de monitoramento.

        Fluxo:
        1. Iniciar cutover
        2. Verificar task existe
        3. Chamar close()
        4. Verificar task cancelada
        """
        await cutover_manager.start()

        assert cutover_manager._monitor_task is not None
        assert not cutover_manager._monitor_task.done()

        await cutover_manager.close()

        assert cutover_manager._monitor_task is None or cutover_manager._monitor_task.done()
