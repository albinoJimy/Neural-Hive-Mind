---
type: refactor
goal: "Auditoria crítica dos fluxos principais do NHM identificando top-10 riscos arquitecturais com mitigações priorizadas por impacto/esforço"
non_goals:
  - "Implementação das mitigações (apenas identificação e priorização)"
  - "Refactor de código (análise arquitectural, não de implementação)"
  - "Revisão de styling/convenções (riscos estruturais apenas)"
---

# Requirements

## R-B1: Consumidor do Relatório

- behavior: O relatório de auditoria deve ser orientado para ação pela equipa de engenharia/dev team implementar mitigações.

#### R-B1.1: Dev Team como Consumidor Primário
- given: O relatório de auditoria está completo com top-10 riscos identificados
- when: O relatório é entregue à equipa de engenharia
- then: A equipa deve ser capaz de entender e implementar as mitigações propostas sem necessidade de consultoria adicional

## R-B2: Trigger da Auditoria

- behavior: A auditoria é triggersada por revisão periódica de débito técnico, não por incidente específico.

#### R-B2.1: Revisão Periódica Obrigatória
- given: Débito técnico acumulado + performance bottlenecks + compliance/segurança pendentes
- when: Chega o momento de revisão periódica (agenda definida)
- then: Auditoria deve ser iniciada automaticamente ou manualmente com base em checklist estruturado

#### R-B2.2: Identificação de Riscos Conhecidos
- given: Research identificou riscos críticos conhecidos (SPOF Gateway, falta DLQ, race condition consensus, state duplication)
- when: A análise arquitectural é executada
- then: Todos os riscos conhecidos devem ser incluídos e priorizados na análise final

## R-B3: Fluxos no Escopo

- behavior: A auditoria deve cobrir os fluxos arquitectónicos críticos do Cognitive Pipeline excluindo frontend.

#### R-B3.1: Fluxos IN Scope - Cognitive Pipeline
- given: Arquitectura actual do NHM com 8 serviços core
- when: A análise de fluxos é realizada
- then: Os seguintes fluxos devem ser analisados: Cognitive Pipeline (Gateway→STE→Consensus→Orchestrator), Message flows (Kafka, DLQ, exactly-once semantics), Service communication (gRPC, timeouts, circuit breakers), Orchestration layer (Temporal, Saga pattern, state management)

#### R-B3.2: Fluxos OUT Scope - Frontend
- given: Frontend/Web interfaces existem no sistema
- when: A análise de fluxos é realizada
- then: Interfaces frontend devem ser explicitamente excluídas da auditoria (focus em backend/microservices)

## R-B4: Critério de Sucesso

- behavior: A auditoria é considerada sucesso quando baseline completo é estabelecido com top-10 riscos priorizados.

#### R-B4.1: Gap Analysis Completo
- given: Arquitectura actual e arquitectura desejada documentadas
- when: A análise de gaps é realizada
- then: Todos os gaps devem ser identificados e documentados com base na diferença entre estado actual e estado desejado

#### R-B4.2: Top-10 Riscos Priorizados
- given: Lista completa de riscos identificados
- when: A priorização multi-factor é aplicada
- then: Os top-10 riscos devem ser seleccionados e ordenados por: Probabilidade × Impacto, Custo/benefício da mitigação, Urgência (compliance/segurança primeiro)

## R-B5: Deliverable Final

- behavior: O relatório deve ser um documento markdown com deep dive por risco incluindo conceito e passos de implementação.

#### R-B5.1: Formato Markdown Estruturado
- given: Análise completa dos top-10 riscos identificada
- when: O relatório é compilado
- then: Cada risco deve ser documentado com: Título e descrição clara, Análise multi-factor (probabilidade, impacto, urgência, custo), Mitigação proposta com conceito técnico, Passos detalhados de implementação, Matriz impacto×esforço para priorização

#### R-B5.2: Matriz de Priorização Multi-Factor
- given: Top-10 riscos identificados e caracterizados
- when: A matriz de priorização é construída
- then: Cada risco deve ter score baseado em: Risco (probabilidade × impacto), Custo/benefício da mitigação, Urgência (compliance/security vs technical debt), Esforço de implementação (persona/dias)

## R-B6: Contexto de Riscos

- behavior: A análise deve considerar débito técnico, PII/privacy compliance e requisitos de segurança regulamentados.

