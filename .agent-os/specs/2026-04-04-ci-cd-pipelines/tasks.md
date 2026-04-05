# Tasks: CI/CD Pipelines

> **Spec:** `.agent-os/specs/2026-04-04-ci-cd-pipelines/spec.md`
> **Criado:** 2026-04-04
> **Status:** Planning

## Resumo Executivo

Implementação de pipelines CI/CD completos para 40 serviços do Neural Hive Mind, baseados nos workflows existentes mas padronizados e otimizados.

**Total de Tickets:** 22 tickets
**Estimativa Total:** 160 horas
**Sprint Recomendada:** 4 semanas

---

## Epico 1: Fundação de CI/CD

**Objetivo:** Criar templates e workflows base reutilizáveis

### Ticket 1.1: Criar Template de CI Reutilizável

**ID:** CI-001
**Estimativa:** 8 horas
**Prioridade:** Alta

**Descrição:**
Criar workflow reutilizável (`.github/workflows/_ci-template.yml`) que padroniza build de serviços Python. Template deve ser usado por todos os serviços através de `workflow_call`.

**Dependencies:** Nenhuma

**Tarefas:**
1. Criar `.github/workflows/_ci-template.yml` com jobs:
   - `detect-changes`: Identifica serviços modificados
   - `build-and-push`: Build e push para GHCR
   - `test`: Executa testes do serviço
   - `security-scan`: Scan com Trivy
2. Implementar lógica de detecção de mudanças incremental
3. Configurar cache de Docker layers (type=registry)
4. Adicionar suporte para Python 3.11 e 3.12
5. Implementar geração de tags: latest, SHA, branch, semver

**Critérios de Aceite:**
- [ ] Template pode ser invocado via `workflow_call`
- [ ] Build incremental funciona (max 6 paralelos)
- [ ] Imagens pushadas apenas em branches não-PR
- [ ] Cache de Docker funciona corretamente
- [ ] Suporte a version_tag via workflow_dispatch

**Arquivos:**
- Novo: `.github/workflows/_ci-template.yml`
- Novo: `.github/workflows/_ci-inputs-schema.yml`

---

### Ticket 1.2: Criar Template de Testes Reutilizável

**ID:** CI-002
**Estimativa:** 6 horas
**Prioridade:** Alta

**Descrição:**
Criar workflow reutilizável para execução de testes com coverage, suportando unitários, integração e E2E.

**Dependencies:** CI-001

**Tarefas:**
1. Criar `.github/workflows/_test-template.yml`
2. Implementar jobs:
   - `unit-tests`: Testes unitários com coverage
   - `integration-tests`: Testes de integração com dependencies (mongo, redis, kafka)
   - `quality-gate`: Verifica threshold de 70%
3. Configurar pytest-asyncio para testes assíncronos
4. Integrar com Codecov para relatórios agregados
5. Gerar badge de coverage automaticamente

**Critérios de Aceite:**
- [ ] Testes executam em Python 3.11 e 3.12
- [ ] Integration tests usam containers GitHub Actions
- [ ] Coverage report agregado funcionando
- [ ] Quality gate em 70% implementado
- [ ] Badge de coverage gerado no main

**Arquivos:**
- Novo: `.github/workflows/_test-template.yml`
- Novo: `.github/scripts/coverage-report.sh`

---

### Ticket 1.3: Padronizar Pipeline de Linting

**ID:** CI-003
**Estimativa:** 4 horas
**Prioridade:** Média

**Descrição:**
Melhorar workflow existente `python-linting.yml` para ser mais eficiente e adicionar checks de segurança.

**Dependencies:** Nenhuma

**Tarefas:**
1. Refatorar `.github/workflows/python-linting.yml` para usar matrix strategy
2. Adicionar checks de segurança:
   - bandit (security linter)
   - safety (dependências vulneráveis)
3. Implementar cache de pip packages
4. Adicionar opção de auto-fix via workflow_dispatch
5. Criar comment no PR com sugestões de correção

**Critérios de Aceite:**
- [ ] Linting executa em paralelo (múltiplos serviços)
- [ ] bandit e safety integrados
- [ ] Comment no PR com sugestões funcionando
- [ ] Auto-fix via workflow_dispatch disponível
- [ ] Cache de pip reduz tempo de execução

**Arquivos:**
- Modificar: `.github/workflows/python-linting.yml`

---

