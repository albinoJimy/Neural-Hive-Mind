# Fluxo H - Manual de Operações

> **Versão:** 1.0
> **Data:** 2026-04-16
> **Responsável:** Operations Team

---

## 1. Visão Geral

### 1.1 Arquitetura do Fluxo H

O Fluxo H é o sistema de migração de software legado do Neural-Hive-Mind, composto por 3 componentes principais:

```
DOCUMENTAÇÃO LEGADA
        ↓
DOC INGESTION SERVICE (8018) - Parse e análise
        ↓
GATEWAY INTENÇÕES (8000)
        ↓
FLUXO G (STE → Consensus → Requirements → Architecture → Code)
        ↓
DATA MIGRATION SYSTEM (8019) - Mapeamento e migração
        ↓
CUTOVER ORCHESTRATOR (8003) - Migração gradual
        ↓
SOFTWARE MIGRADO EM PRODUÇÃO
```

### 1.2 Componentes e Responsabilidades

| Serviço | Porta | Responsabilidade | Dependencies |
|---------|-------|------------------|--------------|
| doc-ingestion | 8018 | Parse e extração de entidades de documentos legados | MongoDB, S3/MinIO, Kafka, LLM APIs |
| data-migration | 8019 | Mapeamento de schema, CDC e migração de dados | PostgreSQL/MySQL, MongoDB, Kafka, Debezium |
| orchestrator-dynamic | 8003 | Orquestração de cutover com rollback | Kafka, Temporal, Redis |

### 1.3 Fluxo de Dados

**Caminho Feliz:**
1. Documento legado é enviado ao Doc Ingestion Service
2. Parser extrai conteúdo (PDF/Word/Visio/Postman)
3. Entity Extractor (LLM) identifica entidades e funcionalidades
4. Gateway Intenções recebe entidades e inicia Fluxo G
5. Requirements Engineering gera requisitos do novo sistema
6. Architect Agent projeta arquitetura moderna
7. Code Forge gera código do novo sistema
8. Data Migration System mapeia schemas e migra dados
9. Cutover Orchestrator promove sistema novo gradualmente

---

## 2. Operações Diárias

### 2.1 Health Checks

**Frequência:** A cada 15 minutos (automático via monitoring)

```bash
# Doc Ingestion Service
curl http://doc-ingestion:8018/health

# Data Migration System
curl http://data-migration:8019/health

# Cutover Orchestrator
curl http://orchestrator-dynamic:8003/health

# Check all Fluxo H services
for port in 8018 8019 8003; do
    echo "Checking port $port..."
    curl -f http://localhost:$port/health || echo "FAIL: Port $port"
done
```

**Resposta Esperada:**
```json
{
  "service": "doc-ingestion",
  "status": "healthy",
  "version": "1.0.0",
  "kafka_connected": true,
  "mongodb_connected": true,
  "s3_connected": true
}
```

### 2.2 Monitoramento

**Métricas Principais (Grafana Dashboard: Fluxo H Operations):**

| Métrica | Descrição | Alerta se |
|---------|-----------|-----------|
| `doc_ingestion_docs_processed_total` | Total de documentos processados | < 1/hora por 4h |
| `doc_ingestion_parser_success_rate` | Taxa de sucesso dos parsers | < 95% |
| `data_migration_progress_percentage` | Progresso da migração | Stuck > 1h |
| `data_migration_cdc_lag_seconds` | Lag do CDC | > 60s |
| `cutover_traffic_percentage` | % de tráfego no target | Sudden drop |
| `cutover_error_rate_target` | Error rate do sistema novo | > 1% |

### 2.3 Alertas Típicos

**Alert: Parser Falhou**
```bash
# Verificar logs do parser
kubectl logs -f deployment/doc-ingestion -c parser | grep ERROR

# Verificar formato do documento
curl http://doc-ingestion:8018/api/v1/documents/{doc_id}/status

# Re-processar documento
curl -X POST http://doc-ingestion:8018/api/v1/documents/{doc_id}/parse
```

**Alert: CDC Lag Alto**
```bash
# Verificar lag do Debezium
kubectl exec -it debezium-connector -- \
  curl http://localhost:8083/connectors/data-migration-connector/status

# Verificar se source DB está sob carga
kubectl exec -it postgres-legacy -- \
  psql -U user -c "SELECT count(*) FROM large_table"

# Ajustar poll interval se necessário
kubectl patch connector data-migration-connector --type=json \
  -p='[{"op": "replace", "path": "/config/poll.interval.ms", "value": "1000"}]'
```

---

## 3. Procedimentos Comuns

### 3.1 Iniciar Migração

**Pré-condições:**
- Documentos legados coletados
- Source database acessível
- Schema mapping aprovado
- Target environment provisionado

**Procedimento:**

