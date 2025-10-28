# Playbook de Disaster Recovery - Neural Hive Mind

## Visão Geral

Este playbook fornece procedimentos orientados a incidentes para disaster recovery do Neural Hive Mind. Diferente do Runbook (procedimentos gerais), este documento foca em **ações step-by-step durante emergências**.

### Quando Usar Este Playbook

- ✅ Sistema de produção com falha crítica
- ✅ Perda ou corrupção de dados
- ✅ Necessidade de rollback urgente
- ✅ Migração de emergência entre ambientes
- ⛔ Backups de rotina (use o Runbook)
- ⛔ Testes planejados (use o Runbook)

### Níveis de Severidade

| Severidade | Descrição | Exemplo | RTO | RPO |
|------------|-----------|---------|-----|-----|
| **SEV1** | Sistema completamente indisponível | Cluster down, dados perdidos | 30min | 24h |
| **SEV2** | Funcionalidade crítica degradada | Especialista específico down | 2h | 24h |
| **SEV3** | Performance degradada | Latência alta, cache loss | 8h | 24h |

**RTO (Recovery Time Objective):** Tempo máximo para restaurar o serviço
**RPO (Recovery Point Objective):** Perda máxima de dados aceitável

---

## Preparação (Antes do Incidente)

### Checklist Pré-Incidente

Execute este checklist **agora** (não espere o incidente):

- [ ] **Acesso**: Tenho credenciais para AWS/GCS/Kubernetes?
- [ ] **Ferramentas**: `kubectl`, `aws-cli`, `gsutil` instalados e configurados?
- [ ] **Contatos**: Lista de escalação atualizada?
- [ ] **Backups**: Último backup foi há menos de 24h?
- [ ] **Testes**: Último teste de recovery foi bem-sucedido?
- [ ] **Documentação**: Runbook e este Playbook estão atualizados?

### Configurar Ambiente de Emergência

```bash
# 1. Configurar kubectl
export KUBECONFIG=/path/to/prod-kubeconfig.yaml
kubectl config use-context neural-hive-prod

# 2. Verificar acesso
kubectl get nodes
kubectl get pods -n neural-hive-mind

# 3. Configurar AWS CLI (se usar S3)
aws configure
aws s3 ls s3://neural-hive-backups-prod/

# 4. Configurar GCS (se usar GCS)
gcloud auth login
gcloud config set project neural-hive-prod
gsutil ls gs://neural-hive-backups/

# 5. Clonar repositório (se necessário)
git clone https://github.com/your-org/neural-hive-mind.git
cd neural-hive-mind/libraries/python
```

### Variáveis de Ambiente Críticas

```bash
# Exportar variáveis essenciais
export NAMESPACE=neural-hive-mind
export BACKUP_BUCKET=neural-hive-backups-prod
export BACKUP_REGION=us-west-2
export PROMETHEUS_URL=http://prometheus.observability.svc.cluster.local:9090
```

---

## Detecção de Incidente

### Sintomas Comuns

#### 1. Especialista Não Responde

**Sintomas:**
- HTTP 500/503 errors
- Timeouts
- Pods em CrashLoopBackOff

**Verificação inicial:**
```bash
# Status dos pods
kubectl get pods -n $NAMESPACE -l specialist-type=technical

# Logs recentes
kubectl logs -n $NAMESPACE deployment/technical-specialist --tail=100

# Eventos
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20
```

#### 2. Dados Corrompidos ou Perdidos

**Sintomas:**
- Respostas inconsistentes
- Erros de "model not found"
- Ledger entries missing

**Verificação inicial:**
```bash
# Verificar MongoDB
kubectl exec -n $NAMESPACE deployment/technical-specialist -- \
  python -c "from pymongo import MongoClient; print(MongoClient('$MONGODB_URI').admin.command('ping'))"

# Verificar Redis
kubectl exec -n $NAMESPACE deployment/technical-specialist -- \
  redis-cli -h redis-cluster ping

# Verificar MLflow
curl http://mlflow-tracking.neural-hive-mind.svc.cluster.local:5000/health
```