### Ticket 1.4: Melhorar Pipeline de Segurança

**ID:** CI-004
**Estimativa:** 6 horas
**Prioridade:** Alta

**Descrição:**
Melhorar workflow `security-scan.yml` para incluir image scan e fail em CRITICAL vulnerabilities.

**Dependencies:** Nenhuma

**Tarefas:**
1. Atualizar `.github/workflows/security-scan.yml`
2. Implementar:
   - Trivy filesystem scan
   - Trivy image scan para imagens buildadas
   - Upload SARIF para GitHub Security tab
   - Fail automático em CRITICAL vulnerabilities
3. Adicionar scan de dependências (pip-audit)
4. Implementar geração de relatório consolidado

**Critérios de Aceite:**
- [ ] Trivy scan funciona para filesystem e imagens
- [ ] SARIF upload para GitHub Security tab
- [ ] Build falha em CRITICAL vulnerabilities
- [ ] pip-audit integrado
- [ ] Relatório consolidado no summary

**Arquivos:**
- Modificar: `.github/workflows/security-scan.yml`

---

## Epico 2: Workflows por Categoria de Serviço

**Objetivo:** Criar workflows específicos para cada categoria de serviço

### Ticket 2.1: Workflows para Serviços Core (8 serviços)

**ID:** CI-005
**Estimativa:** 12 horas
**Prioridade:** Alta

**Descrição:**
Criar workflows CI/CD para os 8 serviços core do sistema.

**Dependencies:** CI-001, CI-002, CI-004

**Serviços Core:**
- `gateway-intencoes` - API Gateway
- `semantic-translation-engine` - Tradução de intenções
- `consensus-engine` - Motor de consenso
- `orchestrator-dynamic` - Orquestrador Temporal
- `approval-service` - Serviço de aprovação
- `worker-agents` - Agentes de execução
- `queen-agent` - Agente supervisor
- `service-registry` - Registro de serviços

**Tarefas:**
1. Para cada serviço core:
   - Criar workflow que invoca `_ci-template.yml`
   - Configurar paths triggers específicos
   - Adicionar testes específicos do serviço
   - Configurar notificações de falha
2. Criar workflow `.github/workflows/ci-core-services.yml` que:
   - Detecta mudanças em `services/{core-service}/`
   - Executa builds em paralelo (max 4)
   - Aguarda testes antes de deploy

**Critérios de Aceite:**
- [ ] Todos os 8 serviços têm CI configurado
- [ ] Builds executam em paralelo
- [ ] Deploy automático para staging em develop
- [ ] Notificações de falha funcionam
- [ ] Tempo de build < 10 minutos

**Arquivos:**
- Novo: `.github/workflows/ci-core-services.yml`
- Modificar: `.github/workflows/_ci-template.yml` (se necessário)

---

### Ticket 2.2: Workflows para Agentes Especializados (8 serviços)

**ID:** CI-006
**Estimativa:** 10 horas
**Prioridade:** Alta

**Descrição:**
Criar workflows CI/CD para os 8 agentes especializados.

**Dependencies:** CI-001, CI-002

**Serviços de Agentes:**
- `analyst-agents` - Analistas de dados
- `scout-agents` - Exploradores
- `guard-agents` - Validadores de segurança
- `optimizer-agents` - Otimizadores
- `self-healing-engine` - Auto-recuperação
- `code-forge` - Geração de código
- `architect-agent` - Arquiteto de sistemas
- `mcp-tool-catalog` - Catálogo de ferramentas MCP

**Tarefas:**
1. Criar workflow `.github/workflows/ci-agents.yml`
2. Configurar triggers para `services/{agent-service}/`
3. Adicionar testes específicos de agentes
4. Configurar matrix para builds paralelos

**Critérios de Aceite:**
- [ ] Todos os 8 agentes têm CI configurado
- [ ] Builds paralelos funcionando
- [ ] Testes específicos executando
- [ ] Deploy automático funcionando

**Arquivos:**
- Novo: `.github/workflows/ci-agents.yml`

---

### Ticket 2.3: Workflows para Serviços MCP (13 servidores)

**ID:** CI-007
**Estimativa:** 10 horas
**Prioridade:** Média

**Descrição:**
Criar workflows CI/CD para os 13 servidores MCP.

**Dependencies:** CI-001, CI-002

