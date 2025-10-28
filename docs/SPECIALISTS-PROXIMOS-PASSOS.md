# Neural Hive Specialists – Próximos Passos Detalhados

Este roadmap aprofunda as iniciativas críticas para levar os especialistas neurais (business, technical, behavior, architecture e evolution) a um nível de maturidade elevado, eliminando dependências frágeis de heurísticas por string-match e fortalecendo toda a cadeia de decisão: modelos (MLflow), ledger, explicabilidade (SHAP/LIME) e métricas operacionais.

## Visão Geral
- **Contexto**: As avaliações ainda dependem majoritariamente de heurísticas determinísticas e palavra-chave; integrações com MLflow, explainability e métricas existem, mas operam em modo básico.
- **Objetivo macro**: Substituir heurísticas frágeis por pipelines de dados estruturados, modelos versionados e explicabilidade auditável, permitindo decisões consistentes e rastreáveis pelo engine de consenso.
- **Horizonte**: Execução fatiada em três ondas (curto, médio e longo prazo) com revisões mensais de progresso e replanejamento trimestral.

## 1. Operacionalizar modelos MLflow end-to-end
- **Motivação**: Sem modelos ativos e dataset padronizado, scores de confiança refletem heurísticas, não inteligência real.
- **Ações principais**:
  1. **Padronizar contrato de entrada**: definir schema imutável do plano cognitivo (JSON Schema + versionamento) e publicar no MLflow Model Registry como input signature.
  2. **Feature store sem string-match**: transformar plano em embeddings estruturados (ontologia de intents, grafos de dependência, estimativas numéricas) usando pipelines em Spark/DBT; registrar `feature_view` versionada.
  3. **CI/CD de modelos**: conectar pipelines de treinamento ao MLflow (experiments automáticos, tracking de datasets com `mlflow.data`) e gate de promoção com métricas de precisão, recall e fairness.
  4. **Inferência resiliente**: atualizar `BaseSpecialist` para checar `model.predict` com timeouts separados, logging de input/output e fallback calibrado (reduzir `confidence_score` e sinalizar `metadata['model_source']='heuristic'`).
  5. **Drift & qualidade**: habilitar monitoramento contínuo (MLflow Model Monitoring ou Evidently) com alertas quando distribuição de features desviar > K-L threshold definido.
- **Entregáveis**: schema oficial, pipeline de feature store, modelos `*-evaluator` em Production com validação automática, playbook de rollback.
- **Dependências**: squad de dados, MLOps, governança para definir glossário de features, infraestrutura de processamento.
- **Indicadores**: % de avaliações com modelo ativo, tempo médio para promover versão, taxa de detecção de drift, diferença média entre heurística e modelo após migração.

## 2. Elevar explainability com SHAP/LIME e narrativas semânticas
- **Motivação**: Explicações atuais refletem apenas fatores heurísticos; precisamos de interpretabilidade consistente, mesmo para modelos complexos.
- **Ações principais**:
  1. **Implementar SHAP/LIME em produção**: incorporar bibliotecas em `requirements`, criar wrappers que abstraiam carregamento do background dataset e amostras perturbadas específicas por domínio.
  2. **Narrativas estruturadas**: vincular fatores de raciocínio às contribuições SHAP (positivas/negativas) e gerar texto final com modelo NLG leve ou templates dinâmicos.
  3. **Explainability Ledger v2**: criar collection versionada com schema `token`, `input_features`, `model_version`, `importance_vectors`, `human_readable_summary`; adicionar índices TTL quando compliance permitir.
  4. **API de auditoria**: expor endpoint autenticado (ou CLI) que recupere explicações completas, incluindo dados de background, seeds e parâmetros de SHAP/LIME para reprodutibilidade.
  5. **Benchmark de performance**: medir overhead por especialista; orquestrar pré-cálculo assíncrono para planos de alta prioridade.
- **Entregáveis**: módulos SHAP/LIME integrados, explainability ledger documentado, endpoints de auditoria, guia de interpretação para squads de negócio.
- **Dependências**: GPU/CPU adequadas (SHAP pode ser pesado), dataset representativo para baselines, políticas de segurança de dados.
- **Indicadores**: % de pareceres com explicabilidade avançada, latência média adicional, número de solicitações de auditoria atendidas sem erro.

## 3. Reforçar governança e versionamento do ledger cognitivo
- **Motivação**: Ledger atual é imutável mas não versiona estrutura; migração para features ricas exige garantir integridade e trilha de auditoria detalhada.
- **Ações principais**:
  1. **Schema management**: publicar schema JSON/Avro do documento de opinião (e explicar) com versionamento em repositório central; usar validação antes do insert.
  2. **Assinatura criptográfica**: além do hash SHA-256, introduzir assinatura digital (chave privada do serviço) para evitar qualquer modificação maliciosa.
  3. **Query APIs semânticas**: criar camadas de acesso que permitam filtros por domínio, feature e decisão, evitando queries manuais direto no Mongo.
  4. **Data retention & compliance**: definir políticas de retenção, criptografia em repouso e mascaramento de campos sensíveis (LGPD/ISO).
  5. **Backups e replicação**: automatizar backup incremental, testes de restauração trimestrais e replicação multi-região.
