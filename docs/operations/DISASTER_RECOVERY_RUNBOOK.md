# Runbook de Disaster Recovery - Neural Hive Mind

## Visão Geral

Este runbook documenta os procedimentos operacionais para backup, restore e teste de disaster recovery (DR) do sistema Neural Hive Mind, com foco nos componentes dos especialistas neurais.

### Escopo

- **Componentes cobertos**: Modelos MLflow, Ledger MongoDB, Feature Store, Cache Redis, Métricas
- **Tipos de especialistas**: Technical, Business, Behavior, Evolution, Architecture
- **Storage providers**: S3 (AWS), GCS (Google Cloud), Local
- **Retenção**: 90 dias
- **Frequência de backup**: Diária (2h UTC)
- **Teste de recovery**: Semanal (domingos 3h UTC)

### Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    Disaster Recovery System                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐             │
│  │   Backup   │   │  Restore   │   │   Test     │             │
│  │  CronJob   │   │   Script   │   │  CronJob   │             │
│  └──────┬─────┘   └──────┬─────┘   └──────┬─────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          │                                      │
│              ┌───────────▼───────────┐                          │
│              │ DisasterRecoveryMgr   │                          │
│              └───────────┬───────────┘                          │
│                          │                                      │
│         ┌────────────────┼────────────────┐                    │
│         │                │                │                    │
│    ┌────▼────┐     ┌────▼────┐     ┌────▼────┐               │
│    │   S3    │     │   GCS   │     │  Local  │               │
│    │ Storage │     │ Storage │     │ Storage │               │
│    └─────────┘     └─────────┘     └─────────┘               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Componentes de Backup

1. **Model** (MLflow)
   - Modelo treinado
   - Artefatos
   - Metadata
   - Registro MLflow

2. **Ledger** (MongoDB)
   - Histórico de decisões
   - Audit trail
   - Metadata de especialistas

3. **Feature Store**
   - Features armazenadas
   - Feature metadata
   - Feature engineering

4. **Cache** (Redis) - Opcional
   - Cache de inferências
   - Cache de features
   - Cache de predictions

5. **Metrics**
   - Métricas de desempenho
   - KPIs
   - Telemetria

---

## Configuração

### Variáveis de Ambiente

#### Configuração Geral
```bash
# Habilitar Disaster Recovery
ENABLE_DISASTER_RECOVERY=true

# Provider de storage (s3, gcs, local)
BACKUP_STORAGE_PROVIDER=s3

# Retenção de backups (dias)
BACKUP_RETENTION_DAYS=90

# Nível de compressão (1-9)
BACKUP_COMPRESSION_LEVEL=6

# Incluir componentes
BACKUP_INCLUDE_CACHE=false
BACKUP_INCLUDE_METRICS=true
BACKUP_INCLUDE_FEATURE_STORE=true
```

#### Configuração S3
```bash
BACKUP_S3_BUCKET=neural-hive-backups-prod
BACKUP_S3_REGION=us-west-2
BACKUP_S3_PREFIX=specialists/backups

# Credenciais (opcional, preferir IAM roles)
AWS_ACCESS_KEY_ID=<access_key>
AWS_SECRET_ACCESS_KEY=<secret_key>
```

#### Configuração GCS
```bash
BACKUP_GCS_BUCKET=neural-hive-backups
BACKUP_GCS_PROJECT=my-project-id
BACKUP_PREFIX=specialists/backups

# Credenciais
GCP_CREDENTIALS_PATH=/path/to/credentials.json
```

#### Configuração Local
```bash
BACKUP_LOCAL_PATH=/opt/neural-hive/backups
```

### Arquivos de Configuração

- **CronJob**: `/home/jimy/Base/Neural-Hive-Mind/k8s/cronjobs/disaster-recovery-backup-job.yaml`
- **Test CronJob**: `/home/jimy/Base/Neural-Hive-Mind/k8s/cronjobs/disaster-recovery-test-job.yaml`
- **Alerts**: `/home/jimy/Base/Neural-Hive-Mind/monitoring/alerts/disaster-recovery-alerts.yaml`
- **Dashboard**: `/home/jimy/Base/Neural-Hive-Mind/monitoring/dashboards/disaster-recovery-dashboard.json`