**Servidores MCP:**
- `mcp-servers/ai-codegen-mcp-server`
- `mcp-servers/sonarqube-mcp-server`
- `mcp-servers/trivy-mcp-server`
- `mcp-servers/scout-mcp-server`
- `mcp-servers/optimizer-mcp-server`
- E mais 8 servidores MCP

**Tarefas:**
1. Criar workflow `.github/workflows/ci-mcp-servers.yml`
2. Configurar triggers para `mcp-servers/**`
3. Adicionar validação de schema MCP
4. Implementar testes de conexão MCP

**Critérios de Aceite:**
- [ ] Todos os 13 servidores MCP têm CI
- [ ] Validação de schema funcionando
- [ ] Testes de conexão MCP executando
- [ ] Deploy automático funcionando

**Arquivos:**
- Novo: `.github/workflows/ci-mcp-servers.yml`

---

### Ticket 2.4: Workflows para Especialistas e Serviços Auxiliares (11 serviços)

**ID:** CI-008
**Estimativa:** 8 horas
**Prioridade:** Média

**Descrição:**
Criar workflows CI/CD para especialistas e serviços auxiliares.

**Dependencies:** CI-001, CI-002

**Serviços:**
- `specialist-business`, `specialist-technical`, `specialist-architecture`, `specialist-behavior`, `specialist-evolution`
- `execution-ticket-service`, `memory-layer-api`, `sla-management-system`, `explainability-api`, `ml-inference-api`, `feature-store`

**Tarefas:**
1. Criar workflow `.github/workflows/ci-specialists.yml`
2. Configurar triggers para `specialist-*/` e serviços auxiliares
3. Adicionar testes específicos de especialistas
4. Implementar validação de schemas de especialistas

**Critérios de Aceite:**
- [ ] Todos os 11 serviços têm CI configurado
- [ ] Validação de schemas funcionando
- [ ] Deploy automático funcionando

**Arquivos:**
- Novo: `.github/workflows/ci-specialists.yml`

---

## Epico 3: Deploy Automation

**Objetivo:** Implementar deploy automatizado para staging e production

### Ticket 3.1: Pipeline de Deploy para Staging

**ID:** CI-009
**Estimativa:** 8 horas
**Prioridade:** Alta

**Descrição:**
Implementar deploy automático para staging (branch `develop`).

**Dependencies:** CI-005, CI-006, CI-007, CI-008

**Tarefas:**
1. Melhorar workflow existente `deploy-to-cluster.yml`
2. Configurar:
   - Trigger automático após build bem-sucedido em `develop`
   - Namespace `neural-hive-staging`
   - Helm upgrade para cada serviço modificado
   - Health checks pós-deploy
   - Rollback automático em falha
3. Adicionar notificações (Slack/Teams)
4. Implementar dry-run mode

**Critérios de Aceite:**
- [ ] Deploy automático em develop funciona
- [ ] Helm upgrade usado para todos os serviços
- [ ] Health checks validam deployments
- [ ] Rollback automático funciona
- [ ] Deploy < 5 minutos
- [ ] Notificações funcionam

**Arquivos:**
- Modificar: `.github/workflows/deploy-to-cluster.yml`
- Novo: `.github/scripts/deploy-staging.sh`

---

### Ticket 3.2: Pipeline de Deploy para Production

**ID:** CI-010
**Estimativa:** 10 horas
**Prioridade:** Alta

**Descrição:**
Implementar deploy para production (branch `main`) com aprovação manual.

**Dependencies:** CI-009

**Tarefas:**
1. Criar workflow `.github/workflows/deploy-production.yml`
2. Configurar:
   - Trigger manual apenas (workflow_dispatch)
   - Requer aprovação de 2 reviewers
   - Namespace `neural-hive-prod`
   - Blue-green deployment ou canary
   - Smoke tests pós-deploy
3. Implementar rollback manual
4. Adicionar audit log

**Critérios de Aceite:**
- [ ] Deploy requer aprovação manual
- [ ] Blue-green ou canary implementado
- [ ] Smoke tests executam pós-deploy
- [ ] Rollback manual disponível
- [ ] Deploy < 15 minutos
- [ ] Audit log funcionando

**Arquivos:**
- Novo: `.github/workflows/deploy-production.yml`
- Novo: `.github/scripts/smoke-tests.sh`

---

### Ticket 3.3: Pipeline de Rollback

**ID:** CI-011
**Estimativa:** 6 horas
**Prioridade:** Média

