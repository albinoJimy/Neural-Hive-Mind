# Executor Integration Guide

Guia rápido para integrar ou estender executors do Worker Agents.

## Arquitetura

- Todos os executors herdam de `BaseTaskExecutor`, que já injeta `vault_client` e `code_forge_client` (quando configurados) e provê helpers (`get_secret`, `submit_code_generation`).
- `ExecutionEngine` usa `TaskExecutorRegistry` para resolver o executor por `task_type` e aplica retry/timeout com métricas (TODO).

## Code Forge Integration

- **ExecuteExecutor**: usa `submit_generation_request` e faz polling com `get_generation_status` até `completed/failed` (timeout de 30min). Retorna artifacts e `pipeline_id` quando disponível. Fallback: simulação mantendo o fluxo.
- **BuildExecutor**: chama `trigger_pipeline` seguido de `wait_for_pipeline_completion` (polling). Retorna artifacts, SBOM e assinatura quando presentes. Fallback: build simulado.
- Exemplo:
  ```python
  request_id = await code_forge_client.submit_generation_request(ticket_id, template_id, params)
  status = await code_forge_client.get_generation_status(request_id)
  if status.status == "completed":
      artifacts = status.artifacts
  ```
- Troubleshooting: timeouts/erros caem para simulação e logam `*_code_forge_error`. Verifique conectividade e autenticação do Code Forge.

## OPA Integration

- **ValidateExecutor**: se `validation_type=policy` e `OPA_ENABLED` ativo, chama `POST {OPA_URL}/v1/data/{policy_path}` com `input`. Usa `result.allow`/`result.violations` para decidir sucesso/falha.
- Resposta esperada do OPA:
  ```json
  { "result": { "allow": true, "violations": [] } }
  ```
- Troubleshooting: erros/timeout retornam fallback simulado e log `validation_opa_error`.

## Test Execution

- **TestExecutor** executa comandos via `subprocess.run` com timeout (`TEST_EXECUTION_TIMEOUT_SECONDS`). Whitelist configurável via `ALLOWED_TEST_COMMANDS` evita injection.
- Suporta parsing de relatórios JSON (`report_path`) ou `stdout` para extrair `tests_passed`, `tests_failed`, `coverage`.
- Exemplo:
  ```bash
  pytest --json-report --json-report-file=report.json
  npm test -- --json > report.json
  ```

## Fallback Patterns

- Code Forge/ArgoCD/OPA/Trivy indisponíveis: executors retornam resultados simulados (`metadata.simulated=True`) para manter o fluxo C operando.
- Logs estruturados (`*_error`, `*_timeout`) indicam motivo do fallback; use para alerting/observabilidade.

## Adicionando Novos Executors

1. Herdar de `BaseTaskExecutor` e implementar `execute()` e `get_task_type()`.
2. Registrar no `TaskExecutorRegistry` em `main.py` (passando dependências necessárias).
3. Adicionar parâmetros/feature flags no `settings.py` e documentar no README.
4. Criar testes unitários e, se aplicável, integração com serviços externos mockados.

## Metrics & Observability (TODOs)

- Métricas a adicionar: `*_tasks_executed_total`, histogramas de duração por `task_type`, contadores de fallbacks.
- Recomendação: instrumentar spans OpenTelemetry dentro de cada executor para external calls (Code Forge, OPA, Trivy, ArgoCD).

## Configuration Reference

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CODE_FORGE_URL` | string | `http://code-forge:8000` | Code Forge API endpoint |
| `CODE_FORGE_ENABLED` | bool | `true` | Enable Code Forge integration |
| `CODE_FORGE_TIMEOUT_SECONDS` | int | `14400` | Code Forge pipeline timeout (4h) |
| `ARGOCD_URL` | string | `""` | ArgoCD API endpoint (e.g., https://argocd.example.com) |
| `ARGOCD_TOKEN` | string | `""` | ArgoCD API token (from Secret) |
| `ARGOCD_ENABLED` | bool | `false` | Enable ArgoCD integration |
| `OPA_URL` | string | `http://opa:8181` | OPA API endpoint |
| `OPA_ENABLED` | bool | `true` | Enable OPA policy validation |
| `TRIVY_ENABLED` | bool | `true` | Enable Trivy SAST scanning |
| `TRIVY_TIMEOUT_SECONDS` | int | `300` | Trivy scan timeout (5min) |
| `TEST_EXECUTION_TIMEOUT_SECONDS` | int | `600` | Test command timeout (10min) |
| `ALLOWED_TEST_COMMANDS` | list | `pytest,npm test,...` | Whitelist of allowed test commands |

### Helm Values Structure

See `helm-charts/worker-agents/values.yaml` for complete reference:

```yaml
config:
  codeForge:
    url: http://code-forge:8000
    enabled: true
    timeoutSeconds: 14400
  argocd:
    url: https://argocd.example.com
    enabled: false
  opa:
    url: http://opa:8181
    enabled: true
  trivy:
    enabled: true
    timeoutSeconds: 300
  testExecution:
    timeoutSeconds: 600
    allowedCommands: [pytest, npm test, go test, mvn test]

secrets:
  argoCdToken: <base64-encoded-token>
```

### Setup Guide

For detailed setup instructions, see [EXTERNAL_TOOLS_SETUP.md](./EXTERNAL_TOOLS_SETUP.md).

### Fallbacks Específicos

- `validation_sast_timeout`: quando o Trivy excede o timeout configurado, o executor retorna fallback simulado (`success=true`, `metadata.simulated=true`) para manter o fluxo de validação.
