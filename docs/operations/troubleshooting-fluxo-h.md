# Fluxo H - Troubleshooting Guide

> **Versão:** 1.0
> **Data:** 2026-04-16
> **Responsável:** Operations Team

---

## 1. Problemas Comuns

### 1.1 Parse Falhando

**Sintomas:**
- Documento em status `parsing_failed`
- Logs com `ParserError` ou `TimeoutError`
- Extração de entidades nunca inicia

**Diagnóstico:**

```bash
# 1. Verificar status do documento
curl http://doc-ingestion:8018/api/v1/documents/{doc_id}/status

# 2. Verificar logs do parser específico
kubectl logs -f deployment/doc-ingestion -c pdf-parser | grep ERROR
kubectl logs -f deployment/doc-ingestion -c word-parser | grep ERROR
kubectl logs -f deployment/doc-ingestion -c visio-parser | grep ERROR
kubectl logs -f deployment/doc-ingestion -c postman-parser | grep ERROR

# 3. Verificar formato do arquivo
kubectl exec -it doc-ingestion-xxxxx -- file /tmp/uploads/{doc_id}

# 4. Verificar se arquivo está corrompido
kubectl exec -it doc-ingestion-xxxxx -- \
  python -c "import pypdf2; pypdf2.PdfReader('/tmp/uploads/{doc_id}')"
```

**Soluções:**

**Problema: Arquivo corrompido**
```bash
# 1. Tentar reparar PDF
kubectl exec -it doc-ingestion-xxxxx -- \
  gs -sDEVICE=pdfwrite -o /tmp/repaired.pdf /tmp/uploads/{doc_id}.pdf

# 2. Re-upload documento reparado
curl -X POST http://doc-ingestion:8018/api/v1/documents/upload \
  -F "file=@repaired.pdf" \
  -F "metadata={\"original_doc_id\":\"{doc_id}\"}"
```

**Problema: Parser timeout**
```bash
# 1. Aumentar timeout do parser
kubectl patch deployment doc-ingestion --type=json \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "PARSER_TIMEOUT_SECONDS", "value": "300"}}]'

# 2. Restart deployment
kubectl rollout restart deployment/doc-ingestion
```

**Problema: Formato não suportado**
```bash
# 1. Verificar formatos suportados
curl http://doc-ingestion:8018/api/v1/documents/formats

# 2. Converter para formato suportado
# Exemplo: DOCX antigo → DOCX novo
libreoffice --headless --convert-to docx old_format.doc

# 3. Re-upload
curl -X POST http://doc-ingestion:8018/api/v1/documents/upload -F "file=@converted.docx"
```

**Problema: Memória insuficiente**
```bash
# 1. Verificar uso de memória
kubectl top pod -l app=doc-ingestion --containers

# 2. Aumentar memory limit
kubectl set resources deployment doc-ingestion \
  --limits=memory=4Gi --requests=memory=2Gi

# 3. Restart
kubectl rollout restart deployment/doc-ingestion
```

### 1.2 LLM Timeout

**Sintomas:**
- Status `entity_extraction_timeout`
- Logs com `LLMAPIError` ou `RequestTimeout`
- Extração de entities falha consistentemente

**Diagnóstico:**

```bash
# 1. Verificar logs do Entity Extractor
kubectl logs -f deployment/doc-ingestion -c entity-extractor | grep -i timeout

# 2. Testar conectividade com LLM API
kubectl exec -it doc-ingestion-xxxxx -- \
  curl -X POST https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 3. Verificar quota/limite da API
kubectl exec -it doc-ingestion-xxxxx -- \
  curl -X GET https://api.openai.com/v1/usage \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 4. Verificar tamanho do input (token limit)
kubectl exec -it doc-ingestion-xxxxx -- \
  python -c "import tiktoken; enc = tiktoken.encoding_for_model('gpt-4'); print(len(enc.encode(open('/tmp/uploads/{doc_id}').read())))"
```

**Soluções:**

