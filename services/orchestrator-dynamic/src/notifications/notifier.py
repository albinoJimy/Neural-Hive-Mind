"""
Implementação do Sistema de Notificações.

Fornece notificadores para Slack e Email, com retries e tratamento de erros.
"""

import asyncio
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import NotificationConfig, NotificationTemplate

logger = structlog.get_logger(__name__)


@dataclass
class NotificationResult:
    """
    Resultado de uma notificação enviada.

    Attributes:
        success: True se a notificação foi enviada com sucesso
        channel: Canal usado (slack, email)
        message: Mensagem de sucesso ou erro
        timestamp: Timestamp do envio
        attempt: Número da tentativa (para retries)
    """

    success: bool
    channel: str
    message: str
    timestamp: datetime
    attempt: int = 1


class BaseNotifier(ABC):
    """
    Classe base para notificadores.

    Define interface comum para todos os canais de notificação.
    """

    def __init__(self, config: NotificationConfig):
        """
        Inicializa o notificador.

        Args:
            config: Configurações de notificação
        """
        self.config = config
        self.logger = logger.bind(component=self.__class__.__name__)

    @abstractmethod
    async def send(self, notification: dict[str, Any]) -> NotificationResult:
        """
        Envia uma notificação.

        Args:
            notification: Dados da notificação

        Returns:
            NotificationResult com status do envio
        """

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Valida se a configuração está completa.

        Returns:
            True se configuração válida
        """


class SlackNotifier(BaseNotifier):
    """
    Notificador via Slack Webhook.

    Envia mensagens formatadas para canais Slack usando Incoming Webhooks.
    """

    def __init__(self, config: NotificationConfig):
        """
        Inicializa o notificador Slack.

        Args:
            config: Configurações de notificação
        """
        super().__init__(config)
        self.webhook_url = config.slack_webhook_url
        self._session = None

    def validate_config(self) -> bool:
        """Valida se webhook URL está configurado."""
        return bool(self.webhook_url)

    async def _get_session(self):
        """Retorna sessão HTTP reutilizável."""
        if self._session is None:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Fecha a sessão HTTP."""
        if self._session:
            await self._session.close()
            self._session = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((asyncio.TimeoutError, OSError)),
    )
    async def send(self, notification: dict[str, Any]) -> NotificationResult:
        """
        Envia notificação para Slack.

        Args:
            notification: Dados da notificação

        Returns:
            NotificationResult com status do envio
        """
        timestamp = datetime.now()

        # Adiciona timestamp à notificação
        notification["timestamp"] = int(timestamp.timestamp())
        notification["timestamp_formatted"] = timestamp.isoformat()

        # Converte para formato Slack
        slack_message = NotificationTemplate.to_slack_message(notification)

        # Determina canal baseado na prioridade
        priority = notification.get("priority", "info")
        channel = (
            self.config.slack_critical_channel
            if priority == "critical"
            else self.config.slack_default_channel
        )

        try:
            session = await self._get_session()

            self.logger.info(
                "sending_slack_notification",
                channel=channel,
                title=notification.get("title"),
                priority=priority,
            )

            async with session.post(
                self.webhook_url,
                json=slack_message,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    self.logger.info(
                        "slack_notification_sent",
                        channel=channel,
                    )
                    return NotificationResult(
                        success=True,
                        channel="slack",
                        message=f"Enviado para {channel}",
                        timestamp=timestamp,
                    )
                else:
                    error_text = await response.text()
                    self.logger.error(
                        "slack_notification_failed",
                        status=response.status,
                        error=error_text,
                    )
                    return NotificationResult(
                        success=False,
                        channel="slack",
                        message=f"Erro {response.status}: {error_text}",
                        timestamp=timestamp,
                    )

        except Exception as e:
            self.logger.error(
                "slack_notification_exception",
                error=str(e),
                error_type=type(e).__name__,
            )
            return NotificationResult(
                success=False,
                channel="slack",
                message=f"Exceção: {e!s}",
                timestamp=timestamp,
            )


class EmailNotifier(BaseNotifier):
    """
    Notificador via Email (SMTP).

    Envia emails HTML formatados usando SMTP.
    """

    def __init__(self, config: NotificationConfig):
        """
        Inicializa o notificador Email.

        Args:
            config: Configurações de notificação
        """
        super().__init__(config)
        self.smtp_host = config.smtp_host
        self.smtp_port = config.smtp_port
        self.smtp_username = config.smtp_username
        self.smtp_password = config.smtp_password
        self.use_tls = config.smtp_use_tls

    def validate_config(self) -> bool:
        """Valida se configuração SMTP está completa."""
        return bool(self.smtp_host and self.config.email_from and self.config.email_to)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((smtplib.SMTPException, OSError)),
    )
    async def send(self, notification: dict[str, Any]) -> NotificationResult:
        """
        Envia notificação por email.

        Args:
            notification: Dados da notificação

        Returns:
            NotificationResult com status do envio
        """
        timestamp = datetime.now()

        # Adiciona timestamp à notificação
        notification["timestamp"] = int(timestamp.timestamp())
        notification["timestamp_formatted"] = timestamp.isoformat()

        # Converte para HTML
        html_body = NotificationTemplate.to_email_html(notification)
        subject = NotificationTemplate.to_email_subject(notification)

        try:
            # Executa em thread pool pois smtplib é síncrono
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._send_sync, subject, html_body
            )

            self.logger.info(
                "email_notification_sent",
                to=self.config.email_to,
                subject=subject,
            )

            return NotificationResult(
                success=result,
                channel="email",
                message="Enviado" if result else "Falha no envio",
                timestamp=timestamp,
            )

        except Exception as e:
            self.logger.error(
                "email_notification_exception",
                error=str(e),
                error_type=type(e).__name__,
            )
            return NotificationResult(
                success=False,
                channel="email",
                message=f"Exceção: {e!s}",
                timestamp=timestamp,
            )

    def _send_sync(self, subject: str, html_body: str) -> bool:
        """
        Envia email de forma síncrona (executado em executor).

        Args:
            subject: Assunto do email
            html_body: Corpo HTML do email

        Returns:
            True se enviado com sucesso
        """
        try:
            # Cria mensagem
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.email_from
            msg["To"] = ", ".join(self.config.email_to)

            # Anexa HTML
            html_part = MIMEText(html_body, "html")
            msg.attach(html_part)

            # Conecta e envia
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)

                server.send_message(msg)

            return True

        except Exception as e:
            self.logger.error(
                "smtp_send_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise


class NotificationManager:
    """
    Gerenciador de notificações.

    Coordena envio para múltiplos canais com fallback e retry.
    """

    def __init__(self, config: Optional[NotificationConfig] = None):
        """
        Inicializa o gerenciador de notificações.

        Args:
            config: Configurações de notificação (usa env se None)
        """
        if config is None:
            config = NotificationConfig.from_env()

        self.config = config
        self.notifiers: list[BaseNotifier] = []
        self.logger = logger.bind(component="NotificationManager")

        # Inicializa notificadores habilitados
        self._initialize_notifiers()

    def _initialize_notifiers(self):
        """Inicializa notificadores baseado na configuração."""
        for channel in self.config.enabled_channels:
            if channel == "slack" and self.config.is_channel_enabled("slack"):
                slack = SlackNotifier(self.config)
                if slack.validate_config():
                    self.notifiers.append(slack)
                    self.logger.info("slack_notifier_initialized")
                else:
                    self.logger.warning(
                        "slack_notifier_disabled_invalid_config"
                    )

            elif channel == "email" and self.config.is_channel_enabled("email"):
                email = EmailNotifier(self.config)
                if email.validate_config():
                    self.notifiers.append(email)
                    self.logger.info("email_notifier_initialized")
                else:
                    self.logger.warning(
                        "email_notifier_disabled_invalid_config"
                    )

        self.logger.info(
            "notification_manager_initialized",
            enabled_channels=self.config.enabled_channels,
            active_notifiers=len(self.notifiers),
        )

    async def notify(
        self,
        notification: dict[str, Any],
        channels: Optional[list[str]] = None,
    ) -> list[NotificationResult]:
        """
        Envia notificação para os canais configurados.

        Args:
            notification: Dados da notificação
            channels: Lista de canais específicos (usa todos se None)

        Returns:
            Lista de resultados por canal
        """
        if not self.notifiers:
            self.logger.warning("no_notifiers_configured_skipping")
            return []

        results = []

        # Filtra notificadores por canal se especificado
        notifiers = self.notifiers
        if channels:
            channel_map = {"slack": SlackNotifier, "email": EmailNotifier}
            notifiers = [
                n
                for n in self.notifiers
                if any(isinstance(n, channel_map.get(c)) for c in channels)
            ]

        # Envia para cada notificador
        for notifier in notifiers:
            try:
                result = await notifier.send(notification)
                results.append(result)
            except Exception as e:
                self.logger.error(
                    "notification_failed",
                    notifier=notifier.__class__.__name__,
                    error=str(e),
                )
                results.append(
                    NotificationResult(
                        success=False,
                        channel=notifier.__class__.__name__.replace("Notifier", "").lower(),
                        message=str(e),
                        timestamp=datetime.now(),
                    )
                )

        return results

    async def notify_retrain_triggered(
        self,
        model_name: str,
        model_version: str,
        drift_type: str,
        drift_score: float,
        priority: str = "warning",
    ) -> list[NotificationResult]:
        """
        Envia notificação de retrain triggered.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo
            drift_type: Tipo de drift
            drift_score: Score do drift
            priority: Prioridade da notificação

        Returns:
            Lista de resultados
        """
        notification = NotificationTemplate.retrain_triggered(
            model_name=model_name,
            model_version=model_version,
            drift_type=drift_type,
            drift_score=drift_score,
            priority=priority,
        )

        return await self.notify(notification)

    async def notify_retrain_success(
        self,
        model_name: str,
        model_version: str,
        new_version: str,
        duration_seconds: float,
        metrics: Optional[dict[str, float]] = None,
    ) -> list[NotificationResult]:
        """
        Envia notificação de retrain success.

        Args:
            model_name: Nome do modelo
            model_version: Versão anterior
            new_version: Nova versão
            duration_seconds: Duração do retrain
            metrics: Métricas do novo modelo

        Returns:
            Lista de resultados
        """
        notification = NotificationTemplate.retrain_success(
            model_name=model_name,
            model_version=model_version,
            new_version=new_version,
            duration_seconds=duration_seconds,
            metrics=metrics,
        )

        return await self.notify(notification)

    async def notify_retrain_failed(
        self,
        model_name: str,
        model_version: str,
        error_message: str,
        retry_attempt: Optional[int] = None,
    ) -> list[NotificationResult]:
        """
        Envia notificação de retrain failed.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo
            error_message: Mensagem de erro
            retry_attempt: Tentativa de retry

        Returns:
            Lista de resultados
        """
        notification = NotificationTemplate.retrain_failed(
            model_name=model_name,
            model_version=model_version,
            error_message=error_message,
            retry_attempt=retry_attempt,
        )

        return await self.notify(notification)

    async def notify_drift_detected(
        self,
        model_name: str,
        drift_type: str,
        drift_score: float,
        severity: str,
    ) -> list[NotificationResult]:
        """
        Envia notificação de drift detected.

        Args:
            model_name: Nome do modelo
            drift_type: Tipo de drift
            drift_score: Score do drift
            severity: Severidade

        Returns:
            Lista de resultados
        """
        notification = NotificationTemplate.drift_detected(
            model_name=model_name,
            drift_type=drift_type,
            drift_score=drift_score,
            severity=severity,
        )

        return await self.notify(notification)

    async def close(self):
        """Fecha recursos dos notificadores."""
        for notifier in self.notifiers:
            if hasattr(notifier, "close"):
                await notifier.close()


def get_notification_manager(
    config: Optional[NotificationConfig] = None,
) -> NotificationManager:
    """
    Factory para NotificationManager.

    Args:
        config: Configurações de notificação

    Returns:
        Instância de NotificationManager
    """
    return NotificationManager(config)
