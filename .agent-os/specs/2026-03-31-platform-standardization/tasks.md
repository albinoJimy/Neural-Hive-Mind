# Tasks - Platform Standardization

Epic: Platform Standardization (Fases 0, 1, 2)
Created: 2026-03-31
Estimated: 4-6 weeks

---

## Fase 0: Emergência (48h)

### Task SEC-001: Padronizar OpenTelemetry
- [ ] 1.1 Identificar todos os serviços usando OpenTelemetry
- [ ] 1.2 Atualizar requirements.txt para opentelemetry-api==1.29.0
- [ ] 1.3 Atualizar requirements.txt para opentelemetry-sdk==1.29.0
- [ ] 1.4 Atualizar pacotes de instrumentação
- [ ] 1.5 Testar tracing entre serviços
- [ ] 1.6 Commit e PR: "Padronizar OpenTelemetry v1.29.0"

### Task SEC-002: Implementar Security Scans no CI/CD
- [ ] 2.1 Criar arquivo .github/workflows/security-scan.yml
- [ ] 2.2 Configurar Trivy para filesystem scan
- [ ] 2.3 Configurar upload de resultados SARIF
- [ ] 2.4 Testar workflow em PR
- [ ] 2.5 Validar que vulnerabilities são detectadas
- [ ] 2.6 Commit e PR: "Implementar security scans CI/CD"

### Task SEC-003: Remover Secrets Padrão
- [ ] 3.1 Identificar campos com secrets padrão
- [ ] 3.2 Remover defaults de passwords em .env.example
- [ ] 3.3 Remover defaults de api_keys em settings.py
- [ ] 3.4 Adicionar validação para campos obrigatórios
- [ ] 3.5 Testar que serviço falha sem config
- [ ] 3.6 Commit e PR: "Remover secrets padrão das configurações"

### Task SEC-004: Habilitar HTTPS em Produção
- [ ] 4.1 Identificar endpoints HTTP em produção
- [ ] 4.2 Substituir http:// por https:// em configs
- [ ] 4.3 Adicionar validação HTTPS em produção
- [ ] 4.4 Atualizar documentação
- [ ] 4.5 Commit e PR: "Habilitar HTTPS endpoints críticos"

---

## Fase 1: Quick Wins (1-2 semanas)

### Task PAD-001: Padronizar Nomenclatura gRPC
- [ ] 5.1 Atualizar OptimizerGrpcClient (optimizer-agents)
- [ ] 5.2 Atualizar OptimizerGrpcClient (consensus-engine)
- [ ] 5.3 Atualizar QueenAgentGrpcClient (analyst-agents)
- [ ] 5.4 Atualizar QueenAgentGrpcClient (scout-agents)
- [ ] 5.5 Atualizar todos os imports afetados
- [ ] 5.6 Rodar testes em todos os serviços
- [ ] 5.7 Commit e PR: "Padronizar nomenclatura clientes gRPC"

### Task PAD-002: Padronizar Endpoints REST
- [ ] 6.1 Identificar endpoints com camelCase
- [ ] 6.2 Renomear /activeLearning/* para /active-learning/*
- [ ] 6.3 Atualizar documentação OpenAPI
- [ ] 6.4 Testar todos os endpoints renomeados
- [ ] 6.5 Commit e PR: "Padronizar endpoints REST kebab-case"

### Task PAD-003: Unificar Health Checks
- [ ] 7.1 Criar biblioteca neural_hive_api
- [ ] 7.2 Criar schema HealthResponse
- [ ] 7.3 Criar função create_health_response
- [ ] 7.4 Atualizar todos os /healthz para /health
- [ ] 7.5 Implementar response schema padronizado
- [ ] 7.6 Testar health checks em todos os serviços
- [ ] 7.7 Commit e PR: "Unificar health check /health"

### Task VER-001: Consolidar Dependências
- [ ] 8.1 Criar requirements-base.txt na raiz
- [ ] 8.2 Listar todas as dependências comuns
- [ ] 8.3 Definir versões consolidadas
- [ ] 8.4 Atualizar services/*/requirements.txt
- [ ] 8.5 Testar builds de todos os serviços
- [ ] 8.6 Commit e PR: "Criar requirements-base.txt"

### Task VER-002: Padronizar Python 3.12
- [ ] 9.1 Identificar Dockerfiles com Python 3.11
- [ ] 9.2 Atualizar FROM python:3.11 para 3.12
- [ ] 9.3 Atualizar base images
- [ ] 9.4 Testar builds com Python 3.12
- [ ] 9.5 Validar compatibilidade de bibliotecas
- [ ] 9.6 Commit e PR: "Padronizar Python 3.12"

