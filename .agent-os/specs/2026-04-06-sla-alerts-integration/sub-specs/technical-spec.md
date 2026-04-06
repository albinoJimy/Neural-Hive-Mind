# Technical Specification

## SLA Alerts Integration

### Requisitos Técnicos

#### 1. SLA Alert Consumer

**Arquivo:** `services/orchestrator-dynamic/src/consumers/sla_alert_consumer.py`

```python
from aiokafka import AIOKafkaConsumer
from structlog import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import settings
from src.clients.slack_client import SlackClient
from src.clients.pagerduty_client import PagerDutyClient


class SLAAlertConsumer:
    """Consumer para alertas SLA vindos do sla-management-system."""

    TOPICS = ["sla.alerts", "sla.violations"]

    def __init__(
        self,
        slack_client: SlackClient | None = None,
        pagerduty_client: PagerDutyClient | None = None,
    ):
        self.logger = get_logger(__name__)
        self.slack_client = slack_client
        self.pagerduty_client = pagerduty_client
        self.consumer: AIOKafkaConsumer | None = None

    async def start(self):
        """Inicia o consumer Kafka."""
        self.consumer = AIOKafkaConsumer(
            *self.TOPICS,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="orchestrator-sla-alerts",
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        self.logger.info("SLA alert consumer started", topics=self.TOPICS)

    async def stop(self):
        """Para o consumer Kafka."""
        if self.consumer:
            await self.consumer.stop()
            self.logger.info("SLA alert consumer stopped")

    async def consume(self):
        """Consome e processa mensagens de alerta."""
        if not self.consumer:
            raise RuntimeError("Consumer not started")

        async for msg in self.consumer:
            try:
                await self._process_message(msg)
            except Exception as e:
                self.logger.error(
                    "Failed to process SLA alert",
                    error=str(e),
                    topic=msg.topic,
                    partition=msg.partition,
                    offset=msg.offset,
                )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _process_message(self, msg):
        """Processa uma mensagem de alerta."""
        import json

        alert_data = json.loads(msg.value)

        self.logger.info(
            "Processing SLA alert",
            alert_type=alert_data.get("alert_type"),
            severity=alert_data.get("severity"),
        )

        # Despachar baseado na severidade
        severity = alert_data.get("severity", "INFO")

        if severity == "CRITICAL" or severity == "EMERGENCY":
            await self._dispatch_critical(alert_data)
        else:
            await self._dispatch_warning(alert_data)

    async def _dispatch_critical(self, alert_data: dict):
        """Despacha alerta crítico para PagerDuty + Slack."""
        # PagerDuty
        if self.pagerduty_client:
            await self.pagerduty_client.trigger_alert(
                dedup_key=alert_data.get("alert_id"),
                event_type="trigger",
                payload={
                    "summary": alert_data.get("title"),
                    "severity": alert_data.get("severity"),
                    "source": "orchestrator-dynamic",
                    "timestamp": alert_data.get("timestamp"),
                    "custom_details": alert_data.get("details", {}),
                },
            )

        # Slack
        if self.slack_client:
            await self.slack_client.send_message(
                text=f":rotating_light: *CRITICAL ALERT*: {alert_data.get('title')}",
                channel="#sla-alerts-critical",
                blocks=self._format_critical_blocks(alert_data),
            )

    async def _dispatch_warning(self, alert_data: dict):
        """Despacha alerta de warning para Slack."""
        if self.slack_client:
            await self.slack_client.send_message(
                text=f":warning: *WARNING*: {alert_data.get('title')}",
                channel="#sla-alerts",
                blocks=self._format_warning_blocks(alert_data),
            )

    def _format_critical_blocks(self, alert_data: dict) -> list[dict]:
        """Formata alerta crítico em blocks Slack."""
        return [
            {"type": "header", "text": {"type": "plain_text", "text": ":rotating_light: CRITICAL SLA ALERT"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Title:* {alert_data.get('title')}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Severity:* {alert_data.get('severity')}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Workflow:* `{alert_data.get('workflow_id')}`"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Service:* {alert_data.get('service_name')}"}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "View in Grafana"}, "url": "https://grafana.example.com/d/sla"},
            ]},
        ]

    def _format_warning_blocks(self, alert_data: dict) -> list[dict]:
        """Formata alerta de warning em blocks Slack."""
        return [
            {"type": "header", "text": {"type": "plain_text", "text": ":warning: SLA Warning"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Title:* {alert_data.get('title')}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Alert Type:* {alert_data.get('alert_type')}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Budget Remaining:* {alert_data.get('context', {}).get('budget_remaining', 'N/A')}%"}},
        ]
```

#### 2. Slack Client

**Arquivo:** `services/orchestrator-dynamic/src/clients/slack_client.py`

```python
import httpx
from structlog import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import settings


class SlackClient:
    """Cliente para enviar mensagens ao Slack via webhook."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or settings.slack_webhook_url
        self.logger = get_logger(__name__)
        self.client = httpx.AsyncClient(timeout=10.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def send_message(
        self,
        text: str,
        channel: str | None = None,
        blocks: list[dict] | None = None,
    ) -> dict:
        """Envia mensagem para o Slack."""
        if not self.webhook_url:
            self.logger.warning("Slack webhook URL not configured, skipping")
            return {}

        payload = {"text": text}
        if channel:
            payload["channel"] = channel
        if blocks:
            payload["blocks"] = blocks

        response = await self.client.post(self.webhook_url, json=payload)
        response.raise_for_status()

        self.logger.info(
            "Slack message sent",
            channel=channel or "default",
            status_code=response.status_code,
        )
        return response.json()

    async def close(self):
        """Fecha o cliente HTTP."""
        await self.client.aclose()
```