**Descrição:**
Criar workflow de rollback automatizado para emergências.

**Dependencies:** CI-010

**Tarefas:**
1. Criar workflow `.github/workflows/rollback.yml`
2. Implementar:
   - Seleção de serviço para rollback
   - Seleção de versão (SHA ou tag)
   - Helm rollback ou image set
   - Validação pós-rollback
   - Notificação de rollback
3. Adicionar botão de rollback no dashboard do GitHub

**Critérios de Aceite:**
- [ ] Rollback funciona via workflow_dispatch
- [ ] Versão anterior selecionável
- [ ] Validação pós-rollback funciona
- [ ] Rollback < 5 minutos
- [ ] Notificações funcionam

**Arquivos:**
- Novo: `.github/workflows/rollback.yml`
- Novo: `.github/scripts/rollback.sh`

---

## Epico 4: Otimização e Observabilidade

**Objetivo:** Otimizar performance e adicionar observabilidade

### Ticket 4.1: Cache e Otimização de Performance

**ID:** CI-012
**Estimativa:** 8 horas
**Prioridade:** Média

**Descrição:**
Otimizar pipelines com cache e parallel execution.

**Dependencies:** CI-005, CI-006, CI-007, CI-008

**Tarefas:**
1. Implementar cache de Docker layers
2. Adicionar cache de pip packages
3. Otimizar parallel execution (max 6 jobs)
4. Implementar build matrix inteligente
5. Adicionar timing reports

**Critérios de Aceite:**
- [ ] Docker cache reduz tempo de build em 30%
- [ ] Pip cache reduz tempo de setup em 50%
- [ ] Parallel execution otimizada
- [ ] Timing reports disponíveis
- [ ] Build incremental < 10 minutos

**Arquivos:**
- Modificar: `.github/workflows/_ci-template.yml`
- Novo: `.github/scripts/timing-report.sh`

---

### Ticket 4.2: Dashboards e Notificações

**ID:** CI-013
**Estimativa:** 6 horas
**Prioridade:** Baixa

**Descrição:**
Criar dashboards e configurar notificações.

**Dependencies:** CI-009, CI-010

**Tarefas:**
1. Criar dashboard no GitHub Actions:
   - Status de todos os pipelines
   - Métricas de build time
   - Coverage trend
   - Vulnerabilities trend
2. Configurar notificações:
   - Slack para falhas
   - Email para approves
   - Status badge no README
3. Implementar relatório diário de CI/CD

**Critérios de Aceite:**
- [ ] Dashboard funcional no GitHub
- [ ] Notificações de falha funcionam
- [ ] Status badges no README
- [ ] Relatório diário configurado

**Arquivos:**
- Novo: `.github/workflows/daily-report.yml`
- Modificar: `README.md` (adicionar badges)

---

### Ticket 4.3: Documentação de CI/CD

**ID:** CI-014
**Estimativa:** 6 horas
**Prioridade:** Média

**Descrição:**
Documentar todos os workflows e processos de CI/CD.

**Dependencies:** Todos os tickets anteriores

**Tarefas:**
1. Criar documentação em `docs/ci-cd/`:
   - Overview da arquitetura CI/CD
   - Guia de uso dos workflows
   - Guia de troubleshooting
   - Políticas de deploy
2. Adicionar comentários nos workflows
3. Criar diagramas (Mermaid)
4. Documentar variáveis de ambiente
5. Criar runbooks operacionais

**Critérios de Aceite:**
- [ ] Documentação completa em `docs/ci-cd/`
- [ ] Workflows comentados
- [ ] Diagramas criados
- [ ] Runbooks disponíveis
- [ ] Variáveis documentadas

**Arquivos:**
- Novo: `docs/ci-cd/README.md`
- Novo: `docs/ci-cd/workflows.md`
- Novo: `docs/ci-cd/troubleshooting.md`
- Novo: `docs/ci-cd/diagrams.md`
- Novo: `docs/ci-cd/runbooks.md`

---

## Epico 5: Bibliotecas Python

**Objetivo:** Implementar CI/CD para bibliotecas Python

### Ticket 5.1: CI para Bibliotecas Python

**ID:** CI-015
**Estimativa:** 8 horas
**Prioridade:** Média

**Descrição:**
Criar workflows CI/CD para bibliotecas em `libraries/python/`.

**Dependencies:** CI-001, CI-002

