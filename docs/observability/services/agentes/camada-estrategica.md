# Camada Estratégica e Coordenação – Agentes

## Visão Geral
- Responsável por alinhar prioridades, traduzir visão estratégica em planos acionáveis e garantir que decisões considerem risco, valor e custo.
- Agentes operam com alta correlação com telemetria e bancos semânticos, fornecendo contexto contínuo para o restante do ecossistema Neural Hive-Mind.
- Referências principais: `documento-03-componentes-e-processos-neural-hive-mind.md`, `docs/observability/architecture.md`, `docs/observability/services/geracao-planos.md`.
- **Natureza Híbrida dos Agentes**: apesar de consumirem modelos de IA (heurísticas swarm, análises bayesianas, embeddings, LLMs especializados), estes agentes também integram automações determinísticas, regras simbólicas, workflows Temporal/Argo e ferramentas operacionais (Grafana, Neo4j, ServiceNow). Não são apenas agentes de prompt/LLM; combinam pipelines de ML, reasoning semântico e integrações DevSecOps para entregar decisões auditáveis.

## Agente Rainha
- **Características**: entidade coordenadora com visão estratégica, inteligência tática e consciência situacional ampla (roteiro-neural-hive-mind-narrativo.md:117-124).
- **Tecnologia/IA**: heurísticas swarm + feromônios digitais combinados com análises bayesianas/ensemble do motor de consenso; otimização multiobjetivo risco→valor→custo; reasoning simbólico sobre ontologias versionadas; valida decisões no ledger cognitivo.
- **Ferramentas/Stack**: dashboards Grafana/Kibana; consultas a Neo4j/JanusGraph; exploração de ledger (QLDB/Delta Lake); integrações ServiceNow/ITSM; ganchos Temporal/Argo para replanejamentos.
- **Responsabilidades**: harmonizar prioridades, arbitrar conflitos entre domínios, sincronizar ciclos Cognitivo→Execução, aprovar exceções.
- **Integrações**: consome relatórios dos Analistas e sinais de Guardiões/Autocura; consulta telemetria agregada (OTel, Prometheus, Grafana); interage com Orquestração para ajustes de QoS.
- **Métricas e Telemetria**: `% replanejamentos`, `decision_latency`, divergência decisão vs execução; spans OTel com atributos `decision_scope`.
- **Riscos/Governança**: dependência da malha de feromônios para visibilidade; necessidade de guardrails éticos e trilhas de auditoria.

## Analistas
- **Características**: cientistas de dados do enxame conectados à telemetria correlacionada (`intent_id`, `plan_id`).
- **Tecnologia/IA**: pipelines analytics sobre Knowledge Graph, Elasticsearch/ClickHouse; consultas Cypher/Gremlin + embeddings vetoriais; notebooks governados e jobs Spark para consolidação quase em tempo real.
- **Ferramentas/Stack**: Grafana, Superset, notebooks Jupyter governados, pipelines Spark/Kafka, catálogo DataHub/Amundsen, repositórios ClickHouse/Prometheus.
- **Responsabilidades**: consolidar dados multi-fonte (telemetria, ledger, feromônios) em insights acionáveis; alimentar Rainha, Orquestração e Especialistas.
- **Integrações**: memória semântica, dashboards de qualidade, pipelines observabilidade, catálogos de dados.
- **Métricas e Telemetria**: precisão vs decisões, `analysis_response_time`, ratio sinal→insight; spans com `analysis_id`.
- **Riscos**: suscetíveis a ruído/viés sem curadoria de feromônios; demandam versionamento de análises e controles de acesso.

## Otimizadores
- **Características**: agentes dedicados à melhoria contínua e ajuste de políticas.
- **Tecnologia/IA**: aprendizado por reforço + bandits contextuais; avaliação causal baseada em DAGs; automação via MLflow para versionar políticas; uso do motor de experimentos.
- **Ferramentas/Stack**: Evidently/DoWhy, MLflow ou Weights & Biases, Argo Workflows para experimentos controlados, painéis de SLO no Grafana, integrações GitOps.
- **Responsabilidades**: recalibrar pesos de consenso, SLOs e heurísticas; monitorar experimentos e aplicar ajustes incrementais.
- **Integrações**: Motor de Experimentos, Autocura, dashboards de fluxos B–F, pipelines CI/CD para promoção de políticas.
- **Métricas e Telemetria**: impacto em lead time, redução de retrabalho, `optimization_success_rate`; eventos `optimization.applied` no ledger.
- **Riscos**: ajustes sem validação podem degradar consenso; requerem guardrails, rollback automático e aprovação ética.

## Indicadores de Camada
| Indicador | Agente Responsável | Notas |
| --- | --- | --- |
| % de decisões estratégicas alinhadas aos guardrails | Agente Rainha | Validar contra auditorias no ledger |
| Precisão analítica por domínio | Analistas | Cruzar com feedback de execução |
| Efetividade pós-ajuste (ΔSLO) | Otimizadores | Monitorar em experimentos controlados |

## Referências Cruzadas
- `docs/observability/services/agentes.md`
- `docs/observability/services/geracao-planos.md`
- `docs/observability/architecture.md`
