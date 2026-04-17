# Fluxo H - Procedimentos de Emergência

> **Versão:** 1.0
> **Data:** 2026-04-16
> **Responsável:** Operations Team
> **Severidade:** CRÍTICO

---

## 1. Rollback Emergencial

### 1.1 Quando Executar Rollback Emergencial

**Critérios Imediatos (executar sem aprovação):**
- Error rate > 5% por 5 minutos consecutivos
- Sistema target completamente DOWN (todos os pods crashando)
- Data corruption confirmada (checksum falhando, dados inconsistentes)
- Security breach detectado no sistema novo
- Perda de dados confirmada

**Critérios de Avaliação (executar após validação):**
- Error rate > 1% mas <5% por 15 minutos
- Latência P95 > 3x legacy por 10 minutos
- Bugs críticos de negócio (impacto em revenue/compliance)

### 1.2 Procedimento de Rollback Completo

**Pré-condições:**
- Acesso ao cluster Kubernetes
- Credenciais de API (se necessário)
- Comunicado preparado para stakeholders

**Passos:**

```bash
# =================================================================
# ROLLBACK EMERGENCIAL - FLUXO H
# =================================================================

# PASSO 1: Identificar workflow ativo
echo "=== PASSO 1: Identificar workflow ativo ==="
WORKFLOW_ID=$(curl -s http://orchestrator-dynamic:8003/api/v1/cutover/workflows?status=active | jq -r '.[0].workflow_id')
echo "Workflow ativo: $WORKFLOW_ID"

# PASSO 2: Coletar estado atual (para postmortem)
echo "=== PASSO 2: Coletar estado atual ==="
curl -s http://orchestrator-dynamic:8003/api/v1/cutover/workflows/$WORKFLOW_ID/status > /tmp/pre-rollback-state.json
curl -s http://data-migration:8019/api/v1/migrations/jobs?status=in_progress > /tmp/pre-rollback-jobs.json
kubectl get pods -l app=fluxo-h -o json > /tmp/pre-rollback-pods.json

# PASSO 3: Iniciar rollback automático
echo "=== PASSO 3: Iniciar rollback ==="
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/$WORKFLOW_ID/rollback \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "EMERGENCY_ROLLBACK",
    "initiated_by": "oncall",
    "preserve_metrics": true,
    "skip_validations": false
  }'

# PASSO 4: Aguardar início do rollback (timeout: 30s)
echo "=== PASSO 4: Aguardar início do rollback ==="
for i in {1..30}; do
  STATUS=$(curl -s http://orchestrator-dynamic:8003/api/v1/cutover/workflows/$WORKFLOW_ID/status | jq -r '.status')
  if [ "$STATUS" == "rolling_back" ]; then
    echo "Rollback iniciado com sucesso"
    break
  fi
  sleep 1
done

# PASSO 5: Monitorar progresso do rollback
echo "=== PASSO 5: Monitorar rollback ==="
watch -n 5 "curl -s http://orchestrator-dynamic:8003/api/v1/cutover/workflows/$WORKFLOW_ID/status | jq '{status, traffic_legacy, traffic_target, rollback_progress}'"

# PASSO 6: Se rollback automático falhar, executar rollback manual
echo "=== PASSO 6: Rollback Manual (se necessário) ==="
MANUAL_ROLLBACK_NEEDED=false
ROLLBACK_STATUS=$(curl -s http://orchestrator-dynamic:8003/api/v1/cutover/workflows/$WORKFLOW_ID/status | jq -r '.status')

if [ "$ROLLBACK_STATUS" != "rolling_back" ] && [ "$ROLLBACK_STATUS" != "rolled_back" ]; then
  MANUAL_ROLLBACK_NEEDED=true
  echo "ATENÇÃO: Rollback automático falhou. Executando rollback manual..."
  
  # 6a. Forçar tráfego para legado via Istio
  kubectl patch virtualservice fluxo-h --type=json \
    -p='[{"op": "replace", "path": "/spec/http/0/route/0/destination/host", "value": "legacy-system"}]'
  
  # 6b. Parar CDC se ativo
  for JOB_ID in $(curl -s http://data-migration:8019/api/v1/migrations/jobs?status=in_progress | jq -r '.[].job_id'); do
    curl -X POST http://data-migration:8019/api/v1/migrations/jobs/$JOB_ID/pause
  done
  
  # 6c. Escalar target para zero (se aplicável)
  # kubectl scale deployment new-system --replicas=0
  
  echo "Rollback manual executado"
fi

# PASSO 7: Validar que legado está recebendo tráfego
echo "=== PASSO 7: Validar tráfego legado ==="
sleep 10
LEGACY_HEALTH=$(curl -s http://legacy-system:3000/health | jq -r '.status')
if [ "$LEGACY_HEALTH" == "healthy" ]; then
  echo "✓ Legado está healthy"
else
  echo "✗ AVISO: Legado não está healthy!"
fi

# PASSO 8: Verificar métricas de erro
echo "=== PASSO 8: Verificar métricas ==="
ERROR_RATE=$(curl -s 'http://prometheus:9090/api/v1/query?query=rate(http_requests_total{status=~"5..",system="legacy"}[5m])' | jq -r '.data.result[0].value[1]')
echo "Error rate legado: $ERROR_RATE"

# PASSO 9: Restaurar dados se necessário
if [ "$MANUAL_ROLLBACK_NEEDED" = true ]; then
  echo "=== PASSO 9: Restaurar dados ==="
  # 9a. Identificar último checkpoint seguro
  CHECKPOINT_ID=$(curl -s http://data-migration:8019/api/v1/migrations/jobs?status=in_progress | jq -r '.[0].last_safe_checkpoint')
  
  # 9b. Restaurar checkpoint
  curl -X POST http://data-migration:8019/api/v1/migrations/jobs/$JOB_ID/restore \
    -H "Content-Type: application/json" \
    -d "{\"checkpoint_id\": \"$CHECKPOINT_ID\"}"
fi

# PASSO 10: Comunicar stakeholders
echo "=== PASSO 10: Comunicar rollback ==="
cat <<EOF | mail -s "URGENTE: Rollback Emergencial Fluxo H" oncall@nhm.local,manager@nhm.local

Rollback emergencial executado em $(date).

Workflow: $WORKFLOW_ID
Motivo: $(cat /tmp/pre-rollback-state.json | jq -r '.rollback_reason')
Manual: $MANUAL_ROLLBACK_NEEDED

Estado atual:
- Tráfego: 100% legado
- Legado health: $LEGACY_HEALTH
- Error rate: $ERROR_RATE

Próximos passos:
1. Investigar causa raiz
2. Preparar postmortem
3. Planejar retry quando seguro

Logs coletados em: /tmp/pre-rollback-*.json
EOF

echo "=== ROLLBACK COMPLETO ==="
echo "Arquivos de debug: /tmp/pre-rollback-*.json"
```