#### 3. Performance Degradada

**Sintomas:**
- Latência alta (>5s)
- Cache miss alto
- Timeout errors

**Verificação inicial:**
```bash
# Verificar métricas
curl -s "$PROMETHEUS_URL/api/v1/query?query=rate(neural_hive_request_duration_seconds_sum[5m])" | jq

# Verificar recursos
kubectl top pods -n $NAMESPACE
```

### Checklist de Detecção

- [ ] Identificar componente afetado (technical, business, behavior, etc.)
- [ ] Determinar severidade (SEV1/SEV2/SEV3)
- [ ] Verificar se há backup disponível (<24h)
- [ ] Estimar RTO/RPO necessário
- [ ] Notificar stakeholders
- [ ] Abrir incident ticket

---

## Procedimento 1: Restore Completo (SEV1)

**Use quando:** Sistema completamente indisponível ou dados completamente perdidos.

**Tempo estimado:** 30-60 minutos
**Requer aprovação:** SRE Lead ou VP Engineering

### Step 1: Declarar Incidente

```bash
# 1. Notificar time
echo "SEV1: Neural Hive Mind - Restore completo em andamento" | slack-cli send -c neural-hive-ops

# 2. Criar incident
incident-cli create \
  --title "Neural Hive DR: Restore Completo" \
  --severity SEV1 \
  --component neural-hive-specialists

# 3. Registrar início
date "+%Y-%m-%d %H:%M:%S - Início do restore completo" >> /tmp/incident.log
```

### Step 2: Avaliar Situação

```bash
# 1. Identificar especialistas afetados
AFFECTED_SPECIALISTS=(technical business behavior evolution architecture)

# 2. Verificar backups disponíveis
for spec in "${AFFECTED_SPECIALISTS[@]}"; do
  echo "=== Backups disponíveis: $spec ==="
  python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
    --list \
    --specialist-type $spec | head -20
done

# 3. Registrar decisão
echo "Decidido: Restaurar backup de YYYY-MM-DD HH:MM" >> /tmp/incident.log
```

### Step 3: Parar Especialistas

```bash
# 1. Escalar para 0 réplicas
for spec in "${AFFECTED_SPECIALISTS[@]}"; do
  echo "Parando ${spec}-specialist..."
  kubectl scale deployment ${spec}-specialist -n $NAMESPACE --replicas=0
done

# 2. Aguardar término
kubectl wait --for=delete pod -n $NAMESPACE -l app=specialist --timeout=120s

# 3. Verificar
kubectl get pods -n $NAMESPACE -l app=specialist
```

### Step 4: Executar Restore

```bash
# Para cada especialista afetado
for spec in "${AFFECTED_SPECIALISTS[@]}"; do
  echo "========================================="
  echo "Restaurando: $spec"
  echo "========================================="

  # Restore do backup mais recente
  python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
    --latest \
    --specialist-type $spec \
    --force \
    --verbose 2>&1 | tee -a /tmp/restore-${spec}.log

  # Verificar exit code
  if [ $? -eq 0 ]; then
    echo "✓ Restore de $spec: SUCESSO"
  else
    echo "✗ Restore de $spec: FALHA"
    echo "VER LOG: /tmp/restore-${spec}.log"
  fi

  echo
done

# Aguardar propagação
echo "Aguardando propagação de dados (30s)..."
sleep 30
```

### Step 5: Reiniciar Especialistas

```bash
# 1. Escalar de volta
for spec in "${AFFECTED_SPECIALISTS[@]}"; do
  echo "Reiniciando ${spec}-specialist..."
  kubectl scale deployment ${spec}-specialist -n $NAMESPACE --replicas=3
done

# 2. Aguardar pods ready
kubectl wait --for=condition=Ready pod -n $NAMESPACE -l app=specialist --timeout=300s

# 3. Verificar status
kubectl get pods -n $NAMESPACE -l app=specialist -o wide
```

### Step 6: Validar Funcionamento

