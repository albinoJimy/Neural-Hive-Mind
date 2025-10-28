# Catálogo de Agentes do Neural Hive-Mind

## Visão Geral
- Consolida a governança sobre os agentes que compõem o ecossistema Neural Hive-Mind e como se relacionam com pipelines de intenção→valor.
- Aprofundamentos técnicos e operacionais estão organizados por camada funcional nos documentos listados abaixo.
- Este índice mantém visão transversal (métricas, fluxos, dependências) para facilitar navegação e governança integrada.
- **Nota sobre a natureza dos agentes**: cada grupo é projetado como componente híbrido — combina modelos de IA (LLMs, heurísticas swarm, modelos preditivos, embeddings) com automações determinísticas, regras simbólicas e integrações DevSecOps (workflows Temporal/Argo, OPA, observabilidade). Portanto, não se trata apenas de agentes baseados em prompt; há sempre acoplamento com pipelines, políticas e ferramentas operacionais para garantir decisões auditáveis.

## Documentos por Camada Funcional
- [Camada Estratégica e Coordenação](./agentes/camada-estrategica.md) — Agente Rainha, Analistas, Otimizadores.
- [Camada de Exploração e Aprendizado](./agentes/camada-exploracao.md) — Exploradores, Mecanismo de Feromônios Digitais.
- [Camada Cognitiva](./agentes/camada-cognitiva.md) — Especialistas Neurais, Especialistas Metacognitivos (roadmap).
- [Camada Executiva](./agentes/camada-executiva.md) — Executores, Agentes de Geração Neurais, Agentes Edge.
- [Camada de Resiliência e Segurança](./agentes/camada-resiliencia.md) — Guardiões, Motor de Autocura e Runbooks Automatizados.

## Visão Resumida dos Agentes

| Camada | Agente | Papel-chave |
| --- | --- | --- |
| Estratégica | Agente Rainha | Coordenação estratégica, priorização e guarda de guardrails éticos |
| Estratégica | Analistas | Conversão de dados multi-fonte em insights acionáveis |
| Estratégica | Otimizadores | Melhoria contínua de pesos, SLOs e políticas |
| Exploração | Exploradores | Descoberta de sinais emergentes em core/edge |
| Exploração | Feromônios Digitais | Memória viva de trilhas, sucessos e alertas |
| Cognitiva | Especialistas Neurais | Avaliação multidomínio com consenso auditável |
| Cognitiva | Especialistas Metacognitivos (roadmap) | Ajuste adaptativo do consenso e detecção de drift |
| Executiva | Executores | Orquestração de tickets e QoS |
| Executiva | Agentes de Geração | Síntese automática de código/IaC/políticas |
| Executiva | Agentes Edge | Execução distribuída offline-first |
| Resiliência | Guardiões | Detecção de ameaças e enforcement |
| Resiliência | Motor de Autocura | Execução de playbooks e restauração de SLAs |

## Métricas e Telemetria por Agente

| Agente | Métricas recomendadas | Telemetria/traces | Alertas orientativos |
| --- | --- | --- | --- |
| Agente Rainha | % de replanejamentos, cadência de decisões, decisão vs execução | Spans `intent_id/plan_id` com `decision_scope` | Divergência decisão vs execução > 8%; backlog estratégico saturado |
| Exploradores | Taxa de descobertas validadas, cobertura de domínios, latência feromônios | Logs `exploration_domain`, traces edge→core | Volume de feromônios inválidos > threshold; ausência de sinais recentes |
| Analistas | Precisão vs decisões finais, tempo de resposta, ratio sinal/insight | Spans `analysis_id`, dashboards Grafana multi-fonte | Insights não consumidos > X h; discrepância previsões vs resultados |
| Otimizadores | Impacto em lead time, redução de retrabalho, effectiveness pós-ajuste | Eventos `optimization.applied`, métricas de experimentos | Ajuste com regressão de KPI; múltiplas mudanças simultâneas |
| Guardiões | MTTD, % incidentes autocorrigidos, falsos positivos | Logs `incident_id`, traces Autocura, Alertmanager | Falhas repetidas no mesmo playbook; incidentes não mitigados |
| Especialistas Neurais | Precisão por domínio, divergência média, tempo de parecer | Spans `specialist_type`, métricas `neural_hive_intent_confidence` | Score médio <0,8; fallback heurístico >3% |
| Especialistas Metacognitivos | Tempo detecção drift, sucesso de recalibração, alertas confirmados | Eventos `metacognition.alert`, dashboards divergência | Recomendações rejeitadas em sequência; ausência de análise > SLA |
| Executores | SLA cumprido, retries, eficiência de recursos | Spans `ticket_id`, métricas `neural_hive_execution_*` | Backlog > threshold, retries em cascata, saturação |
| Agentes de Geração | Aprovação sem edição, cobertura testes gerados, tempo de síntese | Logs de MR automáticos, métricas Code Forge | MRs reprovados consecutivamente; confiança < limite |
| Agentes Edge | Disponibilidade, sucesso de sincronização, latência offline→core | Traces com `edge_node_id`, métricas MQTT/gRPC | Falha em aplicação de patch; ausência heartbeat > SLA |

## Participação dos Agentes por Fluxo Operacional

