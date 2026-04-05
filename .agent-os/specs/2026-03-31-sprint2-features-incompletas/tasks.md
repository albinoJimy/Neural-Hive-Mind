# Tasks - Sprint 2 Features Incompletas

> Sprint: Features Incompletas Fase 2-3
> Created: 2026-03-31
> Total Effort: 13 semanas

---

## EPIC-201: Multi-Source Aggregation (3 semanas) ✅ COMPLETO

### EPIC-201-01: PostgreSQL Client
- [x] 201.01 Criar postgresql_client.py
- [x] 201.02 Implementar conexao asyncpg
- [x] 201.03 Implementar execute_query()
- [x] 201.04 Implementar get_insights()
- [x] 201.05 Implementar get_analyst_actions()
- [x] 201.06 Implementar get_feature_usage()
- [x] 201.07 Adicionar config settings.py
- [x] 201.08 Adicionar vars ambiente
- [x] 201.09 Criar testes
- [x] 201.10 Testar conexao

### EPIC-201-02: Data Fusion Engine
- [x] 202.01 Criar data_fusion_engine.py
- [x] 202.02 Implementar normalize_schema()
- [x] 202.03 Implementar align_temporal()
- [x] 202.04 Implementar join_sources()
- [x] 202.05 Implementar resolve_conflicts()
- [x] 202.06 Implementar enrich_with_context()
- [x] 202.07 Criar AggregatedResult model
- [x] 202.08 Criar testes engine
- [x] 202.09 Testar fusão 2 fontes
- [x] 202.10 Testar fusão 4 fontes
- [x] 202.11 Testar resolução conflitos

### EPIC-201-03: Integrar QueryEngine
- [x] 203.01 Modificar query_engine.py
- [x] 203.02 Adicionar PostgreSQLClient
- [x] 203.03 Integrar DataFusionEngine
- [x] 203.04 Refatorar consolidate_results()
- [x] 203.05 Adicionar join_sources()
- [x] 203.06 Adicionar correlate_metrics()
- [x] 203.07 Atualizar main.py
- [x] 203.08 Passar PostgreSQLClient
- [x] 203.09 Testar query 4 fontes
- [x] 203.10 Testar integração

### EPIC-201-04: Nova API Multi-Source
- [x] 204.01 Criar multi_source.py router
- [x] 204.02 POST /api/v1/analytics/query-multi-source
- [x] 204.03 POST /api/v1/analytics/cross-source-analysis
- [x] 204.04 GET /api/v1/analytics/sources/status
- [x] 204.05 Adicionar schemas request/response
- [x] 204.06 Documentar OpenAPI
- [x] 204.07 Criar testes API
- [x] 204.08 Testar Mock
- [x] 204.09 Testar E2E

---

## EPIC-202: A/B Testing Persistência (2 semanas) ✅ COMPLETO

### EPIC-202-01: Coleção MongoDB
- [x] 202.01 Criar migration m002_ab_test_results.py
- [ ] 202.02 Definir schema collection
- [ ] 202.03 Criar índices experiment_id
- [ ] 202.04 Criar índices created_at
- [ ] 202.05 Criar índices status+created_at
- [ ] 202.06 Criar índices statistical_recommendation
- [ ] 202.07 Adicionar script rollback
- [ ] 202.08 Testar migration

### EPIC-202-02: Métodos MongoDB Client
- [ ] 202.09 Modificar mongodb_client.py
- [ ] 202.10 Implementar save_ab_test_results()
- [ ] 202.11 Implementar get_ab_test_results()
- [ ] 202.12 Implementar list_ab_test_results()
- [ ] 202.13 Implementar get_ab_test_history()
- [ ] 202.14 Implementar get_ab_test_aggregations()
- [ ] 202.15 Criar ABTestResultsPersistent model
- [ ] 202.16 Criar testes métodos
- [ ] 202.17 Testar persistência
- [ ] 202.18 Validar schema