### 1.3 Validação Pós-Rollback

**Checklist:**

```bash
# 1. Verificar health do legado
curl http://legacy-system:3000/health
# Esperado: {"status": "healthy", ...}

# 2. Verificar distribuição de tráfego
kubectl get virtualservice fluxo-h -o yaml | grep -A 5 route
# Esperado: destination: legacy-system (100%)

# 3. Verificar métricas de erro
curl -s 'http://prometheus:9090/api/v1/query?query=rate(http_requests_total{status=~"5..",system="legacy"}[5m])'
# Esperado: value < 0.01 (1%)

# 4. Verificar CDC pausado
curl -s http://data-migration:8019/api/v1/migrations/jobs?status=in_progress | jq -r '.[].cdc_status'
# Esperado: "paused"

# 5. Verificar pods do target escalados para zero (se aplicável)
kubectl get pods -l app=new-system
# Esperado: 0 pods (ou pods mas sem tráfego)

# 6. Verificar logs de erro recentes
kubectl logs --tail=50 deployment/legacy-system | grep ERROR
# Esperado: Nenhum erro novo

# 7. Testar funcionalidade crítica
curl -X POST http://legacy-system:3000/api/v1/test/critical-operation \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
# Esperado: 200 OK com response válido

# 8. Verificar integridade de dados
kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db -c "SELECT count(*) FROM orders WHERE created_at > now() - interval '1 hour'"
# Esperado: Número consistente com período
```