#### R-B6.1: Compliance GDPR/LGPD
- given: Sistema processa PII básico (nomes, emails, identificadores) + business confidential
- when: Riscos de privacidade são analisados
- then: Os seguintes requisitos devem ser verificados: Right to erasure implementado, Data minimization aplicado, Purpose limitation documentado, Retention máxima de 2 anos (salvo obrigação legal), Residência de dados dentro UE/BR conforme aplicável, Encryption at-rest (AES-256) e in-transit (TLS 1.3) para PII

#### R-B6.2: Riscos Críticos Conhecidos
- given: Research identificou riscos críticos no sistema actual
- when: Análise de riscos estruturais é realizada
- then: Os seguintes riscos devem ser incluídos: SPOF Gateway (probabilidade ALTA, impacto ALTO), Falta DLQ (probabilidade MÉDIA, impacto ALTO), Race condition consensus (probabilidade BAIXA, impacto MÉDIO), State duplication Redis/MongoDB (probabilidade ALTA, impacto MÉDIO), Correlation ID inconsistency (probabilidade ALTA, impacto BAIXO)

#### R-B6.3: Assumptions de Escala e Performance
- given: Volume médio de ~5000 operações/dia (assumption do range 1000-10000)
- when: Riscos de escalabilidade são analisados
- then: Os seguintes SLAs best practices devem ser considerados: Latência p50 < 100ms, p95 < 500ms, p99 < 2s (endpoints internos), Throughput >100 ops/sec sustained capability, RTO <5 min (críticos), <30 min (não-críticos), RPO <1 min (execution tickets), <5 min (outros dados), Disponibilidade 99.5% target (~3.65h downtime/mês)

## R-I1: Jornada de Consumo do Relatório

- behavior: O relatório deve estruturar cada risco/mitigação como acção executável que se traduz directamente em tickets no sistema de tracking da equipa.

#### R-I1.1: Tradução de Riscos em Tickets
- given: Relatório de auditoria entregue com top-10 riscos identificados e mitigações propostas
- when: Tech lead revisa o relatório para priorizar implementação
- then: Cada risco/mitigação possui detalhes suficientes para criar ticket acção-oriented no sistema de tracking (JIRA/GitHub Issues)

## R-I2: Fluxo Ideal de Aprovação e Execução

- behavior: O relatório deve permitir que tech leads analisem, criem planos de mitigação e deleguem tasks para a equipa de desenvolvimento de forma estruturada.

#### R-I2.1: Análise pelo Tech Lead
- given: Relatório entregue com top-10 riscos priorizados por impacto×esforço
- when: Tech lead inicia revisão do relatório
- then: Tech lead consegue entender rapidamente (em <30 min) a criticidade e prioridade de cada risco através da matriz de priorização multi-factor

#### R-I2.2: Criação de Planos de Mitigação
- given: Tech lead revisou o relatório e identificou riscos prioritários
- when: Tech lead define roadmap de implementação
- then: Cada mitigação proposta possui "full detalhe" (conceito + passos implementação) suficiente para criar plano de acção sem necessidade de research adicional

#### R-I2.3: Delegação para Dev Team
- given: Planos de mitigação criados pelo tech lead
- when: Tasks são delegadas para desenvolvedores
- then: Cada task contém contexto claro do risco, impacto esperado da mitigação, e passos executáveis detalhados

## R-I3: Casos Edge de Qualidade do Relatório

- behavior: O relatório deve validar que cada risco identificado possui evidências concretas e cada mitigação proposta é específica e acção-oriented.

#### R-I3.1: Validação de Riscos Relevantes
- given: Análise arquitectural identificou potenciais riscos
- when: Risco é candidato ao top-10
- then: Risco possui evidência concreta (código, configuração, ou arquitectura documentada) que justifica a sua inclusão

#### R-I3.2: Especificidade de Mitigações
- given: Risco identificado no relatório
- when: Mitigação é proposta
- then: Mitigação é específica (não vaga) com passos de implementação claros (conceito + passos executáveis)

## R-I4: Versionamento e Evolução

- behavior: O relatório deve ser um living document versionado em git que rastreia o estado de implementação das mitigações ao longo do tempo.

#### R-I4.1: Versão Inicial
- given: Auditoria completa concluída
- when: Relatório é entregue pela primeira vez
- then: Versão v1.0 é criada com top-10 riscos identificados e status "pending" para todas as mitigações

