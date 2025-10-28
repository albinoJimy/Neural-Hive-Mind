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
  'specialist_type': str,  # business, technical, behavior, evolution, architecture
  'domain': str,  # workflow-analysis, code-quality, user-journey, etc.
  'pheromone_type': enum,  # SUCCESS, FAILURE, WARNING
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

### Chave Redis
```
pheromone:{specialist_type}:{domain}:{pheromone_type}
```

### Lista de Feromônios Ativos
```
pheromones:active:{specialist_type}:{domain}
```

## Operações

### 1. Publicar Feromônio
```python
await pheromone_client.publish_pheromone(
    specialist_type='business',
    domain='workflow-analysis',
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
    specialist_type='business',
    domain='workflow-analysis',
    pheromone_type=PheromoneType.SUCCESS
)
```

### 3. Calcular Peso Dinâmico
```python
weight = await pheromone_client.calculate_dynamic_weight(
    specialist_type='business',
    domain='workflow-analysis',
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
- `neural_hive_pheromones_published_total{specialist_type, domain, pheromone_type}`
- `neural_hive_pheromone_strength{specialist_type, domain, pheromone_type}`
- `neural_hive_specialist_dynamic_weight{specialist_type, domain}`
- `neural_hive_pheromone_decay_rate{specialist_type, domain}`

### Logs Estruturados
- Publicação: `specialist_type`, `domain`, `pheromone_type`, `strength`, `signal_id`
- Consulta: `specialist_type`, `domain`, `current_strength`, `age_hours`
- Peso dinâmico: `base_weight`, `net_strength`, `adjusted_weight`

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