---

## 2. Falha Completa do Sistema

### 2.1 Modo de Degradação

**Quando usar:**
- Sistema target completamente falho
- Legado também com problemas
- Necessidade de manter funcionalidade mínima

**Procedimento:**

```bash
# =================================================================
# MODO DE DEGRADAÇÃO - FLUXO H
# =================================================================

# PASSO 1: Avaliar saúde de ambos sistemas
echo "=== Avaliando saúde dos sistemas ==="

TARGET_HEALTH=$(curl -s http://new-system:8080/health 2>/dev/null || echo "unreachable")
LEGACY_HEALTH=$(curl -s http://legacy-system:3000/health 2>/dev/null || echo "unreachable")

echo "Target: $TARGET_HEALTH"
echo "Legacy: $LEGACY_HEALTH"

# PASSO 2: Determinar modo de degradação
if [ "$TARGET_HEALTH" == "unreachable" ] && [ "$LEGACY_HEALTH" == "unreachable" ]; then
  DEGRADATION_MODE="critical"
  echo "MODO: CRÍTICO - Ambos sistemas DOWN"
elif [ "$TARGET_HEALTH" == "unreachable" ]; then
  DEGRADATION_MODE="legacy_only"
  echo "MODO: LEGADO APENAS - Target DOWN"
elif [ "$LEGACY_HEALTH" == "unreachable" ]; then
  DEGRADATION_MODE="target_only"
  echo "MODO: TARGET APENAS - Legado DOWN (não recomendado)"
else
  DEGRADATION_MODE="none"
  echo "MODO: NORMAL - Ambos sistemas OK"
fi

# PASSO 3: Executar ações baseadas no modo
case $DEGRADATION_MODE in
  critical)
    # AÇÃO CRÍTICA: Ambos sistemas DOWN
    echo "=== AÇÕES CRÍTICAS ==="
    
    # 3a. Parar todo tráfego (maintenance mode)
    kubectl apply -f k8s/emergency/maintenance-mode.yaml
    
    # 3b. Notificar stakeholders imediatamente
    cat <<EOF | mail -s "CRÍTICO: Sistema Completo DOWN" emergency@nhm.local
Sistema Fluxo H completamente DOWN em $(date).
Ambos target e legado unreachable.

Ações tomadas:
- Tráfego interrompido (maintenance mode)
- Engenheiros notificados

Status page atualizada: https://status.nhm.local
EOF
    
    # 4. Coletar logs para emergência
    kubectl logs --tail=1000 -l app=fluxo-h --all-containers=true > /tmp/emergency-logs-$(date +%s).txt
    
    ;;

  legacy_only)
    # AÇÃO: Manter apenas legado
    echo "=== AÇÕES LEGADO APENAS ==="
    
    # 3a. Direcionar 100% tráfego para legado
    kubectl patch virtualservice fluxo-h --type=json \
      -p='[{"op": "replace", "path": "/spec/http/0/route/0/destination/host", "value": "legacy-system"}]'
    
    # 3b. Desativar componentes não essenciais do legado
    # (comentários, analytics, etc.)
    
    # 3c. Escalar legado para handle load
    kubectl scale deployment legacy-system --replicas=6
    
    # 3d. Notificar stakeholders
    cat <<EOF | mail -s "ALERTA: Sistema em Modo Legado" ops@nhm.local
Sistema target DOWN em $(date).
Operando em modo degradado (legado apenas).

Funcionalidades impactadas:
- Novas features do target (indisponíveis)
- Performance pode ser degradada

Estimativa de reparo: 2-4 horas
EOF
    ;;

  target_only)
    # AÇÃO: Target apenas (PERIGOSO - evitar)
    echo "=== ATENÇÃO: Modo target-only é PERIGOSO ==="
    
    # Notificar que isto é arriscado
    cat <<EOF | mail -s "PERIGO: Operando Target Apenas!" critical@nhm.local
ATENÇÃO: Operando com target apenas em $(date).
Legado está DOWN.

Isto é PERIGOSO:
- Rollback não é possível
- Problemas de migração de dados podem ocorrer
- Recomendado: Reparar legado primeiro

Se continuar, garantir:
- CDC está PAUSADO
- Não há jobs de migração ativos
- Backup de dados legado está seguro
EOF
    ;;
esac

# PASSO 4: Monitorar recuperação
echo "=== Monitorando recuperação ==="
while true; do
  TARGET_HEALTH=$(curl -s http://new-system:8080/health 2>/dev/null || echo "unreachable")
  LEGACY_HEALTH=$(curl -s http://legacy-system:3000/health 2>/dev/null || echo "unreachable")
  
  echo "$(date): Target=$TARGET_HEALTH, Legacy=$LEGACY_HEALTH"
  
  if [ "$TARGET_HEALTH" != "unreachable" ] && [ "$LEGACY_HEALTH" != "unreachable" ]; then
    echo "SISTEMA RECUPERADO! Sair modo de degradação."
    break
  fi
  
  sleep 30
done
```