```bash
# 1. Verificar logs (sem erros)
for spec in "${AFFECTED_SPECIALISTS[@]}"; do
  echo "=== Logs: $spec ==="
  kubectl logs -n $NAMESPACE deployment/${spec}-specialist --tail=20 | grep -i error
done

# 2. Smoke test
for spec in "${AFFECTED_SPECIALISTS[@]}"; do
  echo "=== Smoke test: $spec ==="
  python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
    --specialist-type $spec \
    --verbose
done

# 3. Teste de inferência
curl -X POST http://technical-specialist.$NAMESPACE.svc.cluster.local:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"input": "test request"}' | jq

# 4. Verificar métricas
curl -s "$PROMETHEUS_URL/api/v1/query?query=up{job=\"specialist-metrics\"}" | jq '.data.result[] | {instance: .metric.instance, value: .value[1]}'
```

### Step 7: Finalizar Incidente

```bash
# 1. Registrar término
date "+%Y-%m-%d %H:%M:%S - Restore completo finalizado com sucesso" >> /tmp/incident.log

# 2. Atualizar incident
incident-cli update \
  --status resolved \
  --resolution "Restore completo executado com sucesso. Todos os especialistas operacionais."

# 3. Notificar time
echo "SEV1 RESOLVIDO: Neural Hive Mind restaurado com sucesso" | slack-cli send -c neural-hive-ops

# 4. Agendar post-mortem
echo "TODO: Agendar post-mortem para análise de causa raiz" >> /tmp/incident.log
```

---

## Procedimento 2: Rollback de Modelo (SEV2)

**Use quando:** Novo modelo deployado causou degradação, mas sistema ainda funcional.

**Tempo estimado:** 15-30 minutos
**Requer aprovação:** ML Engineer + SRE on-call

### Step 1: Identificar Problema

```bash
# 1. Verificar métricas de qualidade
curl -s "$PROMETHEUS_URL/api/v1/query?query=neural_hive_prediction_quality_score" | jq

# 2. Comparar com baseline
# (Assumir que baseline era >0.85, atual está <0.70)

# 3. Identificar quando começou
curl -s "$PROMETHEUS_URL/api/v1/query?query=changes(neural_hive_model_version[1h])" | jq

# 4. Registrar decisão de rollback
echo "$(date): Decidido rollback do modelo technical-specialist" >> /tmp/rollback.log
```

### Step 2: Identificar Backup Anterior

```bash
# 1. Listar backups recentes
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --list \
  --specialist-type technical | head -10

# 2. Identificar backup ANTES do deploy problemático
# Exemplo: modelo deployado hoje 14h, usar backup de ontem 2h
BACKUP_ID="specialist-technical-backup-20250210-020000-abc123.tar.gz"

echo "Backup selecionado: $BACKUP_ID" >> /tmp/rollback.log
```

### Step 3: Executar Rollback

```bash
# 1. Escalar para 1 réplica (manter serviço parcial)
kubectl scale deployment technical-specialist -n $NAMESPACE --replicas=1

# 2. Aguardar estabilização
sleep 10

# 3. Restaurar backup
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --backup-id $BACKUP_ID \
  --specialist-type technical \
  --force \
  --verbose 2>&1 | tee /tmp/rollback-restore.log

# 4. Verificar sucesso
if [ $? -eq 0 ]; then
  echo "✓ Restore bem-sucedido"
else
  echo "✗ ERRO no restore! Escalando processo..."
  exit 1
fi
```

### Step 4: Rolling Restart

```bash
# 1. Reiniciar pods gradualmente
kubectl rollout restart deployment/technical-specialist -n $NAMESPACE

# 2. Aguardar rollout
kubectl rollout status deployment/technical-specialist -n $NAMESPACE --timeout=300s

# 3. Escalar de volta
kubectl scale deployment technical-specialist -n $NAMESPACE --replicas=3

# 4. Aguardar todos pods ready
kubectl wait --for=condition=Ready pod -n $NAMESPACE -l specialist-type=technical --timeout=180s
```