- **Entregáveis**: schema versionado, módulo de assinatura, serviço de consulta, políticas de segurança atualizadas, runbook de recuperação.
- **Dependências**: time de segurança, DBAs, ferramentas PKI internas.
- **Indicadores**: taxa de inserções validadas vs rejeitadas, SLA de recuperação, logs de auditoria consumidos por governança.

## 4. Fortalecer observabilidade com métricas de alto nível e inteligência operacional
- **Motivação**: Métricas atuais monitoram apenas contagens e histogramas básicos; é necessário detectar deriva operacional, anomalias e correlações com o consenso.
- **Ações principais**:
  1. **Camada de métricas derivadas**: calcular precision/recall pós-consenso, divergência entre especialistas e evolução de confiança por domínio; publicar em Prometheus como gauges atualizados por job periódico.
  2. **Tracing distribuído completo**: propagar `trace_id`/`span_id` até chamadas de modelo e banco, adicionando atributos (`model_version`, `explainability_method`).
  3. **Alertas inteligentes**: definir SLOs (latência < 2s, taxa de erro < 1%) e usar Alertmanager com roteamento por especialista, incluindo alertas por aumento abrupto de risco médio.
  4. **Dashboards unificados**: criar painéis Grafana com visão executiva (KPIs) e visão engenharia (latência, filas, uso de SHAP); oferecer modo pivot por plano.
  5. **Feedback loop**: integrar métricas com backlog (ex: abrir issue automática quando risco médio > threshold por 3 dias).
- **Entregáveis**: bibliotecas de métricas avançadas, dashboards aprovados, alertas operacionais, integração com ferramenta de incidentes.
- **Dependências**: time de Observabilidade/SRE, acesso a dados de consenso, integração com tracing (OTel Collector).
- **Indicadores**: cobertura de métricas avançadas, tempo médio de resolução relativo a alertas, adoção de dashboards por stakeholders.

## 5. Erradicar heurísticas de string-match com pipelines semânticos
- **Motivação**: Palavras-chave em descrições de tarefas levam a falsos positivos/negativos e não escalam para novos domínios.
- **Ações principais**:
  1. **Ontologia e taxonomia**: definir vocabulário controlado para tarefas, riscos, padrões arquiteturais; mapear plano cognitivo para IDs de taxonomia em vez de texto cru.
  2. **Parsing estruturado**: utilizar NLP estruturado (spaCy, transformers) para extrair entidades e relações; armazenar resultado no feature store.
  3. **Graph reasoning**: alimentar Neo4j com nós das tarefas, dependências e atributos; usar queries CYPHER parametrizadas em vez de heurísticas textuais.
  4. **Reforço com feedback humano**: permitir que especialistas humanos anotem planos para treinar classificadores supervisionados, reduzindo subjetividade.
  5. **Benchmark contínuo**: manter dataset gold com planos rotulados para comparar heurísticas antigas vs novo pipeline e garantir regressão < 5%.
- **Entregáveis**: taxonomia publicada, pipelines NLP/graph implementados, dataset gold, relatório de benchmark.
- **Dependências**: equipe de Knowledge Management, linguistas computacionais, stack de NLP/graph disponível.
- **Indicadores**: redução de divergências pós-consenso, acurácia do classificador sem string-match, tempo necessário para on-boarding de novo domínio.

## Cronograma Sugerido (Rolling 90 dias)
- **Semana 1-3**: schema e feature store; pipeline NLP inicial; integração SHAP básica.
- **Semana 4-6**: modelos MLflow em staging, explainability ledger v2, dashboards avançados.
- **Semana 7-9**: promoção de modelos, assinatura digital do ledger, alertas inteligentes.
- **Semana 10-12**: benchmark final contra heurísticas antigas, hardening operacional, documentação de governança.

## Governança e Follow-up
- **Rituais**: reuniões quinzenais dos squads (MLOps, Observabilidade, Knowledge Graph, Segurança) para sincronização; review executiva mensal.
- **Artefatos**: atualizar `PHASE2_IMPLEMENTATION_STATUS.md` com status de cada iniciativa; manter documentação técnica em repositório central; registrar decisões arquiteturais via ADRs.
- **Responsáveis sugeridos**:
  - **Tech Lead Especialistas**: coordenação geral, depreciação das heurísticas antigas.
  - **MLOps**: pipelines MLflow, monitoramento de drift, automação de deploy.
  - **Data/Knowledge Engineering**: feature store, ontologia, pipelines NLP/graph.
  - **Observabilidade/SRE**: métricas avançadas, tracing e alertas.
  - **Segurança/Governança**: ledger, compliance, auditoria.

---
_Última atualização: 2025-10-07_