**Bibliotecas:**
- `neural_hive_core`
- `neural_hive_observability`
- `neural_hive_specialists`
- `neural_hive_agent_sdk`
- `neural_hive_ml`
- Outras bibliotecas

**Tarefas:**
1. Criar workflow `.github/workflows/ci-python-libraries.yml`
2. Implementar:
   - Build de pacotes (wheel/sdist)
   - Publicação no GitHub Packages
   - Testes de versões compatíveis
   - Versionamento semántico
3. Configurar dependências entre bibliotecas

**Critérios de Aceite:**
- [ ] Bibliotecas têm CI configurado
- [ ] Pacotes publicados no GitHub Packages
- [ ] Versionamento semântico funcionando
- [ ] Dependências entre bibliotecas resolvidas

**Arquivos:**
- Novo: `.github/workflows/ci-python-libraries.yml`

---

## Epico 6: Migração e Limpeza

**Objetivo:** Migrar serviços existentes e limpar workflows obsoletos

### Ticket 6.1: Mapear e Documentar Workflows Existentes

**ID:** CI-016
**Estimativa:** 4 horas
**Prioridade:** Alta

**Descrição:**
Mapear todos os workflows existentes e documentar o que será mantido, migrado ou removido.

**Dependencies:** Nenhuma

**Tarefas:**
1. Listar todos os workflows em `.github/workflows/`
2. Classificar cada workflow:
   - Manter como está
   - Migrar para novo padrão
   - Remover (obsoleto)
3. Criar matriz de migração
4. Identificar gaps

**Critérios de Aceite:**
- [ ] Todos os workflows mapeados
- [ ] Plano de migração definido
- [ ] Gaps identificados

**Arquivos:**
- Novo: `docs/ci-cd/workflow-migration-plan.md`

---

### Ticket 6.2: Remover Workflows Obsoletos

**ID:** CI-017
**Estimativa:** 2 horas
**Prioridade:** Baixa

**Descrição:**
Remover workflows obsoletos após migração.

**Dependencies:** CI-016, CI-005, CI-006, CI-007, CI-008, CI-015

**Tarefas:**
1. Arquivar workflows obsoletos em `.github/workflows/_archive/`
2. Remover do repositório principal
3. Atualizar referências

**Critérios de Aceite:**
- [ ] Workflows obsoletos arquivados
- [ ] Repo limpo sem workflows duplicados

**Arquivos:**
- Novo: `.github/workflows/_archive/`

---

### Ticket 6.3: Refatorar Workflows Duplicados

**ID:** CI-018
**Estimativa:** 6 horas
**Prioridade:** Média

**Descrição:**
Consolidar workflows duplicados em templates reutilizáveis.

**Dependencies:** CI-016

**Tarefas:**
1. Identificar workflows com lógica duplicada
2. Extrair lógica comum para templates
3. Refatorar workflows para usar templates
4. Testar workflows refatorados

**Critérios de Aceite:**
- [ ] Duplicação eliminada
- [ ] Templates criados
- [ ] Workflows refatorados funcionando

**Arquivos:**
- Modificar: Vários workflows

---

## Epico 7: Testes E2E

**Objetivo:** Implementar testes E2E no CI/CD

### Ticket 7.1: Testes E2E para Workflows CI/CD

**ID:** CI-019
**Estimativa:** 10 horas
**Prioridade:** Média

**Descrição:**
Criar testes E2E que validam os pipelines de CI/CD.

**Dependencies:** CI-001, CI-002, CI-009

**Tarefas:**
1. Criar testes que:
   - Validam build de imagem
   - Validam push para GHCR
   - Validam execução de testes
   - Validam deploy para staging
2. Implementar testes de rollback
3. Criar ambiente de testes E2E
4. Automatizar execução semanal

**Critérios de Aceite:**
- [ ] Testes E2E funcionando
- [ ] Testes executam semanalmente
- [ ] Falhas nos testes alertam a equipe

**Arquivos:**
- Novo: `tests/ci-cd/e2e/`
- Novo: `.github/workflows/e2e-ci-cd.yml`

---

## Epico 8: Integrações Externas

**Objetivo:** Integrar com ferramentas externas

### Ticket 8.1: Integração com SonarQube

**ID:** CI-020
**Estimativa:** 6 horas
**Prioridade:** Baixa

**Descrição:**
Integrar pipelines com SonarQube para análise estática.