### Step 5: Validar Rollback

```bash
# 1. Verificar versão do modelo
kubectl exec -n $NAMESPACE deployment/technical-specialist -- \
  python -c "from neural_hive_specialists.config import SpecialistConfig; print(SpecialistConfig().model_version)"

# 2. Testar inferência
curl -X POST http://technical-specialist.$NAMESPACE.svc.cluster.local:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"input": "test after rollback"}' | jq

# 3. Monitorar métricas por 10 minutos
for i in {1..10}; do
  echo "=== Minuto $i ==="
  curl -s "$PROMETHEUS_URL/api/v1/query?query=neural_hive_prediction_quality_score{specialist_type=\"technical\"}" | jq '.data.result[0].value[1]'
  sleep 60
done

# 4. Verificar se voltou ao normal (>0.85)
echo "Rollback completo. Métricas normalizadas." >> /tmp/rollback.log
```

### Step 6: Comunicar e Documentar

```bash
# 1. Notificar time
echo "Rollback de modelo technical-specialist concluído. Versão restaurada: $(date -d 'yesterday' +%Y-%m-%d)" | slack-cli send -c ml-engineering

# 2. Atualizar incident
incident-cli update \
  --status resolved \
  --resolution "Modelo revertido para versão anterior. Performance normalizada."

# 3. Documentar lições aprendidas
echo "Lição aprendida: Implementar canary deployment antes de full rollout" >> /tmp/rollback.log
```

---

## Procedimento 3: Restore Parcial (Componente Específico)

**Use quando:** Apenas um componente está corrompido (ex: ledger, cache).

**Tempo estimado:** 15-20 minutos
**Requer aprovação:** SRE on-call

### Componente: Ledger (MongoDB)

```bash
# 1. Baixar backup
BACKUP_ID="specialist-technical-backup-20250211-020000-xyz.tar.gz"
aws s3 cp s3://$BACKUP_BUCKET/specialists/backups/technical/$BACKUP_ID /tmp/

# 2. Extrair
cd /tmp
tar -xzf $BACKUP_ID

# 3. Validar checksums
python -m neural_hive_specialists.disaster_recovery.backup_manifest validate backup/manifest.json

# 4. Parar writes no ledger (opcional, se possível)
kubectl scale deployment technical-specialist -n $NAMESPACE --replicas=0

# 5. Restaurar ledger no MongoDB
mongoimport --uri "$MONGODB_URI" \
  --db neural_hive \
  --collection ledger_technical \
  --file backup/ledger/ledger_dump.json \
  --mode upsert

# 6. Reiniciar especialista
kubectl scale deployment technical-specialist -n $NAMESPACE --replicas=3

# 7. Validar
kubectl logs -n $NAMESPACE deployment/technical-specialist --tail=50 | grep ledger
```

### Componente: Feature Store

```bash
# 1-3. Mesmo processo de download e extração

# 4. Copiar features para pod
kubectl cp backup/feature_store/ \
  $NAMESPACE/technical-specialist-pod-xxx:/app/data/feature_store/

# 5. Reiniciar pod
kubectl delete pod -n $NAMESPACE technical-specialist-pod-xxx

# 6. Validar
kubectl logs -n $NAMESPACE deployment/technical-specialist --tail=50 | grep feature_store
```

### Componente: Cache (Redis)

```bash
# 1-3. Mesmo processo de download e extração

# 4. Restaurar para Redis
kubectl exec -n $NAMESPACE deployment/technical-specialist -- \
  redis-cli -h redis-cluster --rdb backup/cache/cache_dump.rdb

# 5. Validar
kubectl exec -n $NAMESPACE deployment/technical-specialist -- \
  redis-cli -h redis-cluster info | grep keys
```

---

## Procedimento 4: Teste de Recovery Emergencial

**Use quando:** Precisa validar rapidamente se backups estão íntegros antes de restore.

**Tempo estimado:** 5-10 minutos