### 2.2 Comunicação com Stakeholders

**Template de Email Crítico:**

```
ASSUNTO: [URGENTE] Incidente Crítico - Fluxo H - [Breve Descrição]

**SEVERIDADE:** P1 - CRÍTICO
**INÍCIO:** [Timestamp UTC]
**ESTIMATIVA DE RESOLUÇÃO:** [X horas]

**IMPACTO CONFIRMADO:**
- [ ] Sistema indisponível
- [ ] Migrações em progresso interrompidas
- [ ] Perda de serviço para [X] usuários
- [ ] Impacto em [revenue/compliance]

**AÇÕES TOMADAS:**
1. [Ação 1 executada em HH:MM]
2. [Ação 2 executada em HH:MM]
3. [Ação 3 em andamento]

**STATUS ATUAL:**
[Descrição clara do estado atual]

**PRÓXIMOS PASSOS:**
1. [Próxima ação imediata]
2. [Ação seguinte]
3. [Ação de longo prazo]

**COMUNICAÇÃO:**
- Status page atualizada: https://status.nhm.local
- Próxima atualização: [HH:MM UTC]
- Channel: #incidentes-fluxo-h

**CONTATO:**
- On-call: [Nome] - [Phone]
- Tech Lead: [Nome] - [Phone]
- EM: [Nome] - [Phone]
```

### 2.3 Recuperação

**Após sistema estável:**

```bash
# 1. Validar sistema completamente
./scripts/validate-full-system.sh

# 2. Coletar métricas do incidente
curl -s 'http://prometheus:9090/api/v1/query_range?query=...' > incident-metrics.json

# 3. Gerar timeline do incidente
kubectl get events --sort-by='.lastTimestamp' > incident-timeline.txt

# 4. Criar postmortem draft
cat <<EOF > postmortem-draft.md
# Postmortem: [Incidente Title]

## Resumo
[Breve descrição do que aconteceu]

## Timeline
| Hora | Evento |
|------|--------|
| HH:MM | Sistema operando normalmente |
| HH:MM | Alerta triggered: [X] |
| HH:MM | Investigação iniciada |
| HH:MM | Rollback executado |
| HH:MM | Sistema recuperado |

## Root Cause
[Causa raiz identificada]

## Impacto
- Duração: [X] minutos
- Usuários afetados: [X]
- Transações perdidas: [X]

## Resolução
[Como foi resolvido]

## Lessons Learned
[O que aprendemos]

## Action Items
| [ ] Ação | Owner | Due Date |
|----------|-------|----------|
EOF

# 5. Agendar reunião de postmortem
echo "Agendar postmortem em 24-48 horas"
```

---

## 3. Data Corruption

### 3.1 Detecção

**Sinais de Data Corruption:**

```bash
# 1. Checksum failures
kubectl logs -f deployment/data-migration -c data-validator | grep checksum_failed

# 2. Discrepancy count aumentando
watch -n 10 "curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/discrepancies | jq '.total_count'"

# 3. Validation reports
curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq '.issues'

# 4. Data integrity checks
kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db -c "SELECT count(*) FROM orders WHERE id IS NULL"

# 5. Application errors
kubectl logs -f deployment/new-system | grep -i "corruption\|integrity\|constraint"
```

