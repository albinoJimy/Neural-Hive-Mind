# Tasks: Padronização de Helm Charts

> **Epic:** INFRA-003 - Helm Charts Standardization
> **Data:** 2026-04-04
> **Estimativa Total:** 16 horas

## Resumo Executivo

**Status Atual:** Todos os 12 serviços listados na spec original já possuem Helm Charts. No entanto, foi identificada uma falta de padronização nos templates. Esta tarefa foca em completar os templates faltantes para garantir que todos os charts sigam o mesmo padrão de produção.

**Gaps Identificados:**
- `explainability-api`: Falta HPA, PDB, NetworkPolicy, ServiceMonitor
- `code-forge`: Falta PDB
- `sla-management-system`: Falta NetworkPolicy
- `memory-layer-api`: Falta PDB
- `mcp-tool-catalog`: Falta PDB

**Critério de Padrão:** Todo chart deve ter 9 templates (deployment, service, hpa, pdb, networkpolicy, servicemonitor, configmap, secret, serviceaccount)

---

## Epic 1: Completar Templates Faltantes (12 horas)

### 1.1 explainability-api - Adicionar Templates Faltantes

**Descrição:** Completar o chart do `explainability-api` com templates de produção que estão faltando. Atualmente tem apenas 4 templates (deployment, service, configmap, secret).

**Templates a Adicionar:**
- `hpa.yaml` - HorizontalPodAutoscaler para scale automático
- `pdb.yaml` - PodDisruptionBudget para alta disponibilidade
- `networkpolicy.yaml` - NetworkPolicy para segurança de rede
- `servicemonitor.yaml` - ServiceMonitor para observabilidade

**Estimativa:** 3 horas

**Dependências:** Nenhuma

**Critérios de Aceite:**
- [ ] 4 templates criados seguindo padrão de `semantic-translation-engine`
- [ ] `helm lint` passa sem erros
- [ ] `helm template` gera manifests válidos
- [ ] HPA configurado com minReplicas=2, maxReplicas=10
- [ ] PDB configurado com minAvailable=1
- [ ] NetworkPolicy com deny-all ingress + allow de serviços específicos
- [ ] ServiceMonitor com selectors corretos

---

### 1.2 code-forge - Adicionar PodDisruptionBudget

**Descrição:** Adicionar template `pdb.yaml` ao chart do `code-forge` para garantir alta disponibilidade durante manutenções.

**Estimativa:** 1 hora

**Dependências:** Nenhuma

**Critérios de Aceite:**
- [ ] Template `pdb.yaml` criado
- [ ] Configuração minAvailable=1
- [ ] Segue padrão de `semantic-translation-engine`
- [ ] `helm lint` passa sem erros

---

### 1.3 sla-management-system - Adicionar NetworkPolicy

**Descrição:** Adicionar template `networkpolicy.yaml` ao chart do `sla-management-system` para isolar rede do serviço.

**Estimativa:** 1.5 horas

**Dependências:** Nenhuma

**Critérios de Aceite:**
- [ ] Template `networkpolicy.yaml` criado
- [ ] Política deny-all de entrada
- [ ] Regras allow para ingress, monitoramento e comunicação inter-serviços
- [ ] Segue padrão de `semantic-translation-engine`
- [ ] `helm lint` passa sem erros

---

### 1.4 memory-layer-api - Adicionar PodDisruptionBudget

**Descrição:** Adicionar template `pdb.yaml` ao chart do `memory-layer-api` para garantir alta disponibilidade durante manutenções.

**Estimativa:** 1 hora

**Dependências:** Nenhuma

**Critérios de Aceite:**
- [ ] Template `pdb.yaml` criado
- [ ] Configuração minAvailable=1
- [ ] Segue padrão de `semantic-translation-engine`
- [ ] `helm lint` passa sem erros

---

### 1.5 mcp-tool-catalog - Adicionar PodDisruptionBudget

**Descrição:** Adicionar template `pdb.yaml` ao chart do `mcp-tool-catalog` para garantir alta disponibilidade durante manutenções.

**Estimativa:** 1 hora

**Dependências:** Nenhuma

**Critérios de Aceite:**
- [ ] Template `pdb.yaml` criado
- [ ] Configuração minAvailable=1
- [ ] Segue padrão de `semantic-translation-engine`
- [ ] `helm lint` passa sem erros

---

## Epic 2: Validação e Testes (2 horas)

### 2.1 Executar helm lint em todos os charts

**Descrição:** Validar que todos os 12 charts passam no `helm lint` sem erros ou warnings críticos.

**Estimativa:** 1 hora

**Dependências:** Epic 1 completo

**Critérios de Aceite:**
- [ ] `helm lint` executado para todos os 12 charts
- [ ] Zero charts com falha
- [ ] Relatório de validação gerado