#### R-I4.2: Atualização de Estado
- given: Relatório v1.0 entregue e mitigações em implementação
- when: Mitigação é completada (ticket fechado)
- then: Estado do risco é actualizado no relatório (de "pending" para "mitigated") com commit git documentando a mudança

#### R-I4.3: Rastreio de Mudanças
- given: Relatório sob evolve ao longo do tempo
- when: Mudanças de estado ocorrem (mitigações implementadas, novos riscos descobertos)
- then: Todas as mudanças são rastreadas em git com mensagens de commit claras

## R-I5: Feedback e Contestação

- behavior: O relatório é considerado deliverable final sem mecanismo formal de feedback inline — disputas ou discordâncias são tratadas via novo ciclo de auditoria se necessário.

#### R-I5.1: Relatório como Deliverable Final
- given: Relatório v1.0 entregue
- when: Equipa de engenharia revisa o relatório
- then: Relatório é tratado como baseline de análise sem mecanismo formal de contestação inline

#### R-I5.2: Ciclo de Re-auditoria
- given: Discordância significativa sobre risco ou mitigação proposta
- when: Equipa solicita revisão da análise
- then: Novo ciclo de auditoria é iniciado para endereçar a disputa (gerando nova versão do relatório se aplicável)

## R-I6: Controlo de Acesso e Confidencialidade

- behavior: O relatório deve ser acedido apenas pela equipa de engenharia devido a informação sensível sobre arquitectura e riscos de segurança.

#### R-I6.1: Access Control Interno
- given: Relatório armazenado no repositório
- when: Membro da equipa tenta acessar o relatório
- then: Apenas membros do dev team possuem permissões para ler o relatório (não é público)

#### R-I6.2: Proteção de Informação Sensível
- given: Relatório contém análise detalhada de riscos arquitecturais
- when: Informação sensível é documentada (segredos, PII, falhas segurança)
- then: Informação é protegida via access controls apropriados (repo privado, permissões granulares)

#### R-I6.3: Non-Publicação
- given: Relatório completo com top-10 riscos
- when: Consideração de partilha externa (blog, open source)
- then: Relatório NÃO é partilhado publicamente devido a info sensível sobre arquitectura/riscos

## R-T1: Cognitive Pipeline Architecture Analysis

- behavior: Analisar estrutura arquitectural do pipeline cognitivo (Gateway→STE→Consensus→Orchestrator) identificando SPOFs, acoplamento e dependências críticas.

#### R-T1.1: Identificação de SPOFs no Gateway
- given: Serviço gateway-intencoes como single entry point na porta 8000
- when: Analisando componentes e dependências do gateway
- then: Identificar todos os pontos de falha única (e.g., sem réplicas, sem fallback, dependência crítica única)

#### R-T1.2: Análise de acoplamento entre serviços
- given: 8 serviços core comunicando via Kafka (aiokafka) e gRPC
- when: Reviewando dependências e contratos entre serviços
- then: Mapear acoplamento forte/fraco entre serviços e identificar riscos de manutenibilidade

#### R-T1.3: Análise de dependências críticas externas
- given: Serviços dependem de Kafka, MongoDB, Redis, Neo4j, Temporal
- when: Analisando falhas de datastore externos
- then: Identificar serviços sem fallback adequado para falhas de dependências

## R-T2: Performance and Availability Targets

- behavior: Analisar desempenho e disponibilidade dos serviços vs best practices para médio volume (~5000 ops/dia), identificando gaps em SLAs.

#### R-T2.1: Análise de latência por serviço
- given: Best practices para p50 < 100ms, p95 < 500ms, p99 < 2s (endpoints internos)
- when: Medindo latências reais nos serviços core
- then: Identificar serviços fora dos SLAs e bottlenecks específicos

#### R-T2.2: Análise de throughput e escalabilidade
- given: Target >100 ops/sec sustained, 8 serviços core, ~50-100 pods total
- when: Analisando capacidade de throughput actual
- then: Identificar services sem HPA configurado (target 70% CPU, scale 2-10 replicas)

#### R-T2.3: Análise de disponibilidade e RTO/RPO
- given: Target 99.5% disponibilidade, RTO <5 min (críticos), RPO <1 min (execution tickets)
- when: Analisando redundância e recovery mechanisms
- then: Identificar serviços sem redundância ou backup adequado

## R-T3: State Management and Consistency

- behavior: Analisar consistência de estado entre Redis, MongoDB e Kafka, identificando duplicação, race conditions e padrões de sincronização.