### EPIC-202-03: Integrar Engine
- [ ] 202.19 Modificar ab_testing_engine.py
- [ ] 202.20 Modificar analyze_results() persistir
- [ ] 202.21 Modificar experiment_manager.py
- [ ] 202.22 Modificar analyze_experiment_results()
- [ ] 202.23 Modificar ab_testing.py router
- [ ] 202.24 GET /api/v1/ab-tests/{id}/results
- [ ] 202.25 GET /api/v1/ab-tests/history
- [ ] 202.26 GET /api/v1/ab-tests/aggregations
- [ ] 202.27 Testar fluxo completo
- [ ] 202.28 Testar histórico

### EPIC-202-04: Dashboard
- [ ] 202.29 GET /api/v1/ab-tests/dashboard
- [ ] 202.30 Implementar agregações
- [ ] 202.31 Implementar filtros
- [ ] 202.32 Criar dashboard frontend
- [ ] 202.33 Testar dashboard

---

## EPIC-203: Feature Lineage (3 semanas) ✅ COMPLETO

### EPIC-203-01: Modelos Lineage
- [x] 203.01 Criar lineage.py models
- [x] 203.02 Implementar FeatureLineage
- [x] 203.03 Implementar TransformationType enum
- [x] 203.04 Implementar SourceType enum
- [x] 203.05 Implementar LineageMetadata
- [x] 203.06 Estender FeatureVector
- [x] 203.07 Criar testes models
- [x] 203.08 Testar validação

### EPIC-203-02: Lineage Tracker
- [x] 203.09 Criar lineage_tracker.py
- [x] 203.10 Implementar LineageTracker
- [x] 203.11 Implementar track_feature()
- [x] 203.12 Implementar update_lineage()
- [x] 203.13 Implementar get_lineage_tree()
- [x] 203.14 Implementar get_impact_analysis()
- [x] 203.15 Implementar validate_integrity()
- [x] 203.16 Implementar compute_computation_hash()
- [x] 203.17 Criar testes tracker
- [x] 203.18 Testar rastreamento
- [x] 203.19 Testar árvore dependências
- [x] 203.20 Testar análise impacto

### EPIC-203-03: Integrar Feature Store
- [x] 203.21 Modificar feature_store.py
- [x] 203.22 Integrar LineageTracker
- [x] 203.23 Modificar save_features()
- [x] 203.24 Modificar get_features()
- [x] 203.25 Modificar computation.py
- [x] 203.26 Adicionar computation_hash
- [x] 203.27 Modificar routers/features.py
- [x] 203.28 GET /api/v1/features/{plan_id}/lineage
- [x] 203.29 GET /api/v1/features/{plan_id}/lineage/tree
- [x] 203.30 GET /api/v1/features/{plan_id}/lineage/impact
- [x] 203.31 GET /api/v1/lineage/validate/{plan_id}
- [x] 203.32 Testar integração

### EPIC-203-04: Export/Import
- [x] 203.33 Implementar export_lineage()
- [x] 203.34 Implementar import_lineage()
- [x] 203.35 POST /api/v1/lineage/export
- [x] 203.36 POST /api/v1/lineage/import
- [x] 203.37 Validar schema
- [x] 203.38 Testar round-trip

---

## EPIC-204: SHAP Values (3 semanas) ✅ COMPLETO

### EPIC-204-01: Modelo ML SHAP
- [x] 204.01 Criar shap_model.py
- [x] 204.02 Implementar DecisionWrapperModel
- [x] 204.03 Implementar FeatureExtractor
- [x] 204.04 Implementar ModelTrainer
- [x] 204.05 Criar shap_training.py script
- [x] 204.06 Coletar decisões históricas
- [x] 204.07 Implementar pipeline sklearn
- [x] 204.08 Persistir modelo treinado
- [x] 204.09 Testar treinamento
- [x] 204.10 Validar performance > 0.8