```bash
# 1. Executar teste de recovery
python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
  --specialist-type technical \
  --verbose \
  --alert-on-failure

# 2. Verificar resultado
if [ $? -eq 0 ]; then
  echo "✓ Backup íntegro. Pode prosseguir com restore."
else
  echo "✗ Backup corrompido! Tentar backup anterior."

  # Listar backups
  python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
    --list \
    --specialist-type technical | head -10

  # Testar backup anterior
  PREVIOUS_BACKUP=$(python -m neural_hive_specialists.scripts.run_disaster_recovery_restore --list --specialist-type technical | grep ".tar.gz" | sed -n '2p' | awk '{print $2}')

  python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
    --specialist-type technical \
    --backup-id $PREVIOUS_BACKUP \
    --verbose
fi
```

---

## Cenários Específicos

### Cenário A: MongoDB Completamente Perdido

**Gravidade:** SEV1
**Impacto:** Todos os especialistas sem ledger

**Procedimento:**

1. **Validar perda total**
   ```bash
   # Tentar conectar
   kubectl exec -n $NAMESPACE deployment/technical-specialist -- \
     mongosh "$MONGODB_URI" --eval "db.adminCommand('ping')"
   ```

2. **Provisionar novo MongoDB** (se necessário)
   ```bash
   helm upgrade --install mongodb bitnami/mongodb \
     -n $NAMESPACE \
     --set auth.rootPassword=$MONGODB_ROOT_PASSWORD
   ```

3. **Restaurar ledgers de todos especialistas**
   ```bash
   for spec in technical business behavior evolution architecture; do
     echo "Restaurando ledger: $spec"

     # Download backup
     BACKUP_ID=$(aws s3 ls s3://$BACKUP_BUCKET/specialists/backups/$spec/ | grep "tar.gz" | tail -1 | awk '{print $4}')
     aws s3 cp s3://$BACKUP_BUCKET/specialists/backups/$spec/$BACKUP_ID /tmp/

     # Extrair
     cd /tmp && tar -xzf $BACKUP_ID

     # Restore
     mongoimport --uri "$MONGODB_URI" \
       --db neural_hive \
       --collection ledger_$spec \
       --file backup/ledger/ledger_dump.json

     echo "✓ Ledger $spec restaurado"
   done
   ```

4. **Reiniciar especialistas**
   ```bash
   kubectl rollout restart deployment -n $NAMESPACE -l app=specialist
   ```

### Cenário B: Redis Cluster Falhou

**Gravidade:** SEV2
**Impacto:** Cache loss, performance degradada

**Procedimento:**

1. **Avaliar se precisa restaurar cache**
   - Cache é efêmero por natureza
   - Se performance aceitável, não restaurar
   - Se crítico, restaurar do backup

2. **Se restaurar:**
   ```bash
   # Provisionar novo Redis (se necessário)
   helm upgrade --install redis bitnami/redis-cluster -n $NAMESPACE

   # Não restaurar cache de backups antigos (dados desatualizados)
   # Deixar cache "aquecer" naturalmente com novas requests

   # OU, se necessário:
   for spec in technical business behavior; do
     BACKUP_ID=$(aws s3 ls s3://$BACKUP_BUCKET/specialists/backups/$spec/ | grep "tar.gz" | tail -1 | awk '{print $4}')
     aws s3 cp s3://$BACKUP_BUCKET/specialists/backups/$spec/$BACKUP_ID /tmp/
     cd /tmp && tar -xzf $BACKUP_ID

     kubectl exec -n $NAMESPACE deployment/${spec}-specialist -- \
       redis-cli -h redis-cluster --rdb /tmp/backup/cache/cache_dump.rdb
   done
   ```

### Cenário C: MLflow Tracking Server Down

**Gravidade:** SEV2
**Impacto:** Não consegue carregar modelos

**Procedimento:**

1. **Restaurar MLflow**
   ```bash
   # Reiniciar MLflow
   kubectl rollout restart deployment/mlflow-tracking -n $NAMESPACE

   # Aguardar ready
   kubectl wait --for=condition=Ready pod -n $NAMESPACE -l app=mlflow-tracking --timeout=120s
   ```

