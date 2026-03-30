# Spec Requirements Document

> Spec: Test Coverage Improvement
> Created: 2026-03-30
> Status: Planning

## Overview

Aumentar cobertura de testes unitários de **14% para 60%** através da criação estratégica de testes para os componentes mais críticos e com menor cobertura atual.

## Contexto

A análise de cobertura revelou:
- **Cobertura atual: 14%** (304 funções de teste, 679 arquivos de teste)
- **Target: 60%**
- **Gap: 46%**
- **Nenhum serviço atinge 20% de cobertura**

Esta é a maior prioridade técnica restante no projecto.

## Análise de Cobertura Actual

### Serviços com Maior Cobertura (baseado em testes existentes)
1. **approval-service** - ~40 testes
2. **feature-store** - ~25 testes
3. **consensus-engine** - ~20 testes
4. **orchestrator-dynamic** - ~15 testes
5. **neural_hive_specialists** - ~94 testes

### Serviços com Menor Cobertura (prioridade alta)
1. **gateway-intencoes** - Crítico (entrada do sistema)
2. **semantic-translation-engine** - Core cognitive pipeline
3. **queen-agent** - Supervisor principal
4. **worker-agents** - Execução de tarefas
5. **guard-agents** - Segurança
6. **scout-agents** - Exploração
7. **optimizer-agents** - Otimização

## User Stories

### Como Quality Engineer
Eu quero ter 60% de cobertura de testes, para que possamos detectar regressões antes de deploy.

### Como Desenvolvedor
Eu quero testes para os componentes críticos, para que eu possa refactorar com confiança.

### Como DevOps Engineer
Eu quero que o CI/CD bloqueie commits que baixem a cobertura, para que garantimos qualidade mínima.

## Spec Scope

1. **Fase 1 (P0):** Testes para serviços críticos - 25 serviços principais
2. **Fase 2 (P1):** Testes para bibliotecas core - 8 bibliotecas
3. **Fase 3 (P2):** Testes de integração - fluxos E2E

## Out of Scope

- Testes de performance (spec separada)
- Testes de carga/stress (spec separada)
- Testes de segurança penetrativa (spec separada)

## Expected Deliverable

1. **+500 testes unitários** criados
2. **Cobertura global: 60%** mínimo
3. **Todos os serviços críticos** com >40% cobertura
4. **CI/CD configurado** para reportar cobertura

## Success Criteria

- [ ] `pytest --cov` reporta 60%+ cobertura
- [ ] Todos os serviços principais têm >100 testes cada
- [ ] `coverage.xml` gerado no CI/CD
- [ ] Codecov ou similar integrado
- [ ] Nenhum commit baixa a cobertura abaixo de 60%

## Estratégia de Implementação

### Fase 1: Serviços Críticos (Target: +300 testes)
- gateway-intencoes: +50 testes
- semantic-translation-engine: +50 testes
- queen-agent: +40 testes
- worker-agents: +40 testes
- approval-service: +30 testes (adicionais)
- orchestrator-dynamic: +30 testes (adicionais)
- specialist-*: +60 testes (12 por especialista)

### Fase 2: Bibliotecas Core (Target: +150 testes)
- neural_hive_domain: +50 testes
- neural_hive_agent_sdk: +30 testes
- neural_hive_ml: +40 testes
- neural_hive_risk_scoring: +30 testes

### Fase 3: Outros Serviços (Target: +50 testes)
- guard-agents: +15 testes
- scout-agents: +15 testes
- optimizer-agents: +20 testes

## Padrões de Testes a Seguir

### Structure
```
tests/
├── unit/           # Testes unitários (mock tudo)
├── integration/    # Testes de integração (docker-compose)
└── e2e/            # Testes end-to-end (ambiente completo)
```

### Fixtures Comuns (conftest.py)
```python
@pytest.fixture
def mock_config():
    """Configuração padrão para testes."""
    return TestConfig()

@pytest.fixture
def mock_mongodb():
    """MongoDB mock."""
    return AsyncMock()

@pytest.fixture
def mock_kafka():
    """Kafka producer mock."""
    return AsyncMock()
```

### Padrão de Teste
```python
class TestFeature:
    """Testes para Feature X."""

    @pytest.mark.asyncio
    async def test_success_case(self, mock_config):
        """Testa caso de sucesso."""
        result = await feature.execute(config=mock_config)
        assert result.success

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_config):
        """Testa tratamento de erros."""
        with pytest.raises(Exception):
            await feature.execute(config=mock_config)
```
