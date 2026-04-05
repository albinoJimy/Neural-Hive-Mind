# EPIC-205: Alert Engine Integration

**ID:** EPIC-205
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** M (2 semanas)
**Related Service:** sla-management-system

---

## Resumo Executivo

Integrar alert engine proativo no SLA Management System. O sistema já tem excelente detecção de risco (BudgetCalculator) e infraestrutura de notificação (AlertmanagerClient), mas falta o componente que conecta os dois - o cérebro que decide QUANDO alertar e PARA ONDE enviar. Completude atual: 60% (detecção existe, integração não).

---

## Análise Técnica

### Componentes Existentes

| Componente | Status | Gap |
|------------|--------|-----|
| `BudgetCalculator` | ✅ Detecta risco | Não dispara alertas |
| `AlertmanagerClient` | ✅ Existe | Nunca usado |
| `KafkaProducer` | ✅ Publica eventos | Passivo only |
| `SLAEventHandler` | ✅ Processa eventos | Sem alertas proativos |

### Fluxo Atual vs Desejado

```python
# ATUAL (sem alertas proativos)
BudgetCalculator.calculate_budget() → status CRITICAL
→ Kafka publish (ninguém consome)
→ NADA ACONTECE

# DESEJADO (com alertas proativas)
BudgetCalculator.calculate_budget() → status CRITICAL
→ AlertEngine.evaluate_and_send()
→ Alertmanager → Slack/PagerDuty
→ ONCALL RECEBE ALERTA
```

---

## Ticket EPIC-205-01: Criar Alert Engine

**ID:** TICKET-EPIC-205-01
**Priority:** Alta
**Effort:** M (4 dias)

### Tasks

- [ ] 205.01 Criar `src/services/alert_engine.py`
- [ ] 205.02 Implementar `AlertEngine` class
- [ ] 205.03 Implementar `evaluate_and_send()` - avaliação e envio
- [ ] 205.04 Implementar `check_all_budgets()` - varre todos SLOs
- [ ] 205.05 Implementar `should_alert()` - regras de alerta
- [ ] 205.06 Implementar `get_alert_severity()` - severidade baseada em risco
- [ ] 205.07 Criar `src/models/alert_rule.py`
- [ ] 205.08 Implementar `AlertRule` model
- [ ] 205.09 Implementar `AlertSeverity` enum
- [ ] 205.10 Criar tests/test_alert_engine.py
- [ ] 205.11 Testar avaliação de regras
- [ ] 205.12 Testar envio de alertas

### AlertEngine

```python
class AlertEngine:
    """Motor de alertas proativos para SLA."""
    
    def __init__(
        self,
        budget_calculator: BudgetCalculator,
        alert_dispatcher: AlertDispatcher,
        rules_registry: AlertRulesRegistry,
        check_interval_seconds: int = 60
    ):
        self.budget_calculator = budget_calculator
        self.alert_dispatcher = alert_dispatcher
        self.rules_registry = rules_registry
        self.check_interval = check_interval_seconds
        self._running = False
    
    async def start_monitoring(self):
        """Inicia monitoramento contínuo em background."""
        self._running = True
        while self._running:
            await self.check_all_budgets()
            await asyncio.sleep(self.check_interval)
    
    async def stop_monitoring(self):
        """Para monitoramento."""
        self._running = False
    
    async def check_all_budgets(self):
        """Varre todos os SLOs em busca de riscos."""
        
        # Buscar todos os SLOs ativos
        slos = await self.get_active_slos()
        
        for slo in slos:
            # Calcular budget atual
            budget = await self.budget_calculator.calculate_budget(slo.id)
            
            # Avaliar regras de alerta
            if await self.should_alert(budget):
                # Determinar severidade
                severity = self.get_alert_severity(budget)
                
                # Disparar alerta
                await self.alert_dispatcher.send_alert(
                    slo_id=slo.id,
                    budget=budget,
                    severity=severity,
                    rule=self.rules_registry.get_matched_rule(budget)
                )
    
    async def should_alert(self, budget: ErrorBudget) -> bool:
        """Avalia se deve alertar baseado em regras."""
        
        # Regra 1: Status CRITICAL ou EXHAUSTED
        if budget.status in (BudgetStatus.CRITICAL, BudgetStatus.EXHAUSTED):
            return True
        
        # Regra 2: Burn rate alto (vai esgotar em < 1h)
        if budget.time_until_exhausted and budget.time_until_exhausted < 3600:
            return True
        
        # Regra 3: Tendência de degradação
        if self._is_degrading_trend(budget):
            return True
        
        # Regra 4: SLO violado recentemente
        if await self._was_violated_recently(budget.slo_id, hours=1):
            return True
        
        return False
    
    def get_alert_severity(self, budget: ErrorBudget) -> AlertSeverity:
        """Determina severidade baseada no risco."""
        
        if budget.status == BudgetStatus.EXHAUSTED:
            return AlertSeverity.CRITICAL
        
        if budget.status == BudgetStatus.CRITICAL:
            return AlertSeverity.HIGH
        
        if budget.remaining_percentage < 20:
            return AlertSeverity.WARNING
        
        return AlertSeverity.INFO
    
    def _is_degrading_trend(self, budget: ErrorBudget) -> bool:
        """Verifica se o budget está degradando."""
        # Comparar burn rates: 1h vs 6h vs 24h
        if budget.burn_rate_1h > budget.burn_rate_6h * 1.5:
            return True  # Acelerando
        return False
```

