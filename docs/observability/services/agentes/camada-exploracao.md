# Camada de Exploração e Aprendizado – Agentes

## Visão Geral
- Responsável por descobrir sinais fracos, oportunidades emergentes e alimentar o conhecimento coletivo antes da formalização em intenções.
- Trabalha próxima a canais core e edge, garantindo contexto atualizado para pipelines cognitivos.
- Referências principais: `roteiro-neural-hive-mind-narrativo.md`, `documento-08-detalhamento-tecnico-camadas-neural-hive-mind.md`, `docs/observability/architecture.md`.
- **Natureza Híbrida**: agentes desta camada combinam modelos de detecção/anomalia e embeddings com automações determinísticas (MQTT, Kafka Streams, jobs de saneamento), garantindo que descobertas passem por curadoria e integração operacional — não atuam apenas via prompts/LLM.

## Exploradores (Scout Agents)
- **Características**: agentes móveis atuando em fluxos core/edge, identificando padrões emergentes e demandas latentes.
- **Tecnologia/IA**: modelos de séries temporais + embeddings contextualizados; filtros Bayesianos; autoencoders leves em edge; scoring de curiosidade adaptativa.
- **Ferramentas/Stack**: conectores MQTT/WebSockets, runtimes Rust/WASM, coletores OpenTelemetry, feature store Redis/Feast, tópicos Kafka/NATS.
- **Responsabilidades**: descobrir oportunidades e anomalias positivas antes de formalização da intenção; priorizar sinais com base em relevância e risco.
- **Integrações**: sensores edge, canais digitais, feromônios digitais, backlog de experimentos e Analistas.
- **Métricas e Telemetria**: taxa de descobertas validadas, cobertura por domínio, latência observação→publicação; logs com `exploration_domain`, traces edge→core.
- **Riscos**: falsos positivos/negativos; dependem de curadoria dos Analistas e validação dos Guardiões.

## Mecanismo de Feromônios Digitais
- **Características**: grafo distribuído que guarda trilhas, sucessos, alertas e rotas otimizadas inspiradas em colônias biológicas.
- **Tecnologia/IA**: Neo4j/JanusGraph com reforço de feromônios virtuais; decay adaptativo; algoritmos de centralidade/PageRank; TTL dinâmico guiado por modelos de sobrevivência; replicação federada.
- **Ferramentas/Stack**: clusters Neo4j/JanusGraph, Kafka Streams para atualização de pesos, Redis para cache curto, APIs GraphQL/gRPC, jobs Lambda/Argo para saneamento periódico.
- **Responsabilidades**: sustentar comunicação indireta entre agentes; priorizar rotas eficientes; preservar memória coletiva.
- **Integrações**: pipelines OTel/Kafka, ledger cognitivo, mecanismos de consenso, dashboards de observabilidade.
- **Métricas e Telemetria**: consistência dos sinais, tempo de propagação, consumo vs descarte, densidade de trilhas por domínio.
- **Riscos**: saturação/ruído quando TTL inadequado; necessidade de auditoria ética e compliance de dados.

## Indicadores de Camada
| Indicador | Fonte | Observações |
| --- | --- | --- |
| % de sinais confirmados pós-validação | Exploradores | Correlacionar com decisões da camada cognitiva |
| Tempo médio para atualização de feromônio crítico | Mecanismo de Feromônios | Monitorar via Kafka Streams |
| Cobertura de domínios (core vs edge) | Exploradores | Utilizar métricas edge→core |

## Referências Cruzadas
- `docs/observability/services/agentes.md`
- `docs/observability/services/captura-intencao.md`
- `documento-08-detalhamento-tecnico-camadas-neural-hive-mind.md`