### Task PAD-004: Padronizar Tópicos Kafka
- [ ] 10.1 Documentar padrão {domain}.{event}
- [ ] 10.2 Renomear tópicos fora do padrão
- [ ] 10.3 Atualizar producers
- [ ] 10.4 Atualizar consumers
- [ ] 10.5 Testar fluxos Kafka completos
- [ ] 10.6 Commit e PR: "Padronizar nomes tópicos Kafka"

---

## Fase 2: Consolidação (3-4 semanas)

### Task BIB-001: Criar Biblioteca de Exceções
- [ ] 11.1 Criar estrutura neural_hive_exceptions/
- [ ] 11.2 Implementar NeuralHiveError base
- [ ] 11.3 Implementar ValidationError
- [ ] 11.4 Implementar ConfigurationError
- [ ] 11.5 Implementar GRPCError
- [ ] 11.6 Criar adaptadores HTTP/gRPC
- [ ] 11.7 Escrever testes unitários
- [ ] 11.8 Commit e PR: "Criar biblioteca exceções"

### Task BIB-002: Implementar BaseInfrastructureSettings
- [ ] 12.1 Criar neural_hive_infrastructure/
- [ ] 12.2 Implementar BaseInfrastructureSettings
- [ ] 12.3 Mover configs partilhadas para base
- [ ] 12.4 Atualizar services para herdar base
- [ ] 12.5 Testar carregamento de configs
- [ ] 12.6 Commit e PR: "Criar settings base compartilhado"

### Task LOG-001: Migrar para Structlog
- [ ] 13.1 Identificar arquivos com logging padrão
- [ ] 13.2 Substituir import logging por structlog
- [ ] 13.3 Atualizar formatação de logs
- [ ] 13.4 Adicionar correlation IDs
- [ ] 13.5 Testar logging em todos os serviços
- [ ] 13.6 Commit e PR: "Migrar logging para structlog"

###Task TYP-001: Completar Type Hints
- [ ] 14.1 Identificar funções sem type hints
- [ ] 14.2 Adicionar type hints em funções públicas
- [ ] 14.3 Usar Dict[str, Any] consistentemente
- [ ] 14.4 Habilitar mypy no projeto
- [ ] 14.5 Corrigir erros do mypy
- [ ] 14.6 Commit e PR: "Completar type hints código"

### Task DOCKER-001: Criar Base Image Única
- [ ] 15.1 Analisar base images atuais
- [ ] 15.2 Criar dockerfile base unificado
- [ ] 15.3 Consolidar dependências comuns
- [ ] 15.4 Testar nova base image
- [ ] 15.5 Atualizar serviços para usar nova base
- [ ] 15.6 Documentar procedimento de build
- [ ] 15.7 Commit e PR: "Criar base image única"

### Task DEVOPS-001: Implementar Dependabot
- [ ] 16.1 Criar arquivo dependabot.yml
- [ ] 16.2 Configurar grupos de dependências
- [ ] 16.3 Configurar schedule semanal
- [ ] 16.4 Testar automação de PRs
- [ ] 16.5 Commit e PR: "Implementar Dependabot"

---

## Checkpoints de Validação

### Após Fase 0
- [ ] CI/CD com security scans funcionando
- [ ] Zero high/critical CVEs abertos
- [ ] OpenTelemetry v1.29.0 em produção
- [ ] Todos os secrets removidos do código

### Após Fase 1
- [ ] 100% clientes gRPC com nomenclatura correta
- [ ] 100% endpoints REST com kebab-case
- [ ] 100% serviços com /health padronizado
- [ ] requirements-base.txt em uso
- [ ] Python 3.12 em todos os serviços

### Após Fase 2
- [ ] neural_hive_exceptions em produção
- [ ] 100% dos logs com structlog
- [ ] Type hints em todas as funções públicas
- [ ] Base image única em uso
- [ ] Dependabot criando PRs automaticamente

---

## Progresso Geral

- [ ] Fase 0: Emergência (0/4 tarefas)
- [ ] Fase 1: Quick Wins (0/6 tarefas)
- [ ] Fase 2: Consolidação (0/6 tarefas)
- [ ] Total: 0/16 tarefas

**Estimativa:** 160-228 horas (~4-6 semanas)