#### 3. PagerDuty Client

**Arquivo:** `services/orchestrator-dynamic/src/clients/pagerduty_client.py`

```python
import httpx
from structlog import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import settings


class PagerDutyClient:
    """Cliente para Events API v2 do PagerDuty."""

    API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str | None = None):
        self.routing_key = routing_key or settings.pagerduty_routing_key
        self.logger = get_logger(__name__)
        self.client = httpx.AsyncClient(timeout=10.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def trigger_alert(
        self,
        dedup_key: str,
        event_type: str = "trigger",
        payload: dict | None = None,
    ) -> dict:
        """Envia alerta para o PagerDuty."""
        if not self.routing_key:
            self.logger.warning("PagerDuty routing key not configured, skipping")
            return {}

        request_payload = {
            "routing_key": self.routing_key,
            "event_action": event_type,
            "dedup_key": dedup_key,
            "payload": payload or {},
        }

        response = await self.client.post(self.API_URL, json=request_payload)
        response.raise_for_status()

        self.logger.info(
            "PagerDuty alert triggered",
            dedup_key=dedup_key,
            status_code=response.status_code,
        )
        return response.json()

    async def acknowledge_alert(self, dedup_key: str) -> dict:
        """Acknowledge um alerta existente."""
        return await self.trigger_alert(dedup_key, event_type="acknowledge")

    async def resolve_alert(self, dedup_key: str) -> dict:
        """Resolve um alerta existente."""
        return await self.trigger_alert(dedup_key, event_type="resolve")

    async def close(self):
        """Fecha o cliente HTTP."""
        await self.client.aclose()
```

#### 4. Configurações

**Arquivo:** `services/orchestrator-dynamic/src/config/settings.py`

```python
# SLA Alerts Integration
enable_sla_alert_consumer: bool = Field(
    default=True,
    description="Habilitar consumer de alertas SLA"
)
slack_webhook_url: str = Field(
    default="",
    description="Webhook URL para Slack (vazio = desabilitado)"
)
pagerduty_routing_key: str = Field(
    default="",
    description="Routing key para PagerDuty Events API v2 (vazio = desabilitado)"
)
sla_alerts_topics: list[str] = Field(
    default=["sla.alerts", "sla.violations"],
    description="Tópicos Kafka para consumir alertas SLA"
)
```

#### 5. Testes E2E

**Arquivo:** `tests/e2e/test_sla_alerts_e2e.py`

```python
import pytest
from aioresponses import aioresponses
from httpx import Response


@pytest.mark.asyncio
class TestSLAAlertsE2E:
    """Testes E2E de integração de alertas SLA."""

    async def test_critical_alert_dispatches_to_pagerduty_and_slack(
        self, sla_alert_consumer, mock_pagerduty, mock_slack
    ):
        """Alerta crítico é despachado para PagerDuty e Slack."""
        # Setup mock responses
        mock_pagerduty.post("https://events.pagerduty.com/v2/enqueue", status=202, payload={"status": "success"})
        mock_slack.post("https://hooks.slack.com/services/TEST", status=200, payload="ok")

        alert_data = {
            "alert_id": "alert-123",
            "title": "SLA Violation: Workflow timeout",
            "severity": "CRITICAL",
            "workflow_id": "orch-123",
            "service_name": "orchestrator-dynamic",
            "timestamp": "2026-04-06T12:00:00Z",
        }

        await sla_alert_consumer._dispatch_critical(alert_data)

        # Assert PagerDuty foi chamado
        assert len(mock_pagerduty.requests) == 1

        # Assert Slack foi chamado
        assert len(mock_slack.requests) == 1

    async def test_warning_alert_dispatches_to_slack_only(
        self, sla_alert_consumer, mock_slack
    ):
        """Alerta de warning é despachado apenas para Slack."""
        mock_slack.post("https://hooks.slack.com/services/TEST", status=200, payload="ok")

        alert_data = {
            "alert_id": "alert-456",
            "title": "SLA Warning: Budget consuming fast",
            "severity": "WARNING",
            "workflow_id": "orch-456",
        }

        await sla_alert_consumer._dispatch_warning(alert_data)

        # Assert Slack foi chamado
        assert len(mock_slack.requests) == 1

    async def test_retry_on_failure(self, sla_alert_consumer, mock_pagerduty):
        """Falha no envio é retried 3 vezes."""
        mock_pagerduty.post("https://events.pagerduty.com/v2/enqueue", status=503)

        alert_data = {
            "alert_id": "alert-789",
            "title": "Test alert",
            "severity": "CRITICAL",
        }

        with pytest.raises(Exception):
            await sla_alert_consumer._dispatch_critical(alert_data)

        # Assert 3 tentativas foram feitas
        assert len(mock_pagerduty.requests) == 3
```

### Dependências Externas

**Novas dependências:**
- `httpx` - Cliente HTTP async (já provavelmente incluído)
- `aioresponses` - Mock de respostas HTTP para testes

**Variáveis de ambiente:**
```bash
# SLA Alerts
ENABLE_SLA_ALERT_CONSUMER=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/XXXX
PAGERDUTY_ROUTING_KEY=INTEGRATION_KEY_HERE
```