```bash
# 1. Upload dos documentos
curl -X POST http://doc-ingestion:8018/api/v1/documents/upload \
  -F "file=@user_manual.pdf" \
  -F "file=@technical_spec.docx" \
  -F "file=@database_schema.vsd" \
  -F "file=@api_collection.json" \
  -F "metadata={\"project\":\"legacy_system\",\"version\":\"1.0\"}"

# 2. Aguardar parsing completar
watch curl http://doc-ingestion:8018/api/v1/documents/{doc_id}/status

# 3. Aprovar entidades extraídas
curl -X POST http://doc-ingestion:8018/api/v1/documents/{doc_id}/approve \
  -H "Authorization: Bearer $JWT_TOKEN"

# 4. Criar job de migração de dados
curl -X POST http://data-migration:8019/api/v1/migrations/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "source_db": {
      "type": "postgresql",
      "host": "postgres-legacy",
      "port": 5432,
      "database": "legacy_db",
      "tables": ["users", "orders", "products"]
    },
    "target_db": {
      "type": "mongodb",
      "connection_string": "mongodb://mongodb:27017",
      "database": "new_system"
    },
    "strategy": "hybrid"
  }'

# 5. Aguardar schema mapping
curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/schema-mapping

# 6. Aprovar schema mapping
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/approve \
  -H "Authorization: Bearer $JWT_TOKEN"

# 7. Iniciar migração
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/start

# 8. Monitorar progresso
watch curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/progress
```

### 3.2 Aprovar Schema Mapping

**Contexto:** O LLM propõe um mapeamento de schema que requer aprovação humana.

```bash
# 1. Obter schema mapping proposto
curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/schema-mapping

# Exemplo de resposta:
{
  "source_schema": {
    "table": "users",
    "columns": [
      {"name": "id", "type": "INTEGER", "primary_key": true},
      {"name": "username", "type": "VARCHAR(50)"},
      {"name": "email", "type": "VARCHAR(100)"},
      {"name": "created_at", "type": "TIMESTAMP"}
    ]
  },
  "target_schema": {
    "collection": "users",
    "fields": [
      {"name": "_id", "type": "ObjectId", "source": "id"},
      {"name": "username", "type": "string"},
      {"name": "email", "type": "string"},
      {"name": "created_at", "type": "datetime"},
      {"name": "metadata", "type": "object", "source": "generated"}
    ]
  },
  "transformations": [
    {"from": "id", "to": "_id", "transform": "to_object_id"},
    {"from": null, "to": "metadata", "transform": "generate_default"}
  ],
  "confidence_score": 0.92
}

# 2. Revisar transformações propostas

# 3. Aprovar ou modificar
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/approve \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "modifications": [],
    "approver": "joao.silva",
    "comments": "Schema mapping looks correct. No modifications needed."
  }'
```

### 3.3 Executar Rollback

**Quando executar:**
- Error rate > 5% por 5 minutos consecutivos
- Data corruption detectada
- Sistema target completamente DOWN
- Bugs críticos de negócio

**Procedimento:**

```bash
# 1. Identificar job de migração ativo
curl http://data-migration:8019/api/v1/migrations/jobs?status=in_progress

# 2. Iniciar rollback
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/rollback \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "High error rate detected",
    "initiated_by": "oncall.engineer",
    "preserve_target_data": true
  }'

# 3. Aguardar rollback completar
watch curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/status

# 4. Verificar que tráfego retornou ao legado
curl http://orchestrator-dynamic:8003/api/v1/cutover/status

# 5. Validar dados legados
kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db -c "SELECT count(*) FROM orders"

# 6. Verificar logs do rollback
kubectl logs -f deployment/data-migration | grep rollback
```

### 3.4 Limpeza de Recursos

**Frequência:** Semanal

```bash
# 1. Limpar documentos processados antigos (retention: 90 dias)
kubectl exec -it mongo-0 -- \
  mongo doc_ingestion --eval \
  'db.documents.deleteMany({upload_date: {$lt: new Date(Date.now() - 90*24*60*60*1000)}})'

# 2. Limpar blobs S3/MinIO
mc rm --older-than 90d --recursive minio/nhm-documents/

# 3. Limpar jobs de migração completos
kubectl exec -it mongo-0 -- \
  mongo data_migration --eval \
  'db.migration_jobs.updateMany({status: "completed"}, {$set: {archived: true}})'

# 4. Limpar connectors Debezium não utilizados
kubectl exec -it kafka-connect -- \
  curl -X DELETE http://localhost:8083/connectors/old-connector-name

# 5. Limpar pods evicted
kubectl delete pods --field-selector=status.phase=Failed -l app=fluxo-h

# 6. Limpar PVCs órfãos
kubectl get pvc -A | grep "<none>" && \
  kubectl delete pvc -A --selector=app=fluxo-h --field-selector=status.phase=Bound
```

---