---

## Procedimentos de Backup

### Backup Automático (Diário)

O backup automático é executado diariamente às 2h UTC pelo CronJob Kubernetes.

**Componentes envolvidos:**
- CronJob: `disaster-recovery-backup-job`
- Script: `run_disaster_recovery_backup.py`
- Namespace: `neural-hive-mind`

**Verificar execução:**
```bash
# Listar execuções do CronJob
kubectl get jobs -n neural-hive-mind -l app=disaster-recovery,component=backup

# Ver logs do último job
kubectl logs -n neural-hive-mind -l app=disaster-recovery,component=backup --tail=100

# Ver status do CronJob
kubectl get cronjob disaster-recovery-backup-job -n neural-hive-mind
```

### Backup Manual

#### Via Python CLI

```bash
# Backup de todos os especialistas
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --verbose

# Backup de especialista específico
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --specialist-type technical \
  --verbose

# Backup de tenant específico
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --tenant-id tenant-A \
  --verbose

# Dry-run (simulação)
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --dry-run \
  --verbose

# Com limpeza automática de backups expirados
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --cleanup \
  --verbose

# Enviar métricas para Pushgateway
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --pushgateway-url http://prometheus-pushgateway.observability.svc.cluster.local:9091 \
  --verbose
```

#### Via Make (se disponível)

```bash
# Backup completo
make dr-backup

# Backup de especialista específico
make dr-backup SPECIALIST_TYPE=technical

# Backup com cleanup
make dr-backup-cleanup
```

#### Via kubectl exec

```bash
# Executar backup dentro de um pod especialista
kubectl exec -n neural-hive-mind deployment/technical-specialist -- \
  python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --specialist-type technical \
  --verbose
```

### Verificar Backups Disponíveis

```bash
# Listar backups no S3
aws s3 ls s3://neural-hive-backups-prod/specialists/backups/ --recursive

# Listar backups no GCS
gsutil ls -r gs://neural-hive-backups/specialists/backups/

# Listar backups localmente
ls -lh /opt/neural-hive/backups/
```

### Estrutura de Backup

```
s3://bucket/specialists/backups/
├── technical/
│   ├── specialist-technical-backup-20250211-020000-abc123.tar.gz
│   ├── specialist-technical-backup-20250210-020000-def456.tar.gz
│   └── ...
├── business/
│   ├── specialist-business-backup-20250211-020000-xyz789.tar.gz
│   └── ...
└── ...
```

**Nomenclatura:**
- `specialist-{type}-backup-{YYYYMMDD}-{HHMMSS}-{uuid}.tar.gz`

**Conteúdo do .tar.gz:**
```
backup/
├── manifest.json          # Metadata e checksums
├── model/                 # Modelo MLflow
│   ├── model.pkl
│   ├── MLmodel
│   └── ...
├── ledger/                # Dump MongoDB
│   └── ledger_dump.json
├── feature_store/         # Features
│   └── features.parquet
├── cache/                 # Cache Redis (opcional)
│   └── cache_dump.rdb
└── metrics/               # Métricas
    └── metrics.json
```

---

## Procedimentos de Restore

### Listar Backups Disponíveis

```bash
# Via Python CLI
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --list \
  --specialist-type technical

# Exemplo de output:
# Total de backups: 15
#
# #    Backup File                                                    Size (MB)    Timestamp
# ------------------------------------------------------------------------------------------------
# 1    specialist-technical-backup-20250211-020000-abc123.tar.gz       245.32    2025-02-11 02:00:00
# 2    specialist-technical-backup-20250210-020000-def456.tar.gz       243.18    2025-02-10 02:00:00
# ...
```

### Restore Completo

#### Restore do Backup Mais Recente

```bash
# Com confirmação interativa
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --latest \
  --specialist-type technical \
  --verbose

# Forçar sem confirmação (cuidado!)
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --latest \
  --specialist-type technical \
  --force \
  --verbose
```

