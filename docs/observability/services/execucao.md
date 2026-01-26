# Execução – Visão Detalhada

## Papel no Pipeline
- Converte tickets de orquestração em artefatos de software, ações operacionais ou tarefas edge, garantindo validação, deploy progressivo e feedback (documento-08, Seção 6.6; documento-06, Fluxo C).
- Abrange pipelines CI/CD (“Code Forge”), microserviços especializados, agentes edge e ferramentas de engenharia.

## Componentes Principais
- **Pipeline"Code Forge" (GitOps/CI/CD)**  
  - Cadeia automatizada que coordena lint, testes unitários/integração/contrato, SAST/DAST, build, geração de SBOM, assinatura de artefatos e deploy progressivo (documento-08, Seção 6.6; documento-05, Seção 3).  
  - Executado via ArgoCD/Tekton/GitLab CI com estágios parametrizáveis conforme tipo de ticket (build de microserviço, IaC, modelo ML, assets edge).  
  - Integra scripts em `scripts/deploy/` e `scripts/validation/` para padronizar validações (README.md; DEPLOYMENT_GUIDE.md).  
- **Microserviços e Funções Especializadas**  
  - Conjunto de serviços cloud-native e lambdas responsáveis pela lógica de negócio, expostos via APIs versionadas com contratos (documento-08, Seção 6.2).  
  - Implantados com sidecars Istio para mTLS, rate limiting e observabilidade, seguindo políticas de recursos e quotas.  
  - Suportam canary/blue-green, autoscaling e rollback automático com base em métricas e error budgets (documento-05, Seção 3.3).  
- **Agentes de Geração Neurais**  
  - Subconjunto de especialistas cognitivos dedicados à síntese automatizada de artefatos: código-fonte, testes, infraestrutura como código, políticas OPA, scripts operacionais ou documentação técnica (documento-08, Seção 6.2; documento-03, Seção 2.2).  
  - Composição híbrida de modelos generativos (LLMs finetunados e modelos estruturados) + heurísticas determinísticas + templates versionados para garantir consistência e aderência a padrões.  
  - Responsáveis por consultar catálogos de componentes reutilizáveis, padrões arquiteturais, policies e ontologias; produzem artefatos acompanhados de metadados (`intent_id`, `plan_id`, `justificativa`, `confidence`).  
  - Executam avaliação preliminar (linting, unit tests rápidos) antes de subir artefatos para repositórios Git, minimizando falhas adiante.  
  - Operam sob supervisão humana configurável, com thresholds de confiança e gatilhos de revisão manual para domínios críticos.  
  - Publishes outputs em branches ou MR automáticos, acionando pipelines `Code Forge`; logs e decisões são registrados para auditoria e aprendizado contínuo.  
- **Ferramentas de Engenharia Integradas**  
  - Serviços como SonarQube, Snyk, Trivy, Checkov, ZAP e linters customizados incorporados ao pipeline para reforçar qualidade e segurança (VERIFICACOES_IMPLEMENTADAS.md, itens 2–3; documento-05, Seção 3.2).  
  - Publicam relatórios em dashboards, alimentam métricas de qualidade e definem gates mínimos para promoção.  
- **Agentes Edge**  
  - Execução distribuída offline-first que recebe pacotes assinados, armazena-os localmente (storage criptografado) e sincroniza resultados quando conectividade retorna (documento-02, Seção 3; documento-08, Seção 6.2).  
  - Mantêm atestação remota, políticas de atualização segura e fallback para comandos críticos.  
- **Repositórios de Artefatos & Supply Chain**  
  - AWS ECR como registry padrão com scanning automático, policies de lifecycle e replicação cross-region (ADR-0003).  
  - Armazena contêineres, charts, pacotes edge e modelos com metadados de provenance (`intent_id`, `plan_id`, `commit_hash`).  
  - Conecta-se a Política OPA para bloquear deploy de imagens não assinadas e enforce de digest.  
- **Orquestrador de Deploy Progressivo**  
  - Controla estratégias blue/green, canary, progressive delivery e feature flags, analisando métricas em tempo real para aprovar ou reverter releases (documento-05, Seção 3.3).  
  - Coordena rollbacks, atualizações de configuração e comunicação com Orquestração para sinalizar status final.  