2. **Se MLflow database perdido:**
   ```bash
   # Restaurar metadata de modelos dos backups
   for spec in technical business behavior evolution architecture; do
     BACKUP_ID=$(aws s3 ls s3://$BACKUP_BUCKET/specialists/backups/$spec/ | grep "tar.gz" | tail -1 | awk '{print $4}')
     aws s3 cp s3://$BACKUP_BUCKET/specialists/backups/$spec/$BACKUP_ID /tmp/
     cd /tmp && tar -xzf $BACKUP_ID

     # Registrar modelo no MLflow
     kubectl cp backup/model/ $NAMESPACE/mlflow-tracking-pod:/mnt/mlflow/
   done
   ```

### Cenário D: Corrupção Silenciosa de Dados

**Gravidade:** SEV3
**Impacto:** Dados gradualmente corrompendo-se

**Procedimento:**

1. **Identificar janela de corrupção**
   ```bash
   # Analisar métricas de qualidade
   curl -s "$PROMETHEUS_URL/api/v1/query_range?query=neural_hive_prediction_quality_score&start=$(date -d '7 days ago' +%s)&end=$(date +%s)&step=1h" | jq

   # Identificar quando qualidade começou a degradar
   # Exemplo: 3 dias atrás
   ```

2. **Testar múltiplos backups**
   ```bash
   # Testar backup de 2 dias atrás
   python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
     --specialist-type technical \
     --timestamp 20250209-020000

   # Testar backup de 4 dias atrás
   python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
     --specialist-type technical \
     --timestamp 20250207-020000

   # Testar backup de 7 dias atrás
   python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
     --specialist-type technical \
     --timestamp 20250204-020000
   ```

3. **Restaurar backup mais antigo que passou no teste**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --timestamp 20250207-020000 \
     --specialist-type technical \
     --force
   ```

4. **Investigar causa raiz da corrupção**
   - Revisar mudanças de código entre 2025-02-07 e 2025-02-09
   - Analisar logs de MongoDB/Redis
   - Verificar se há padrão de corrupção

---

## KPIs de Disaster Recovery

### Métricas de Sucesso

| Métrica | Target | Atual | Status |
|---------|--------|-------|--------|
| **RTO (Recovery Time Objective)** | 30min | - | ⏱️ |
| **RPO (Recovery Point Objective)** | 24h | - | ⏱️ |
| **Backup Success Rate** | >99% | - | 📊 |
| **Recovery Test Success Rate** | >95% | - | 📊 |
| **MTTR (Mean Time To Restore)** | <45min | - | ⏱️ |

### Como Medir

```bash
# 1. RTO: Tempo desde detecção até serviço restaurado
# Registrar em /tmp/incident.log durante incidente
# Calcular: tempo_fim - tempo_inicio

# 2. RPO: Idade do backup restaurado
# Verificar timestamp do backup usado

# 3. Backup Success Rate
curl -s "$PROMETHEUS_URL/api/v1/query?query=sum(rate(neural_hive_dr_backup_total{status=\"success\"}[7d]))/sum(rate(neural_hive_dr_backup_total[7d]))" | jq '.data.result[0].value[1]'

# 4. Recovery Test Success Rate
curl -s "$PROMETHEUS_URL/api/v1/query?query=avg_over_time(neural_hive_dr_recovery_test_last_status[30d])" | jq '.data.result[0].value[1]'

# 5. MTTR: Média de tempo de restore nos últimos incidentes
# Calcular manualmente a partir de incident logs
```

---

## Appendix A: Comandos Rápidos

### Verificação Rápida de Status

```bash
# Status geral
kubectl get pods -n neural-hive-mind -o wide

# Últimos backups
for spec in technical business behavior evolution architecture; do
  aws s3 ls s3://$BACKUP_BUCKET/specialists/backups/$spec/ | tail -3
done