### EPIC-204-02: SHAP Calculator Real
- [x] 204.11 Criar model_based_shap.py
- [x] 204.12 Implementar ModelBasedShapCalculator
- [x] 204.13 Integrar biblioteca SHAP
- [x] 204.14 Implementar calculate_shap()
- [x] 204.15 Implementar calculate_feature_importance()
- [x] 204.16 Implementar generate_waterfall_plot()
- [x] 204.17 Implementar generate_summary_plot()
- [x] 204.18 Criar testes SHAP
- [x] 204.19 Validar SHAP vs heurística
- [x] 204.20 Testar decisões reais

### EPIC-204-03: Integração API
- [x] 204.21 Modificar main.py carregar modelo
- [x] 204.22 Modificar explainability router
- [x] 204.23 Adicionar endpoint SHAP real
- [x] 204.24 GET /api/v1/explain/feature-importance
- [x] 204.25 GET /api/v1/explain/waterfall/{decision_id}
- [x] 204.26 Manter heurística fallback
- [x] 204.27 Adicionar flag use_real_shap
- [x] 204.28 Testar integração
- [x] 204.29 Documentar mudanças

### EPIC-204-04: Treino Contínuo
- [x] 204.30 Retreino automático mensal
- [x] 204.31 Validação pré-deploy
- [x] 204.32 Rollback automático
- [x] 204.33 Métricas monitoramento
- [x] 204.34 Testar ciclo treino

---

## EPIC-205: Alert Engine (2 semanas) ✅ COMPLETO

### EPIC-205-01: Alert Engine
- [x] 205.01 Criar alert_engine.py
- [x] 205.02 Implementar AlertEngine
- [x] 205.03 Implementar evaluate_and_send()
- [x] 205.04 Implementar check_all_budgets()
- [x] 205.05 Implementar should_alert()
- [x] 205.06 Implementar get_alert_severity()
- [x] 205.07 Criar alert_rule.py models
- [x] 205.08 Implementar AlertRule
- [x] 205.09 Implementar AlertSeverity enum
- [x] 205.10 Criar testes engine
- [x] 205.11 Testar regras
- [x] 205.12 Testar envio alertas

### EPIC-205-02: Alert Dispatcher
- [x] 205.13 Criar alert_dispatcher.py
- [x] 205.14 Implementar AlertDispatcher
- [x] 205.15 Implementar send_alert()
- [x] 205.16 Implementar send_to_alertmanager()
- [x] 205.17 Implementar send_to_slack()
- [x] 205.18 Implementar send_to_pagerduty()
- [x] 205.19 Implementar send_to_email()
- [x] 205.20 Implementar apply_cooldown()
- [x] 205.21 Criar testes dispatcher
- [x] 205.22 Testar canais

### EPIC-205-03: Integração Main
- [x] 205.23 Modificar main.py
- [x] 205.24 Inicializar AlertEngine lifespan
- [x] 205.25 Inicializar AlertDispatcher
- [x] 205.26 Task background monitoramento
- [x] 205.27 POST /api/v1/alerts/test
- [x] 205.28 GET /api/v1/alerts/history
- [x] 205.29 Adicionar config settings
- [x] 205.30 Adicionar vars ambiente
- [x] 205.31 Testar monitoramento
- [x] 205.32 Testar endpoint teste

### EPIC-205-04: Dashboard
- [x] 205.33 Criar coleção alert_history
- [x] 205.34 Persistir alertas
- [x] 205.35 GET /api/v1/alerts/dashboard
- [x] 205.36 Agregações totais
- [x] 205.37 Implementar MTTR
- [x] 205.38 Testar dashboard

---

## Total

- **Total Tasks:** 205
- **Total Effort:** 13 semanas
- **Critical Path:** EPIC-201 → EPIC-203 (Data Fusion → Lineage)
- **Quick Wins:** EPIC-202 (A/B Testing), EPIC-205 (Alert Engine)