#### Restore de Backup Específico

```bash
# Por ID do backup
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --backup-id specialist-technical-backup-20250211-020000-abc123.tar.gz \
  --specialist-type technical \
  --verbose

# Por timestamp
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --timestamp 20250211-020000 \
  --specialist-type technical \
  --verbose
```

#### Restore para Diretório Customizado

```bash
python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
  --latest \
  --specialist-type technical \
  --target-dir /tmp/restore-test \
  --verbose
```

### Restore Parcial (Componentes Específicos)

**Nota:** Para restore parcial, você precisa extrair o backup manualmente e restaurar componentes individualmente.

```bash
# 1. Baixar backup
aws s3 cp s3://neural-hive-backups-prod/specialists/backups/technical/specialist-technical-backup-20250211-020000-abc123.tar.gz .

# 2. Extrair
tar -xzf specialist-technical-backup-20250211-020000-abc123.tar.gz

# 3. Restaurar componente específico (exemplo: ledger)
mongoimport --uri $MONGODB_URI \
  --db neural_hive \
  --collection ledger_technical \
  --file backup/ledger/ledger_dump.json
```

### Validação Pós-Restore

Após o restore, sempre execute validação:

```bash
# Smoke tests automáticos (incluídos no restore)
# Se skippou durante restore, execute manualmente:
python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
  --specialist-type technical \
  --verbose

# Verificar status do especialista
kubectl get pods -n neural-hive-mind -l specialist-type=technical

# Verificar logs
kubectl logs -n neural-hive-mind deployment/technical-specialist --tail=100

# Testar inferência
curl -X POST http://technical-specialist:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"input": "test"}'
```

---

## Testes de Recovery

### Teste Automático (Semanal)

Teste automático executado semanalmente aos domingos às 3h UTC.

```bash
# Ver execução do CronJob de teste
kubectl get cronjob disaster-recovery-test-job -n neural-hive-mind

# Logs do último teste
kubectl logs -n neural-hive-mind -l app=disaster-recovery,component=test --tail=200
```

### Teste Manual

```bash
# Testar recovery do backup mais recente
python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
  --specialist-type technical \
  --verbose

# Testar backup específico
python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
  --specialist-type technical \
  --backup-id specialist-technical-backup-20250211-020000-abc123.tar.gz \
  --verbose

# Com alertas em caso de falha
python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
  --specialist-type technical \
  --alert-on-failure \
  --verbose

# Enviar métricas para Prometheus
python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
  --specialist-type technical \
  --pushgateway-url http://prometheus-pushgateway:9091 \
  --verbose
```

### O Que o Teste de Recovery Valida

1. **Download** do backup do storage
2. **Validação** de checksums do arquivo e componentes
3. **Extração** do .tar.gz
4. **Restore** de componentes em diretório temporário
5. **Smoke tests**:
   - Carregar modelo
   - Executar inferência de teste
   - Verificar integridade de dados
6. **Cleanup** de arquivos temporários

---

## Cenários de Disaster Recovery

### Cenário 1: Perda Completa de Dados de Especialista

**Situação:** O MongoDB ou Redis foram corrompidos ou perderam dados de um especialista.

**Procedimento:**

1. **Identificar último backup válido**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --list \
     --specialist-type technical
   ```

2. **Parar especialista afetado**
   ```bash
   kubectl scale deployment technical-specialist -n neural-hive-mind --replicas=0
   ```

3. **Restaurar backup**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --latest \
     --specialist-type technical \
     --verbose
   ```

4. **Reiniciar especialista**
   ```bash
   kubectl scale deployment technical-specialist -n neural-hive-mind --replicas=3
   ```

5. **Validar funcionamento**
   ```bash
   kubectl logs -n neural-hive-mind deployment/technical-specialist --tail=50
   ```

### Cenário 2: Rollback de Modelo

**Situação:** Novo modelo deployado tem performance ruim e precisa reverter.

**Procedimento:**