### AlertRule Model

```python
from enum import Enum

class AlertSeverity(str, Enum):
    CRITICAL = "critical"  # PagerDuty + Slack #sla-alerts-critical
    HIGH = "high"         # Slack #sla-alerts
    WARNING = "warning"   # Slack #sla-alerts
    INFO = "info"         # Email only

class AlertRule(BaseModel):
    """Regra de alerta para SLOs."""
    
    rule_id: str
    name: str
    description: str
    
    # Condições
    status_trigger: List[BudgetStatus] = Field(default_factory=list)
    remaining_threshold: Optional[float] = None  # < X%
    time_until_exhausted_threshold: Optional[int] = None  # < X segundos
    degradation_rate_multiplier: Optional[float] = None  # > X
    
    # Ação
    severity: AlertSeverity
    channels: List[AlertChannel] = Field(default_factory=list)
    cooldown_minutes: int = 15  # Não spammar
    
    # Metadata
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))

class AlertChannel(str, Enum):
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    EMAIL = "email"
    WEBHOOK = "webhook"
```

### Critérios de Aceite
- [ ] AlertEngine criado
- [ ] Monitoramento contínuo funcionando
- [ ] Regras de alerta funcionando
- [ ] Severidade calculada corretamente
- [ ] Testes passando

---

## Ticket EPIC-205-02: Criar Alert Dispatcher

**ID:** TICKET-EPIC-205-02
**Priority:** Alta
**Effort:** M (4 dias)

### Tasks

- [ ] 205.13 Criar `src/services/alert_dispatcher.py`
- [ ] 205.14 Implementar `AlertDispatcher` class
- [ ] 205.15 Implementar `send_alert()` - envia para canais configurados
- [ ] 205.16 Implementar `send_to_alertmanager()` - integração Alertmanager
- [ ] 205.17 Implementar `send_to_slack()` - Slack webhook
- [ ] 205.18 Implementar `send_to_pagerduty()` - PagerDuty API
- [ ] 205.19 Implementar `send_to_email()` - Email notifications
- [ ] 205.20 Implementar `apply_cooldown()` - evita spam
- [ ] 205.21 Criar tests/test_alert_dispatcher.py
- [ ] 205.22 Testar envio para cada canal

### AlertDispatcher