## 4. Manutenção

### 4.1 Backup/Restore

**Backup Diário (automático via CronJob):**

```yaml
# MongoDB Backup
apiVersion: batch/v1
kind: CronJob
metadata:
  name: fluxo-h-mongodb-backup
  namespace: neural-hive-mind
spec:
  schedule: "0 2 * * *"  # 02:00 UTC diário
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: mongo:7
            command:
            - mongodump
            - --uri=mongodb://mongodb:27017
            - --archive=/backup/mongodb-fluxoh-$(date +%Y%m%d).gz
            volumeMounts:
            - name: backup
              mountPath: /backup
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
```

**Restore Manual:**

```bash
# 1. Parar serviços Fluxo H
kubectl scale deployment doc-ingestion --replicas=0
kubectl scale deployment data-migration --replicas=0

# 2. Identificar backup
mc ls minio/backups/mongodb/

# 3. Restore MongoDB
kubectl exec -it mongo-0 -- \
  mongorestore --archive=/backup/mongodb-fluxoh-20260416.gz

# 4. Validar dados
kubectl exec -it mongo-0 -- \
  mongo doc_ingestion --eval "db.documents.count()"

# 5. Reiniciar serviços
kubectl scale deployment doc-ingestion --replicas=1
kubectl scale deployment data-migration --replicas=1

# 6. Verificar health
curl http://doc-ingestion:8018/health
curl http://data-migration:8019/health
```

### 4.2 Atualização de Serviços

**Rolling Update (zero downtime):**

```bash
# 1. Build e push nova imagem
docker build -t registry.nhm.local/doc-ingestion:v1.1.0 services/doc-ingestion/
docker push registry.nhm.local/doc-ingestion:v1.1.0

# 2. Atualizar deployment
kubectl set image deployment/doc-ingestion \
  doc-ingestion=registry.nhm.local/doc-ingestion:v1.1.0

# 3. Monitorar rollout
kubectl rollout status deployment/doc-ingestion

# 4. Verificar nova versão
curl http://doc-ingestion:8018/health
# "version": "1.1.0"

# 5. Se problema, rollback
kubectl rollout undo deployment/doc-ingestion
```

**Blue-Green Deploy (para mudanças maiores):**

```bash
# 1. Deploy green environment
kubectl apply -f k8s/fluxo-h-green/
kubectl wait --for=condition=ready pod -l app=fluxo-h,env=green --timeout=300s

# 2. Validar green
curl http://doc-ingestion-green:8018/health

# 3. Switch traffic (Istio)
kubectl apply -f k8s/istio/virtualservice-fluxoh-green.yaml

# 4. Monitorar por 1h
# Se OK: remover blue
kubectl delete -f k8s/fluxo-h-blue/

# Se PROBLEMA: revert traffic
kubectl apply -f k8s/istio/virtualservice-fluxoh-blue.yaml
```

### 4.3 Escalonamento

**Horizontal (aumentar pods):**

```bash
# 1. Verificar carga atual
kubectl top pods -l app=fluxo-h

# 2. Escalar se necessário
kubectl scale deployment doc-ingestion --replicas=3
kubectl scale deployment data-migration --replicas=2

# 3. Configurar HPA (autoscaling)
kubectl autoscale deployment doc-ingestion \
  --min=2 --max=10 --cpu-percent=70

# 4. Verificar HPA
kubectl get hpa
```

**Vertical (aumentar recursos):**

```bash
# 1. Verificar uso de recursos
kubectl top pod -l app=doc-ingestion --containers

# 2. Editar deployment
kubectl edit deployment doc-ingestion

# Alterar resources:
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"

# 3. Aguardar rollout
kubectl rollout status deployment doc-ingestion
```

---

## 5. Procedimentos de Emergência

### 5.1 Falha Completa do Doc Ingestion

**Sintomas:**
- Todos os parsers falhando
- Service não responde ao /health
- Erro 500 em todas as requests

**Diagnóstico:**

```bash
# 1. Verificar status dos pods
kubectl get pods -l app=doc-ingestion

# 2. Verificar logs recentes
kubectl logs --tail=100 deployment/doc-ingestion

# 3. Verificar eventos
kubectl describe pod doc-ingestion-xxxxx

# 4. Verificar dependências
kubectl exec -it doc-ingestion-xxxxx -- nc -zv mongodb 27017
kubectl exec -it doc-ingestion-xxxxx -- nc -zv kafka 9092
kubectl exec -it doc-ingestion-xxxxx -- nc -zv minio 9000
```

**Resolução:**