#### R-T3.1: Análise de duplicação de estado
- given: Estado duplicado entre Redis (cache) e MongoDB (persistência)
- when: Reviewando padrões de state management em todos os serviços
- then: Identificar inconsistências de dados e risks de desincronização

#### R-T3.2: Análise de race conditions no Consensus Engine
- given: Consensus Engine usa cálculo de pesos hierárquicos e consolidação de decisões
- when: Analisando concorrência em operações de consenso
- then: Identificar race conditions na consolidação de decisões de especialistas

#### R-T3.3: Análise de consistência de mensagens Kafka
- given: Kafka configurado com exactly-once (enable.idempotence=true, acks=all)
- when: Verificando ordering e idempotência em consumers/producers
- then: Identificar serviços sem proper message ordering ou deduplication

## R-T4: Message Reliability and Error Handling

- behavior: Analisar confiabilidade de mensagens Kafka, DLQ handling, retries e circuit breakers em todos os serviços.

#### R-T4.1: Análise de DLQ handling
- given: Mensagens Kafka podem falhar permanentemente (e.g., schema invalid, biz logic error)
- when: Analisando dead letter queue patterns em todos os consumers
- then: Identificar serviços sem DLQ configurada ou sem processamento de DLQ

#### R-T4.2: Análise de retry logic e exponential backoff
- given: Serviços usam Kafka producers com retries automáticos
- when: Reviewing configurações de retry em consumers e producers
- then: Identificar serviços com retry infinito (risk de congestionamento) ou sem backoff

#### R-T4.3: Análise de circuit breakers
- given: Biblioteca neural_hive_resilience e self-healing-engine fornecem circuit breakers
- when: Verificando se circuit breakers estão configurados em todos os serviços
- then: Identificar serviços extern dependencies sem circuit breaker protection

## R-T5: PII/Privacy and GDPR/LGPD Compliance

- behavior: Analisar proteção de dados PII (nomes, emails, identificadores) em trânsito, em repouso e em logs, verificando compliance GDPR/LGPD.

#### R-T5.1: Análise de PII masking em logs
- given: Serviços fazem logging com structlog (observability)
- when: Analisando logs de todos os serviços para detectar PII em plaintext
- then: Identificar serviços sem PII masking/redaction em logs

#### R-T5.2: Análise de encryption at-rest e in-transit
- given: Target AES-256 at-rest, TLS 1.3 in-transit para PII
- when: Verificando configuração de encryption em MongoDB, Redis, Kafka
- then: Identificar datastores sem encryption activa ou com versões deprecated de TLS

#### R-T5.3: Análise de retention e right to erasure
- given: GDPR/LGPD requer retention máx 2 anos após fim relação (salvo obrigação legal)
- when: Analisando políticas de retention em execution tickets e outros dados PII
- then: Identificar dados sem política de retention explicity ou sem mecanismo de erasure

## R-T6: Kubernetes Infrastructure and Deployment

- behavior: Analisar configuração de recursos, limits, HPA e tolerâncias a falhas no cluster Kubernetes, identificando under-provisioning e over-provisioning.

#### R-T6.1: Análise de resource limits e requests
- given: 8 serviços core com ~50-100 pods total, limits 512Mi-2Gi RAM, 0.5-2 CPU
- when: Analisando configuração de resources em todos os deployments
- then: Identificar pods sem limits configurados (risk de resource starvation) ou com limits inadequados

#### R-T6.2: Análise de health checks e readiness probes
- given: Serviços FastAPI devem ter /health e /ready endpoints
- when: Verificando configuração de liveness/readiness probes em K8s
- then: Identificar serviços sem health checks ou com probes mal configurados

#### R-T6.3: Análise de tolerância a falhas de node
- given: Cluster Kubernetes pode ter node failures
- when: Analisando pod anti-affinity, pod disruption budgets e zone distribution
- then: Identificar serviços sem redundância跨 nodes ou sem PDB configurado

## R-T7: Library Version Conflicts and Compatibility

- behavior: Analisar conflitos de versões em dependências Python, FastAPI, Kafka drivers e gRPC, identificando incompatibilidades transitive e paths de resolução.

#### R-T7.1: Análise de version pinning consistency
- given: requirements-base.txt + pyproject.toml gerenciam dependências
- when: Analisando version constraints e transitive dependencies
- then: Identificar conflitos de versão (e.g., grpc version mismatch) ou pinning inconsistente