```python
class AlertDispatcher:
    """Dispatch alertas para múltiplos canais."""
    
    def __init__(
        self,
        alertmanager_client: AlertmanagerClient,
        slack_webhook_url: str,
        pagerduty_api_key: str,
        email_sender: str
    ):
        self.alertmanager = alertmanager_client
        self.slack_webhook = slack_webhook_url
        self.pagerduty_key = pagerduty_api_key
        self.email_sender = email_sender
        
        # Cooldown para evitar spam
        self._last_alert_times: Dict[str, datetime] = {}
    
    async def send_alert(
        self,
        slo_id: str,
        budget: ErrorBudget,
        severity: AlertSeverity,
        rule: AlertRule
    ):
        """Envia alerta para canais configurados na regra."""
        
        # Verificar cooldown
        if not self._can_send_alert(slo_id, rule.cooldown_minutes):
            logger.info(f"Alert for {slo_id} in cooldown, skipping")
            return
        
        # Preparar mensagem
        message = self._format_alert_message(slo_id, budget, severity, rule)
        
        # Enviar para cada canal
        for channel in rule.channels:
            try:
                if channel == AlertChannel.SLACK:
                    await self.send_to_slack(message, severity)
                elif channel == AlertChannel.PAGERDUTY and severity == AlertSeverity.CRITICAL:
                    await self.send_to_pagerduty(message)
                elif channel == AlertChannel.EMAIL:
                    await self.send_to_email(message)
                elif channel == AlertChannel.WEBHOOK:
                    await self.send_to_alertmanager(message)
                
                logger.info(f"Alert sent to {channel} for {slo_id}")
            except Exception as e:
                logger.error(f"Failed to send to {channel}: {e}")
        
        # Registrar timestamp
        self._last_alert_times[slo_id] = datetime.now(timezone.utc)
    
    async def send_to_slack(self, message: str, severity: AlertSeverity):
        """Envia alerta para Slack."""
        import httpx
        
        # Determinar canal baseado na severidade
        if severity == AlertSeverity.CRITICAL:
            channel = "#sla-alerts-critical"
        else:
            channel = "#sla-alerts"
        
        payload = {
            "channel": channel,
            "username": "SLA Bot",
            "icon_emoji": ":warning:",
            "attachments": [
                {
                    "color": self._get_color_for_severity(severity),
                    "title": f"SLA Alert: {message['slo_name']}",
                    "text": message['description'],
                    "fields": [
                        {"title": "Status", "value": message['status'], "short": True},
                        {"title": "Remaining", "value": f"{message['remaining']}%", "short": True},
                        {"title": "Time Until Exhausted", "value": message['time_until'], "short": True}
                    ]
                }
            ]
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(self.slack_webhook, json=payload)
    
    async def send_to_pagerduty(self, message: str):
        """Envia alerta crítico para PagerDuty."""
        import httpx
        
        payload = {
            "routing_key": self.pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": message['title'],
                "severity": "critical",
                "source": "sla-management-system",
                "custom_details": message
            }
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload
            )
    
    async def send_to_alertmanager(self, message: str):
        """Envia alerta para Alertmanager."""
        await self.alertmanager.create_alert(
            name=message['title'],
            message=message['description'],
            severity=message['severity'].lower(),
            labels=message['labels']
        )
    
    def _can_send_alert(self, slo_id: str, cooldown_minutes: int) -> bool:
        """Verifica cooldown para evitar spam."""
        if slo_id not in self._last_alert_times:
            return True
        
        last_time = self._last_alert_times[slo_id]
        cooldown = timedelta(minutes=cooldown_minutes)
        
        return datetime.now(timezone.utc) - last_time > cooldown
    
    def _get_color_for_severity(self, severity: AlertSeverity) -> str:
        """Retorna cor Slack para severidade."""
        colors = {
            AlertSeverity.CRITICAL: "#FF0000",  # Vermelho
            AlertSeverity.HIGH: "#FF6600",      # Laranja
            AlertSeverity.WARNING: "#FFCC00",   # Amarelo
            AlertSeverity.INFO: "#36A64F"       # Verde
        }
        return colors.get(severity, "#36A64F")
    
    def _format_alert_message(
        self,
        slo_id: str,
        budget: ErrorBudget,
        severity: AlertSeverity,
        rule: AlertRule
    ) -> Dict:
        """Formata mensagem de alerta."""
        return {
            "slo_id": slo_id,
            "slo_name": budget.slo_name,
            "title": f"SLA Alert: {budget.slo_name}",
            "description": f"SLO {budget.slo_name} está {budget.status.value}. Budget restante: {budget.remaining_percentage:.1f}%",
            "status": budget.status.value,
            "remaining": budget.remaining_percentage,
            "time_until": self._format_timedelta(budget.time_until_exhausted),
            "severity": severity,
            "rule": rule.name,
            "labels": {
                "slo_id": slo_id,
                "severity": severity.value,
                "status": budget.status.value
            }
        }
```

### Critérios de Aceite
- [ ] AlertDispatcher criado
- [ ] Envio para Slack funcionando
- [ ] Envio para PagerDuty funcionando
- [ ] Envio para Alertmanager funcionando
- [ ] Cooldown funcionando
- [ ] Testes passando

---

## Ticket EPIC-205-03: Integração no Main

**ID:** TICKET-EPIC-205-03
**Priority:** Alta
**Effort:** M (3 dias)

### Tasks

- [ ] 205.23 Modificar `src/main.py`
- [ ] 205.24 Inicializar AlertEngine no lifespan
- [ ] 205.25 Inicializar AlertDispatcher no lifespan
- [ ] 205.26 Iniciar task em background para monitoramento
- [ ] 205.27 Criar endpoint `POST /api/v1/alerts/test` - teste manual
- [ ] 205.28 Criar endpoint `GET /api/v1/alerts/history` - histórico
- [ ] 205.29 Adicionar config em settings.py
- [ ] 205.30 Adicionar variáveis de ambiente
- [ ] 205.31 Testar monitoramento contínuo
- [ ] 205.32 Testar endpoint de teste

### Main.py Refatorado