**Problema: API key inválida ou expirada**
```bash
# 1. Verificar secret atual
kubectl get secret llm-api-keys -o jsonpath='{.data.openai-api-key}' | base64 -d

# 2. Criar nova API key (via OpenAI dashboard)

# 3. Atualizar secret
kubectl create secret generic llm-api-keys-new \
  --from-literal=openai-api-key=$NEW_OPENAI_KEY \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Rolling restart
kubectl rollout restart deployment/doc-ingestion
```

**Problema: Rate limiting**
```bash
# 1. Implementar retry com exponential backoff (já configurado)
# 2. Aumentar delay entre requests
kubectl patch deployment doc-ingestion --type=json \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "LLM_REQUEST_DELAY_MS", "value": "1000"}}]'

# 3. Se problema persistir, escalar para múltiplas instâncias
kubectl scale deployment doc-ingestion --replicas=3
```

**Problema: Input muito grande**
```bash
# 1. Verificar chunking configuration
kubectl exec -it doc-ingestion-xxxxx -- \
  curl http://localhost:8018/api/v1/config/chunking

# 2. Ativar chunking (se não ativo)
curl -X PATCH http://doc-ingestion:8018/api/v1/documents/{doc_id}/config \
  -H "Content-Type: application/json" \
  -d '{"chunking": {"enabled": true, "max_tokens": 8000, "overlap": 200}}'

# 3. Re-processar
curl -X POST http://doc-ingestion:8018/api/v1/documents/{doc_id}/extract
```

**Problema: LLM API indisponível**
```bash
# 1. Verificar status page
curl https://status.openai.com/api/v2/status.json

# 2. Trocar para provedor alternativo (Anthropic)
kubectl patch deployment doc-ingestion --type=json \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/env/1/value", "value": "anthropic"}]'

# 3. Ou implementar fallback automático
# (configurado em src/services/entity_extractor.py)
```

### 1.3 CDC Lag Alto

**Sintomas:**
- Métrica `data_migration_cdc_lag_seconds` > 60
- Source DB tem mudanças mas target não
- Debezium connector status mostra lag crescente

**Diagnóstico:**

```bash
# 1. Verificar lag do connector
kubectl exec -it kafka-connect -- \
  curl http://localhost:8083/connectors/data-migration-connector/status | jq '.tasks[0].state'

# 2. Verificar métricas do connector
kubectl exec -it kafka-connect -- \
  curl http://localhost:8083/connectors/data-migration-connector/metrics | grep lag

# 3. Verificar throughput de source DB
kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db -c "SELECT count(*) FROM orders WHERE created_at > now() - interval '5 minutes'"

# 4. Verificar capacidade do target
kubectl exec -it mongo-0 -- \
  mongo new_system --eval "db.serverStatus().metrics"

# 5. Verificar se há mensagens acumuladas no Kafka
kubectl exec -it kafka-0 -- \
  kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic data-migration-cdc \
  --time -1
```

**Soluções:**

**Problema: Source DB sob alta carga**
```bash
# 1. Aumentar poll interval do Debezium
kubectl exec -it kafka-connect -- \
  curl -X PATCH http://localhost:8083/connectors/data-migration-connector/config \
  -H "Content-Type: application/json" \
  -d '{"poll.interval.ms": "5000"}'

# 2. Ou usar snapshot.mode=schema_only (se batch já feito)
kubectl exec -it kafka-connect -- \
  curl -X PATCH http://localhost:8083/connectors/data-migration-connector/config \
  -H "Content-Type: application/json" \
  -d '{"snapshot.mode": "schema_only"}'
```

**Problema: Target DB lento**
```bash
# 1. Verificar índices no target
kubectl exec -it mongo-0 -- \
  mongo new_system --eval "db.orders.getIndexes()"

# 2. Criar índices se necessário
kubectl exec -it mongo-0 -- \
  mongo new_system --eval "db.orders.createIndex({created_at: 1})"

# 3. Aumentar batch size do Debezium
kubectl exec -it kafka-connect -- \
  curl -X PATCH http://localhost:8083/connectors/data-migration-connector/config \
  -H "Content-Type: application/json" \
  -d '{"max.batch.size": "2048"}'
```