| Fluxo (Documento 06) | Principais agentes envolvidos | Responsabilidade | Interações críticas |
| --- | --- | --- | --- |
| Fluxo A – Captura | Exploradores, Analistas, Guardiões | Detectar intenções, validar segurança inicial | Feromônios digitais → Analistas; Guardiões filtram anomalias |
| Fluxo B – Cognitivo | Especialistas neurais, Otimizadores, Rainha | Gerar planos, consolidar consenso, priorizar | Otimizadores ajustam pesos; Rainha aprova priorização |
| Fluxo C – Orquestração/Execução | Executores, Agentes de Geração, Agentes Edge, Guardiões | Transformar planos em tickets e entregas | Guardiões monitoram QoS; Edge sincroniza operações locais |
| Fluxo D – Observabilidade | Analistas, Otimizadores, Guardiões | Correlacionar telemetria, detectar desvios | Analistas alimentam dashboards; Guardiões disparam alertas |
| Fluxo E – Autocura | Guardiões, Motor de Autocura, Rainha | Executar playbooks e restaurar serviço | Autocura gera feromônios pós-incident; Rainha atualiza prioridades |
| Fluxo F – Experimentos | Otimizadores, Especialistas Metacognitivos, Exploradores | Propor, executar e avaliar experimentos | Resultados alimentam consenso cognitivo; Exploradores coletam sinais |

### Diagramas de Participação por Fluxo

```mermaid
flowchart LR
    subgraph Flows[Fluxos Operacionais]
        FA[Fluxo A – Captura]
        FB[Fluxo B – Cognitivo]
        FC[Fluxo C – Orquestração/Execução]
        FD[Fluxo D – Observabilidade]
        FE[Fluxo E – Autocura]
        FF[Fluxo F – Experimentos]
    end

    subgraph Agents[Agentes Principais]
        AR[Agente Rainha]
        AX[Exploradores]
        AN[Analistas]
        AO[Otimizadores]
        AG[Guardiões]
        AE[Especialistas Neurais]
        AM[Especialistas Metacognitivos]
        AW[Executores]
        AGN[Agentes de Geração]
        AEdge[Agentes Edge]
        AA[Motor de Autocura]
    end

    FA --> AX
    FA --> AN
    FA --> AG

    FB --> AE
    FB --> AR
    FB --> AO

    FC --> AW
    FC --> AGN
    FC --> AEdge
    FC --> AG

    FD --> AN
    FD --> AO
    FD --> AG

    FE --> AG
    FE --> AA
    FE --> AR

    FF --> AO
    FF --> AM
    FF --> AX
```

```mermaid
flowchart TB
    subgraph Fluxo_A[Fluxo A – Captura]
        AX1[Exploradores]
        AN1[Analistas]
        AG1[Guardiões]
        AX1 --> AN1
        AG1 -. validação .-> AN1
    end

    subgraph Fluxo_B[Fluxo B – Cognitivo]
        AE1[Especialistas Neurais]
        AR1[Agente Rainha]
        AO1[Otimizadores]
        AE1 --> AR1
        AO1 -. calibração .-> AE1
    end

    subgraph Fluxo_C[Fluxo C – Orquestração/Execução]
        AW1[Executores]
        AGN1[Agentes de Geração]
        AEdge1[Agentes Edge]
        AG2[Guardiões]
        AGN1 --> AW1
        AW1 --> AEdge1
        AG2 -. guardrails .-> AW1
    end

    subgraph Fluxo_D[Fluxo D – Observabilidade]
        AN2[Analistas]
        AO2[Otimizadores]
        AG3[Guardiões]
        AN2 --> AO2
        AG3 -. alertas .-> AN2
    end

    subgraph Fluxo_E[Fluxo E – Autocura]
        AG4[Guardiões]
        AA1[Motor de Autocura]
        AR2[Agente Rainha]
        AG4 --> AA1
        AA1 --> AR2
    end

    subgraph Fluxo_F[Fluxo F – Experimentos]
        AO3[Otimizadores]
        AM1[Metacognitivos]
        AX2[Exploradores]
        AO3 --> AM1
        AM1 --> AO3
        AX2 -. sinais .-> AO3
    end

    Fluxo_A --> Fluxo_B
    Fluxo_B --> Fluxo_C
    Fluxo_C --> Fluxo_D
    Fluxo_D --> Fluxo_E
    Fluxo_E --> Fluxo_F
    Fluxo_F --> Fluxo_B
```

## Interações e Dependências Críticas
- Memória Neural Multicamadas alimenta Especialistas, Analistas e Otimizadores; inconsistências afetam decisões do enxame.
- Ledger cognitivo e de auditoria registra ações da Rainha, pareceres dos especialistas e execuções de Autocura, garantindo rastreabilidade.
- Service Mesh + OPA fornecem guardrails transversais para Guardiões, Executores e Agentes de Geração.
- Telemetria OpenTelemetry conecta todos os agentes à observabilidade central, sustentando feedback contínuo e feromônios sincronizados.
- Motor de Experimentos é a ponte entre Otimizadores, Metacognitivos e Rainha para incorporar melhorias sem comprometer SLOs.

## Referências
- `documento-03-componentes-e-processos-neural-hive-mind.md`
- `docs/observability/services/geracao-planos.md`
- `docs/observability/services/orquestracao.md`
- `docs/observability/services/execucao.md`
- `docs/observability/services/autocura.md`
- `docs/observability/architecture.md`
