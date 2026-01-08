# Code Forge S3 SBOM Storage - Runbook Operacional

## Visão Geral
Este runbook cobre operações de monitoramento, troubleshooting e recuperação para o sistema de armazenamento S3 de SBOMs do Code Forge.

## Componentes
- **S3ArtifactClient**: Cliente Python para upload/download de SBOMs
- **S3 Bucket**: `code-forge-artifacts-{env}` com versionamento e criptografia AES256
- **IRSA**: IAM Role para Service Account do Code Forge
- **Métricas Prometheus**: `code_forge_s3_*`

## Métricas Chave

| Métrica | Descrição | Threshold Alerta |
|---------|-----------|------------------|
| `code_forge_s3_upload_total{status="failure"}` | Uploads com falha | >5% em 5min |
| `code_forge_s3_upload_duration_seconds` | Latência P95 de upload | >10s |
| `code_forge_s3_integrity_check_total{status="failure"}` | Falhas de integridade | >0 em 1h |

## Operações Comuns

### Verificar Status do S3
```bash
# Verificar conectividade
kubectl exec -it deploy/code-forge -n neural-hive-pipeline -- \
  python -c "from src.clients.s3_artifact_client import S3ArtifactClient; \
  import asyncio; \
  c = S3ArtifactClient(bucket='$BUCKET', region='$REGION'); \
  print(asyncio.run(c.health_check()))"

# Listar SBOMs de um ticket
aws s3 ls s3://code-forge-artifacts-prod/sboms/{ticket_id}/ --recursive
```

### Verificar IRSA
```bash
# Verificar ServiceAccount annotations
kubectl get sa code-forge -n neural-hive-pipeline -o yaml | grep annotations -A5

# Verificar role ARN no pod
kubectl exec -it deploy/code-forge -n neural-hive-pipeline -- \
  curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

### Download Manual de SBOM
```bash
# Via AWS CLI
aws s3 cp s3://code-forge-artifacts-prod/sboms/{ticket_id}/{artifact_id}/sbom.cyclonedx.json ./

# Verificar checksum
sha256sum sbom.cyclonedx.json
```

## Troubleshooting

### Upload S3 Falhando

**Sintomas**: Métrica `code_forge_s3_upload_total{status="failure"}` aumentando

**Diagnóstico**:
```bash
# Verificar logs do Code Forge
kubectl logs -n neural-hive-pipeline -l app=code-forge --tail=500 | grep -i "s3\|upload\|error"

# Verificar credenciais IRSA
kubectl exec -it deploy/code-forge -n neural-hive-pipeline -- \
  aws sts get-caller-identity

# Verificar permissões do bucket
aws s3api get-bucket-policy --bucket code-forge-artifacts-prod
```

**Soluções**:
1. **Credenciais expiradas**: Reiniciar pods para renovar tokens IRSA
   ```bash
   kubectl rollout restart deployment/code-forge -n neural-hive-pipeline
   ```
2. **Bucket inexistente**: Verificar Terraform e recriar se necessário
3. **Permissões IAM**: Verificar policy anexada ao role

### Latência Alta de Upload

**Sintomas**: `code_forge_s3_upload_duration_seconds` P95 >10s

**Diagnóstico**:
```bash
# Verificar tamanho dos SBOMs
aws s3api list-objects-v2 --bucket code-forge-artifacts-prod \
  --prefix sboms/ --query 'Contents[].Size' | jq -s 'add/length'

# Verificar network do pod
kubectl exec -it deploy/code-forge -n neural-hive-pipeline -- \
  curl -o /dev/null -s -w '%{time_total}' https://s3.us-east-1.amazonaws.com
```

**Soluções**:
1. **SBOMs grandes**: Verificar se Syft está gerando SBOMs inflados
2. **Network issues**: Verificar VPC endpoints e NAT Gateway
3. **Throttling S3**: Verificar CloudWatch para 503 SlowDown

### Falha de Integridade

**Sintomas**: `code_forge_s3_integrity_check_total{status="failure"}` > 0

**Diagnóstico**:
```bash
# Verificar logs específicos
kubectl logs -n neural-hive-pipeline -l app=code-forge --tail=1000 | \
  grep -i "integrity\|checksum\|mismatch"