1. **Identificar backup antes do deploy**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --list \
     --specialist-type technical
   ```

2. **Restaurar modelo anterior**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --backup-id specialist-technical-backup-20250210-020000-def456.tar.gz \
     --specialist-type technical \
     --force
   ```

3. **Reiniciar pods**
   ```bash
   kubectl rollout restart deployment/technical-specialist -n neural-hive-mind
   ```

### Cenário 3: Migração Entre Clusters

**Situação:** Migrar especialistas para novo cluster Kubernetes.

**Procedimento:**

1. **No cluster antigo: Fazer backup final**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
     --verbose
   ```

2. **Transferir credenciais de storage para novo cluster**
   ```bash
   kubectl create secret generic aws-credentials \
     --from-literal=access_key_id=$AWS_ACCESS_KEY_ID \
     --from-literal=secret_access_key=$AWS_SECRET_ACCESS_KEY \
     -n neural-hive-mind
   ```

3. **No novo cluster: Deploy de infraestrutura (MongoDB, Redis, MLflow)**

4. **Restaurar cada especialista**
   ```bash
   for type in technical business behavior evolution architecture; do
     python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
       --latest \
       --specialist-type $type \
       --force
   done
   ```

5. **Validar todos os especialistas**

### Cenário 4: Corrupção de Dados

**Situação:** Dados corrompidos detectados, mas não se sabe quando começou.

**Procedimento:**

1. **Identificar janela de tempo suspeita**
   - Analisar métricas e logs
   - Identificar quando anomalias começaram

2. **Testar múltiplos backups**
   ```bash
   # Testar backup de 1 dia atrás
   python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
     --specialist-type technical \
     --timestamp 20250210-020000

   # Testar backup de 3 dias atrás
   python -m neural_hive_specialists.scripts.run_disaster_recovery_test \
     --specialist-type technical \
     --timestamp 20250208-020000
   ```

3. **Restaurar backup mais recente validado**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --timestamp 20250208-020000 \
     --specialist-type technical
   ```

---

## Troubleshooting

### Backup Falhando

**Sintomas:**
- Jobs de backup falhando
- Alert `BackupFailed` disparando

**Verificações:**

1. **Logs do job**
   ```bash
   kubectl logs -n neural-hive-mind -l app=disaster-recovery,component=backup --tail=200
   ```

2. **Credenciais de storage**
   ```bash
   kubectl get secret aws-credentials -n neural-hive-mind -o yaml
   ```

3. **Conectividade com storage**
   ```bash
   # Testar S3
   aws s3 ls s3://neural-hive-backups-prod/

   # Testar GCS
   gsutil ls gs://neural-hive-backups/
   ```

4. **Espaço em disco no pod**
   ```bash
   kubectl exec -n neural-hive-mind <pod-name> -- df -h
   ```

5. **Variáveis de ambiente**
   ```bash
   kubectl describe cronjob disaster-recovery-backup-job -n neural-hive-mind | grep -A 50 "Environment:"
   ```

**Soluções comuns:**

- **Credenciais expiradas**: Atualizar secrets
  ```bash
  kubectl create secret generic aws-credentials \
    --from-literal=access_key_id=$NEW_KEY \
    --from-literal=secret_access_key=$NEW_SECRET \
    --dry-run=client -o yaml | kubectl apply -f -
  ```

- **Bucket não existe**: Criar bucket
  ```bash
  aws s3 mb s3://neural-hive-backups-prod --region us-west-2
  ```

- **Falta de espaço**: Aumentar `emptyDir.sizeLimit` no CronJob

- **Timeout**: Aumentar `activeDeadlineSeconds` no CronJob

### Restore Falhando

**Sintomas:**
- Restore não completa
- Checksum validation failing

**Verificações:**

1. **Backup existe?**
   ```bash
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --list \
     --specialist-type technical
   ```

2. **Backup está corrompido?**
   ```bash
   # Baixar e verificar
   aws s3 cp s3://bucket/path/backup.tar.gz .
   tar -tzf backup.tar.gz
   ```