**Dependencies:** CI-001

**Tarefas:**
1. Configurar SonarQube scanner
2. Integrar com workflows CI
3. Configurar quality gates
4. Adicionar relatórios no PR

**Critérios de Aceite:**
- [ ] SonarQube scanner funcionando
- [ ] Quality gates configurados
- [ ] Relatórios no PR

**Arquivos:**
- Modificar: `.github/workflows/_ci-template.yml`
- Novo: `sonar-project.properties`

---

### Ticket 8.2: Integração com Snyk

**ID:** CI-021
**Estimativa:** 4 horas
**Prioridade:** Baixa

**Descrição:**
Integrar Snyk para scan de vulnerabilidades em dependências.

**Dependencies:** CI-004

**Tarefas:**
1. Configurar Snyk
2. Integrar com workflow de segurança
3. Configurar alertas

**Critérios de Aceite:**
- [ ] Snyk scan funcionando
- [ ] Alertas configurados

**Arquivos:**
- Modificar: `.github/workflows/security-scan.yml`

---

## Epico 9: Validação Final

**Objetivo:** Validar e testar toda a implementação

### Ticket 9.1: Teste End-to-End dos Pipelines

**ID:** CI-022
**Estimativa:** 12 horas
**Prioridade:** Alta

**Descrição:**
Validar todos os pipelines com teste completo de ponta a ponta.

**Dependencies:** Todos os tickets anteriores

**Tarefas:**
1. Testar workflow completo:
   - Push em feature branch
   - Pull request
   - Merge para develop
   - Deploy automático em staging
   - Merge para main
   - Deploy manual em production
2. Validar rollback
3. Validar notificações
4. Documentar issues encontrados
5. Criar checklist de validação

**Critérios de Aceite:**
- [ ] Workflow completo testado
- [ ] Rollback testado
- [ ] Notificações validadas
- [ ] Checklist criado

**Arquivos:**
- Novo: `docs/ci-cd/validation-checklist.md`

---

## Resumo de Estimativas

| Epico | Tickets | Horas | Semanas |
|-------|---------|-------|---------|
| Epico 1: Fundação | 4 | 24h | 0.75 |
| Epico 2: Workflows por Categoria | 4 | 38h | 1.0 |
| Epico 3: Deploy Automation | 3 | 24h | 0.75 |
| Epico 4: Otimização | 3 | 20h | 0.5 |
| Epico 5: Bibliotecas | 1 | 8h | 0.25 |
| Epico 6: Migração | 3 | 12h | 0.375 |
| Epico 7: Testes E2E | 1 | 10h | 0.3125 |
| Epico 8: Integrações | 2 | 10h | 0.3125 |
| Epico 9: Validação | 1 | 12h | 0.375 |
| **TOTAL** | **22** | **158h** | **~4.3 semanas** |

## Ordem de Implementação Recomendada

### Sprint 1 (Semana 1-2): Fundação
1. CI-016: Mapear Workflows Existentes (começar primeiro)
2. CI-001: Template de CI Reutilizável
3. CI-002: Template de Testes Reutilizável
4. CI-004: Pipeline de Segurança

### Sprint 2 (Semana 2-3): Workflows e Deploy
5. CI-005: Workflows Core Services
6. CI-006: Workflows Agentes
7. CI-007: Workflows MCP
8. CI-008: Workflows Especialistas
9. CI-009: Deploy Staging
10. CI-003: Linting (paralelo)

### Sprint 3 (Semana 3-4): Production e Otimização
11. CI-010: Deploy Production
12. CI-011: Rollback
13. CI-012: Cache e Otimização
14. CI-015: CI Bibliotecas
15. CI-019: Testes E2E

### Sprint 4 (Semana 4-5): Finalização
16. CI-017: Remover Obsoletos
17. CI-018: Refatorar Duplicados
18. CI-013: Dashboards
19. CI-014: Documentação
20. CI-020: SonarQube (opcional)
21. CI-021: Snyk (opcional)
22. CI-022: Validação Final

## Definição de Pronto

Um ticket é considerado "pronto" quando:
- [ ] Código implementado e commitado
- [ ] Testes passando localmente
- [ ] Workflow testado no GitHub Actions
- [ ] Documentação atualizada
- [ ] Code review aprovado
- [ ] Merge para branch principal

---

*Tasks criadas por Claude Code - 2026-04-04*
