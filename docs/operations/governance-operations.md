# Operações de Governança - Neural Hive-Mind Fase 1

## Visão Geral
Guia operacional consolidado para gerenciar governança, auditoria, explicabilidade, risk scoring e compliance do Neural Hive-Mind.

## Componentes de Governança

### 1. Pheromone Communication Protocol
- **Implementação**: `services/consensus-engine/src/clients/pheromone_client.py`
- **Armazenamento**: Redis Cluster (TTL 1h) + Neo4j (futuro)
- **Tipos**: SUCCESS, FAILURE, WARNING
- **Decay**: 10% por hora (exponencial)
- **Uso**: Coordenação de enxame, ajuste de pesos dinâmicos
- **Documentação**: [Pheromone Communication Protocol](../protocols/pheromone-communication-protocol.md)

### 2. Risk Scoring Engine
- **Implementação**: `libraries/python/neural_hive_risk_scoring`
- **Domínios**: Business, Technical, Security, Operational, Compliance
- **Classificação**: LOW, MEDIUM, HIGH, CRITICAL
- **Uso**: Avaliação de planos, decisões, execuções

### 3. Explainability Generator
- **Implementação**: `libraries/python/neural_hive_specialists/explainability_generator.py`
- **Métodos**: SHAP, LIME, rule_based, heuristic
- **Armazenamento**: MongoDB (explainability_ledger)
- **API**: `services/explainability-api` (consulta de explicações)

### 4. Ledger de Auditoria
- **Implementação**: MongoDB (cognitive_ledger, specialist_opinions, consensus_decisions)
- **Integridade**: Hash SHA-256 em cada registro
- **Retenção**: 1-5 anos conforme tipo de dados
- **Auditoria**: 100% dos registros auditáveis

### 5. Compliance e Políticas
- **Implementação**: OPA Gatekeeper + fallback determinístico
- **Políticas**: Definidas em `policies/` e CRDs
- **Enforcement**: Automático via admission controllers
- **Auditoria**: Logs imutáveis assinados

## Operações Comuns

### Consultar Feromônios
```bash
# Via Redis diretamente
kubectl exec -n redis-cluster <pod> -- redis-cli KEYS 'pheromone:*'

# Consultar feromônio específico
kubectl exec -n redis-cluster <pod> -- redis-cli GET 'pheromone:business:workflow-analysis:success'

# Listar todos os feromônios ativos de um especialista
kubectl exec -n redis-cluster <pod> -- redis-cli KEYS 'pheromone:business:*'
```

### Consultar Risk Scores
```bash
# Via MongoDB
mongosh mongodb://mongodb:27017/neural_hive

# Distribuição de risk scores
db.cognitive_ledger.aggregate([
  {$group: {
    _id: "$risk_band",
    count: {$sum: 1},
    avg_score: {$avg: "$risk_score"}
  }}
])

# Top 10 entidades de alto risco
db.cognitive_ledger.find({risk_band: {$in: ['high', 'critical']}}).sort({risk_score: -1}).limit(10)

# Via Prometheus
curl http://prometheus:9090/api/v1/query?query=neural_hive_risk_score
```

### Consultar Explicações
```bash
# Via API de Explicabilidade
curl http://explainability-api:8000/api/v1/explainability/<token>

# Explicações por plano
curl http://explainability-api:8000/api/v1/explainability/by-plan/<plan_id>

# Explicações por decisão
curl http://explainability-api:8000/api/v1/explainability/by-decision/<decision_id>

# Estatísticas de explicabilidade
curl http://explainability-api:8000/api/v1/explainability/stats

# Via MongoDB diretamente
mongosh mongodb://mongodb:27017/neural_hive
db.explainability_ledger.findOne({explainability_token: '<token>'})
```

### Verificar Integridade do Ledger
```bash
# Via MongoDB - verificar registros com hash
mongosh mongodb://mongodb:27017/neural_hive

# Contar registros com hash
db.cognitive_ledger.countDocuments({hash: {$exists: true}})

# Verificar registros sem hash (potencial problema)
db.cognitive_ledger.find({hash: {$exists: false}}).limit(10)

# Verificar integridade de hash (exemplo de script de verificação)
# Implementar script Python para recalcular e comparar hashes
```

