# Guia de Integração - Validação Proativa de Tickets

## Modificações Necessárias em main.py

### 1. Imports Adicionais (após linha 51)

```python
from src.clients.vault_client import GuardVaultClient
from src.clients.trivy_client import TrivyClient
from src.services.security_validator import SecurityValidator
from src.services.guardrail_enforcer import GuardrailEnforcer
from src.consumers.ticket_consumer import TicketConsumer
from src.producers.validation_producer import ValidationProducer
from src.api import validation
```

### 2. Inicialização do Vault Client (após linha ~90 - após Redis)

```python
# Inicializar Vault Client (se habilitado)
vault_client = None
if settings.vault_enabled:
    logger.info("guard_agent.initializing_vault_client")
    vault_client = GuardVaultClient(settings)
    try:
        await vault_client.initialize()
        logger.info("guard_agent.vault_client_ready")
    except Exception as e:
        logger.warning("guard_agent.vault_client_failed", error=str(e))
        if not settings.vault_fail_open:
            raise
        vault_client = None
app.state.vault_client = vault_client
```

### 3. Inicialização do Trivy Client (após Prometheus Client, linha ~164)

```python
# Inicializar Trivy Client (se habilitado)
trivy_client = None
if settings.trivy_enabled:
    logger.info("guard_agent.initializing_trivy_client")
    trivy_client = TrivyClient(
        base_url=settings.trivy_url,
        timeout=settings.trivy_timeout_seconds
    )
    try:
        await trivy_client.connect()
        logger.info("guard_agent.trivy_client_ready")
    except Exception as e:
        logger.warning("guard_agent.trivy_client_failed", error=str(e))
        trivy_client = None
app.state.trivy_client = trivy_client
```

### 4. Inicialização do SecurityValidator e GuardrailEnforcer (após Message Handler, linha ~178)

```python
# Inicializar SecurityValidator e GuardrailEnforcer
logger.info("guard_agent.initializing_security_validator")
security_validator = SecurityValidator(
    opa_client=opa_client,
    k8s_client=k8s_client,
    vault_client=vault_client,
    trivy_client=trivy_client,
    redis_client=redis_client,
    mongodb_client=mongodb
)
app.state.security_validator = security_validator

guardrail_enforcer = GuardrailEnforcer(
    opa_client=opa_client,
    mongodb_client=mongodb,
    redis_client=redis_client,
    mode=settings.guardrails_mode
)
app.state.guardrail_enforcer = guardrail_enforcer
```

### 5. Inicialização do ValidationProducer (após Kafka Producer, linha ~108)

```python
# Inicializar Validation Producer
logger.info("guard_agent.initializing_validation_producer")
validation_producer = ValidationProducer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topic=settings.kafka_validations_topic
)
await validation_producer.connect()
app.state.validation_producer = validation_producer
```

### 6. Inicialização do TicketConsumer (após consumers existentes, linha ~207)

```python
# Consumer para execution tickets (validação proativa)
logger.info("guard_agent.initializing_ticket_consumer")
ticket_consumer = TicketConsumer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    group_id=f"{settings.kafka_consumer_group}-ticket-validator",
    security_validator=security_validator,
    guardrail_enforcer=guardrail_enforcer,
    validation_producer=validation_producer
)
await ticket_consumer.connect()
await ticket_consumer.start_consuming()
app.state.ticket_consumer = ticket_consumer
```

### 7. Shutdown - Adicionar antes de fechar MongoDB (linha ~246)

```python
# Parar ticket consumer
if hasattr(app.state, 'ticket_consumer'):
    logger.info("guard_agent.stopping_ticket_consumer")
    await app.state.ticket_consumer.stop()

# Fechar validation producer
if hasattr(app.state, 'validation_producer'):
    logger.info("guard_agent.closing_validation_producer")
    await app.state.validation_producer.close()

# Fechar Vault client
if app.state.vault_client:
    logger.info("guard_agent.closing_vault_client")
    await app.state.vault_client.close()

# Fechar Trivy client
if app.state.trivy_client:
    logger.info("guard_agent.closing_trivy_client")
    await app.state.trivy_client.close()
```

### 8. Incluir Router de Validação (após linha 263)

```python
app.include_router(validation.router, prefix="/api/v1", tags=["validation"])
```

### 9. Atualizar MongoDB connect() call (linha ~78)

Modificar:
```python
await mongodb.connect(
    incidents_coll=settings.mongodb_incidents_collection,
    remediation_coll=settings.mongodb_remediation_collection,
    validations_coll=settings.mongodb_validations_collection  # ADICIONAR
)
```

## Resumo das Mudanças

- ✅ 3 novos clientes: VaultClient, TrivyClient
- ✅ 2 novos serviços: SecurityValidator, GuardrailEnforcer
- ✅ 1 novo consumer: TicketConsumer
- ✅ 1 novo producer: ValidationProducer
- ✅ 1 novo router: validation
- ✅ Graceful shutdown para todos os novos componentes
- ✅ Graceful degradation (Vault, Trivy opcionais)