### 3.2 Isolamento

**Ao detectar corrupção:**

```bash
# =================================================================
# ISOLAMENTO DE DATA CORRUPTION - FLUXO H
# =================================================================

# PASSO 1: PARAR TUDO IMEDIATAMENTE
echo "=== PARANDO TODAS OPERAÇÕES ==="

# 1a. Pausar CDC (para não espalhar corrupção)
for JOB_ID in $(curl -s http://data-migration:8019/api/v1/migrations/jobs?status=in_progress | jq -r '.[].job_id'); do
  curl -X POST http://data-migration:8019/api/v1/migrations/jobs/$JOB_ID/pause
  echo "CDC pausado para job $JOB_ID"
done

# 1b. Parar cutover se ativo
curl -s http://orchestrator-dynamic:8003/api/v1/cutover/workflows?status=active | jq -r '.[].workflow_id' | \
  while read WORKFLOW_ID; do
    curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/$WORKFLOW_ID/freeze \
      -H "Content-Type: application/json" \
      -d '{"reason": "Data corruption detected", "emergency": true}'
  done

# 1c. Colocar target em modo read-only
kubectl patch deployment new-system --type=json \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "READ_ONLY_MODE", "value": "true"}}]'

# PASSO 2: IDENTIFICAR ESCOPO DA CORRUPÇÃO
echo "=== IDENTIFICANDO ESCOPO ==="

# 2a. Quais tabelas/collections afetadas?
curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq '.affected_tables'

# 2b. Quanto dados corrompidos?
curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq '.corrupted_records_count'

# 2c. Quando começou?
curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq '.corruption_start_time'

# PASSO 3: CRIAR SNAPSHOT DO ESTADO ATUAL
echo "=== CRIANDO SNAPSHOT ==="

# 3a. Snapshot do target (MongoDB)
kubectl exec -it mongo-0 -- mongodump --archive=/tmp/corruption-snapshot-$(date +%s).gz

# 3b. Snapshot do source (PostgreSQL)
kubectl exec -it postgres-legacy -- pg_dump -U user corruption_db > /tmp/corruption-source-$(date +%s).sql

# 3c. Snapshot dos logs
kubectl logs --tail=10000 deployment/data-migration > /tmp/corruption-logs-$(date +%s).txt

# PASSO 4: MARCAR DADOS CORROMPIDOS
echo "=== MARCANDO DADOS CORROMPIDOS ==="

# 4a. Adicionar flag de corrupção (para não processar)
kubectl exec -it mongo-0 -- \
  mongo new_system --eval 'db.orders.updateMany(
    {_corruption_detected: {$exists: false}},
    {$set: {_corruption_detected: true, _corruption_timestamp: new Date()}}
  )'

# PASSO 5: NOTIFICAR EQUIPE
cat <<EOF | mail -s "CRÍTICO: Data Corruption Detectado" emergency@nhm.local

DATA CORRUPTION DETECTADO em $(date)

Job ID: {job_id}
Tabelas afetadas: [lista]
Registros corrompidos: [quantidade]

AÇÕES TOMADAS:
- CDC pausado
- Cutover congelado
- Target em read-only
- Snapshots criados

ESCOPO:
- Source: [X]%
- Target: [Y]%

PRÓXIMOS PASSOS:
1. Investigar causa raiz
2. Determinar estratégia de recuperação
3. Executar recuperação

Logs: /tmp/corruption-*
EOF
```

### 3.3 Recuperação

**Estratégias baseadas no escopo:**

