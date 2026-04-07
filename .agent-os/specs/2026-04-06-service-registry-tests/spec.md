# Spec: Service Registry - Test Suite Implementation

> **Epic:** Fase 2.4–2.13 Execução - service-registry completion
> **Ticket:** SRV-001
> **Priority:** Alta
> **Status:** Planning

## Overview

Implementar suite completa de testes unitários para o service-registry, que atualmente tem apenas 2 ficheiros de teste.

## Contexto

O service-registry está a 75% completo com funcionalidade core implementada, mas coverage de testes é crítica:

**Estado Atual:**
```
tests/
├── unit/
│   ├── test_agent_type.py      # Testes de conversão protobuf
│   └── test_config_validation.py  # Validação de configs
└── integration/
    ├── test_discover_e2e.py
    └── test_watch_agents_e2e.py
```

**Total: 2 testes unitários** (deveria ter ~40)

## User Stories

### US1: Cobertura de RegistryService

Como **desenvolvedor**, quero **testes unitários para RegistryService**, para **garantir que operações core funcionam**.

**Cenários:**
- Registro de agente com sucesso
- Registro com capabilities vazias
- Registro sem namespace
- Update de heartbeat com telemetria
- Mudança de status via heartbeat
- Desregistro de agente
- Listagem com filtros
- Paginação de resultados

### US2: Cobertura de MatchingEngine

Como **desenvolvedor**, quero **testes para MatchingEngine**, para **garantir seleção correta de agents**.

**Cenários:**
- Match por capabilities
- Match com filtros (namespace, security_level)
- Match com limite de resultados
- Ranking por health score
- Ranking por pheromone score
- Score composto
- Lista vazia de candidates

### US3: Cobertura de HealthCheckManager

Como **operador**, quero **testes para health checks**, para **garantir detecção de agentes unhealthy**.

**Cenários:**
- Início/parada do manager
- Loop de health check
- Detecção de agente expirado
- Remoção de agente unhealthy
- Notificação de autocura

### US4: Cobertura de RedisRegistryClient

Como **desenvolvedor**, quero **testes para client Redis**, para **garantir operações de storage**.

**Cenários:**
- Inicialização com sucesso
- Falha de conexão
- Put/Get/Delete de agentes
- Listagem de agentes
- Fechamento de conexões

## Spec Scope

### Testes a Criar

**1. RegistryService Tests** (`tests/unit/test_registry_service.py`)
```python
- test_register_agent_success()
- test_register_agent_empty_capabilities()
- test_register_agent_missing_namespace()
- test_register_agent_duplicate()
- test_update_heartbeat_success()
- test_update_heartbeat_with_telemetry()
- test_update_heartbeat_status_change()
- test_deregister_agent_success()
- test_deregister_agent_not_found()
- test_get_agent_success()
- test_get_agent_not_found()
- test_list_agents_filtering()
- test_list_agents_pagination()
- test_list_agents_empty()
- test_list_agents_by_capability()
```

**2. MatchingEngine Tests** (`tests/unit/test_matching_engine.py`)
```python
- test_match_agents_by_capabilities()
- test_match_agents_with_filters()
- test_match_agents_max_results()
- test_match_agents_no_candidates()
- test_filter_by_capabilities()
- test_rank_agents_by_health_score()
- test_rank_agents_by_pheromone_score()
- test_rank_agents_by_telemetry_score()
- test_rank_agents_composite_score()
- test_rank_agents_empty_list()
- test_rank_agents_with_tiebreak()
```

**3. HealthCheckManager Tests** (`tests/unit/test_health_check_manager.py`)
```python
- test_start_stop()
- test_health_check_loop()
- test_handle_expired_agent_cycle()
- test_handle_expired_agent_removal()
- test_notify_autocure()
- test_check_agent_health()
- test_multiple_agents_expired()
```

**4. RedisRegistryClient Tests** (`tests/unit/test_redis_client.py`)
```python
- test_initialize_success()
- test_initialize_invalid_endpoint()
- test_put_agent()
- test_get_agent()
- test_get_agent_not_found()
- test_delete_agent()
- test_list_agents()
- test_list_agents_empty()
- test_close()
- test_connection_failure()
- test_retry_on_failure()
```

## Out of Scope

- Testes de integração (já existem em `tests/integration/`)
- Testes E2E (já existem)
- Testes de performance (novo epic separado)
- Testes de carga/stress (novo epic separado)

## Expected Deliverable

1. 4 novos ficheiros de teste unitário
2. Cobertura mínima de 80% para code core
3. Todos os testes passando
4. Fix de qualquer bug descoberto durante testes

## Technical Constraints

- pytest + pytest-asyncio
- Mocks para dependências externas (Redis, MongoDB)
- Fixtures reutilizáveis em conftest.py
- Testes independentes (podem correr em paralelo)
