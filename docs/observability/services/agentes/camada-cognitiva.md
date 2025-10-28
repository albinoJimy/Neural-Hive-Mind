# Camada Cognitiva – Agentes

## Visão Geral
- Responsável por interpretar intenções enriquecidas, avaliar riscos e gerar recomendações auditáveis com consenso.
- Combina especialistas neurais multi-domínio, mecanismos de consenso e futuras capacidades metacognitivas.
- Referências: `documento-03-componentes-e-processos-neural-hive-mind.md`, `docs/observability/services/geracao-planos.md`, `documento-07-arquitetura-referencia-especifica-neural-hive-mind.md`.
- **Natureza Híbrida**: embora usem LLMs e modelos especializados, os agentes cognitivos também aplicam regras determinísticas, explainability obrigatória, integração com memória semântica e ledger auditável; o processo envolve pipelines de ML, consenso algorítmico e supervisão humana, extrapolando o modelo de “apenas agentes de prompt”.

## Especialistas Neurais (Negócios, Técnico, Comportamento, Evolução, Arquitetura)
- **Características**: contêineres cognitivos isolados com contrato gRPC, registro dinâmico e quotas de recursos por namespace.
- **Tecnologia/IA**: LLMs fine-tunados + modelos especializados (process mining, APM, transformers temporais); regras determinísticas; inferência acelerada por GPU/FPGA; explainability (SHAP/LIME/contrafactuais); validação cruzada com memória semântica.
- **Ferramentas/Stack**: MLflow/Model Registry, servidores Triton/ONNX Runtime, Process Mining Suite, APIs SonarQube/Snyk, bibliotecas de explainability (SHAP, LIME, Alibi), namespaces Kubernetes com GPU/FPGA e sidecars Istio.
- **Responsabilidades**: consumir planos preliminares, avaliar risco/valor, emitir parecer com score ≥0,8, fornecer justificativas auditáveis, sinalizar revisão humana quando necessário.
- **Integrações**: Memória Neural Multicamadas (Redis, Elastic, ClickHouse, Data Lake), Motor de Consenso, ledger cognitivo, pipelines de feedback.
- **Métricas e Telemetria**: precisão por domínio, divergência média entre parecer e decisão final, tempo de resposta, `% fallback heurístico`; spans OTel com `specialist_type`.
- **Riscos**: drift de modelos, viés algorítmico, dependência de dados históricos; mitigação com monitoramento PSI/K-S, fairness checks e comitês de ética.

## Especialistas Metacognitivos (Roadmap)
- **Características**: agentes planejados para avaliar desempenho dos especialistas ativos e ajustar heurísticas do consenso.
- **Tecnologia/IA**: meta-learning, análise causal, monitoramento de drift com PSI/K-S; AutoML/hyperband para otimização; simuladores sandbox para testes offline; pipelines de aprovação ética.
- **Ferramentas/Stack**: plataformas AutoML (Kubeflow Katib/Optuna), ambientes sandbox (Great Expectations + dados sintéticos), Argo/MLflow, catálogos de experimentos, integrações ServiceNow/Jira para workflow de aprovação.
- **Responsabilidades**: detectar degradações, propor ajustes automáticos de pesos, recomendar re-treinamentos, avaliar confiabilidade pós-ajuste.
- **Integrações**: Motor de Experimentos, dashboards de divergência, ledger cognitivo, pipelines MLOps.
- **Métricas e Telemetria**: tempo para detectar drift cognitivo, `% recomendações aceitas`, eficácia de recalibração; eventos `metacognition.alert`.
- **Riscos**: mudanças automatizadas sem supervisão podem gerar instabilidade; necessário guardrails éticos, sandbox e revisão humana.

## Indicadores de Camada
| Indicador | Fonte | Observações |
| --- | --- | --- |
| Score médio ≥0,8 por domínio | Especialistas Neurais | Planos abaixo do threshold exigem revisão humana |
| Divergência especialista vs decisão final | Especialistas + Motor de Consenso | Monitorar >5% para recalibração |
| Tempo para detectar drift cognitivo | Especialistas Metacognitivos | Ativar pipelines de re-treinamento |

## Referências Cruzadas
- `docs/observability/services/agentes.md`
- `docs/observability/services/geracao-planos.md`
- `documento-03-componentes-e-processos-neural-hive-mind.md`