# Métricas de backup
curl -s "$PROMETHEUS_URL/api/v1/query?query=neural_hive_dr_backup_last_success_timestamp" | jq

# Alerts ativos
curl -s "$PROMETHEUS_URL/api/v1/alerts" | jq '.data.alerts[] | select(.labels.alertname | startswith("Backup") or startswith("Recovery"))'
```

### Comandos de Emergência

```bash
# Parar TUDO
kubectl scale deployment -n neural-hive-mind --all --replicas=0

# Reiniciar TUDO
kubectl rollout restart deployment -n neural-hive-mind --all

# Deletar pods problemáticos
kubectl delete pod -n neural-hive-mind -l app=specialist --grace-period=0 --force

# Forçar pull de nova imagem
kubectl set image deployment/technical-specialist \
  technical-specialist=neural-hive/specialist-base:latest \
  -n neural-hive-mind
```

### Debug Rápido

```bash
# Logs em tempo real
kubectl logs -n neural-hive-mind -f deployment/technical-specialist

# Shell no pod
kubectl exec -it -n neural-hive-mind deployment/technical-specialist -- /bin/bash

# Port-forward para debug local
kubectl port-forward -n neural-hive-mind svc/technical-specialist 8000:8000

# Descrever pod (eventos)
kubectl describe pod -n neural-hive-mind <pod-name>
```

---

## Appendix B: Checklist de Post-Mortem

Após resolver o incidente, execute este checklist:

- [ ] **Documentar timeline** completo do incidente
- [ ] **Identificar causa raiz** (root cause analysis)
- [ ] **Avaliar RTO/RPO** atingidos vs target
- [ ] **Documentar ações tomadas** e efetividade
- [ ] **Identificar melhorias** no processo
- [ ] **Atualizar runbook/playbook** com lições aprendidas
- [ ] **Implementar ações preventivas** (se aplicável)
- [ ] **Revisar alertas**: dispararam corretamente?
- [ ] **Revisar backup strategy**: backups estavam ok?
- [ ] **Comunicar stakeholders** sobre resolução e próximos passos
- [ ] **Agendar DR drill** para validar melhorias

### Template de Post-Mortem

```markdown
# Post-Mortem: [Título do Incidente]

**Data:** YYYY-MM-DD
**Severidade:** SEV1/SEV2/SEV3
**Duração:** X horas
**Impacto:** Descrição do impacto

## Timeline

- HH:MM - Incidente detectado
- HH:MM - Início do restore
- HH:MM - Restore completo
- HH:MM - Validação
- HH:MM - Serviço restaurado

## Causa Raiz

[Descrição detalhada]

## O Que Funcionou

- [Item 1]
- [Item 2]

## O Que Não Funcionou

- [Item 1]
- [Item 2]

## Ações Corretivas

| Ação | Owner | Deadline | Status |
|------|-------|----------|--------|
| [Ação 1] | [Nome] | YYYY-MM-DD | 🔄 |

## Lições Aprendidas

- [Lição 1]
- [Lição 2]
```

---

## Appendix C: Contatos de Emergência

### Time de Operações

| Role | Nome | Slack | Email | Telefone |
|------|------|-------|-------|----------|
| **SRE On-call** | - | @sre-oncall | ops-oncall@example.com | - |
| **SRE Lead** | - | @sre-lead | sre-lead@example.com | - |
| **ML Engineer Lead** | - | @ml-lead | ml-lead@example.com | - |
| **VP Engineering** | - | @vp-eng | vp-eng@example.com | - |

### Escalação

1. **Nível 1 (0-15min)**: SRE on-call
2. **Nível 2 (15-30min)**: SRE Lead + ML Engineer Lead
3. **Nível 3 (30min+)**: VP Engineering

### Canais de Comunicação

- **Slack**: #neural-hive-ops, #neural-hive-incidents
- **PagerDuty**: neural-hive-prod
- **Status Page**: status.neuralhive.example.com

---

**Última atualização:** 2025-10-11
**Versão:** 1.0
**Mantido por:** SRE Team
**Revisão:** Trimestral
