"""
Testes unitários para o Sistema de Notificações.

Testa os notificadores Slack, Email e o NotificationManager.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestNotificationConfig:
    """Testes de configuração de notificações."""

    def test_config_default_values(self):
        """Testa valores padrão da configuração."""
        from notifications.config import NotificationConfig

        config = NotificationConfig()

        assert config.slack_default_channel == "#ml-alerts"
        assert config.slack_critical_channel == "#ml-alerts-critical"
        assert config.slack_username == "NeuralHive ML"
        assert config.slack_icon_emoji == ":robot_face:"
        assert config.smtp_port == 587
        assert config.smtp_use_tls is True
        assert config.email_from == "noreply@neuralhive.local"
        assert config.email_to == []
        assert config.enabled_channels == []
        assert config.retry_max_attempts == 3
        assert config.retry_initial_delay == 1.0

    def test_config_from_env_empty(self):
        """Testa criação de config com env vazio."""
        from notifications.config import NotificationConfig

        with patch.dict("os.environ", {}, clear=True):
            config = NotificationConfig.from_env()

            assert config.enabled_channels == []
            assert config.email_to == []
            assert config.slack_webhook_url is None

    def test_config_from_env_slack_enabled(self):
        """Testa criação de config com Slack habilitado."""
        from notifications.config import NotificationConfig

        env_vars = {
            "NOTIFICATION_SLACK_ENABLED": "true",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/TEST",
            "SLACK_ALERTS_CHANNEL": "#test-channel",
            "SLACK_CRITICAL_CHANNEL": "#test-critical",
        }

        with patch.dict("os.environ", env_vars, clear=True):
            config = NotificationConfig.from_env()

            assert "slack" in config.enabled_channels
            assert config.slack_webhook_url == "https://hooks.slack.com/services/TEST"
            assert config.slack_default_channel == "#test-channel"
            assert config.slack_critical_channel == "#test-critical"

    def test_config_from_env_email_enabled(self):
        """Testa criação de config com Email habilitado."""
        from notifications.config import NotificationConfig

        env_vars = {
            "NOTIFICATION_EMAIL_ENABLED": "true",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "user@example.com",
            "SMTP_PASSWORD": "secret",
            "EMAIL_FROM": "noreply@example.com",
            "NOTIFICATION_EMAIL_TO": "admin@example.com,ops@example.com",
        }

        with patch.dict("os.environ", env_vars, clear=True):
            config = NotificationConfig.from_env()

            assert "email" in config.enabled_channels
            assert config.smtp_host == "smtp.example.com"
            assert config.smtp_port == 587
            assert config.smtp_username == "user@example.com"
            assert config.email_from == "noreply@example.com"
            assert config.email_to == ["admin@example.com", "ops@example.com"]

    def test_is_channel_enabled(self):
        """Testa verificação de canal habilitado."""
        from notifications.config import NotificationConfig

        config = NotificationConfig(enabled_channels=["slack", "email"])

        assert config.is_channel_enabled("slack") is True
        assert config.is_channel_enabled("email") is True
        assert config.is_channel_enabled("sms") is False


class TestNotificationTemplate:
    """Testes de templates de notificação."""

    def test_retrain_triggered_template(self):
        """Testa template de retrain triggered."""
        from notifications.config import NotificationTemplate

        notification = NotificationTemplate.retrain_triggered(
            model_name="approval_predictor",
            model_version="v7.0",
            drift_type="feature",
            drift_score=0.45,
            priority="critical",
        )

        assert notification["title"] == ":warning: Retrain Triggered"
        assert notification["priority"] == "critical"
        assert notification["text"].startswith("Automatic retrain triggered")

        fields = {f["name"]: f["value"] for f in notification["fields"]}
        assert fields["Model"] == "approval_predictor"
        assert fields["Version"] == "v7.0"
        assert fields["Drift Type"] == "feature"
        assert fields["Drift Score"] == "0.4500"
        assert fields["Priority"] == "CRITICAL"

    def test_retrain_success_template(self):
        """Testa template de retrain success."""
        from notifications.config import NotificationTemplate

        notification = NotificationTemplate.retrain_success(
            model_name="approval_predictor",
            model_version="v7.0",
            new_version="v8.0",
            duration_seconds=125.5,
            metrics={"mae": 0.0234, "precision": 0.92},
        )

        assert notification["title"] == ":white_check_mark: Retrain Successful"
        assert notification["priority"] == "info"

        fields = {f["name"]: f["value"] for f in notification["fields"]}
        assert fields["Model"] == "approval_predictor"
        assert fields["Previous Version"] == "v7.0"
        assert fields["New Version"] == "v8.0"
        assert fields["Duration"] == "125.5s"
        assert fields["Mae"] == "0.0234"
        assert fields["Precision"] == "0.9200"

    def test_retrain_failed_template(self):
        """Testa template de retrain failed."""
        from notifications.config import NotificationTemplate

        notification = NotificationTemplate.retrain_failed(
            model_name="approval_predictor",
            model_version="v7.0",
            error_message="Training failed: out of memory",
            retry_attempt=2,
        )

        assert notification["title"] == ":x: Retrain Failed"
        assert notification["priority"] == "critical"

        fields = {f["name"]: f["value"] for f in notification["fields"]}
        assert fields["Model"] == "approval_predictor"
        assert fields["Version"] == "v7.0"
        assert fields["Retry Attempt"] == "2"

    def test_drift_detected_template(self):
        """Testa template de drift detected."""
        from notifications.config import NotificationTemplate

        notification = NotificationTemplate.drift_detected(
            model_name="approval_predictor",
            drift_type="feature",
            drift_score=0.35,
            severity="warning",
        )

        assert notification["title"] == ":warning: Drift Detected"
        assert notification["priority"] == "warning"

        fields = {f["name"]: f["value"] for f in notification["fields"]}
        assert fields["Model"] == "approval_predictor"
        assert fields["Drift Type"] == "feature"
        assert fields["Score"] == "0.3500"
        assert fields["Severity"] == "WARNING"

    def test_get_color_for_priority(self):
        """Testa mapeamento de cores por prioridade."""
        from notifications.config import NotificationTemplate

        assert NotificationTemplate.get_color_for_priority("info") == "#36a64f"
        assert NotificationTemplate.get_color_for_priority("warning") == "#ff9900"
        assert NotificationTemplate.get_color_for_priority("critical") == "#ff0000"

    def test_to_slack_message(self):
        """Testa conversão para formato Slack."""
        from notifications.config import NotificationTemplate

        notification = {
            "title": "Test Notification",
            "priority": "warning",
            "text": "Test message",
            "fields": [{"name": "Field1", "value": "Value1"}],
            "timestamp": 1234567890,
        }

        slack_msg = NotificationTemplate.to_slack_message(notification)

        assert "attachments" in slack_msg
        assert len(slack_msg["attachments"]) == 1
        attachment = slack_msg["attachments"][0]
        assert attachment["color"] == "#ff9900"
        assert attachment["title"] == "Test Notification"
        assert attachment["text"] == "Test message"
        assert attachment["ts"] == 1234567890

    def test_to_email_html(self):
        """Testa conversão para HTML de email."""
        from notifications.config import NotificationTemplate

        notification = {
            "title": "Test Notification",
            "priority": "info",
            "text": "Test message",
            "fields": [{"name": "Field1", "value": "Value1"}],
            "timestamp_formatted": "2026-04-24T12:00:00",
        }

        html = NotificationTemplate.to_email_html(notification)

        assert "<!DOCTYPE html>" in html
        assert "Test Notification" in html
        assert "Test message" in html
        assert "Field1" in html
        assert "Value1" in html
        assert "2026-04-24T12:00:00" in html

    def test_to_email_subject(self):
        """Testa geração de assunto de email."""
        from notifications.config import NotificationTemplate

        notification = {
            "title": "Retrain Triggered",
            "priority": "critical",
        }

        subject = NotificationTemplate.to_email_subject(notification)

        assert subject == "[CRITICAL] NeuralHive - Retrain Triggered"


class TestSlackNotifier:
    """Testes do notificador Slack."""

    def test_validate_config_with_webhook(self):
        """Testa validação com webhook configurado."""
        from notifications.config import NotificationConfig
        from notifications.notifier import SlackNotifier

        config = NotificationConfig(slack_webhook_url="https://hooks.slack.com/services/TEST")
        notifier = SlackNotifier(config)

        assert notifier.validate_config() is True

    def test_validate_config_without_webhook(self):
        """Testa validação sem webhook configurado."""
        from notifications.config import NotificationConfig
        from notifications.notifier import SlackNotifier

        config = NotificationConfig(slack_webhook_url=None)
        notifier = SlackNotifier(config)

        assert notifier.validate_config() is False

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Testa envio bem-sucedido para Slack."""
        from notifications.config import NotificationConfig, NotificationTemplate
        from notifications.notifier import SlackNotifier

        config = NotificationConfig(
            slack_webhook_url="https://hooks.slack.com/services/TEST",
            slack_default_channel="#test",
        )

        notification = NotificationTemplate.retrain_triggered(
            model_name="test_model",
            model_version="v1.0",
            drift_type="feature",
            drift_score=0.3,
            priority="warning",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            notifier = SlackNotifier(config)
            result = await notifier.send(notification)

            assert result.success is True
            assert result.channel == "slack"
            assert "Enviado para" in result.message

            await notifier.close()

    @pytest.mark.asyncio
    async def test_send_failure(self):
        """Testa falha no envio para Slack."""
        from notifications.config import NotificationConfig, NotificationTemplate
        from notifications.notifier import SlackNotifier

        config = NotificationConfig(
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        notification = NotificationTemplate.retrain_triggered(
            model_name="test_model",
            model_version="v1.0",
            drift_type="feature",
            drift_score=0.3,
            priority="warning",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Server Error")
            mock_post.return_value.__aenter__.return_value = mock_response

            notifier = SlackNotifier(config)
            result = await notifier.send(notification)

            assert result.success is False
            assert result.channel == "slack"
            assert "Erro 500" in result.message

            await notifier.close()


class TestEmailNotifier:
    """Testes do notificador Email."""

    def test_validate_config_complete(self):
        """Testa validação com configuração completa."""
        from notifications.config import NotificationConfig
        from notifications.notifier import EmailNotifier

        config = NotificationConfig(
            smtp_host="smtp.example.com",
            email_from="noreply@example.com",
            email_to=["admin@example.com"],
        )
        notifier = EmailNotifier(config)

        assert notifier.validate_config() is True

    def test_validate_config_incomplete(self):
        """Testa validação com configuração incompleta."""
        from notifications.config import NotificationConfig
        from notifications.notifier import EmailNotifier

        config = NotificationConfig(smtp_host=None)
        notifier = EmailNotifier(config)

        assert notifier.validate_config() is False

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Testa envio bem-sucedido de email."""
        from notifications.config import NotificationConfig, NotificationTemplate
        from notifications.notifier import EmailNotifier

        config = NotificationConfig(
            smtp_host="smtp.example.com",
            email_from="noreply@example.com",
            email_to=["admin@example.com"],
        )

        notification = NotificationTemplate.retrain_success(
            model_name="test_model",
            model_version="v1.0",
            new_version="v2.0",
            duration_seconds=100,
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            notifier = EmailNotifier(config)
            result = await notifier.send(notification)

            assert result.success is True
            assert result.channel == "email"

            mock_server.starttls.assert_called_once()
            mock_server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_authentication(self):
        """Testa envio de email com autenticação."""
        from notifications.config import NotificationConfig
        from notifications.notifier import EmailNotifier

        config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_username="user@example.com",
            smtp_password="secret",
            email_from="noreply@example.com",
            email_to=["admin@example.com"],
        )

        notification = {
            "title": "Test",
            "priority": "info",
            "text": "Test message",
            "fields": [],
            "timestamp": 1234567890,
            "timestamp_formatted": "2026-04-24T12:00:00",
        }

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            notifier = EmailNotifier(config)
            result = await notifier.send(notification)

            assert result.success is True
            mock_server.login.assert_called_once_with("user@example.com", "secret")


class TestNotificationManager:
    """Testes do gerenciador de notificações."""

    def test_init_without_config(self):
        """Testa inicialização sem config (usa env)."""
        from notifications.notifier import NotificationManager

        with patch.dict("os.environ", {}, clear=True):
            manager = NotificationManager()

            assert len(manager.notifiers) == 0

    def test_init_with_slack_enabled(self):
        """Testa inicialização com Slack habilitado."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        manager = NotificationManager(config)

        assert len(manager.notifiers) == 1
        assert manager.notifiers[0].__class__.__name__ == "SlackNotifier"

    def test_init_with_email_enabled(self):
        """Testa inicialização com Email habilitado."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["email"],
            smtp_host="smtp.example.com",
            email_from="noreply@example.com",
            email_to=["admin@example.com"],
        )

        manager = NotificationManager(config)

        assert len(manager.notifiers) == 1
        assert manager.notifiers[0].__class__.__name__ == "EmailNotifier"

    @pytest.mark.asyncio
    async def test_notify_no_notifiers(self):
        """Testa notificação sem notificadores configurados."""
        from notifications.notifier import NotificationManager

        manager = NotificationManager()
        results = await manager.notify({"title": "Test"})

        assert results == []

    @pytest.mark.asyncio
    async def test_notify_retrain_triggered(self):
        """Testa notificação de retrain triggered."""
        from notifications.config import NotificationConfig, NotificationTemplate
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            manager = NotificationManager(config)
            results = await manager.notify_retrain_triggered(
                model_name="test_model",
                model_version="v1.0",
                drift_type="feature",
                drift_score=0.35,
                priority="warning",
            )

            assert len(results) == 1
            assert results[0].success is True

            await manager.close()

    @pytest.mark.asyncio
    async def test_notify_retrain_success(self):
        """Testa notificação de retrain success."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            manager = NotificationManager(config)
            results = await manager.notify_retrain_success(
                model_name="test_model",
                model_version="v1.0",
                new_version="v2.0",
                duration_seconds=150,
                metrics={"mae": 0.02},
            )

            assert len(results) == 1
            assert results[0].success is True

            await manager.close()

    @pytest.mark.asyncio
    async def test_notify_retrain_failed(self):
        """Testa notificação de retrain failed."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            manager = NotificationManager(config)
            results = await manager.notify_retrain_failed(
                model_name="test_model",
                model_version="v1.0",
                error_message="Training failed",
                retry_attempt=1,
            )

            assert len(results) == 1
            assert results[0].success is True

            await manager.close()

    @pytest.mark.asyncio
    async def test_notify_drift_detected(self):
        """Testa notificação de drift detected."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            manager = NotificationManager(config)
            results = await manager.notify_drift_detected(
                model_name="test_model",
                drift_type="feature",
                drift_score=0.28,
                severity="warning",
            )

            assert len(results) == 1
            assert results[0].success is True

            await manager.close()

    @pytest.mark.asyncio
    async def test_close(self):
        """Testa fechamento do gerenciador."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            manager = NotificationManager(config)
            await manager.close()

            # Verifica que não raises exception


class TestGetNotificationManager:
    """Testes da factory function."""

    def test_get_notification_manager_default(self):
        """Testa criação com configuração padrão."""
        from notifications.notifier import NotificationManager, get_notification_manager

        with patch.dict("os.environ", {}, clear=True):
            manager = get_notification_manager()

            assert isinstance(manager, NotificationManager)

    def test_get_notification_manager_with_config(self):
        """Testa criação com configuração customizada."""
        from notifications.config import NotificationConfig
        from notifications.notifier import NotificationManager, get_notification_manager

        config = NotificationConfig(
            enabled_channels=["slack"],
            slack_webhook_url="https://hooks.slack.com/services/TEST",
        )

        manager = get_notification_manager(config)

        assert isinstance(manager, NotificationManager)
        assert len(manager.notifiers) == 1