3. **Logs do restore**
   ```bash
   # Modo verbose
   python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
     --latest \
     --specialist-type technical \
     --verbose
   ```

**Soluções:**

- **Checksum falhou**: Backup corrompido, usar backup anterior
  ```bash
  # Pular validação (emergência apenas!)
  python -m neural_hive_specialists.scripts.run_disaster_recovery_restore \
    --backup-id <previous-backup> \
    --specialist-type technical \
    --skip-validation
  ```

- **Componente específico falhou**: Restore parcial manual (ver seção acima)

### Backups Não Sendo Limpos

**Sintomas:**
- Backups antigos (>90 dias) ainda presentes
- Storage crescendo indefinidamente

**Verificação:**
```bash
# Ver backups antigos
aws s3 ls s3://neural-hive-backups-prod/specialists/backups/technical/ | grep 2024
```

**Solução:**
```bash
# Executar cleanup manual
python -m neural_hive_specialists.scripts.run_disaster_recovery_backup \
  --cleanup \
  --verbose

# Ou configurar lifecycle policy no S3
aws s3api put-bucket-lifecycle-configuration \
  --bucket neural-hive-backups-prod \
  --lifecycle-configuration file://lifecycle-policy.json
```

### Métricas Não Aparecendo

**Sintomas:**
- Dashboard vazio
- Alerts não disparando

**Verificações:**

1. **Prometheus está scraping?**
   ```bash
   # Verificar targets
   kubectl port-forward -n observability svc/prometheus 9090:9090
   # Acessar http://localhost:9090/targets
   ```

2. **Pushgateway está recebendo métricas?**
   ```bash
   kubectl port-forward -n observability svc/prometheus-pushgateway 9091:9091
   # Acessar http://localhost:9091/metrics
   ```

3. **Jobs estão enviando métricas?**
   ```bash
   kubectl logs -n neural-hive-mind -l app=disaster-recovery,component=backup \
     | grep -i "métricas enviadas"
   ```

**Soluções:**

- Verificar `--pushgateway-url` nos CronJobs
- Verificar NetworkPolicy não está bloqueando
- Reinstalar Prometheus/Pushgateway se necessário

---

## Métricas e Alertas

### Métricas Principais

#### Backup
- `neural_hive_dr_backup_last_success_timestamp`: Timestamp do último backup bem-sucedido
- `neural_hive_dr_backup_duration_seconds`: Duração do backup
- `neural_hive_dr_backup_size_bytes`: Tamanho do backup
- `neural_hive_dr_backup_total`: Total de backups (counter)
- `neural_hive_dr_backup_component_duration_seconds`: Duração por componente
- `neural_hive_dr_backup_component_size_bytes`: Tamanho por componente

#### Restore
- `neural_hive_dr_restore_total`: Total de restores
- `neural_hive_dr_restore_duration_seconds`: Duração de restore

#### Recovery Test
- `neural_hive_dr_recovery_test_last_status`: Status do último teste (1=success, 0=failed)
- `neural_hive_dr_recovery_test_last_timestamp`: Timestamp do último teste
- `neural_hive_dr_recovery_test_duration_seconds`: Duração do teste

#### Storage
- `neural_hive_dr_storage_upload_errors_total`: Erros de upload
- `neural_hive_dr_storage_download_errors_total`: Erros de download

### Alerts Configurados

Veja `/home/jimy/Base/Neural-Hive-Mind/monitoring/alerts/disaster-recovery-alerts.yaml`:

- **BackupFailed**: Backup falhou
- **BackupNotRunRecently**: Sem backup há mais de 25 horas
- **RecoveryTestFailed**: Teste de recovery falhou
- **StorageUploadErrors**: Erros de upload para storage
- **BackupDurationAnomaly**: Duração do backup anormalmente alta
- **BackupSizeAnomaly**: Tamanho do backup anormalmente diferente

### Dashboard

Acesse o dashboard Grafana em:
- **Nome**: Disaster Recovery Monitoring
- **Path**: `/home/jimy/Base/Neural-Hive-Mind/monitoring/dashboards/disaster-recovery-dashboard.json`

