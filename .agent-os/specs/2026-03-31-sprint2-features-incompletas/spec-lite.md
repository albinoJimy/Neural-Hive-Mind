# Spec Summary (Lite)

Completar 5 features críticas identificadas como incompletas na Fase 2 (Especialistas) e Fase 3 (Aprendizado). O Sprint 2 foca em funcionalidades que bloqueiam a maturidade do sistema: multi-source aggregation, A/B testing persistência, feature lineage, SHAP values, e alert engine integration.

## 5 Epics

### EPIC-201: Multi-Source Aggregation (3 semanas)
Completar agregação de dados de 4 fontes (MongoDB, PostgreSQL, ClickHouse, Neo4j) com verdadeira fusão de dados. Completude atual: 40%. Entregar: PostgreSQL Client, Data Fusion Engine, QueryEngine refatorado, nova API multi-source.

### EPIC-202: A/B Testing Persistência (2 semanas)
Implementar persistência de resultados de experimentos A/B no MongoDB. Engine está 100% completo mas resultados não são salvos. Entregar: Coleção ab_test_results, métodos MongoDBClient, integração engine, dashboard.

### EPIC-203: Feature Lineage (3 semanas)
Implementar rastreamento completo de lineage para as 26 features. Completude atual: 0%. Entregar: Modelos de lineage, LineageTracker, integração feature-store, export/import, endpoints API.

### EPIC-204: SHAP Values (3 semanas)
Implementar cálculo real de SHAP values usando biblioteca SHAP e modelo sklearn. Atualmente usa heurística "fake". Entregar: Modelo ML DecisionWrapper, ModelBasedShapCalculator, integração API, treino contínuo.

### EPIC-205: Alert Engine (2 semanas)
Integrar alert engine proativo no SLA Management System. Detecção de risco existe mas não dispara alertas. Entregar: AlertEngine, AlertDispatcher (Slack/PagerDuty/Email), integração main, dashboard histórico.

## Ordem Recomendada

1. EPIC-202 (2 semanas) - Mais simples, alta prioridade
2. EPIC-205 (2 semanas) - Independente, alto valor
3. EPIC-201 (3 semanas) - Complexo, pode paralelo com 204
4. EPIC-203 (3 semanas) - Depende deEPIC-201 parcialmente
5. EPIC-204 (3 semanas) - Mais complexo, bloqueia explainability

Total: 13 semanas até todas features completas.
