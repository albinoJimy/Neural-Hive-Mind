# Consensus Engine

Serviço de consenso multi-agente do Neural-Hive-Mind.

## Visão Geral

O **Consensus Engine** é responsável por agregar opiniões de múltiplos especialistas e gerar decisões consolidadas. Implementa:

- **Bayesian Aggregation**: Agregação probabilística de confiança e risco
- **Voting Ensemble**: Decisão por votação ponderada
- **Compliance Fallback**: Fallback determinístico quando thresholds não são atendidos
- **Consenso Hierárquico** (GAPS-03): Pesos baseados em senioridade de especialistas

## Arquitetura

```
Cognitive Plan (Kafka)
        ↓
Consensus Orchestrator
    ├── Bayesian Aggregator
    ├── Voting Ensemble
    ├── Hierarchical Weight Calculator (GAPS-03)
    └── Compliance Fallback
        ↓
Consolidated Decision (Kafka)
```

## Funcionalidades

### Bayesian Aggregation

Agrega scores de confiança e risco usando abordagem Bayesiana com prior conjugado.

### Voting Ensemble

Combina recomendações de especialistas usando votação ponderada por pesos dinâmicos.

### Consenso Hierárquico (GAPS-03)

Sistema que permite especialistas mais seniores terem maior peso nas decisões:

- **5 níveis**: trainee, junior, mid_level, senior, expert
- **Multiplicadores**: 0.5× a 2.0×
- **Feature flag**: `ENABLE_HIERARCHICAL_CONSENSUS`

Documentação completa: [docs/GAPS-03-CONSENSO_HIERARQUICO.md](docs/GAPS-03-CONSENSO_HIERARQUICO.md)

## Configuração

### Variáveis de Ambiente Obrigatórias

```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP_ID=consensus-engine

# MongoDB
MONGODB_URI=mongodb://localhost:27017

# Redis
REDIS_CLUSTER_NODES=localhost:6379
```

### Variáveis de Consenso Hierárquico

```bash
# Feature Flag
ENABLE_HIERARCHICAL_CONSENSUS=true

# Mapeamento de senioridade (JSON)
SPECIALIST_SENIORITY='{"business":"senior","technical":"senior","architecture":"expert"}'

# Nível padrão
DEFAULT_SENIORITY_LEVEL=mid_level

# Pesos por domínio (JSON)
DOMAIN_SPECIALIST_WEIGHTS='{"business_BUSINESS":0.25,"technical_TECHNICAL":0.25,"architecture_ARCHITECTURE":0.30}'
```

### Thresholds de Consenso

```bash
MIN_CONFIDENCE_SCORE=0.65
MAX_DIVERGENCE_THRESHOLD=0.25
CRITICAL_RISK_THRESHOLD=0.9
```

## Desenvolvimento

### Estrutura do Projeto

```
src/
├── models/          # Modelos de dados
├── services/        # Serviços de consenso
├── config/          # Configurações
└── observability/   # Métricas e logging

tests/
├── unit_tests/      # Testes unitários
├── integration_tests/ # Testes E2E
└── fixtures/         # Fixtures de teste
```

### Executar Testes

```bash
# Todos os testes
pytest tests/

# Apenas testes hierárquicos
pytest tests/ -k "hierarchical"

# Testes específicos
pytest tests/integration_tests/
pytest tests/seniority_tests/
```

### Linting

```bash
flake8 src/ --max-line-length=100
ruff check src/
```

## Métricas

O serviço expõe métricas Prometheus na porta 8080:

- `consensus_decisions_total` - Total de decisões geradas
- `consensus_duration_seconds` - Tempo de processamento
- `consensus_divergence_score` - Divergência entre especialistas
- `hierarchical_consensus_enabled` - Feature flag status

## Deploy

### Pré-requisitos

- Kubernetes cluster
- Kafka cluster
- MongoDB
- Redis

### Deploy via Helm

```bash
helm repo add neural-hive https://charts.neural-hive.local
helm upgrade neural-hive neural-hive/consensus-engine \
  --set image.tag=latest \
  --set enableHierarchicalConsensus=true
```

### Checklist de Deploy

Verifique [docs/DEPLOY_CHECKLIST_GAPS-03.md](docs/DEPLOY_CHECKLIST_GAPS-03.md) para o checklist completo do consenso hierárquico.

## Monitoramento

### Logs Estruturados

O serviço usa `structlog` para logs estruturados:

```json
{
  "event": "consenso_processado",
  "decision_id": "...",
  "plan_id": "...",
  "final_decision": "approve",
  "aggregated_confidence": 0.85,
  "seniority_distribution": {"senior": 2, "expert": 1}
}
```

### Métricas Importantes

- **Taxa de aprovação**: Deve ser mantida ou melhorada
- **Divergência média**: Deve ser < 0.3 em operação normal
- **Tempo de convergência**: Deve ser < 1 segundo
- **Distribuição de senioridade**: Monitorar balanceamento

## Troubleshooting

### Decisões sempre vão para fallback

Verifique se os thresholds estão configurados corretamente e se os scores de confiança estão sendo calculados adequadamente.

### Pesos hierárquicos não aplicados

Certifique-se que `ENABLE_HIERARCHICAL_CONSENSUS=true` e que os níveis de senioridade estão configurados.

### Alto consumo de memória

O serviço mantém cache de feromônios em Redis. Se houver problemas de memória, reduza o TTL ou desative o cache temporariamente.

## Links Úteis

- [Documentação GAPS-03](docs/GAPS-03-CONSENSO_HIERARQUICO.md)
- [Deploy Checklist](docs/DEPLOY_CHECKLIST_GAPS-03.md)
- [Feature Map](../../docs/feature-map.md)

## Licença

Copyright © 2026 Neural-Hive-Mind
