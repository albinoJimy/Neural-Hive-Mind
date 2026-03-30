# Tasks - Completude Gap Correction

## Epic A: Correção de Segurança Crítica

- [ ] A001 - Corrigir allowed_hosts wildcard em gateway-intencoes
  - [ ] A001.1 Identificar linha 217-220 em services/gateway-intencoes/src/config/settings.py
  - [ ] A001.2 Criar propriedade `allowed_hosts_property` que retorna hosts por ambiente
  - [ ] A001.3 Substituir `default=["*"]` por chamada à propriedade
  - [ ] A001.4 Adicionar validação que bloqueia wildcard em production
  - [ ] A001.5 Testar que hosts não autorizados são rejeitados
  - [ ] A001.6 Verificar todos os testes passam

## Epic B: Criação de READMEs

> **Nota:** Análise verificou que apenas 2 serviços não têm README (feature-store e software-engineering-pipeline).
> Os outros serviços já foram documentados em implementação anterior.

- [ ] B001 - Criar README para feature-store
  - [ ] B001.1 Seguir template padronizado (Descrição, Arquitetura, API, Config, Deploy)
  - [ ] B001.2 Incluir diagrama mermaid da arquitetura (Feature Store API + Computation Service)
  - [ ] B001.3 Documentar endpoints REST (8 endpoints: GET/POST/DELETE features, health)
  - [ ] B001.4 Documentar 26 features computáveis (metadata, ontology, graph, embedding)
  - [ ] B001.5 Documentar variáveis de ambiente (MONGODB_URL, REDIS_URL)
  - [ ] B001.6 Incluir secção de troubleshooting (cache issues, MongoDB connection)

- [ ] B002 - Criar README para software-engineering-pipeline
  - [ ] B002.1 Seguir template padronizado
  - [ ] B002.2 Documentar pipeline de geração de código/IaC
  - [ ] B002.3 Documentar integração com Code Forge
  - [ ] B002.4 Incluir diagrama do fluxo de geração

## Epic C: Criação de Helm Charts

- [ ] C001 - Criar Helm chart para feature-store
  - [ ] C001.1 Criar estrutura helm/ (Chart.yaml, templates/, values.yaml)
  - [ ] C001.2 Criar Deployment com resources limits/requests
  - [ ] C001.3 Criar Service (ClusterIP)
  - [ ] C001.4 Criar ConfigMap para environment variables
  - [ ] C001.5 Criar HPA (HorizontalPodAutoscaler)
  - [ ] C001.6 Criar PDB (PodDisruptionBudget)
  - [ ] C001.7 Criar NetworkPolicy
  - [ ] C001.8 Criar ServiceAccount
  - [ ] C001.9 Validar com `helm lint`
  - [ ] C001.10 Testar `helm template`

- [ ] C002 - Criar Helm chart para software-engineering-pipeline
  - [ ] C002.1 Criar estrutura helm/
  - [ ] C002.2 Criar Deployment com resources
  - [ ] C002.3 Criar Service (ClusterIP)
  - [ ] C002.4 Criar ConfigMap
  - [ ] C002.5 Criar HPA e PDB
  - [ ] C002.6 Criar NetworkPolicy
  - [ ] C002.7 Criar ServiceAccount
  - [ ] C002.8 Validar com `helm lint`
  - [ ] C002.9 Testar `helm template`

## Epic D: Validação Final

- [ ] D001 - Validar correções de segurança
  - [ ] D001.1 Verificar `grep -r 'allowed_hosts.*\*"'` retorna vazio
  - [ ] D001.2 Verificar score de segurança > 90%

- [ ] D002 - Validar documentação
  - [ ] D002.1 Contar READMEs (esperado: 29/29, excluindo mlruns e opa)
  - [ ] D002.2 Verificar que feature-store e software-engineering-pipeline têm README
  - [ ] D002.3 Verificar que todos seguem template padronizado

- [ ] D003 - Validar Helm charts
  - [ ] D003.1 Contar Chart.yaml (esperado: 28/28)
  - [ ] D003.2 Rodar `helm lint` em todos
  - [ ] D003.3 Rodar `helm template` em todos

- [ ] D004 - Commit e push
  - [ ] D004.1 Fazer git add dos ficheiros modificados
  - [ ] D004.2 Criar commit com mensagem descritiva
  - [ ] D004.3 Push para branch feat/completude-gap-correction
  - [ ] D004.4 Criar PR para main