```python
# src/main.py
from src.services.alert_engine import AlertEngine
from src.services.alert_dispatcher import AlertDispatcher

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting SLA Management System")
    
    # Inicializar Alert Engine
    alert_dispatcher = AlertDispatcher(
        alertmanager_client=alertmanager_client,
        slack_webhook_url=settings.slack_webhook_url,
        pagerduty_api_key=settings.pagerduty_api_key,
        email_sender=settings.alert_email_sender
    )
    
    alert_engine = AlertEngine(
        budget_calculator=budget_calculator,
        alert_dispatcher=alert_dispatcher,
        rules_registry=rules_registry,
        check_interval_seconds=settings.alert_check_interval_seconds
    )
    
    # Iniciar monitoramento em background
    monitoring_task = asyncio.create_task(alert_engine.start_monitoring())
    
    yield {
        "alert_engine": alert_engine,
        "monitoring_task": monitoring_task
    }
    
    # Shutdown
    monitoring_task.cancel()
    await alert_engine.stop_monitoring()
    logger.info("SLA Management System stopped")

app = FastAPI(lifespan=lifespan)

@app.post("/api/v1/alerts/test")
async def test_alert(
    severity: AlertSeverity = AlertSeverity.INFO,
    message: str = "Test alert"
):
    """Envia alerta de teste."""
    # Buscar app.state para componentes
    alert_engine = app.state["alert_engine"]
    
    # Criar budget de teste
    test_budget = ErrorBudget(
        slo_id="test-slo",
        slo_name="Test SLO",
        status=BudgetStatus.WARNING,
        remaining_percentage=15.0,
        time_until_exhausted=3600
    )
    
    # Enviar alerta
    await alert_engine.alert_dispatcher.send_alert(
        slo_id="test-slo",
        budget=test_budget,
        severity=severity,
        rule=AlertRule(
            rule_id="test-rule",
            name="Test Rule",
            description=description,
            severity=severity,
            channels=[AlertChannel.SLACK, AlertChannel.EMAIL],
            cooldown_minutes=0
        )
    )
    
    return {"status": "sent", "message": message}
```

### Critérios de Aceite
- [ ] AlertEngine inicializado no lifespan
- [ ] Monitoramento background rodando
- [ ] Endpoint de teste funcionando
- [ ] Endpoint de histórico funcionando

---

## Ticket EPIC-205-04: Dashboard de Alertas

**ID:** TICKET-EPIC-205-04
**Priority:** Média
**Effort:** S (3 dias)

### Tasks

- [ ] 205.33 Criar coleção `alert_history` no MongoDB
- [ ] 205.34 Persistir todos os alertas enviados
- [ ] 205.35 Criar endpoint `GET /api/v1/alerts/dashboard`
- [ ] 205.36 Implementar agregações: total por dia, por severidade
- [ ] 205.37 Implementar MTTR (mean time to resolution)
- [ ] 205.38 Testar dashboard com dados reais

### Critérios de Aceite
- [ ] Alertas sendo persistidos
- [ ] Endpoint dashboard funcionando
- [ ] Agregações corretas

---

## Resumo do Epic

| Ticket | Descrição | Effort | Deliverables |
|--------|-----------|--------|--------------|
| EPIC-205-01 | Alert Engine | 4 dias | Motor de alertas |
| EPIC-205-02 | Alert Dispatcher | 4 dias | Multi-canais |
| EPIC-205-03 | Integração Main | 3 dias | Background task |
| EPIC-205-04 | Dashboard | 3 dias | Histórico + agregações |
| **TOTAL** | | **2 semanas** | **Alertas proativos** |

---

## Arquitetura Final

```
                    ┌─────────────────────────────────────┐
                    │         Background Task             │
                    │      AlertEngine.start_monitoring()  │
                    │         (a cada 60 segundos)         │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │         AlertEngine                 │
                    │  - check_all_budgets()             │
                    │  - should_alert()                  │
                    │  - get_alert_severity()            │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │       AlertDispatcher              │
                    │  - send_alert()                    │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┬─────────────┐
              ▼                       ▼                       ▼             ▼
    ┌───────────────────┐   ┌──────────────┐   ┌──────────────┐  ┌──────────┐
    │  Slack            │   │ PagerDuty    │   │ Alertmanager │  │  Email   │
    │  #sla-alerts      │   │ (críticos)   │   │              │  │          │
    └───────────────────┘   └──────────────┘   └──────────────┘  └──────────┘
```

---

## Handoff para Claude Code

```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-205 - Alert Engine Integration
Spec: .agent-os/specs/2026-03-31-sprint2-features-incompletas/
```
