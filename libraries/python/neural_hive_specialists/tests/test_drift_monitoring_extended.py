"""
Testes adicionais para drift_monitoring.

Cobertura extra para drift_detector.py, drift_alerts.py, evidently_monitor.py
"""

from unittest.mock import Mock

import pytest


class TestDriftDetectorExtended:
    """Testes estendidos para DriftDetector."""

    @pytest.fixture()
    def config(self):
        """Configuração de teste."""
        return {
            "drift_detection_window_hours": 24,
            "drift_threshold_psi": 0.2,
            "drift_check_interval_minutes": 60,
        }

    @pytest.fixture()
    def mock_dependencies(self):
        """Mock de dependências."""
        return {
            "evidently_monitor": Mock(),
            "drift_alerter": Mock(),
            "ledger_client": Mock(),
        }

    def test_init_with_custom_config(self, config, mock_dependencies):
        """Testa inicialização com configuração customizada."""
        from neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector

        detector = DriftDetector(
            config,
            mock_dependencies["evidently_monitor"],
            mock_dependencies["drift_alerter"],
            mock_dependencies["ledger_client"],
        )

        assert detector.window_hours == 24
        assert detector.threshold_psi == 0.2
        assert detector.check_interval_minutes == 60

    def test_init_with_default_config(self, mock_dependencies):
        """Testa inicialização com configuração padrão."""
        config = {}  # Config vazia

        from neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector

        detector = DriftDetector(
            config,
            mock_dependencies["evidently_monitor"],
            mock_dependencies["drift_alerter"],
            mock_dependencies["ledger_client"],
        )

        # Deve usar valores padrão
        assert detector.window_hours == 24
        assert detector.threshold_psi == 0.2
        assert detector.check_interval_minutes == 60

    @pytest.mark.asyncio()
    async def test_start_monitoring(self, config, mock_dependencies):
        """Testa início de monitoramento."""
        from neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector

        detector = DriftDetector(
            config,
            mock_dependencies["evidently_monitor"],
            mock_dependencies["drift_alerter"],
            mock_dependencies["ledger_client"],
        )

        await detector.start_monitoring()

        assert detector._running is True
        assert detector._task is not None

        # Cleanup
        await detector.stop_monitoring()

    @pytest.mark.asyncio()
    async def test_start_monitoring_already_running(self, config, mock_dependencies):
        """Testa que iniciar monitoring novamente não causa problemas."""
        from neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector

        detector = DriftDetector(
            config,
            mock_dependencies["evidently_monitor"],
            mock_dependencies["drift_alerter"],
            mock_dependencies["ledger_client"],
        )

        await detector.start_monitoring()
        first_task = detector._task

        # Chamar novamente não deve criar nova task
        await detector.start_monitoring()

        assert detector._task == first_task

        # Cleanup
        await detector.stop_monitoring()

    @pytest.mark.asyncio()
    async def test_stop_monitoring_when_not_running(self, config, mock_dependencies):
        """Testa parar monitoramento quando não está rodando."""
        from neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector

        detector = DriftDetector(
            config,
            mock_dependencies["evidently_monitor"],
            mock_dependencies["drift_alerter"],
            mock_dependencies["ledger_client"],
        )

        # Não deve levantar erro
        await detector.stop_monitoring()

        assert detector._running is False


class TestDriftAlertsExtended:
    """Testes estendidos para DriftAlerter."""

    @pytest.fixture()
    def config(self):
        """Configuração de teste."""
        return {
            "drift_alert_enabled": True,
            "drift_alert_webhook": "https://example.com/webhook",
        }

    @pytest.fixture()
    def mock_ledger(self):
        """Mock de ledger client."""
        return Mock()

    def test_init_with_webhook(self, config, mock_ledger):
        """Testa inicialização com webhook configurado."""
        from neural_hive_specialists.drift_monitoring.drift_alerts import DriftAlerter

        alerter = DriftAlerter(config, mock_ledger)

        assert alerter.enabled is True
        assert alerter.webhook_url == "https://example.com/webhook"

    def test_init_disabled(self, mock_ledger):
        """Testa inicialização desabilitado."""
        config = {"drift_alert_enabled": False}

        from neural_hive_specialists.drift_monitoring.drift_alerts import DriftAlerter

        alerter = DriftAlerter(config, mock_ledger)

        assert alerter.enabled is False

    def test_init_default_config(self, mock_ledger):
        """Testa inicialização com configuração padrão."""
        config = {}

        from neural_hive_specialists.drift_monitoring.drift_alerts import DriftAlerter

        alerter = DriftAlerter(config, mock_ledger)

        # Valores padrão
        assert alerter.enabled is True  # Se não especificado, assume True


class TestEvidentlyMonitorExtended:
    """Testes estendidos para EvidentlyMonitor."""

    @pytest.fixture()
    def config(self):
        """Configuração de teste."""
        return {
            "evidently_enabled": True,
            "evidently_project_id": "test_project",
        }

    def test_init_with_project(self, config):
        """Testa inicialização com project ID."""
        from neural_hive_specialists.drift_monitoring.evidently_monitor import EvidentlyMonitor

        monitor = EvidentlyMonitor(config)

        assert monitor.enabled is True
        assert monitor.project_id == "test_project"

    def test_init_disabled(self):
        """Testa inicialização desabilitado."""
        config = {"evidently_enabled": False}

        from neural_hive_specialists.drift_monitoring.evidently_monitor import EvidentlyMonitor

        monitor = EvidentlyMonitor(config)

        assert monitor.enabled is False

    def test_get_drift_score_empty_data(self, config):
        """Testa cálculo de drift score com dados vazios."""
        from neural_hive_specialists.drift_monitoring.evidently_monitor import EvidentlyMonitor

        monitor = EvidentlyMonitor(config)

        score = monitor.get_drift_score([], [])

        # Dados vazios devem retornar score neutro
        assert score == 0.0

    def test_get_drift_score_with_reference(self, config):
        """Testa cálculo de drift score com dados de referência."""
        from neural_hive_specialists.drift_monitoring.evidently_monitor import EvidentlyMonitor

        monitor = EvidentlyMonitor(config)

        reference_data = [1.0, 2.0, 3.0, 4.0, 5.0]
        current_data = [1.1, 2.1, 3.1, 4.1, 5.1]

        score = monitor.get_drift_score(reference_data, current_data)

        # Deve retornar um score entre 0 e 1
        assert 0.0 <= score <= 1.0