**Problema: Partição única (bottleneck)**
```bash
# 1. Verificar número de partições do tópico
kubectl exec -it kafka-0 -- \
  kafka-topics --describe --topic data-migration-cdc --bootstrap-server localhost:9092

# 2. Aumentar partições
kubectl exec -it kafka-0 -- \
  kafka-topics --alter --topic data-migration-cdc \
  --partitions 12 --bootstrap-server localhost:9092

# 3. Aumentar tarefas do connector
kubectl exec -it kafka-connect -- \
  curl -X PATCH http://localhost:8083/connectors/data-migration-connector/config \
  -H "Content-Type: application/json" \
  -d '{"tasks.max": "12"}'
```

**Problema: Transformação complexa**
```bash
# 1. Verificar SMT (Single Message Transform)
kubectl exec -it kafka-connect -- \
  curl http://localhost:8083/connectors/data-migration-connector/config | jq '.transforms'

# 2. Desativar SMTs não essenciais temporariamente
kubectl exec -it kafka-connect -- \
  curl -X PATCH http://localhost:8083/connectors/data-migration-connector/config \
  -H "Content-Type: application/json" \
  -d '{"transforms": "none"}'

# 3. Aplicar transformações offline (batch) após catch-up
```

### 1.4 Rollback Falhando

**Sintomas:**
- Status `rollback_failed`
- Tráfego não retorna ao legado
- Logs com `RollbackError` ou `TrafficSwitchFailed`

**Diagnóstico:**

```bash
# 1. Verificar status do rollback
curl http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/status

# 2. Verificar logs do Traffic Switcher
kubectl logs -f deployment/traffic-switcher | grep rollback

# 3. Verificar configuração de roteamento (Istio)
kubectl get virtualservice fluxo-h -o yaml

# 4. Verificar health do legado
curl http://legacy-system:3000/health

# 5. Verificar health do target
curl http://new-system:8080/health
```

**Soluções:**

**Problema: Legado DOWN**
```bash
# 1. Verificar pods legados
kubectl get pods -l app=legacy-system

# 2. Verificar logs
kubectl logs -f deployment/legacy-system

# 3. Se legado está DOWN, não é possível rollback completo
# 4. Ações alternativas:
#    a. Manter tráfego no target com mitigação
#    b. Promover target imediatamente (full cutover)
#    c. Modo degradação (funcionalidades críticas apenas)
```

**Problema: Traffic switcher falhou**
```bash
# 1. Verificar Istio VirtualService
kubectl get virtualservice fluxo-h -o yaml

# 2. Forçar roteamento via patch manual
kubectl patch virtualservice fluxo-h --type=json \
  -p='[{"op": "replace", "path": "/spec/http/0/route/0/destination/host", "value": "legacy-system"}]'

# 3. Verificar se atualizou
kubectl get virtualservice fluxo-h -o yaml

# 4. Testar roteamento
kubectl exec -it sleep -- curl -v http://fluxo-h/health
```

**Problema: Rollback de dados falhou**
```bash
# 1. Verificar status do migration job
curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/status

# 2. Verificar checkpoints disponíveis
curl http://data-migration:8019/api/v1/migrations/jobs/{job_id}/checkpoints

# 3. Restaurar checkpoint
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/restore \
  -H "Content-Type: application/json" \
  -d '{"checkpoint_id": "last_safe_checkpoint"}'

# 4. Se checkpoint falhar, fazer rollback manual (restore DB backup)
kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db < /backup/legacy_dump.sql
```

---

## 2. Diagnóstico

### 2.1 Logs a Verificar