#### R-T7.2: Análise de gRPC version alignment
- given: gRPC version mismatch conhecido nos requirements
- when: Verificando versão de grpc em todos os serviços
- then: Identificar serviços desalinhados da versão target 1.71.2

#### R-T7.3: Análise de breaking changes e migration paths
- given: Serviços evoluem independentemente com versionamento semântico
- when: Analisando histórico de breaking changes em APIs e contratos
- then: Identificar mudanças breaking sem proper migration path ou sem backward compat

## R-T8: Security Hardening and Access Control

- behavior: Analisar posture de segurança incluindo authN/authZ, mTLS, secrets management, network policies e audit logging para identificar vulnerabilidades.

#### R-T8.1: Análise de mTLS enforcement entre serviços
- given: Istio service mesh com mTLS obrigatório entre serviços
- when: Verificando configuração de mTLS em todos os services
- then: Identificar serviços sem mTLS activado ou com policies permissive

#### R-T8.2: Análise de secrets management
- given: Serviços usam secrets (DB passwords, API keys, encryption keys)
- when: Analisando como secrets são injectados e rotacionados
- then: Identificar secrets hardcoded em configs ou sem rotation schedule

#### R-T8.3: Análise de network policies e ingress/egress
- given: Serviços comunicam via Kafka, gRPC, HTTP; podem ter tráfego externo
- when: Reviewing network policies em Kubernetes e firewall rules
- then: Identificar serviços sem restrição de egress ou com portas expostas desnecessariamente

## R-T9: Observability and Monitoring Coverage

- behavior: Analisar cobertura de logging (structlog), métricas (Prometheus), tracing (OpenTelemetry) e alerting para identificar gaps de visibilidade.

#### R-T9.1: Análise de correlation ID propagation
- given: Correlation ID inconsistente entre serviços é risco conhecido
- when: Analisando propagation de correlation ID em todos os serviços
- then: Identificar serviços sem inject/extract de correlation ID em logs distributed traces

#### R-T9.2: Análise de tracing coverage
- given: OpenTelemetry tracing disponível via neural_hive_observability
- when: Verificando se todos os serviços core têm spans configurados
- then: Identificar serviços sem tracing activo ou com spans missing em operations críticas

#### R-T9.3: Análise de métricas e alerting
- given: Prometheus + Grafana stack para monitorização
- when: Analisando métricas expostas e alertas configurados
- then: Identificar serviços sem métricas de business/technical KPIs ou sem alertas em SLOs

## R-T10: Timeout Configuration and Async Patterns

- behavior: Analisar configuração de timeouts em chamadas HTTP, gRPC, Kafka e Temporal, identificando timeouts missing, globais demais ou sem proper backpressure.

#### R-T10.1: Análise de timeout granularidade
- given: Timeout globais podem ser inadequados para operações específicas
- when: Analisando configuração de timeouts em todos os clients HTTP, gRPC, Kafka
- then: Identificar serviços com timeout global único ou sem timeout configurado

#### R-T10.2: Análise de async patterns e backpressure
- given: Serviços usam asyncio + aiokafka para operações async
- when: Verificando padrões de async/await e mecanismos de backpressure
- then: Identificar blocking calls em async context ou sem rate limiting/backpressure

#### R-T10.3: Análise de Temporal workflow timeouts
- given: Orchestrator-dynamic usa Temporal para Saga orchestration
- when: Analisando workflow timeouts e activity timeouts
- then: Identificar workflows sem timeout ou com timeout inadequado para long-running operations

## Pre-work

- [ ] Revisar documentação existente em /docs/ para conhecimentos de riscos
- [ ] Verificar access controls do repositório para garantir que relatório será interno-only

## Open Decisions

### OD-1: Volume real de operações
- context: O volume exacto de operações/dia não é conhecido; foi assumido ~5000 ops/dia como média do range "médio volume" (1000-10000)
- options: [Usar assumption, Medir valor real primeiro]
- impact: Se o valor real for significativamente diferente, os SLAs e análises de escala devem ser ajustados

### OD-2: SLAs formais
- context: Não há SLAs formalmente definidos; foram usados best practices da indústria
- options: [Usar best practices, Definir SLAs formais primeiro]
- impact: Se SLAs formais existirem ou forem definidos, devem substituir os best practices assumptions

### OD-3: Multi-region DR
- context: Foi assumido single-region deployment; DR strategy não está definida
- options: [Single-region, Multi-region]
- impact: Análise de DR deve ser ajustada se multi-region for requerido
