# Requisitos de Interação — nhm-fluxos-auditoria-riscos

axis: interaction
count: 6
spec: nhm-fluxos-auditoria-riscos
status: complete

## Visão Geral

Este documento especifica os requisitos de interação para a auditoria de riscos arquitecturais do Neural-Hive-Mind, focando na experiência da equipa de engenharia como consumidora do relatório de auditoria.

**Contexto do Projecto:** Dev-tool que gera relatório de análise arquitectural
**Consumidor Principal:** Engenharia/Dev team
**Deliverable:** Relatório markdown com top-10 riscos + mitigações priorizadas

---

## R-I1: Jornada de Consumo do Relatório

**Comportamento:** O relatório deve estruturar cada risco/mitigação como acção executável que se traduz directamente em tickets no sistema de tracking da equipa.

- #### R-I1.1: Tradução de Riscos em Tickets
  - **given:** Relatório de auditoria entregue com top-10 riscos identificados e mitigações propostas
  - **when:** Tech lead revisa o relatório para priorizar implementação
  - **then:** Cada risco/mitigação possui detalhes suficientes para criar ticket acção-oriented no sistema de tracking (JIRA/GitHub Issues)

**Fonte:** Q&A JOURNEY — "Como é que a equipa de engenharia vai consumir o relatório de auditoria? → Ticket system — Cada risco/mitigação deve criar ticket no sistema de tracking."

---

## R-I2: Fluxo Ideal de Aprovação e Execução

**Comportamento:** O relatório deve permitir que tech leads analisem, criem planos de mitigação e deleguem tasks para a equipa de desenvolvimento de forma estruturada.

- #### R-I2.1: Análise pelo Tech Lead
  - **given:** Relatório entregue com top-10 riscos priorizados por impacto×esforço
  - **when:** Tech lead inicia revisão do relatório
  - **then:** Tech lead consegue entender rapidamente (em <30 min) a criticidade e prioridade de cada risco através da matriz de priorização multi-factor

- #### R-I2.2: Criação de Planos de Mitigação
  - **given:** Tech lead revisou o relatório e identificou riscos prioritários
  - **when:** Tech lead define roadmap de implementação
  - **then:** Cada mitigação proposta possui "full detalhe" (conceito + passos implementação) suficiente para criar plano de acção sem necessidade de research adicional

- #### R-I2.3: Delegação para Dev Team
  - **given:** Planos de mitigação criados pelo tech lead
  - **when:** Tasks são delegadas para desenvolvedores
  - **then:** Cada task contém contexto claro do risco, impacto esperado da mitigação, e passos executáveis detalhados

**Fonte:** Q&A HAPPY — "Qual é o fluxo ideal (happy path) após entrega do relatório? → Lead-driven: Tech lead analisa relatório → cria planos → delega tasks para dev team."

---

## R-I3: Casos Edge de Qualidade do Relatório

**Comportamento:** O relatório deve validar que cada risco identificado possui evidências concretas e cada mitigação proposta é específica e acção-oriented.

- #### R-I3.1: Validação de Riscos Relevantes
  - **given:** Análise arquitectural identificou potenciais riscos
  - **when:** Risco é candidato ao top-10
  - **then:** Risco possui evidência concreta (código, configuração, ou arquitectura documentada) que justifica a sua inclusão

- #### R-I3.2: Especificidade de Mitigações
  - **given:** Risco identificado no relatório
  - **when:** Mitigação é proposta
  - **then:** Mitigação é específica (não vaga) com passos de implementação claros (conceito + passos executáveis)

**Fonte:** Q&A EDGE — "Quais edge cases devem ser considerados no relatório? → Nenhum selecionado — Casos edge standard (riscos insuficientes, mitigações vagas) são tratados na própria análise."

---

## R-I4: Versionamento e Evolução do Relatório

**Comportamento:** O relatório deve ser um living document versionado em git que rastreia o estado de implementação das mitigações ao longo do tempo.

- #### R-I4.1: Versão Inicial
  - **given:** Auditoria completa concluída
  - **when:** Relatório é entregue pela primeira vez
  - **then:** Versão v1.0 é criada com top-10 riscos identificados e status "pending" para todas as mitigações