**Doc Ingestion Service:**
```bash
# Logs completos (com contexto)
kubectl logs -f deployment/doc-ingestion --all-containers=true

# Apenas erros
kubectl logs deployment/doc-ingestion | jq 'select(.level == "error")'

# Por componente
kubectl logs -f deployment/doc-ingestion -c pdf-parser
kubectl logs -f deployment/doc-ingestion -c entity-extractor
kubectl logs -f deployment/doc-ingestion -c doc-producer

# Buscar por correlation_id
kubectl logs deployment/doc-ingestion | grep "correlation_id=abc123"
```

**Data Migration System:**
```bash
# Logs completos
kubectl logs -f deployment/data-migration --all-containers=true

# Pipeline específico
kubectl logs -f deployment/data-migration -c cdc-pipeline
kubectl logs -f deployment/data-migration -c batch-migrator
kubectl logs -f deployment/data-migration -c data-validator

# Buscar erros de schema mismatch
kubectl logs deployment/data-migration | grep "schema_mismatch"
```

**Cutover Orchestrator:**
```bash
# Logs completos
kubectl logs -f deployment/orchestrator-dynamic

# Workflow específico
kubectl logs deployment/orchestrator-dynamic | grep "workflow_id=xyz789"

# Buscar decisões de rollback
kubectl logs deployment/orchestrator-dynamic | grep "rollback_decision"
```

### 2.2 Métricas a Checar

**Via Prometheus/Grafana:**

**Doc Ingestion:**
```promql
# Throughput de processamento
rate(doc_ingestion_docs_processed_total[5m])

# Success rate dos parsers
rate(doc_ingestion_parser_success[5m]) / rate(doc_ingestion_parser_total[5m])

# Latência de parsing
histogram_quantile(0.95, rate(doc_ingestion_parse_duration_seconds_bucket[5m]))

# Memória usada
process_resident_memory_bytes{job="doc-ingestion"}
```

**Data Migration:**
```promql
# Progresso da migração
data_migration_progress_percentage

# CDC lag
data_migration_cdc_lag_seconds

# Throughput de migração
rate(data_migration_records_migrated_total[5m])

# Discrepâncias
data_migration_discrepancies_total
```

**Cutover:**
```promql
# Distribuição de tráfego
cutover_traffic_percentage{system="target"}
cutover_traffic_percentage{system="legacy"}

# Error rates
cutover_error_rate_target
cutover_error_rate_legacy

# Latência comparativa
histogram_quantile(0.95, rate(cutover_request_duration_seconds_bucket{system="target"}[5m]))
histogram_quantile(0.95, rate(cutover_request_duration_seconds_bucket{system="legacy"}[5m]))
```

### 2.3 Comandos Úteis

**Depuração de conexões:**
```bash
# Testar conectividade entre pods
kubectl exec -it doc-ingestion-xxxxx -- nc -zv mongodb 27017
kubectl exec -it doc-ingestion-xxxxx -- nc -zv kafka 9092
kubectl exec -it data-migration-xxxxx -- nc -zv postgres-legacy 5432

# Verificar DNS resolution
kubectl exec -it doc-ingestion-xxxxx -- nslookup mongodb
kubectl exec -it doc-ingestion-xxxxx -- nsolver kafka-0.kafka

# Verificar rotas de rede
kubectl exec -it doc-ingestion-xxxxx -- traceroute mongodb
kubectl exec -it doc-ingestion-xxxxx -- route -n
```

**Inspeção de recursos:**
```bash
# Descrever pod (ver eventos recentes)
kubectl describe pod doc-ingestion-xxxxx

# Verificar uso de recursos
kubectl top pods -l app=fluxo-h
kubectl top nodes

# Verificar PVCs
kubectl get pvc -l app=fluxo-h
kubectl describe pvc doc-ingestion-storage
```

**Dumps e captures:**
```bash
# TCP dump (debug de rede)
kubectl exec -it doc-ingestion-xxxxx -- \
  tcpdump -i any -w /tmp/capture.pcap port 9092

# Heap dump (debug de memória)
kubectl exec -it doc-ingestion-xxxxx -- \
  jmap -dump:format=b,file=/tmp/heap.dump 1

# Thread dump (debug de travamentos)
kubectl exec -it doc-ingestion-xxxxx -- \
  jstack 1 > /tmp/threads.dump
```

