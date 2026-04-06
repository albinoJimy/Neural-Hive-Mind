# Spec Tasks

> Spec: INFRA-005 - Middleware OPA Authorization Activation
> Status: Planning

## Tasks

- [ ] 1. Adicionar configurações em settings.py
    - [ ] 1.1 Adicionar `enable_opa_authorization` (default: True)
    - [ ] 1.2 Adicionar `opa_authorization_policy_path` (default: "neuralhive/orchestrator/authz")
    - [ ] 1.3 Adicionar `opa_fail_open` (default: False)
    - [ ] 1.4 Adicionar headers de autenticação (user_id, tenant_id, role)
    - [ ] 1.5 Adicionar testes de configuração

- [ ] 2. Criar política OPA HTTP
    - [ ] 2.1 Criar arquivo `policies/rego/orchestrator/http_authz.rego`
    - [ ] 2.2 Implementar regra de paths públicos
    - [ ] 2.3 Implementar regra para admin role
    - [ ] 2.4 Implementar regra para developer role
    - [ ] 2.5 Implementar regra de tenant isolation
    - [ ] 2.6 Implementar regra para workers (service accounts)
    - [ ] 2.7 Adicionar testes OPA para todas as regras

- [ ] 3. Ativar middleware em main.py
    - [ ] 3.1 Importar `OPAAuthorizationMiddleware` e `OPAMiddlewareConfig`
    - [ ] 3.2 Adicionar middleware na ordem correta (CORS → OPA → RateLimit → Metrics)
    - [ ] 3.3 Configurar com valores do settings
    - [ ] 3.4 Adicionar condicional `enable_opa_authorization`

- [ ] 4. Escrever testes de integração
    - [ ] 4.1 Testar paths públicos sem autenticação
    - [ ] 4.2 Testar API sem headers retorna 403
    - [ ] 4.3 Testar API com headers válidos retorna 200
    - [ ] 4.4 Testar admin pode acessar tudo
    - [ ] 4.5 Testar tenant isolation
    - [ ] 4.6 Testar cache hit reduz latência
    - [ ] 4.7 Testar OPA indisponível retorna 503 (fail-closed)

- [ ] 5. Verificar métricas Prometheus
    - [ ] 5.1 Validar métrica `opa_middleware_decisions_total` exposta
    - [ ] 5.2 Validar métrica `opa_middleware_latency_seconds` exposta
    - [ ] 5.3 Validar métrica `opa_middleware_cache_hits_total` exposta
    - [ ] 5.4 Validar métrica `opa_middleware_circuit_breaker_open` exposta
    - [ ] 5.5 Validar métrica `opa_middleware_opa_unavailable_total` exposta

- [ ] 6. Documentação
    - [ ] 6.1 Atualizar README.md com instruções de autenticação
    - [ ] 6.2 Documentar headers obrigatórios
    - [ ] 6.3 Criar guia de troubleshooting
    - [ ] 6.4 Atualizar MEMORY.md com spec completude

- [ ] 7. Deploy e validação
    - [ ] 7.1 Carregar política OPA no servidor
    - [ ] 7.2 Deploy em staging primeiro
    - [ ] 7.3 Executar testes de smoke em staging
    - [ ] 7.4 Deploy em produção com feature flag
    - [ ] 7.5 Monitorar métricas por 24h
    - [ ] 7.6 Remover feature flag se estável