**Panels incluídos:**
- Status do último backup/teste
- Trends de tamanho e duração
- Breakdown por componente
- Erros de storage
- Tabela de alertas ativos

---

## Contatos e Escalação

### Time de Operações

- **SRE On-call**: ops-oncall@example.com
- **Slack**: #neural-hive-ops
- **PagerDuty**: neural-hive-prod

### Escalação

1. **Nível 1 (0-15min)**: SRE on-call
   - Tentar restore automático
   - Verificar logs e métricas

2. **Nível 2 (15-30min)**: SRE Lead + ML Engineer
   - Restore manual
   - Análise de causa raiz

3. **Nível 3 (30min+)**: VP Engineering
   - Decisões de failover
   - Comunicação com stakeholders

---

## Checklist de Verificação

### Pré-Backup
- [ ] Variáveis de ambiente configuradas
- [ ] Credenciais de storage válidas
- [ ] Conectividade com storage OK
- [ ] Espaço suficiente em disco
- [ ] CronJob habilitado e agendado

### Pós-Backup
- [ ] Job completou com sucesso
- [ ] Backup aparece no storage
- [ ] Tamanho do backup dentro do esperado
- [ ] Métricas atualizadas no Prometheus
- [ ] Sem alerts disparados

### Pré-Restore
- [ ] Backup validado (checksum OK)
- [ ] Especialista parado ou em manutenção
- [ ] Backup de segurança do estado atual (se aplicável)
- [ ] Aprovação de mudança (change request)
- [ ] Janela de manutenção comunicada

### Pós-Restore
- [ ] Restore completou sem erros
- [ ] Smoke tests passaram
- [ ] Especialista reiniciado
- [ ] Inferências funcionando
- [ ] Métricas normais
- [ ] Logs sem erros

### Teste de Recovery
- [ ] Teste executado com sucesso
- [ ] Todos os componentes validados
- [ ] Métricas registradas
- [ ] Documentação atualizada (se necessário)

---

## Referências

### Documentação Relacionada

- **Playbook de DR**: `/home/jimy/Base/Neural-Hive-Mind/docs/operations/DISASTER_RECOVERY_PLAYBOOK.md`
- **Runbook Geral**: `/home/jimy/Base/Neural-Hive-Mind/docs/operations/runbook.md`
- **Troubleshooting**: `/home/jimy/Base/Neural-Hive-Mind/docs/operations/troubleshooting-guide.md`

### Código Fonte

- **DR Manager**: `/home/jimy/Base/Neural-Hive-Mind/libraries/python/neural_hive_specialists/disaster_recovery/disaster_recovery_manager.py`
- **Backup Script**: `/home/jimy/Base/Neural-Hive-Mind/libraries/python/neural_hive_specialists/scripts/run_disaster_recovery_backup.py`
- **Restore Script**: `/home/jimy/Base/Neural-Hive-Mind/libraries/python/neural_hive_specialists/scripts/run_disaster_recovery_restore.py`
- **Test Script**: `/home/jimy/Base/Neural-Hive-Mind/libraries/python/neural_hive_specialists/scripts/run_disaster_recovery_test.py`

### Configuração Kubernetes

- **Backup CronJob**: `/home/jimy/Base/Neural-Hive-Mind/k8s/cronjobs/disaster-recovery-backup-job.yaml`
- **Test CronJob**: `/home/jimy/Base/Neural-Hive-Mind/k8s/cronjobs/disaster-recovery-test-job.yaml`

### Observabilidade

- **Alerts**: `/home/jimy/Base/Neural-Hive-Mind/monitoring/alerts/disaster-recovery-alerts.yaml`
- **Dashboard**: `/home/jimy/Base/Neural-Hive-Mind/monitoring/dashboards/disaster-recovery-dashboard.json`
- **Métricas**: `/home/jimy/Base/Neural-Hive-Mind/libraries/python/neural_hive_specialists/metrics.py` (linhas 538-620)

---

**Última atualização:** 2025-10-11
**Versão:** 1.0
**Mantido por:** SRE Team