```bash
# =================================================================
# RECUPERAÇÃO DE DATA CORRUPTION - FLUXO H
# =================================================================

# PASSO 1: DETERMINAR ESTRATÉGIA
CORRUPTION_SCOPE=$(curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq -r '.scope')

if [ "$CORRUPTION_SCOPE" == "small" ]; then
  RECOVERY_STRATEGY="targeted"
elif [ "$CORRUPTION_SCOPE" == "medium" ]; then
  RECOVERY_STRATEGY="batch_restore"
elif [ "$CORRUPTION_SCOPE" == "large" ]; then
  RECOVERY_STRATEGY="full_restore"
else
  RECOVERY_STRATEGY="manual_review"
fi

echo "Estratégia de recuperação: $RECOVERY_STRATEGY"

# PASSO 2: EXECUTAR RECUPERAÇÃO
case $RECOVERY_STRATEGY in
  targeted)
    # RECUPERAÇÃO TARGETED (pequeno número de registros)
    echo "=== RECUPERAÇÃO TARGETED ==="
    
    # 2a. Identificar IDs corrompidos
    CORRUPTED_IDS=$(kubectl exec -it mongo-0 -- \
      mongo new_system --quiet --eval 'db.orders.find({_corruption_detected: true}, {_id: 1}).toArray()' | jq -r '.[]._id')
    
    # 2b. Buscar dados corretos do source
    for ID in $CORRUPTED_IDS; do
      kubectl exec -it postgres-legacy -- \
        psql -U user -d legacy_db -c "SELECT * FROM orders WHERE id = '$ID'" > /tmp/record-$ID.json
    done
    
    # 2c. Re-importar dados corretos
    for ID in $CORRUPTED_IDS; do
      kubectl exec -i mongo-0 -- \
        mongo new_system --eval "db.orders.updateOne({_id: ObjectId('$ID')}, $(cat /tmp/record-$ID.json))"
    done
    
    # 2d. Limpar flag de corrupção
    kubectl exec -it mongo-0 -- \
      mongo new_system --eval 'db.orders.updateMany({_corruption_detected: true}, {$unset: {_corruption_detected: 1, _corruption_timestamp: 1}})'
    ;;
    
  batch_restore)
    # RECUPERAÇÃO EM LOTE
    echo "=== RECUPERAÇÃO EM LOTE ==="
    
    # 2a. Identificar range de corrupção
    START_ID=$(curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq -r '.corruption_start_id')
    END_ID=$(curl -s http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate | jq -r '.corruption_end_id')
    
    # 2b. Deletar dados corrompidos do target
    kubectl exec -it mongo-0 -- \
      mongo new_system --eval "db.orders.deleteMany({_id: {\$gte: ObjectId('$START_ID'), \$lte: ObjectId('$END_ID')}})"
    
    # 2c. Re-migrar range do source
    curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/re-migrate \
      -H "Content-Type: application/json" \
      -d "{\"start_id\": \"$START_ID\", \"end_id\": \"$END_ID\", \"strategy\": \"batch\"}"
    ;;
    
  full_restore)
    # RESTAURAÇÃO COMPLETA
    echo "=== RESTAURAÇÃO COMPLETA ==="
    
    # 2a. Parar completamente target
    kubectl scale deployment new-system --replicas=0
    
    # 2b. Drop database corrompida
    kubectl exec -it mongo-0 -- \
      mongo --eval "db.getSiblingDB('new_system').dropDatabase()"
    
    # 2c. Restaurar do último backup válido
    kubectl exec -i mongo-0 -- \
      mongorestore --archive=/backup/last-valid-backup.gz
    
    # 2d. Reiniciar CDC do checkpoint
    curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/restore \
      -H "Content-Type: application/json" \
      -d '{"checkpoint_id": "last_valid_checkpoint"}'
    
    # 2e. Re-iniciar target
    kubectl scale deployment new-system --replicas=3
    ;;
    
  manual_review)
    # REVISÃO MANUAL (caso complexo)
    echo "=== REVISÃO MANUAL NECESSÁRIA ==="
    
    cat <<EOF | mail -s "AÇÃO NECESSÁRIA: Revisão Manual de Corruption" data-team@nhm.local
    
Data corruption requer revisão manual em $(date).

Job ID: {job_id}
Complexidade: Alta

Anexos:
- Snapshot logs: /tmp/corruption-logs-*.txt
- State dump: /tmp/corruption-state-*.json

Recomendação:
1. Agendar reunião de triagem
2. Analisar logs de corrupção
3. Determinar causa raiz
4. Planejar recuperação customizada
EOF
    ;;
esac

# PASSO 3: VALIDAR RECUPERAÇÃO
echo "=== VALIDANDO RECUPERAÇÃO ==="

# 3a. Re-validar dados
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/validate

# 3b. Verificar que não há mais corrupção
kubectl exec -it mongo-0 -- \
  mongo new_system --eval 'db.orders.countDocuments({_corruption_detected: true})'
# Esperado: 0

# 3c. Verificar integridade referencial
kubectl exec -it mongo-0 -- \
  mongo new_system --eval 'db.orders.validate()'

# 3d. Comparar contagens source vs target
SOURCE_COUNT=$(kubectl exec -it postgres-legacy -- \
  psql -U user -d legacy_db -t -c "SELECT count(*) FROM orders")
TARGET_COUNT=$(kubectl exec -it mongo-0 -- \
  mongo new_system --eval 'db.orders.count()')

echo "Source: $SOURCE_COUNT, Target: $TARGET_COUNT"
if [ "$SOURCE_COUNT" == "$TARGET_COUNT" ]; then
  echo "✓ Contagens batem"
else
  echo "✗ AVISO: Contagens divergem"
fi

# PASSO 4: RETOMAR OPERAÇÕES
echo "=== RETOMANDO OPERAÇÕES ==="

# 4a. Sair modo read-only
kubectl patch deployment new-system --type=json \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/env/0/value", "value": "false"}]'

# 4b. Retomar CDC
curl -X POST http://data-migration:8019/api/v1/migrations/jobs/{job_id}/resume

# 4c. Retomar cutover (se aplicável)
curl -X POST http://orchestrator-dynamic:8003/api/v1/cutover/workflows/{workflow_id}/resume

# PASSO 5: DOCUMENTAR INCIDENTE
cat <<EOF > postmortem-corruption-$(date +%Y%m%d).md
# Postmortem: Data Corruption - $(date +%Y-%m-%d)

## Resumo
Data corruption detectado e recuperado em $(date).

## Detalhes
- Job ID: {job_id}
- Escopo: $CORRUPTION_SCOPE
- Estratégia: $RECOVERY_STRATEGY
- Duração: [X] minutos
- Registros afetados: [X]

## Root Cause
[CAUSA RAIZ IDENTIFICADA]

## Timeline
[EVENTOS]

## Ações Tomadas
[AÇÕES]

## Lessons Learned
[LIÇÕES]

## Prevenção Futura
[AÇÕES PREVENTIVAS]
EOF

echo "=== RECUPERAÇÃO COMPLETA ==="
```