```bash
# 1. Tentar restart do pod
kubectl delete pod doc-ingestion-xxxxx

# 2. Se não resolver, restart deployment
kubectl rollout restart deployment/doc-ingestion

# 3. Se persistir, verificar configuração
kubectl get configmap doc-ingestion-config -o yaml

# 4. Verificar variáveis de ambiente
kubectl exec -it doc-ingestion-xxxxx -- env | grep -E "MONGODB|KAFKA|S3|LLM"

# 5. Se problema de API key LLM, rotacionar
kubectl create secret generic llm-api-keys-new \
  --from-literal=openai-api-key=$NEW_OPENAI_KEY
kubectl patch deployment doc-ingestion -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"doc-ingestion","envFrom":[{"secretRef":{"name":"llm-api-keys-new"}}]}]}}}}'
```

### 5.2 Data Corruption no CDC

**Sintomas:**
- Discrepância entre source e target
- Checksum falhando
- Data validator reportando erros

**Diagnóstico:**

```bash
# 1. Verificar relatório de validação
curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate

# 2. Comparar contagens
kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db -c "SELECT count(*) FROM orders"
kubectl exec -it mongo-0 -- \
  mongo new_system --eval "db.orders.count()"

# 3. Verificar Debezium offsets
kubectl exec -it kafka-connect -- \
  curl http://localhost:8083/connectors/data-migration-connector/status

# 4. Verificar logs do CDC
kubectl logs -f deployment/data-migration -c cdc-pipeline
```

**Resolução:**

```bash
# 1. Pausar CDC imediatamente
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/pause

# 2. Identificar registros corrompidos
curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/discrepancies

# 3. Limpar dados corrompidos do target
kubectl exec -it mongo-0 -- \
  mongo new_system --eval "db.orders.deleteMany({corrupted: true})"

# 4. Reset offset do Debezium para ponto seguro
kubectl exec -it kafka-connect -- \
  curl -X POST http://localhost:8083/connectors/data-migration-connector/reset \
  -d '{"offsets": {"source_offset": "SAFE_OFFSET"}}'

# 5. Retomar CDC
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/resume

# 6. Verificar reconciliação
watch curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/progress
```

### 5.3 Rollback de Cutover

**Quando:**
- Canary 5% com error rate > 1%
- Shadow mode detectou problema crítico
- Stakeholders solicitaram parada

**Procedimento:**

```bash
# 1. Identificar workflow de cutover ativo
curl http://orchestrator-dynamic:8003/api/v1/cutover/workflows?status=active

# 2. Verificar status atual
curl http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/status

# 3. Iniciar rollback automático
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/rollback \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "High error rate at 5% canary",
    "initiated_by": "auto",
    "preserve_metrics": true
  }'

# 4. Monitorar rollback progress
watch curl http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/status

# 5. Verificar que tráfego retornou ao 100% legado
kubectl get svc -n istio-system
curl http://traffic-switcher:8020/api/v1/traffic/distribution
# Esperado: {"legacy": "100%", "target": "0%"}

# 6. Coletar métricas para postmortem
curl http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/metrics > rollback-metrics.json

# 7. Comunicar time
echo "Rollback executado em $(date)" | \
  mail -s "URGENTE: Rollback Fluxo H Cutover" oncall@nhm.local
```

---

## 6. Comunicados

### 6.1 Template de Incidente

```
:warning: INCIDENTE: Fluxo H - [Breve Descrição]

**Severidade:** P1/P2/P3
**Início:** [Timestamp UTC]
**Owner:** @username

**Impacto:**
- [ ] Migrações em progresso interrompidas
- [ ] Documentos não sendo processados
- [ ] CDC sync atrasado
- [ ] Cutover pausado

**Status Atual:**
[O que está acontecendo agora]

**Investigação:**
[O que estamos verificando]

**Próximos Passos:**
1. [Ação 1]
2. [Ação 2]

**Updates:**
- [HH:MM] [Update 1]
- [HH:MM] [Update 2]
```

### 6.2 Escalação

| Nível | Quando | Contato | SLA |
|-------|--------|---------|-----|
| L1 | Incidente P1/P2 | #fluxo-h-oncall | 15 min |
| L2 | Não resolvido em 30 min | Tech Lead | 30 min |
| L3 | Não resolvido em 1h | Engineering Manager | 1h |
| L4 | Impacto de negócio | CTO/Stakeholders | Imediato |

---

## 7. Referências

### Documentação Relacionada

- [Fluxo H Design Specification](../superpowers/specs/2026-04-16-fluxo-h-design.md)
- [Fluxo H Implementation Plan](../superpowers/plans/2026-04-16-fluxo-h-implementation-plan.md)
- [Fluxo H Troubleshooting Guide](./troubleshooting-fluxo-h.md)
- [Fluxo H Emergency Procedures](./emergency-procedures-fluxo-h.md)

### Contatos

- **On-call:** #fluxo-h-oncall
- **Development:** #fluxo-h-dev
- **Architecture:** #architecture
- **Product:** #product-migration

---

**Changelog:**

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-04-16 | Versão inicial | Operations Team |