# Comparar checksums
aws s3api head-object --bucket code-forge-artifacts-prod \
  --key sboms/{ticket_id}/{artifact_id}/sbom.cyclonedx.json \
  --query 'Metadata.checksum'
```

**Soluções**:
1. **Corrupção em trânsito**: Habilitar checksums adicionais no upload
2. **Versão incorreta**: Verificar versionamento do bucket
3. **Bug no cliente**: Verificar versão do S3ArtifactClient

### SBOMs Não Encontrados

**Sintomas**: Downloads retornando 404

**Diagnóstico**:
```bash
# Verificar se objeto existe
aws s3api head-object --bucket code-forge-artifacts-prod \
  --key sboms/{ticket_id}/{artifact_id}/sbom.cyclonedx.json

# Listar versões do objeto
aws s3api list-object-versions --bucket code-forge-artifacts-prod \
  --prefix sboms/{ticket_id}/{artifact_id}/
```

**Soluções**:
1. **Objeto deletado**: Restaurar de versão anterior
   ```bash
   aws s3api get-object --bucket code-forge-artifacts-prod \
     --key sboms/{ticket}/{artifact}/sbom.cyclonedx.json \
     --version-id {version} ./restored-sbom.json
   ```
2. **Lifecycle policy**: Verificar se objeto foi movido para Glacier

## Migração de SBOMs

### Migrar SBOMs file:// para S3
```bash
# Dry-run (apenas lista)
kubectl exec -it deploy/code-forge -n neural-hive-pipeline -- \
  python scripts/migrate_sboms_to_s3.py --dry-run

# Executar migração
kubectl exec -it deploy/code-forge -n neural-hive-pipeline -- \
  python scripts/migrate_sboms_to_s3.py
```

### Rollback para file://
Se necessário reverter para armazenamento local:
1. Desabilitar S3 no Helm values:
   ```yaml
   s3:
     enabled: false
   ```
2. Aplicar:
   ```bash
   helm upgrade code-forge helm-charts/code-forge -n neural-hive-pipeline
   ```

## Recuperação de Desastres

### Restaurar SBOM de Versão Anterior
```bash
# Listar versões
aws s3api list-object-versions --bucket code-forge-artifacts-prod \
  --prefix sboms/{ticket}/{artifact}/ --max-items 10

# Restaurar versão específica
aws s3api copy-object \
  --bucket code-forge-artifacts-prod \
  --copy-source "code-forge-artifacts-prod/sboms/{ticket}/{artifact}/sbom.cyclonedx.json?versionId={version_id}" \
  --key sboms/{ticket}/{artifact}/sbom.cyclonedx.json
```

### Restaurar Bucket de Backup Cross-Region
Se bucket primário indisponível:
```bash
# Copiar de bucket DR
aws s3 sync s3://code-forge-artifacts-dr/ s3://code-forge-artifacts-prod/ \
  --source-region us-west-2 --region us-east-1
```

## Alertas e Escalação

### Alertas Configurados
- `CodeForgeS3UploadFailureHigh`: Taxa de falha >5% por 5min
- `CodeForgeS3LatencyHigh`: P95 latência >10s por 5min
- `CodeForgeS3IntegrityFailure`: Qualquer falha de integridade

### Escalação
| Severidade | Tempo Resposta | Ação |
|------------|----------------|------|
| Warning | 30min | Investigar logs, verificar métricas |
| Critical | 15min | Restart pods, verificar AWS |
| Emergency | 5min | Escalar para L2, considerar rollback |

## Dashboards
- Grafana: `Code Forge - S3 SBOM Storage`
- Prometheus queries em `/monitoring/dashboards/code-forge-s3.json`

## Contatos
- Equipe Code Forge: #code-forge-team
- AWS/Infrastructure: #platform-team
