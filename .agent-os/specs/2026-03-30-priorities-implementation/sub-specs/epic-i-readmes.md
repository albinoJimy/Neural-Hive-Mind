# Sub-Spec: Epic I - READMEs para Serviços Sem Documentação

## Objetivo

Criar READMEs para 10 serviços sem documentação: approval-service, queen-agent, guard-agents, 5 specialist services, explainability-api e mcp-servers.

## Padrão de README

### Estrutura (500-700 linhas)

```markdown
# [Nome do Serviço]

## Descrição
Breve descrição do serviço (2-3 linhas)

## Arquitetura
### Componentes Principais
- Componente 1: descrição
- Componente 2: descrição

### Fluxo de Dados
Diagrama mermaid do fluxo

## Configuração
### Variáveis de Ambiente
Lista de variáveis

### Estrutura de Directórios
```
src/
├── main.py
├── config/
└── services/
```

## API
### Endpoints
Lista de endpoints com métodos e parâmetros

## Integrações
### Kafka
Tópicos produzidos/consumidos

### gRPC
Serviços gRPC

### Banco de Dados
Coleções MongoDB

## Deploy
### Docker
### Kubernetes/Helm

## Desenvolvimento
### Como Executar Localmente
### Testes

## Troubleshooting
Problemas comuns e soluções
```

## Serviços e Conteúdo

### 1. approval-service
**Arquivo:** `services/approval-service/README.md`
**Seções:**
- Descrição: Serviço de aprovação humana para decisões de IA
- Arquitetura: MLPredictor, Active Learning, FeedbackCollector
- API: 5 endpoints Active Learning + aprovação
- Integrações: Kafka (cognitive-plans-approval-requests), MongoDB
- Deploy: Dockerfile, Helm chart

### 2. queen-agent
**Arquivo:** `services/queen-agent/README.md`
**Seções:**
- Descrição: Serviço de supervisão e coordenação de agentes
- Arquitetura: Strategic Decision Engine, Conflict Arbitrator, Leader Election
- API: REST endpoints (election, workers, pheromones)
- Integrações: Kafka (telemetry, incidents), Redis (leader election)
- Deploy: Dockerfile, configurção

### 3. guard-agents
**Arquivo:** `services/guard-agents/README.md`
**Seções:**
- Descrição: Serviço de segurança e validação
- Arquitetura: ThreatDetector, SecurityValidator, GuardrailEnforcer
- API: endpoints de validação e incidentes
- Integrações: OPA, Kubernetes, Vault, Trivy
- Deploy: Dockerfile

### 4. specialist-business
**Arquivo:** `services/specialist-business/README.md`
**Seções:**
- Descrição: Especialista em domínio business
- Arquitetura: BaseSpecialist扩展
- Funcionalidades: Análise de business value, ROI, process-mining
- Deploy: Dockerfile, Helm chart

### 5. specialist-technical
**Arquivo:** `services/specialist-technical/README.md`
**Seções:**
- Descrição: Especialista em domínio technical
- Arquitetura: BaseSpecialist扩展
- Funcionalidades: Análise de code-quality, security-analysis

### 6. specialist-architecture
**Arquivo:** `services/specialist-architecture/README.md`
**Seções:**
- Descrição: Especialista em domínio architecture
- Arquitetura: BaseSpecialist扩展
- Funcionalidades: Análise SOLID, design-patterns

### 7. specialist-behavior
**Arquivo:** `services/specialist-behavior/README.md`
**Seções:**
- Descrição: Especialista em domínio behavior
- Arquitetura: BaseSpecialist扩展
- Funcionalidades: Análise de acessibilidade, UX

### 8. specialist-evolution
**Arquivo:** `services/specialist-evolution/README.md`
**Seções:**
- Descrição: Especialista em domínio evolution
- Arquitetura: BaseSpecialist扩展
- Funcionalidades: Análise de maintainability, scalability

### 9. explainability-api
**Arquivo:** `services/explainability-api/README.md`
**Seções:**
- Descrição: API de explicabilidade de decisões de IA
- Arquitetura: HierarchicalExplainer, CounterfactualAnalyzer
- API: endpoints de explicação
- Integrações: MongoDB (histórico)

### 10. mcp-servers
**Arquivo:** `services/mcp-servers/README.md`
**Seções:**
- Descrição: MCP Servers para integração de ferramentas
- Serviços: scout-mcp-server, optimizer-mcp-server, etc.
- Deploy: Dockerfile por serviço

## Verificação

```bash
# Verificar READMEs criados
find services/ -name "README.md" | grep -E "(approval|queen|guard|specialist|explainability|mcp)" | wc -l
# Deve ser 10

# Verificar qualidade (mínimo 300 linhas)
wc -l services/approval-service/README.md
# Deve ser > 300

# Verificar seções obrigatórias
grep -E "^## (Descrição|Arquitetura|API|Deploy)" services/approval-service/README.md | wc -l
# Deve ser ≥ 4
```