- **Backplane de Telemetria & Feedback**  
  - Camada que coleta métricas de pipelines, deploys e runtime (lead time, taxa de falha, cobertura de testes) via OTel, Prometheus e Loki, retroalimentando Orquestração e Autocura.  
  - Calibra políticas de erro, thresholds de rollback e insights para experimentação.  

## Execution Ticket Service (gRPC + PostgreSQL + MongoDB)

Servico dedicado para persistencia e gerenciamento de execution tickets, expondo API gRPC para orchestrator e worker agents. Mantem dual-store (PostgreSQL para queries transacionais, MongoDB para audit trail).

### Responsabilidades
- Persistir tickets gerados pelo orchestrator (C2)
- Fornecer queries de tickets por plan_id, status, priority (C3, C5)
- Atualizar status de tickets durante execucao (C5)
- Gerar tokens JWT para autorizacao de workers

### Metricas Especificas
- `tickets_persisted_total`: Total de tickets persistidos
- `grpc_server_handled_total{grpc_method="GetTicket"}`: Chamadas gRPC por metodo
- `grpc_server_handling_seconds{grpc_method="UpdateTicketStatus"}`: Latencia por metodo
- `postgres_queries_total`: Queries PostgreSQL
- `mongodb_operations_total`: Operacoes MongoDB

### Protocolos
- **gRPC (porta 50052)**: Protocolo primario para orchestrator-dynamic e worker-agents
- **HTTP (porta 8000)**: Health checks e REST API secundaria
- **HTTP (porta 9090)**: Metricas Prometheus

## Arquitetura e Tecnologias
- Deployment automatizado via Terraform/Helm, ArgoCD/Tekton e GitOps.
- Sidecars Istio asseguram mTLS e observabilidade; OTele instrumentation fornece métricas e traces.
- Edge nodes usam MQTT/gRPC seguros, storage local criptografado e atestação remota.

## Integração com IA (ML/LLM)
- Agentes neurais podem gerar código, testes e IaC usando modelos generativos combinados com templates e heurísticas determinísticas (documento-08, Seção 6.2; documento-03, Seção 2.2).
- Especialistas de evolução avaliam melhorias e ativam experimentos controlados (documento-05, Seção 2.5).
- Monitoramento de desempenho alimenta aprendizado contínuo para ajustar pipelines.

## Integrações Operacionais
- Comunicação com Strimzi/Kafka para eventos de build/deploy; integration com observabilidade para feedback pós-deploy.
- Políticas OPA reforçam compliance (imagens assinadas, restrições de recursos, catálogo de APIs/dados).
- Automação com scripts `scripts/deploy/` e `scripts/validation/` garante consistência (README.md; DEPLOYMENT_GUIDE.md).

## Escalabilidade e Resiliência
- HPA para microserviços, escalonamento de runners CI/CD e execução paralela em clusters secundários.
- Estratégias blue/green, canary, progressive delivery com rollback automático (documento-05, Seção 3.3).
- Edge com buffers locais e failback planejado.

## Segurança
- Supply chain seguro: scanning automático, política de imagens assinadas, ACLs mínimas em Kafka (ADR-0003; VERIFICACOES_IMPLEMENTADAS.md, itens 3–4).
- RBAC por namespace, quotas de recursos, compliance auditável.
- Logs de deploy assinados, telemetria correlacionada, testes adversariais periódicos.

## Observabilidade
- Métricas: lead time intenção→deploy, taxa de sucesso de deploys, cobertura de testes, violações SAST/DAST.
- Tracing correlaciona `intent_id` → `plan_id` → `ticket_id` → `deploy_id`.
- Alertas: queda de sucesso <98%, aumento de incidentes pós-deploy, backlog de pipelines.

## Riscos e Ações
- **Debt técnico crescente**: reforçar quality gates e revisões periódicas.
- **Falha em edge nodes**: expandir monitoração e automatizar failover.
- **Dependência de pipelines complexos**: documentar runbooks e realizar game days.

## Próximos Passos Sugeridos
1. Completar implementação de assinatura Sigstore e enforcement OPA correspondente.
2. Criar dashboards de tempo de ciclo intenção→valor com correlação de erros.
3. Rodar exercícios de caos focados em falhas em cadeia (CI/CD + deploy).