- #### R-I4.2: Atualização de Estado
  - **given:** Relatório v1.0 entregue e mitigações em implementação
  - **when:** Mitigação é completada (ticket fechado)
  - **then:** Estado do risco é actualizado no relatório (de "pending" para "mitigated") com commit git documentando a mudança

- #### R-I4.3: Rastreio de Mudanças
  - **given:** Relatório sob evolve ao longo do tempo
  - **when:** Mudanças de estado ocorrem (mitigações implementadas, novos riscos descobertos)
  - **then:** Todas as mudanças são rastreadas em git com mensagens de commit claras

**Fonte:** Q&A STATE — "Como o relatório deve ser versionado/atualizado? → Versionado (living document) — Versão única no momento da entrega (v1.0), Atualizado à medida que mitigações são implementadas, Mudanças de estado tracked em git."

---

## R-I5: Feedback e Contestação de Análise

**Comportamento:** O relatório é considerado deliverable final sem mecanismo formal de feedback inline — disputas ou discordâncias são tratadas via novo ciclo de auditoria se necessário.

- #### R-I5.1: Relatório como Deliverable Final
  - **given:** Relatório v1.0 entregue
  - **when:** Equipa de engenharia revisa o relatório
  - **then:** Relatório é tratado como baseline de análise sem mecanismo formal de contestação inline

- #### R-I5.2: Ciclo de Re-auditoria (Opcional)
  - **given:** Discordância significativa sobre risco ou mitigação proposta
  - **when:** Equipa solicita revisão da análise
  - **then:** Novo ciclo de auditoria é iniciado para endereçar a disputa (gerando nova versão do relatório se aplicável)

**Fonte:** Q&A FEEDBACK — "Como a equipa dá feedback ou contesta a análise? → Nenhum — Relatório é deliverable final; disputas são tratadas via novo ciclo de auditoria se necessário."

---

## R-I6: Controlo de Acesso e Confidencialidade

**Comportamento:** O relatório deve ser acedido apenas pela equipa de engenharia devido a informação sensível sobre arquitectura e riscos de segurança.

- #### R-I6.1: Access Control Interno
  - **given:** Relatório armazenado no repositório
  - **when:** Membro da equipa tenta acessar o relatório
  - **then:** Apenas membros do dev team possuem permissões para ler o relatório (não é público)

- #### R-I6.2: Proteção de Informação Sensível
  - **given:** Relatório contém análise detalhada de riscos arquitecturais
  - **when:** Informação sensível é documentada (segredos, PII, falhas segurança)
  - **then:** Informação é protegida via access controls apropriados (repo privado, permissões granulares)

- #### R-I6.3: Non-Publicação
  - **given:** Relatório completo com top-10 riscos
  - **when:** Consideração de partilha externa (blog, open source)
  - **then:** Relatório NÃO é partilhado publicamente devido a info sensível sobre arquitectura/riscos

**Fonte:** Q&A ACCESS — "Quem tem acesso ao relatório? → Interno (dev team apenas) — Access control: dev team, Não público — contém info sensível sobre arquitectura/riscos."

---

## Mapeamento de Fontes

| Requisito | Fonte Q&A | Linhas |
|-----------|-----------|--------|
| R-I1 | JOURNEY | 246-250 |
| R-I2 | HAPPY | 254-258 |
| R-I3 | EDGE | 262-266 |
| R-I4 | STATE | 270-276 |
| R-I5 | FEEDBACK | 280-284 |
| R-I6 | ACCESS | 288-293 |

---

## Notas de Implementação

**Profundidade de Análise (depth_calibration):**
- **ACCESS:** deep — acesso controlado é crítico devido a informação sensível
- **JOURNEY/HAPPY/EDGE/STATE/FEEDBACK:** standard — fluxo standard de consumo de relatório técnico

**Confidence Levels:**
- R-I1.1: high — fluxo de ticket system explicitamente definido
- R-I2.1-R-I2.3: high — happy path claro (tech lead → planos → delegação)
- R-I3.1-R-I3.2: medium — edge cases tratados na própria análise (validação standard)
- R-I4.1-R-I4.3: high — versionamento em git explicitamente especificado
- R-I5.1-R-I5.2: high — mecanismo de feedback é "nenhum" (deliverable final)
- R-I6.1-R-I6.3: high — acesso interno é explicitamente requerido