### Consultar Compliance
```bash
# Verificar violações OPA Gatekeeper
kubectl get constraints -A

# Verificar violações de constraint específico
kubectl get <constraint-name> -o yaml

# Listar todas as constraints ativas
kubectl get constrainttemplates

# Métricas de compliance via Prometheus
curl http://prometheus:9090/api/v1/query?query=gatekeeper_constraint_violations
```

### Dashboards de Governança
```bash
# Port-forward Grafana
kubectl port-forward -n neural-hive-observability svc/grafana 3000:80

# Acessar dashboards principais:
# - Governance Executive Dashboard: http://localhost:3000/d/governance-executive-dashboard
# - Consensus Governance: http://localhost:3000/d/consensus-governance
# - Data Governance: http://localhost:3000/d/data-governance
# - Specialists Cognitive Layer: http://localhost:3000/d/specialists-cognitive-layer
```

## Troubleshooting

### Feromônios não sendo publicados
**Sintomas**: Métricas `neural_hive_pheromones_published_total` zeradas ou estagnadas

**Diagnóstico**:
```bash
# Verificar conectividade com Redis
kubectl exec -n consensus-engine <pod> -- redis-cli -h redis-cluster ping

# Verificar logs do consensus-engine
kubectl logs -n consensus-engine <pod> --tail=100 | grep pheromone

# Verificar TTL e decay rate
kubectl exec -n redis-cluster <pod> -- redis-cli TTL 'pheromone:business:workflow-analysis:success'
```

**Resolução**:
- Verificar configuração de Redis (host, porta, autenticação)
- Verificar se feature flag `enable_pheromones` está habilitada
- Verificar se há erros de serialização nos logs
- Reiniciar consensus-engine se necessário

### Risk scores inconsistentes
**Sintomas**: Scores muito baixos ou muito altos para entidades similares

**Diagnóstico**:
```bash
# Consultar configuração de pesos
kubectl get configmap -n semantic-translation-engine risk-scoring-config -o yaml

# Verificar logs de cálculo de risk
kubectl logs -n semantic-translation-engine <pod> | grep risk_score

# Comparar scores similares
mongosh --eval "db.cognitive_ledger.find({domain: 'workflow-analysis'}).sort({risk_score: -1})"
```

**Resolução**:
- Revisar configuração de pesos por domínio
- Verificar thresholds de classificação (LOW/MEDIUM/HIGH/CRITICAL)
- Considerar recalibração baseada em feedback histórico
- Ajustar heurísticas se necessário

### Explicações ausentes
**Sintomas**: Decisões sem `explainability_token` ou consultas retornando 404

**Diagnóstico**:
```bash
# Verificar conectividade com MongoDB
kubectl exec -n explainability-api <pod> -- mongosh mongodb://mongodb:27017/admin --eval "db.runCommand({ping: 1})"

# Verificar logs do explainability generator
kubectl logs -n semantic-translation-engine <pod> | grep explainability

# Verificar feature flag
kubectl get configmap -n semantic-translation-engine app-config -o yaml | grep enable_explainability

# Verificar espaço em disco no MongoDB
kubectl exec -n mongodb-cluster <pod> -- df -h
```

**Resolução**:
- Habilitar feature flag `enable_explainability` se desabilitada
- Verificar permissões de escrita no MongoDB
- Aumentar espaço em disco se necessário
- Reiniciar explainability-api se houver falhas de conexão

### Violações de integridade no ledger
**Sintomas**: Registros com hash incorreto ou ausente

**Diagnóstico**:
```bash
# Executar verificação de hash (script customizado)
python scripts/verify-ledger-integrity.py

# Identificar registros corrompidos
mongosh --eval "db.cognitive_ledger.find({hash: {$exists: false}})"

# Verificar logs de escrita
kubectl logs -n semantic-translation-engine <pod> | grep "ledger_write"
```

**Resolução**:
- Investigar causa raiz (falha de escrita, corrupção de dados, ataque)
- Restaurar de backup se disponível
- Recalcular hashes para registros válidos
- Marcar registros corrompidos para revisão manual

### Compliance violations aumentando
**Sintomas**: Alertas de `ComplianceViolationsCritical` disparando

**Diagnóstico**:
```bash
# Identificar constraint violado
kubectl get constraints -A | grep -v "0"

# Analisar detalhes da violação
kubectl describe constraint <constraint-name>

# Verificar mudanças recentes
kubectl get events -n <namespace> --sort-by='.lastTimestamp' | head -20

# Verificar logs de aplicação
kubectl logs -n <namespace> <pod> --tail=100
```

