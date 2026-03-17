# Spec Tasks

## Tasks

- [x] 1. DatasetBalanceAnalyzer - Analisar balanceamento do dataset
  - [x] 1.1 Write tests for DatasetBalanceAnalyzer
  - [x] 1.2 Implementar calculate_balance_metrics()
  - [x] 1.3 Implementar get_priority_recommendations()
  - [x] 1.4 Verificar todos os testes passam

- [x] 2. ActiveLearningStrategy - Calcular valor informacional
  - [x] 2.1 Write tests for ActiveLearningStrategy
  - [x] 2.2 Implementar calculate_information_value()
  - [x] 2.3 Implementar should_collect_feedback()
  - [x] 2.4 Verificar todos os testes passam

- [x] 3. PriorityFeedbackQueue - Gerenciar fila de casos prioritários
  - [x] 3.1 Write tests for PriorityFeedbackQueue
  - [x] 3.2 Implementar enqueue_plan_for_review()
  - [x] 3.3 Implementar dequeue_next_case()
  - [x] 3.4 Implementar mark_feedback_submitted()
  - [x] 3.5 Verificar todos os testes passam

- [x] 4. Active Learning API - Endpoints REST
  - [x] 4.1 Write tests for ActiveLearningController
  - [x] 4.2 Implementar GET /api/v1/active-learning/metrics
  - [x] 4.3 Implementar GET /api/v1/active-learning/queue
  - [x] 4.4 Implementar POST /api/v1/active-learning/{queue_id}/claim
  - [x] 4.5 Implementar POST /api/v1/active-learning/{queue_id}/feedback
  - [x] 4.6 Implementar POST /api/v1/active-learning/{queue_id}/release
  - [x] 4.7 Verificar todos os testes passam (10/10)

- [x] 5. MongoDB Schema - Criar índices e coleções
  - [x] 5.1 Criar migration script para coleção active_learning_queue
  - [x] 5.2 Adicionar campos novos em specialist_feedback
  - [x] 5.3 Criar índices otimizados
  - [x] 5.4 Verificar schema com testes de integração

- [x] 6. Integração com ApprovalService
  - [x] 6.1 Write tests para integração (4 testes)
  - [x] 6.2 Integrar enqueue automático em approval requests
  - [x] 6.3 Marcar feedbacks com balanced_dataset=True
  - [x] 6.4 Verificar fluxo E2E com testes

- [x] 7. E2E Tests - Validação do fluxo completo
  - [x] 7.1 Testar análise de balanceamento
  - [x] 7.2 Testar enfileiramento e desenfileiramento
  - [x] 7.3 Testar claim e release de casos
  - [x] 7.4 Testar submissão de feedback com marcação
  - [x] 7.5 Verificar todos os testes E2E passam (7/7)

- [x] 8. Deploy e Monitoração
  - [x] 8.1 Configurar variáveis de ambiente
  - [x] 8.2 Deploy para staging (main.py + .env.example)
  - [x] 8.3 Validar métricas em produção (docs/ACTIVE_LEARNING_DEPLOY.md)
  - [x] 8.4 Criar dashboard de balanceamento (docs/ACTIVE_LEARNING_DASHBOARD.json)
