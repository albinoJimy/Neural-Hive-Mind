# Pheromone Communication Protocol - Neural Hive-Mind

## Visão Geral
Protocolo de comunicação indireta entre agentes do Neural Hive-Mind inspirado em colônias biológicas, permitindo coordenação de enxame sem comunicação direta.

## Arquitetura
- **Armazenamento**: Redis Cluster (curto prazo) + Neo4j/JanusGraph (longo prazo)
- **TTL**: 1 hora (configurável por tipo)
- **Decay**: 10% por hora (exponencial)
- **Tipos**: SUCCESS, FAILURE, WARNING

## Estrutura de Feromônio

### PheromoneSignal Schema
```python
{
  'signal_id': UUID,
  'layer': str,  # strategic, exploration, consensus, specialist
  'domain': UnifiedDomain,  # BUSINESS, TECHNICAL, SECURITY, INFRASTRUCTURE, BEHAVIOR, OPERATIONAL, COMPLIANCE
  'pheromone_type': enum,  # SUCCESS, FAILURE, WARNING, ANOMALY_POSITIVE, ANOMALY_NEGATIVE
  'strength': float,  # 0.0-1.0
  'plan_id': str,
  'intent_id': str,
  'decision_id': str (optional),
  'created_at': datetime,
  'expires_at': datetime,
  'decay_rate': float,  # 0.0-1.0 (taxa de decay por hora)
  'metadata': dict
}
```

### Chave Redis Unificada
```
pheromone:{layer}:{domain}:{pheromone_type}:{id}
```

**Exemplos:**
```
pheromone:strategic:BUSINESS:SUCCESS:plan-123
pheromone:exploration:BEHAVIOR:ANOMALY_POSITIVE:signal-456
pheromone:consensus:SECURITY:WARNING:decision-789
pheromone:specialist:TECHNICAL:SUCCESS:evaluation-012
```

### Domínios Unificados
- **BUSINESS**: Análise de negócios, workflows, processos
- **TECHNICAL**: Código, APIs, performance técnica
- **SECURITY**: Autenticação, autorização, vulnerabilidades
- **INFRASTRUCTURE**: Provisionamento, deployment, escalabilidade
- **BEHAVIOR**: Padrões de uso, UX, jornadas de usuário
- **OPERATIONAL**: Monitoramento, SLAs, alertas, observabilidade
- **COMPLIANCE**: Auditoria, governança, regulamentações

### Lista de Feromônios Ativos
```
pheromones:active:{layer}:{domain}
```

## Operações

### 1. Publicar Feromônio
```python
from neural_hive_domain import UnifiedDomain

await pheromone_client.publish_pheromone(
    layer='strategic',
    domain=UnifiedDomain.BUSINESS,
    pheromone_type=PheromoneType.SUCCESS,
    strength=0.85,
    plan_id='plan-123',
    intent_id='intent-456',
    decision_id='decision-789'
)
```

### 2. Consultar Força de Feromônio
```python
strength = await pheromone_client.get_pheromone_strength(
    layer='strategic',
    domain=UnifiedDomain.BUSINESS,
    pheromone_type=PheromoneType.SUCCESS
)
```

### 3. Calcular Peso Dinâmico
```python
weight = await pheromone_client.calculate_dynamic_weight(
    layer='consensus',
    domain=UnifiedDomain.TECHNICAL,
    base_weight=0.2
)
```

## Cálculo de Força Líquida
```
net_strength = success - failure - (warning * 0.5)
net_strength = max(0.0, min(1.0, net_strength))
```

## Ajuste de Pesos Dinâmicos
```
adjusted_weight = base_weight * (1.0 + net_strength)
adjusted_weight = max(0.05, min(0.4, adjusted_weight))
```

## Decay Temporal
```
current_strength = initial_strength * ((1 - decay_rate) ^ elapsed_hours)
```

## Integração com Camadas

### Camada Cognitiva (Especialistas)
- Publicam feromônios após cada avaliação
- SUCCESS: quando recomendação alinha com decisão final
- FAILURE: quando diverge significativamente
- WARNING: quando diverge moderadamente

### Camada Estratégica (Consensus Engine)
- Consulta feromônios para calcular pesos dinâmicos
- Publica feromônios após decisão consolidada
- Usa net_strength para ajustar confiança em especialistas

### Camada de Exploração (Scout Agents - Futuro)
- Consulta feromônios para priorizar domínios
- Publica feromônios de descoberta
- Usa densidade de feromônios para roteamento

## Métricas e Observabilidade

### Métricas Prometheus
- `neural_hive_pheromones_published_total{layer, domain, pheromone_type}`
- `neural_hive_pheromone_strength{layer, domain, pheromone_type}`
- `neural_hive_specialist_dynamic_weight{layer, domain}`
- `neural_hive_pheromone_decay_rate{layer, domain}`

### Logs Estruturados
- Publicação: `layer`, `domain`, `pheromone_type`, `strength`, `signal_id`
- Consulta: `layer`, `domain`, `current_strength`, `age_hours`
- Peso dinâmico: `layer`, `domain`, `base_weight`, `net_strength`, `adjusted_weight`

### Traces OpenTelemetry
- Span `pheromone.publish` com atributos `pheromone.type`, `pheromone.strength`
- Span `pheromone.query` com atributos `pheromone.cache_hit`

## Políticas de Retenção
- **Redis**: TTL 1 hora (automático)
- **Neo4j** (futuro): versionamento de trilhas, retenção 90 dias
- **MongoDB**: eventos de feromônios, retenção 30 dias

## Segurança e Governança
- Feromônios não contêm PII
- Auditoria de publicações no ledger
- Rate limiting para evitar spam
- Validação de strength (0.0-1.0)

## Referências
- Implementação: `services/consensus-engine/src/clients/pheromone_client.py`
- Modelo: `services/consensus-engine/src/models/pheromone_signal.py`
- Documento 03, §4: Algoritmos Swarm-Based
- Camada de Exploração: `docs/observability/services/agentes/camada-exploracao.md`