**Comando:**
```bash
for chart in semantic-translation-engine specialist-business specialist-technical specialist-architecture specialist-behavior guard-agents service-registry code-forge sla-management-system memory-layer-api explainability-api mcp-tool-catalog; do
  echo "Linting $chart..."
  helm lint helm-charts/$chart
done
```

---

### 2.2 Executar helm template para validar manifests

**Descrição:** Gerar manifests Kubernetes com `helm template` para garantir que todos os templates renderizam corretamente.

**Estimativa:** 1 hora

**Dependências:** 2.1 completa

**Critérios de Aceite:**
- [ ] `helm template` executado para todos os 12 charts
- [ ] Zero erros de renderização
- [ ] Manifestos YAML válidos (verificado com `kubectl apply --dry-run`)

**Comando:**
```bash
for chart in semantic-translation-engine specialist-business specialist-technical specialist-architecture specialist-behavior guard-agents service-registry code-forge sla-management-system memory-layer-api explainability-api mcp-tool-catalog; do
  echo "Templating $chart..."
  helm template test-release helm-charts/$chart --values helm-charts/$chart/values.yaml
done
```

---

## Epic 3: Documentação (2 horas)

### 3.1 Criar README para explainability-api

**Descrição:** Documentar o chart do `explainability-api` com instruções de instalação, configuração e upgrade. Este chart teve mais templates adicionados e precisa de documentação atualizada.

**Estimativa:** 1 hora

**Dependências:** 1.1 completa

**Critérios de Aceite:**
- [ ] Arquivo `README.md` criado em `helm-charts/explainability-api/`
- [ ] Seções: Instalação, Configuração, Upgrade, Troubleshooting
- [ ] Exemplos de valores para dev/staging/production
- [ ] Instruções de deploy local com minikube

---

### 3.2 Atualizar guia de deploy consolidado

**Descrição:** Criar/atualizar documento consolidado com instruções de deploy de todos os 12 serviços usando Helm.

**Estimativa:** 1 hora

**Dependências:** Epic 1 e 2 completos

**Critérios de Aceite:**
- [ ] Documento criado em `helm-charts/DEPLOY_GUIDE.md`
- [ ] Instruções para deploy individual por serviço
- [ ] Instruções para deploy em lote
- [ ] Lista de prerequisitos (kubectl, helm, kubeconfig)
- [ ] Valores padrão explicados
- [ ] Comandos de verify e rollback

---

## Resumo de Esforço

| Epic | Tarefas | Horas |
|------|---------|-------|
| Epic 1: Completar Templates | 5 tarefas | 7.5h |
| Epic 2: Validação | 2 tarefas | 2h |
| Epic 3: Documentação | 2 tarefas | 2h |
| **TOTAL** | **9 tarefas** | **11.5h** |

*Nota: Estimativa original era 17 tarefas / 8 dias. Após análise, o escopo real é menor pois os charts já existem.*

---

## Serviços Analisados (Status Final)

| Serviço | Chart | Templates | Status |
|---------|-------|-----------|--------|
| semantic-translation-engine | ✓ | 9/9 | ✅ Completo |
| specialist-business | ✓ | 8/8 | ✅ Completo |
| specialist-technical | ✓ | 8/8 | ✅ Completo |
| specialist-architecture | ✓ | 8/8 | ✅ Completo |
| specialist-behavior | ✓ | 8/8 | ✅ Completo |
| specialist-evolution | ✓ | 8/8 | ✅ Completo |
| guard-agents | ✓ | 11/11 | ✅ Completo |
| service-registry | ✓ | 9/9 | ✅ Completo |
| code-forge | ✓ | 8/9 (falta PDB) | ⚠️ Ticket 1.2 |
| sla-management-system | ✓ | 8/9 (falta NP) | ⚠️ Ticket 1.3 |
| memory-layer-api | ✓ | 8/9 (falta PDB) | ⚠️ Ticket 1.4 |
| explainability-api | ✓ | 4/9 (falta 4) | ⚠️ Ticket 1.1 |
| mcp-tool-catalog | ✓ | 8/9 (falta PDB) | ⚠️ Ticket 1.5 |

---

## Padrão de Referência

Usar `helm-charts/semantic-translation-engine` como padrão de referência para todos os templates a criar.

**Estrutura completa:**
```
helm-charts/{servico}/
├── Chart.yaml
├── values.yaml          # Valores base
├── values-k8s.yaml      # Valores para K8s dev
├── values-local.yaml    # Valores para minikube
├── charts/
│   └── common-templates/ (dependency)
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml                    # HorizontalPodAutoscaler
    ├── pdb.yaml                    # PodDisruptionBudget
    ├── networkpolicy.yaml          # NetworkPolicy
    ├── servicemonitor.yaml         # ServiceMonitor (Prometheus)
    ├── configmap.yaml
    ├── secret.yaml
    └── serviceaccount.yaml
```

---

*Tasks document criado por Claude Code - 2026-04-04*