**Resolução**:
- Analisar causa raiz (mudança de código, configuração, política)
- Ajustar políticas OPA se apropriado (com aprovação)
- Remediar violações (corrigir código ou configuração)
- Criar ticket para mudanças estruturais se necessário

## Métricas de Governança (SLOs)

### SLOs da Fase 1
- **Auditabilidade**: 100% dos registros com hash SHA-256
- **Explicabilidade**: 100% das decisões com explainability_token
- **Divergência entre especialistas**: < 5%
- **Confiança agregada**: ≥ 0.8
- **Latência de consenso**: < 120ms
- **Taxa de fallback determinístico**: < 3%
- **Compliance em controles críticos**: 100%

### Verificar SLOs
```bash
# Port-forward Prometheus
kubectl port-forward -n neural-hive-observability svc/prometheus 9090:9090

# Consultar SLOs via PromQL
# Auditabilidade
rate(neural_hive_ledger_writes_total[5m])

# Explicabilidade
rate(neural_hive_explainability_tokens_generated_total[5m]) / rate(neural_hive_consensus_decisions_total[5m])

# Divergência
histogram_quantile(0.95, neural_hive_specialist_divergence_bucket)

# Confiança agregada
histogram_quantile(0.50, neural_hive_aggregated_confidence_bucket)

# Latência de consenso
histogram_quantile(0.95, neural_hive_consensus_duration_seconds_bucket)
```

## Runbooks

### Runbook: Violação de Auditabilidade
1. Identificar registros sem hash
2. Verificar logs de escrita no ledger
3. Investigar causa raiz (falha de rede, MongoDB, código)
4. Recalcular hashes ausentes (script de recuperação)
5. Criar incidente se perda de dados
6. Revisar políticas de backup

### Runbook: Falha de Explicabilidade
1. Verificar health da Explainability API
2. Verificar conectividade com MongoDB
3. Verificar feature flag habilitada
4. Verificar espaço em disco
5. Reiniciar serviço se necessário
6. Regenerar explicações ausentes (backfill)

### Runbook: Divergência Alta entre Especialistas
1. Identificar plano com divergência > 5%
2. Analisar pareceres individuais
3. Verificar se há bug em especialista específico
4. Verificar dados de entrada (plano malformado?)
5. Escalar para revisão humana
6. Ajustar pesos se padrão recorrente

## Dashboards
- [Governance Executive Dashboard](http://grafana/d/governance-executive-dashboard) - Visão executiva consolidada
- [Consensus Governance](http://grafana/d/consensus-governance) - Consenso e divergência
- [Data Governance](http://grafana/d/data-governance) - Qualidade de dados e compliance
- [Specialists Cognitive Layer](http://grafana/d/specialists-cognitive-layer) - Especialistas neurais
- [Memory Layer Data Quality](http://grafana/d/memory-layer-data-quality) - Camada de memória

## Alertas
- **Governance Alerts**: `monitoring/alerts/governance-alerts.yaml` (novo)
- **Consensus Alerts**: `monitoring/alerts/consensus-alerts.yaml`
- **Data Quality Alerts**: `monitoring/alerts/data-quality-alerts.yaml`
- **Security Alerts**: `monitoring/alerts/security-alerts.yaml`

## Referências
- [Documento 04 - Segurança e Governança](../../documento-04-seguranca-governanca-neural-hive-mind.md)
- [Documento 06 - Fluxos Operacionais](../../documento-06-fluxos-processos-neural-hive-mind.md)
- [Pheromone Communication Protocol](../protocols/pheromone-communication-protocol.md)
- [Camada Estratégica](../observability/services/agentes/camada-estrategica.md)
- [Camada de Resiliência](../observability/services/agentes/camada-resiliencia.md)
- [Runbook Geral](runbook.md)
- [Memory Layer Operations](memory-layer-operations.md)
- [Specialists Operations](specialists-operations.md)

## Contacts & Escalation
- **Governança**: Equipe de Compliance e Auditoria
- **Risk Scoring**: Equipe de Segurança da Informação
- **Explicabilidade**: Equipe de ML/AI
- **Pheromones**: Equipe de Arquitetura de Sistemas
- **On-call**: Seguir procedimento de escalation padrão
