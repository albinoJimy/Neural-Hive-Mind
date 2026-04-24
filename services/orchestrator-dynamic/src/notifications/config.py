"""
Configurações do Sistema de Notificações.

Define templates, prioridades e configurações para envio de notificações
via Slack e Email.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class NotificationPriority(Enum):
    """Níveis de prioridade para notificações."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class NotificationConfig:
    """
    Configurações do sistema de notificações.

    Attributes:
        slack_webhook_url: URL do webhook Slack
        slack_default_channel: Canal padrão para notificações
        slack_critical_channel: Canal para alertas críticos
        smtp_host: Host do servidor SMTP
        smtp_port: Porta do servidor SMTP
        smtp_username: Usuário SMTP (opcional)
        smtp_password: Senha SMTP (opcional)
        smtp_use_tls: Usar TLS para conexão SMTP
        email_from: Endereço de origem dos emails
        email_to: Lista de destinatários padrão
        enabled_channels: Canais habilitados (slack, email)
        retry_max_attempts: Máximo de tentativas de retry
        retry_initial_delay: Delay inicial entre retries (segundos)
    """

    # Slack
    slack_webhook_url: Optional[str] = None
    slack_default_channel: str = "#ml-alerts"
    slack_critical_channel: str = "#ml-alerts-critical"
    slack_username: str = "NeuralHive ML"
    slack_icon_emoji: str = ":robot_face:"

    # Email (SMTP)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    email_from: str = "noreply@neuralhive.local"
    email_to: list[str] = None

    # Configurações gerais
    enabled_channels: list[str] = None
    retry_max_attempts: int = 3
    retry_initial_delay: float = 1.0

    def __post_init__(self):
        """Inicializa valores padrão."""
        if self.email_to is None:
            self.email_to = []
        if self.enabled_channels is None:
            self.enabled_channels = []

    @classmethod
    def from_env(cls, env_vars: Optional[dict[str, str]] = None) -> "NotificationConfig":
        """
        Cria configuração a partir de variáveis de ambiente.

        Args:
            env_vars: Dicionário de variáveis de ambiente (usa os.environ se None)

        Returns:
            Instância de NotificationConfig
        """
        import os

        if env_vars is None:
            env_vars = os.environ

        enabled = []
        if env_vars.get("NOTIFICATION_SLACK_ENABLED", "false").lower() == "true":
            enabled.append("slack")
        if env_vars.get("NOTIFICATION_EMAIL_ENABLED", "false").lower() == "true":
            enabled.append("email")

        email_to = []
        email_to_str = env_vars.get("NOTIFICATION_EMAIL_TO", "")
        if email_to_str:
            email_to = [e.strip() for e in email_to_str.split(",")]

        return cls(
            slack_webhook_url=env_vars.get("SLACK_WEBHOOK_URL"),
            slack_default_channel=env_vars.get(
                "SLACK_ALERTS_CHANNEL", "#ml-alerts"
            ),
            slack_critical_channel=env_vars.get(
                "SLACK_CRITICAL_CHANNEL", "#ml-alerts-critical"
            ),
            slack_username=env_vars.get("SLACK_USERNAME", "NeuralHive ML"),
            slack_icon_emoji=env_vars.get("SLACK_ICON_EMOJI", ":robot_face:"),
            smtp_host=env_vars.get("SMTP_HOST"),
            smtp_port=int(env_vars.get("SMTP_PORT", "587")),
            smtp_username=env_vars.get("SMTP_USERNAME"),
            smtp_password=env_vars.get("SMTP_PASSWORD"),
            smtp_use_tls=env_vars.get("SMTP_USE_TLS", "true").lower() == "true",
            email_from=env_vars.get("EMAIL_FROM", "noreply@neuralhive.local"),
            email_to=email_to,
            enabled_channels=enabled,
            retry_max_attempts=int(env_vars.get("NOTIFICATION_RETRY_MAX", "3")),
            retry_initial_delay=float(env_vars.get("NOTIFICATION_RETRY_DELAY", "1.0")),
        )

    def is_channel_enabled(self, channel: str) -> bool:
        """Verifica se um canal está habilitado."""
        return channel in self.enabled_channels


