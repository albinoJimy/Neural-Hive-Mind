# Camada Executiva – Agentes

## Visão Geral
- Converte planos cognitivos em tickets e entregas tangíveis (software, IaC, artefatos operacionais, ações edge).
- Abrange orquestração de workflows, geração automatizada de artefatos e execução distribuída.
- Referências: `docs/observability/services/orquestracao.md`, `docs/observability/services/execucao.md`, `documento-08-detalhamento-tecnico-camadas-neural-hive-mind.md`.
- **Natureza Híbrida**: agentes executivos misturam IA (LLMs generativos, modelos preditivos edge) com automação determinística (CI/CD, workflows Temporal, políticas OPA, OTA). São pipelines completos de engenharia, não apenas prompts disparando LLMs.

## Executores (Worker Agents)
- **Características**: agentes operacionais que orquestram tarefas complexas alinhadas a execution tickets.
- **Tecnologia/IA**: engines Temporal/Akka com políticas QoS alimentadas por modelos preditivos; simulações de carga (Monte Carlo); caching de tokens efêmeros; spans OTel automáticos por etapa.
- **Ferramentas/Stack**: Temporal/Cadence, Argo Workflows, Karpenter/KEDA para escalonamento, HashiCorp Vault para credenciais efêmeras, Istio Service Mesh, Prometheus/Grafana para métricas de QoS.
- **Responsabilidades**: executar atividades distribuídas, coordenar dependências, garantir SLAs, acionar compensações.
- **Integrações**: Orquestração, pipelines CI/CD, Agentes de Geração, Agentes Edge, Guardiões.
- **Métricas e Telemetria**: SLA cumprido, retries, eficiência de recursos, backlog; spans `ticket_id`.
- **Riscos**: instruções ambíguas, saturação de agentes, dependência de credenciais; mitigados com telemetria e runbooks.

## Agentes de Geração Neurais
- **Características**: agentes responsáveis por sintetizar código, IaC, políticas e documentação com modelos generativos + heurísticas.
- **Tecnologia/IA**: LLMs especializados, RAG sobre catálogos arquiteturais, scoring automático de confiança, mutation testing, verificações automáticas (lint, unit, SAST), geração de SBOM e assinatura Sigstore.
- **Ferramentas/Stack**: GitLab CI/Tekton, ArgoCD, SonarQube, Snyk, Trivy, Checkov, Sigstore/Cosign, registries OCI (ECR/Harbor), frameworks de mutation testing (Stryker/PITest), catálogos de templates versionados em Git.
- **Responsabilidades**: gerar artefatos com metadados (`intent_id`, `plan_id`, `confidence`), abrir MRs automáticos, acionar pipelines “Code Forge”, realizar validações pré-submissão.
- **Integrações**: templates reutilizáveis, repositórios Git, pipelines CI/CD, motores de aprovação humana, Autocura (para patches), ledger cognitivo.
- **Métricas e Telemetria**: taxa de aprovação sem edição, cobertura de testes gerados, tempo de síntese, confiança média; logs de MR automáticos.
- **Riscos**: geração inadequada exige supervisão humana; drift dos modelos generativos; necessidade de compliance.

## Agentes Edge
- **Características**: executores offline-first com storage criptografado, comunicação adaptativa e atestação remota.
- **Tecnologia/IA**: inferência embarcada (TinyML/WASM), validação de assinatura com TPM/TEE, canais seguros com compressão delta, feature flags locais, replicação eventual criptografada e buffering resiliente.
- **Ferramentas/Stack**: runtimes Rust/Go/WASM, brokers MQTT (Mosquitto/AWS IoT Core), gRPC seguro, módulos TPM/Intel SGX, sistemas de arquivos criptografados, agentes Fluent Bit/Vector, gerenciadores OTA (Mender/Balena).
- **Responsabilidades**: aplicar patches, executar tarefas locais, sincronizar resultados quando conectividade retorna, reportar telemetria edge.
- **Integrações**: Orquestração, Guardiões, Feromônios Digitais, Autocura, pipelines de telemetria.
- **Métricas e Telemetria**: disponibilidade, sucesso de sincronização, latência offline→core, heartbeat; traces com `edge_node_id`.
- **Riscos**: falhas físicas, segurança física, perda de conexão prolongada; mitigadas por buffers, failover e auditoria.

## Indicadores de Camada
| Indicador | Agente | Observações |
| --- | --- | --- |
| SLA de execução cumprido | Executores | Monitorar backlog e retries |
| Aprovação automática sem retrabalho | Agentes de Geração | Correlacionar com score de confiança |
| Disponibilidade edge ≥99% | Agentes Edge | Validar via heartbeats e sincronização |

## Referências Cruzadas
- `docs/observability/services/agentes.md`
- `docs/observability/services/orquestracao.md`
- `docs/observability/services/execucao.md`
- `documento-08-detalhamento-tecnico-camadas-neural-hive-mind.md`
