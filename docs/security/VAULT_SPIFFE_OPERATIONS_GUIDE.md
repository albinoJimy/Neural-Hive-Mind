# Vault e SPIFFE - Guia de Operações

## 1. Deployment
- Pré-requisitos: Terraform aplicado, Helm charts do Vault/SPIRE instalados, `vault` e `kubectl` configurados.
- Passos:  
  1. `./scripts/vault-configure-policies.sh`  
  2. `./scripts/vault-populate-secrets.sh` (use `DRY_RUN=true` para pré-visualizar)  
  3. `./scripts/spire-create-entries.sh`  
  4. Ative nos charts: `vault.enabled=true`, `spiffe.enabled=true`.
- Checklist: policies criadas, database engine configurado, secrets populados, entries SPIRE criadas.
- Validação: `./scripts/validate-vault-spiffe-integration.sh`.

## 2. Monitoring
- Métricas chave: `vault_token_ttl_seconds`, `vault_credential_renewals_total`, `spiffe_svid_fetch_total`, `grpc_jwt_auth_attempts_total`.
- Dashboard: `monitoring/dashboards/vault-spiffe-integration.json`.
- Alertas: `monitoring/alerts/vault-spiffe-alerts.yaml`.
- Observação: acompanhe p95 de `vault_request_duration_seconds` e taxa de falhas de `spiffe_svid_fetch_total{status="error"}`.

## 3. Token Rotation
- Renovação automática: tasks de `vault_client` + `vault_integration` renovam token antes de 80% do TTL.
- Credenciais dinâmicas: `database/roles/temporal-orchestrator` renova e invalida credenciais antigas.
- Procedimento manual: `vault token renew -self` e `vault read database/creds/temporal-orchestrator`.
- X.509/JWT-SVID: SPIRE agent renova SVIDs via Workload API; monitore `spiffe_svid_ttl_seconds`.

## 4. Troubleshooting
- Vault token expirou: verifique `vault_token_ttl_seconds`, rode `vault login` e reimplante pod se necessário.
- SPIFFE SVID falhou: `kubectl logs -n spire-system spire-agent-*`, `spire-server entry show`.
- gRPC UNAUTHENTICATED: confirme JWT-SVID no metadata, consulte logs com `jwt_svid_attached` e `grpc_jwt_auth_failures_total`.
- Credencial não encontrada: `vault kv get secret/orchestrator/*`, valide policies e path.

## 5. Emergency Procedures
- Vault selado: `vault operator unseal` com keys, verificar auto-unseal KMS.
- SPIRE server down: reiniciar StatefulSet, checar datastore.
- Token rotation parada: matar pod para reiniciar renewal task, ou renovar manualmente token/credenciais.
- Rollback: desativar `vault.enabled`/`spiffe.enabled` nos valores Helm e redeploy; usar credenciais estáticas.