class NotificationTemplate:
    """Templates para notificações."""

    # Cores para mensagens Slack
    COLOR_INFO = "#36a64f"  # verde
    COLOR_WARNING = "#ff9900"  # laranja
    COLOR_CRITICAL = "#ff0000"  # vermelho
    COLOR_SUCCESS = "#00ff00"  # verde claro

    @staticmethod
    def retrain_triggered(
        model_name: str,
        model_version: str,
        drift_type: str,
        drift_score: float,
        priority: str,
    ) -> dict[str, Any]:
        """
        Template para notificação de retrain triggered.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo
            drift_type: Tipo de drift detectado
            drift_score: Score do drift
            priority: Prioridade da notificação

        Returns:
            Dicionário com dados da notificação
        """
        emoji = ":warning:" if priority == "critical" else ":information_source:"

        return {
            "title": f"{emoji} Retrain Triggered",
            "priority": priority,
            "fields": [
                {"name": "Model", "value": model_name, "short": True},
                {"name": "Version", "value": model_version, "short": True},
                {"name": "Drift Type", "value": drift_type, "short": True},
                {"name": "Drift Score", "value": f"{drift_score:.4f}", "short": True},
                {
                    "name": "Priority",
                    "value": priority.upper(),
                    "short": True,
                },
            ],
            "text": f"Automatic retrain triggered for *{model_name}* v{model_version} due to {drift_type} drift (score: {drift_score:.4f})",
        }

    @staticmethod
    def retrain_success(
        model_name: str,
        model_version: str,
        new_version: str,
        duration_seconds: float,
        metrics: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        """
        Template para notificação de retrain success.

        Args:
            model_name: Nome do modelo
            model_version: Versão anterior do modelo
            new_version: Nova versão do modelo
            duration_seconds: Duração do retrain
            metrics: Métricas do novo modelo (opcional)

        Returns:
            Dicionário com dados da notificação
        """
        fields = [
            {"name": "Model", "value": model_name, "short": True},
            {"name": "Previous Version", "value": model_version, "short": True},
            {"name": "New Version", "value": new_version, "short": True},
            {
                "name": "Duration",
                "value": f"{duration_seconds:.1f}s",
                "short": True,
            },
        ]

        if metrics:
            for key, value in metrics.items():
                fields.append(
                    {"name": key.replace("_", " ").title(), "value": f"{value:.4f}", "short": True}
                )

        return {
            "title": ":white_check_mark: Retrain Successful",
            "priority": "info",
            "fields": fields,
            "text": f"Model *{model_name}* successfully retrained from v{model_version} to v{new_version} in {duration_seconds:.1f}s",
        }

    @staticmethod
    def retrain_failed(
        model_name: str,
        model_version: str,
        error_message: str,
        retry_attempt: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Template para notificação de retrain failed.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo
            error_message: Mensagem de erro
            retry_attempt: Tentativa de retry (opcional)

        Returns:
            Dicionário com dados da notificação
        """
        fields = [
            {"name": "Model", "value": model_name, "short": True},
            {"name": "Version", "value": model_version, "short": True},
        ]

        if retry_attempt is not None:
            fields.append(
                {"name": "Retry Attempt", "value": str(retry_attempt), "short": True}
            )

        return {
            "title": ":x: Retrain Failed",
            "priority": "critical",
            "fields": fields,
            "text": f"Retrain failed for *{model_name}* v{model_version}: {error_message}",
        }

    @staticmethod
    def drift_detected(
        model_name: str,
        drift_type: str,
        drift_score: float,
        severity: str,
    ) -> dict[str, Any]:
        """
        Template para notificação de drift detected.

        Args:
            model_name: Nome do modelo
            drift_type: Tipo de drift
            drift_score: Score do drift
            severity: Severidade (ok, warning, critical)

        Returns:
            Dicionário com dados da notificação
        """
        emoji_map = {
            "ok": ":white_check_mark:",
            "warning": ":warning:",
            "critical": ":rotating_light:",
        }
        emoji = emoji_map.get(severity, ":information_source:")

        return {
            "title": f"{emoji} Drift Detected",
            "priority": severity,
            "fields": [
                {"name": "Model", "value": model_name, "short": True},
                {"name": "Drift Type", "value": drift_type, "short": True},
                {"name": "Score", "value": f"{drift_score:.4f}", "short": True},
                {"name": "Severity", "value": severity.upper(), "short": True},
            ],
            "text": f"Drift detected for model *{model_name}* - {drift_type}: {drift_score:.4f} ({severity})",
        }

    @staticmethod
    def get_color_for_priority(priority: str) -> str:
        """
        Retorna cor Slack baseada na prioridade.

        Args:
            priority: Nível de prioridade

        Returns:
            Código hexadecimal da cor
        """
        color_map = {
            "info": NotificationTemplate.COLOR_INFO,
            "warning": NotificationTemplate.COLOR_WARNING,
            "critical": NotificationTemplate.COLOR_CRITICAL,
        }
        return color_map.get(priority, NotificationTemplate.COLOR_INFO)

    @staticmethod
    def to_slack_message(notification: dict[str, Any]) -> dict[str, Any]:
        """
        Converte notificação para formato Slack.

        Args:
            notification: Dados da notificação

        Returns:
            Mensagem formatada para Slack
        """
        priority = notification.get("priority", "info")
        color = NotificationTemplate.get_color_for_priority(priority)

        attachments = [
            {
                "color": color,
                "title": notification.get("title", "Notification"),
                "text": notification.get("text", ""),
                "fields": notification.get("fields", []),
                "footer": "NeuralHive Orchestrator",
                "ts": int(notification.get("timestamp", 0)),
            }
        ]

        return {"attachments": attachments}

    @staticmethod
    def to_email_html(notification: dict[str, Any]) -> str:
        """
        Converte notificação para HTML de email.

        Args:
            notification: Dados da notificação

        Returns:
            HTML formatado para email
        """
        priority = notification.get("priority", "info")
        color = NotificationTemplate.get_color_for_priority(priority)

        # Header
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 15px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-radius: 0 0 5px 5px; }}
                .field {{ margin: 10px 0; }}
                .field-name {{ font-weight: bold; }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #777; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{notification.get('title', 'Notification')}</h2>
                </div>
                <div class="content">
                    <p>{notification.get('text', '')}</p>
        """

        # Fields
        for field in notification.get("fields", []):
            html += f"""
                    <div class="field">
                        <span class="field-name">{field.get('name', '')}:</span>
                        <span>{field.get('value', '')}</span>
                    </div>
            """

        # Footer
        html += f"""
                    <div class="footer">
                        <p>NeuralHive Orchestrator - IA/ML Pipeline</p>
                        <p>{notification.get('timestamp_formatted', '')}</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    @staticmethod
    def to_email_subject(notification: dict[str, Any]) -> str:
        """
        Gera assunto de email a partir da notificação.

        Args:
            notification: Dados da notificação

        Returns:
            Assunto do email
        """
        priority = notification.get("priority", "info").upper()
        title = notification.get("title", "Notification")
        return f"[{priority}] NeuralHive - {title}"
