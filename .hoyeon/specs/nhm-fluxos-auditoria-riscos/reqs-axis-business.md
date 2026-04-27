# Business Requirements - Neural Hive Mind Auditoria

axis: business
count: 6
spec: nhm-fluxos-auditoria-riscos
status: complete

## R-B1: Consumidor do Relatório

**behavior:** O relatório de auditoria deve ser orientado para ação pela equipa de engenharia/dev team implementar mitigações.

**source:** Q: Quem é o consumidor principal do relatório de auditoria?

#### R-B1.1: Dev Team como Consumidor Primário
- **given:** O relatório de auditoria está completo com top-10 riscos identificados
- **when:** O relatório é entregue à equipa de engenharia
- **then:** A equipa deve ser capaz de entender e implementar as mitigações propostas sem necessidade de consultoria adicional

---

## R-B2: Trigger da Auditoria

**behavior:** A auditoria é triggersada por revisão periódica de débito técnico, não por incidente específico.

**source:** Q: Por que esta auditoria é necessária agora?

#### R-B2.1: Revisão Periódica Obrigatória
- **given:** Débito técnico acumulado + performance bottlenecks + compliance/segurança pendentes
- **when:** Chega o momento de revisão periódica (agenda definida)
- **then:** Auditoria deve ser iniciada automaticamente ou manualmente com base em checklist estruturado

#### R-B2.2: Identificação de Riscos Conhecidos
- **given:** Research identificou riscos críticos conhecidos (SPOF Gateway, falta DLQ, race condition consensus, state duplication)
- **when:** A análise arquitectural é executada
- **then:** Todos os riscos conhecidos devem ser incluídos e priorizados na análise final

---

## R-B3: Fluxos no Escopo

**behavior:** A auditoria deve cobrir os fluxos arquitectónicos críticos do Cognitive Pipeline excluindo frontend.

**source:** Q: Quais fluxos devem ser incluídos na auditoria?

#### R-B3.1: Fluxos IN Scope - Cognitive Pipeline
- **given:** Arquitectura actual do NHM com 8 serviços core
- **when:** A análise de fluxos é realizada
- **then:** Os seguintes fluxos devem ser analisados:
  - Cognitive Pipeline (Gateway→STE→Consensus→Orchestrator)
  - Message flows (Kafka, DLQ, exactly-once semantics)
  - Service communication (gRPC, timeouts, circuit breakers)
  - Orchestration layer (Temporal, Saga pattern, state management)

#### R-B3.2: Fluxos OUT Scope - Frontend
- **given:** Frontend/Web interfaces existem no sistema
- **when:** A análise de fluxos é realizada
- **then:** Interfaces frontend devem ser explicitamente excluídas da auditoria (focus em backend/microservices)

---

## R-B4: Critério de Sucesso

**behavior:** A auditoria é considerada sucesso quando baseline completo é estabelecido com top-10 riscos priorizados.

**source:** Q: Como definimos que a auditoria foi um sucesso?

#### R-B4.1: Gap Analysis Completo
- **given:** Arquitectura actual e arquitectura desejada documentadas
- **when:** A análise de gaps é realizada
- **then:** Todos os gaps devem ser identificados e documentados com base na diferença entre estado actual e estado desejado

#### R-B4.2: Top-10 Riscos Priorizados
- **given:** Lista completa de riscos identificados
- **when:** A priorização multi-factor é aplicada
- **then:** Os top-10 riscos devem ser seleccionados e ordenados por:
  - Probabilidade × Impacto
  - Custo/benefício da mitigação
  - Urgência (compliance/segurança primeiro)

---

## R-B5: Deliverable Final

**behavior:** O relatório deve ser um documento markdown com deep dive por risco incluindo conceito e passos de implementação.

**source:** Q: Qual é o deliverable final?

#### R-B5.1: Formato Markdown Estruturado
- **given:** Análise completa dos top-10 riscos identificada
- **when:** O relatório é compilado
- **then:** Cada risco deve ser documentado com:
  - Título e descrição clara
  - Análise multi-factor (probabilidade, impacto, urgência, custo)
  - Mitigação proposta com conceito técnico
  - Passos detalhados de implementação
  - Matriz impacto×esforço para priorização

#### R-B5.2: Matriz de Priorização Multi-Factor
- **given:** Top-10 riscos identificados e caracterizados
- **when:** A matriz de priorização é construída
- **then:** Cada risco deve ter score baseado em:
  - Risco (probabilidade × impacto)
  - Custo/benefício da mitigação
  - Urgência (compliance/security vs technical debt)
  - Esforço de implementação (persona/dias)

---

## R-B6: Contexto de Riscos

**behavior:** A análise deve considerar débito técnico, PII/privacy compliance e requisitos de segurança regulamentados.

**source:** Q: Que contexto de riscos já conhecidos devemos considerar?

#### R-B6.1: Compliance GDPR/LGPD
- **given:** Sistema processa PII básico (nomes, emails, identificadores) + business confidential
- **when:** Riscos de privacidade são analisados
- **then:** Os seguintes requisitos devem ser verificados:
  - Right to erasure implementado
  - Data minimization aplicado
  - Purpose limitation documentado
  - Retention máxima de 2 anos (salvo obrigação legal)
  - Residência de dados dentro UE/BR conforme aplicável
  - Encryption at-rest (AES-256) e in-transit (TLS 1.3) para PII

#### R-B6.2: Riscos Críticos Conhecidos
- **given:** Research identificou riscos críticos no sistema actual
- **when:** Análise de riscos estruturais é realizada
- **then:** Os seguintes riscos devem ser incluídos:
  - **SPOF Gateway**: probabilidade ALTA, impacto ALTO (perda completa serviço)
  - **Falta DLQ**: probabilidade MÉDIA, impacto ALTO (perda dados)
  - **Race condition consensus**: probabilidade BAIXA, impacto MÉDIO (inconsistência decisões)
  - **State duplication Redis/MongoDB**: probabilidade ALTA, impacto MÉDIO (manutenibilidade)
  - **Correlation ID inconsistency**: probabilidade ALTA, impacto BAIXO (observabilidade)

#### R-B6.3: Assumptions de Escala e Performance
- **given:** Volume médio de ~5000 operações/dia (assumption do range 1000-10000)
- **when:** Riscos de escalabilidade são analisados
- **then:** Os seguintes SLAs best practices devem ser considerados:
  - Latência: p50 < 100ms, p95 < 500ms, p99 < 2s (endpoints internos)
  - Throughput: >100 ops/sec sustained capability
  - RTO: <5 min (críticos), <30 min (não-críticos)
  - RPO: <1 min (execution tickets), <5 min (outros dados)
  - Disponibilidade: 99.5% target (~3.65h downtime/mês)
