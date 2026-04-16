# Kafka Integration Tests - Neural Hive Mind

Testes E2E para validar fluxo completo Kafka entre serviços.

## Arquitetura de Testes

```
[cognitive.plans.created] → Architect Agent → [architecture.plans.generated]
                            → Software Engineering → [pipelines.generated]
[hypotheses.created] → Hypothesis Library → [hypotheses.validated]
[experiments.completed] → Experiment Impact Analyzer → [impact.analyzed]
[inference.requests] → ML Inference API → [inference.results]
```

## Estrutura de Testes

### Por Serviço

- **test_architect_agent.py** - Testa consumo de cognitive.plans.created e produção de architecture.plans.generated
- **test_software_engineering_pipeline.py** - Testa geração de manifests CI/CD
- **test_experiment_impact_analyzer.py** - Testa análise de impacto de experimentos
- **test_hypothesis_library.py** - Testa persistência e validação de hipóteses
- **test_ml_inference_api.py** - Testa predições ML via Kafka

### De Ponta a Ponta

- **test_full_cognitive_flow.py** - Testa fluxo completo: Gateway → STE → Architects → Pipeline
- **test_feedback_loop.py** - Testa loop de feedback: Experiment → Impact → Hypothesis

## Configuração

```bash
# Subir Kafka local para testes
docker-compose -f docker-compose.test.yml up -d

# Rodar testes
pytest tests/ -v --tb=short

# Testes específicos
pytest tests/test_architect_agent.py -v
pytest tests/test_full_cognitive_flow.py -v
```

## Fixtures

### Kafka Test Container
- Sobre Kafka/Zookeepr em container isolado
- Limpa tópicos entre testes
- Configura timeout adequado

### Mock Services
- Mock MongoDB
- Mock ML Models
- Mock External APIs

## Assertivas

- Mensagem consumida do tópico de entrada
- Processamento executado sem erros
- Mensagem publicada no tópico de saída
- Schema validado
- Latência dentro do limite
