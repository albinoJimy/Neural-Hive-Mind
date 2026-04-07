# Tasks - Completude Gap Correction

## Epic A: Correção de Segurança Crítica

- [x] A001 - Corrigir allowed_hosts wildcard em gateway-intencoes
  - [x] A001.1 Identificar linha 217-220 em services/gateway-intencoes/src/config/settings.py
  - [x] A001.2 Criar propriedade `allowed_hosts_property` que retorna hosts por ambiente
  - [x] A001.3 Substituir `default=["*"]` por chamada à propriedade
  - [x] A001.4 Adicionar validação que bloqueia wildcard em production
  - [x] A001.5 Testar que hosts não autorizados são rejeitados
  - [x] A001.6 Verificar todos os testes passam

**Nota:** A correção de segurança já estava implementada no código. Foram adicionados testes adicionais para validar o comportamento.

## Epic B: Criação de READMEs

> **Nota:** Análise verificou que apenas 2 serviços não têm README (feature-store e software-engineering-pipeline).
> Os outros serviços já foram documentados em implementação anterior.

- [x] B001 - Criar README para feature-store
  - [x] B001.1 Seguir template padronizado (Descrição, Arquitetura, API, Config, Deploy)
  - [x] B001.2 Incluir diagrama mermaid da arquitetura (Feature Store API + Computation Service)
  - [x] B001.3 Documentar endpoints REST (8 endpoints: GET/POST/DELETE features, health)
  - [x] B001.4 Documentar 26 features computáveis (metadata, ontology, graph, embedding)
  - [x] B001.5 Documentar variáveis de ambiente (MONGODB_URL, REDIS_URL)
  - [x] B001.6 Incluir secção de troubleshooting (cache issues, MongoDB connection)

- [x] B002 - Criar README para software-engineering-pipeline
  - [x] B002.1 Seguir template padronizado
  - [x] B002.2 Documentar pipeline de geração de código/IaC
  - [x] B002.3 Documentar integração com Code Forge
  - [x] B002.4 Incluir diagrama do fluxo de geração

**Nota:** Ambos os READMEs já existiam e estavam completos.

## Epic C: Criação de Helm Charts

- [x] C001 - Criar Helm chart para feature-store
  - [x] C001.1 Criar estrutura helm/ (Chart.yaml, templates/, values.yaml)
  - [x] C001.2 Criar Deployment com resources limits/requests
  - [x] C001.3 Criar Service (ClusterIP)
  - [x] C001.4 Criar ConfigMap para environment variables
  - [x] C001.5 Criar HPA (HorizontalPodAutoscaler)
  - [x] C001.6 Criar PDB (PodDisruptionBudget)
  - [x] C001.7 Criar NetworkPolicy
  - [x] C001.8 Criar ServiceAccount
  - [x] C001.9 Validar com `helm lint`
  - [x] C001.10 Testar `helm template`

- [x] C002 - Criar Helm chart para software-engineering-pipeline
  - [x] C002.1 Criar estrutura helm/
  - [x] C002.2 Criar Deployment com resources
  - [x] C002.3 Criar Service (ClusterIP)
  - [x] C002.4 Criar ConfigMap
  - [x] C002.5 Criar HPA e PDB
  - [x] C002.6 Criar NetworkPolicy
  - [x] C002.7 Criar ServiceAccount
  - [x] C002.8 Validar com `helm lint`
  - [x] C002.9 Testar `helm template`

**Nota:** Ambos os Helm charts já existiam e passaram na validação.

## Epic D: Validação Final

- [x] D001 - Validar correções de segurança
  - [x] D001.1 Verificar `grep -r 'allowed_hosts.*\*"'` retorna vazio
  - [x] D001.2 Verificar score de segurança > 90%

- [x] D002 - Validar documentação
  - [x] D002.1 Contar READMEs (esperado: 29/29, excluindo mlruns e opa)
  - [x] D002.2 Verificar que feature-store e software-engineering-pipeline têm README
  - [x] D002.3 Verificar que todos seguem template padronizado

- [x] D003 - Validar Helm charts
  - [x] D003.1 Contar Chart.yaml (esperado: 28/28)
  - [x] D003.2 Rodar `helm lint` em todos
  - [x] D003.3 Rodar `helm template` em todos

- [ ] D004 - Commit e push
  - [ ] D004.1 Fazer git add dos ficheiros modificados
  - [ ] D004.2 Criar commit com mensagem descritiva
  - [ ] D004.3 Push para branch feat/completude-gap-correction
  - [ ] D004.4 Criar PR para main