---

## 4. Checklist de Emergência

### 4.1 Pré-incidente (Preparação)

- [ ] Runbooks acessíveis offline (backup local)
- [ ] Contatos de emergência atualizados
- [ ] Acesso a todos sistemas verificado
- [ ] Backups recentes testados
- [ ] Comunicados preparados (templates)
- [ ] Status page configurada
- [ ] Canais de comunicação prontos

### 4.2 Durante incidente

- [ ] Severidade corretamente classificada
- [ ] Stakeholders notificados
- [ ] Status page atualizada
- [ ] Ações documentadas em tempo real
- [ ] Logs/métricas coletadas
- [ ] Decisões gravadas (por quê, não só o quê)
- [ ] Timeline mantida

### 4.3 Pós-incidente

- [ ] Sistema completamente recuperado
- [ ] Validação completa executada
- [ ] Postmortem agendado (24-48h)
- [ ] Action itens atribuídos
- [ ] Runbooks atualizados
- [ ] Stakeholders informados da resolução
- [ ] Métricas de melhora definidas

---

**Referências:**

- [Fluxo H Runbooks](./fluxo-h-runbooks.md)
- [Fluxo H Troubleshooting](./troubleshooting-fluxo-h.md)
- [Disaster Recovery Playbook](./DISASTER_RECOVERY_PLAYBOOK.md)

**Contatos de Emergência:**

- On-call: #fluxo-h-oncall
- Tech Lead: tech-lead@nhm.local
- Engineering Manager: emanager@nhm.local
- CTO: cto@nhm.local

---

**Changelog:**

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-04-16 | Versão inicial | Operations Team |
