# Spec Summary (Lite) - CI/CD Pipelines

Implementar pipelines de CI/CD padronizados para 40 serviços do Neural Hive Mind com builds incrementais, testes automatizados, scans de segurança e deploy automatizado para staging/production.

## Objetivos Principais

1. **Build Incremental:** Detectar serviços modificados e buildar apenas o necessário
2. **Testes Automatizados:** Unitários, integração e E2E com coverage >= 70%
3. **Segurança:** Trivy scans para vulnerabilidades, falha em CRITICAL
4. **Deploy Automatizado:** Staging (auto em develop), Production (manual com aprovação)

## Estrutura de Epicos (22 Tickets, 158 horas)

- **Epico 1 - Fundação:** Templates reutilizáveis de CI, testes e segurança (4 tickets)
- **Epico 2 - Workflows por Categoria:** Core services, agentes, MCP, especialistas (4 tickets)
- **Epico 3 - Deploy Automation:** Staging, production, rollback (3 tickets)
- **Epico 4 - Otimização:** Cache, dashboards, documentação (3 tickets)
- **Epico 5 - Bibliotecas:** CI para libraries/python (1 ticket)
- **Epico 6 - Migração:** Mapear, remover obsoletos, refatorar duplicados (3 tickets)
- **Epico 7 - E2E:** Testes end-to-end dos pipelines (1 ticket)
- **Epico 8 - Integrações:** SonarQube, Snyk (2 tickets)
- **Epico 9 - Validação:** Teste final completo (1 ticket)

## Critérios de Aceite Global

- [ ] Todos 40 serviços têm CI/CD implementado
- [ ] Build incremental < 10 minutos
- [ ] Coverage global >= 70%
- [ ] Zero vulnerabilidades CRITICAL
- [ ] Deploy staging < 5 minutos
- [ ] Deploy production < 15 minutos
- [ ] Rollback < 5 minutos

## Status Atual

Workflows existentes (35+):
- `build-and-push-ghcr.yml` - Build e push para GHCR
- `python-linting.yml` - Linting com black/ruff/mypy
- `security-scan.yml` - Scan Trivy
- `deploy-to-cluster.yml` - Deploy manual
- `test-coverage.yml` - Coverage reports

Gaps identificados:
- Templates reutilizáveis não existem
- Workflows duplicados
- Deploy automático incompleto
- Falta padronização entre serviços

---

*Spec Summary criada por Claude Code - 2026-04-04*
