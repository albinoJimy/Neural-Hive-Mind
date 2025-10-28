# Captura de Intenção – Visão Detalhada

## Papel no Pipeline
- Primeira etapa cognitiva responsável por validar, enriquecer e classificar envelopes recebidos do gateway (Fluxo A, documento-06).
- Determina score de confiança, identifica PII, aplica heurísticas de domínio e encaminha para geração de planos ou validação humana.

## Componentes Principais
- **Motor NLP/PII**: pipelines de detecção de idioma, sentiment analysis, redatores seguros.
- **Normalizador Semântico**: aplica ontologias JSON-LD, expande contexto via Knowledge Graph (documento-03, Seção 3).
- **Gating & Roteamento**: regras baseadas em `requires_manual_validation` e políticas de risco (VERIFICACOES_IMPLEMENTADAS.md, item 2).
- **Telemetry Hooks**: instrumentação OTel para métricas de confiança e volume por domínio.

## Arquitetura e Tecnologias
- Serviços containerizados sob namespaces `neural-hive-cognition`, protegidos por Istio PeerAuthentication STRICT.
- Conecta-se ao Redis Cluster para contexto de curto prazo e ao Elastic/Mongo para contexto operacional.
- Usa pipelines Terraform/Helm para provisionamento (README.md, Seção Estrutura; documento-05, Seção 3).

## Integração com IA (ML/LLM)
- LLMs especializados em linguagem natural (transformers) para intent classification, topic extraction e detecção de entidades.
- Modelos simbólicos complementares para regras determinísticas e scoring.
- Feedback loop de aprendizado online com monitoramento de drift (documento-03, Seção 5.2; documento-05, Seção 6).

## Integrações Operacionais
- Consumidores/subscritores Kafka configurados com exactly-once e políticas de ACL mínimas (ADR-0004; VERIFICACOES_IMPLEMENTADAS.md, item 4).
- Exporta envelopes enriquecidos para `plans.ready` topics e gera eventos de auditoria para ledger.
- Integra com Keycloak para autorização de serviços downstream via tokens de curta duração.

## Escalabilidade e Resiliência
- Autoescalonamento per domínio com HPA baseado em latência p95 e backlog de intents.
- Topologia federada permite instâncias regionais sincronizadas via replicação eventual da memória semântica (documento-02, Seção 3).
- Mecanismos de fallback heurístico ativados se modelos ML falham (documento-06, Seção 5.6).

## Segurança
- Políticas de mascaramento e anonimização automáticas para campos sensíveis (documento-04, Seção 4).
- Criptografia ponta a ponta com mTLS e assinatura de logs; compliance com LGPD/GDPR avaliada via PIA.
- Segregação de funções impede que operadores com baixa permissão acessem intenções confidenciais.

## Observabilidade
- Métricas: `neural_hive_intent_confidence`, taxas de roteamento manual, tempo de enriquecimento, erros PII.
- Tracing distribuído correlacionando `intent_id`, `plan_candidate_id`, `risk_band`.
- Alertas baseados em spikes de baixa confiança, latência >200 ms, ou volume de exceções.

## Riscos e Ações
- **Drift de modelos**: implementar monitoração PSI e gatilhos de re-treinamento automatizado (documento-03, Seção 5.2).
- **Falhas de Knowledge Graph**: garantir caches locais e fallback a heurísticas.
- **Exposição de PII**: reforçar testes de mascaramento e auditorias periódicas.

## Próximos Passos Sugeridos
1. Automatizar publicação de relatórios de confiança para o board de governança digital.
2. Ampliar cobertura de testes adversariais para modelos NLP (documento-04, Seção 5).
3. Integrar métricas de gating com dashboards executivos para visibilidade de backlog manual.
