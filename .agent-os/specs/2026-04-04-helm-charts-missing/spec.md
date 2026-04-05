# Spec: Helm Charts Faltantes

> **Data:** 2026-04-04
> **Status:** Planning
> **Prioridade:** 🟡 ALTA

## Resumo Executivo

Implementar Helm Charts para serviços do Neural Hive Mind que atualmente não possuem charts no diretório principal `/helm-charts`.

## Contexto da Análise

**Status Atual:** ⚠️ 63% (21/33 serviços com charts)

**Serviços SEM Chart Helm (12):**
- semantic-translation-engine (STE)
- specialist-business
- specialist-technical
- specialist-architecture
- specialist-behavior
- guard-agents
- service-registry
- code-forge
- sla-management-system
- memory-layer-api
- explainability-api
- mcp-tool-catalog

**Nota:** 4 serviços com charts em subdiretórios foram excluídos (architect-agent, feature-store, ml-inference-api, software-engineering-pipeline)

## User Stories

### US-HELM-001: Deploy via Helm Padronizado
Como engenheiro de DevOps, quero fazer deploy de todos os serviços via Helm usando estrutura padronizada.

## Escopo

### IN SCOPE
1. Criar Helm Charts para 12 serviços sem chart
2. Seguir padrão dos charts existentes
3. Componentes: deployment, service, hpa, pdb, networkpolicy, servicemonitor
4. Values para dev/staging/production

### OUT OF SCOPE
- Modificação na lógica dos serviços
- Alteração de portas ou protocolos
- Configuração de Ingress/LoadBalancer

## Tickets

### Fase 1: Core Services (2 dias)
- [ ] 1.1 semantic-translation-engine Helm Chart
- [ ] 1.2 service-registry Helm Chart
- [ ] 1.3 guard-agents Helm Chart

### Fase 2: Specialists (2 dias)
- [ ] 2.1 specialist-business Helm Chart
- [ ] 2.2 specialist-technical Helm Chart
- [ ] 2.3 specialist-architecture Helm Chart
- [ ] 2.4 specialist-behavior Helm Chart
- [ ] 2.5 specialist-evolution Helm Chart

### Fase 3: Advanced Services (2 dias)
- [ ] 3.1 code-forge Helm Chart
- [ ] 3.2 sla-management-system Helm Chart
- [ ] 3.3 memory-layer-api Helm Chart
- [ ] 3.4 explainability-api Helm Chart

### Fase 4: MCP (1 dia)
- [ ] 4.1 mcp-tool-catalog Helm Chart

### Fase 5: Documentação (1 dia)
- [ ] 5.1 README por chart
- [ ] 5.2 Guia de deploy
- [ ] 5.3 Valores de exemplo

## Template Padrão

```
helm-charts/{nome-servico}/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-prod.yaml
├── charts/
│   └── common-templates/
└── templates/
    ├── configmap.yaml
    ├── deployment.yaml
    ├── secret.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── pdb.yaml
    └── servicemonitor.yaml
```

## Estimativa Total

**17 tickets | 8 dias (~2 semanas)**

## Critérios de Aceite

- [ ] helm lint passa sem erros
- [ ] helm template gera manifests válidos
- [ ] Deploy funciona em minikube
- [ ] Health checks funcionando
- [ ] Metrics disponíveis
- [ ] HPA configurado

---

*Spec criada por Claude Code - 2026-04-04*
