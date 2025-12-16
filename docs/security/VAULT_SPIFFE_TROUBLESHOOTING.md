# Vault/SPIFFE Troubleshooting

## Matriz de diagnóstico
| Sintoma | Possível causa | Comando de diagnóstico | Solução |
| --- | --- | --- | --- |
| Orchestrator não conecta ao MongoDB | Secret ausente no Vault | `vault kv get secret/orchestrator/mongodb` | Popular secret com URI correta |
| Worker gRPC UNAUTHENTICATED | JWT-SVID expirado ou inválido | `grep jwt_svid_attached` nos logs do worker; `spiffe_svid_ttl_seconds` | Garantir SPIRE agent saudável; renovar SVID |
| Token renewal falhando | Policy sem `renew-self` | `vault token lookup` | Ajustar policy, rodar `vault token renew -self` |
| Credencial dinâmica expirada | Renewal task parado | `vault_credential_renewals_total` e logs `renewing_postgres_credentials` | Reiniciar pod, verificar Vault connectivity |
| SPIFFE trust bundle desatualizado | SPIRE server não atualiza JWKS | `spire-server entry show` e `spiffe_trust_bundle_updates_total` | Reiniciar SPIRE server/agent, revisar datastore |

## Guia de logs
- Mensagens-chave: `vault_integration_initialized`, `jwt_svid_attached`, `vault_token_renewed_successfully`, `grpc_discovery_error`.
- Buscar falhas: `vault_initialization_failed`, `jwt_auth_required_fallback_disabled`, `spiffe_initialization_failed`.
- Correlação: usar `request_id`/`plan_id` nos logs do orchestrator e worker para seguir fluxos gRPC/Kafka.

## Análise de métricas
- Saúde do Vault: `vault_requests_total`, `vault_request_duration_seconds`, `vault_token_ttl_seconds`.
- Credenciais: `orchestrator_vault_credentials_fetched_total`, `orchestrator_vault_renewal_task_runs_total`.
- SPIFFE: `spiffe_svid_fetch_total`, `spiffe_svid_ttl_seconds`, `spiffe_trust_bundle_updates_total`.
- gRPC auth: `grpc_jwt_auth_attempts_total`, `grpc_jwt_auth_failures_total`.

## Procedimentos rápidos
- Regenerar role Temporal: `vault write database/roles/temporal-orchestrator ...`
- Recriar entries SPIRE: `./scripts/spire-create-entries.sh`
- Validar end-to-end: `RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_vault_spiffe_integration_full.py -v`