---

## 3. Soluções e Workarounds

### 3.1 Workarounds Temporários

**Parser timeout:**
```bash
# Dividir documento em partes e processar separadamente
# (usar chunking API)
curl -X POST http://doc-ingestion:8018/api/v1/documents/{doc_id}/split \
  -H "Content-Type: application/json" \
  -d '{"strategy": "page_range", "ranges": [[1,50], [51,100], [101,150]]}'
```

**CDC lag crítico:**
```bash
# Pausar CDC, fazer batch catch-up, retomar
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/pause
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/batch-catch-up
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/resume
```

**Cutover com problemas:**
```bash
# Congelar em percentagem atual
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/freeze \
  -H "Content-Type: application/json" \
  -d '{"current_percentage": 5, "reason": "Investigating issues"}'

# Extender canary por mais 24h
curl -X PATCH http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/config \
  -H "Content-Type: application/json" \
  -d '{"canary_extension_hours": 24}'
```

### 3.2 Recuperação de Estado

**Reprocessar documento:**
```bash
# 1. Limpar entidades anteriores
curl -X DELETE http://doc-ingestion:8018/api/v1/documents/{doc_id}/entities

# 2. Re-extrair
curl -X POST http://doc-ingestion:8018/api/v1/documents/{doc_id}/extract

# 3. Forçar timeout customizado
curl -X POST http://doc-ingestion:8018/api/v1/documents/{doc_id}/extract \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 600}'
```

**Reconciliar dados:**
```bash
# 1. Gerar relatório de discrepâncias
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/reconcile \
  -H "Content-Type: application/json" \
  -d '{"mode": "full"}'

# 2. Aplicar correções automáticas
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/auto-fix \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# 3. Re-validar
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate
```

**Reiniciar cutover:**
```bash
# 1. Reset workflow
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/reset

# 2. Re-iniciar do zero
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/start \
  -H "Content-Type: application/json" \
  -d '{"source_system": "legacy", "target_system": "new", "strategy": "canary"}'

# 3. Ou retomar de checkpoint
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/resume
```

---

## 4. Escalonamento

### 4.1 Quando Escalar

**Nível 1 (On-call):**
- Tentar resolução usando este guide
- Documentar o que foi tentado
- Tempo: 30 min

**Nível 2 (Tech Lead):**
- Problemas não resolvidos em 30 min (P1) ou 2h (P2)
- Questões arquiteturais
- Decisões de rollback parciais
- Contato: #tech-lead

**Nível 3 (Engineering Manager):**
- Impacto de negócio significativo
- Coordenar comunicação com stakeholders
- Alocar recursos adicionais
- Contato: emanager@nhm.local

**Nível 4 (CTO/Stakeholders):**
- Interrupção completa de serviço
- Perda de dados confirmada
- Impacto em clientes externos
- Contato: cto@nhm.local

### 4.2 Informação para Escalar

Ao escalar, fornecer:

1. **Resumo do incidente**
   - Serviço afetado
   - Sintomas observados
   - Tempo de duração

2. **Impacto atual**
   - Usuários afetados
   - Funcionalidades impactadas
   - Perda de dados (se aplicável)

3. **Ações tomadas**
   - O que já foi tentado
   - Resultados de cada tentativa
   - Logs/relevantes capturados

4. **Problema bloqueador**
   - Por que não consegui resolver
   - O que precisa de aprovação/autorização
   - Urgência (P1/P2/P3)

---

**Referências:**

- [Fluxo H Runbooks](./fluxo-h-runbooks.md)
- [Fluxo H Emergency Procedures](./emergency-procedures-fluxo-h.md)
- [Troubleshooting Guide Geral](./troubleshooting-guide.md)

---

**Changelog:**

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-04-16 | Versão inicial | Operations Team |
