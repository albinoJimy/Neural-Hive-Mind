# Arquitetura gRPC dos Especialistas Neurais

## Visão Geral

Os especialistas neurais expõem interface gRPC definida em `specialist.proto` com 3 métodos:
- `EvaluatePlan`: Avalia plano cognitivo e retorna parecer
- `HealthCheck`: Verifica saúde do especialista
- `GetCapabilities`: Retorna metadados e capacidades

## Estrutura de Arquivos

### Definições Proto
- **Proto**: `schemas/specialist-opinion/specialist.proto`
- **Stubs gerados**: `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2_grpc.py`
  - ⚠️ **IMPORTANTE**: Este arquivo é auto-gerado e contém apenas stubs com `NotImplementedError`
  - ❌ **NÃO MODIFICAR**: Qualquer mudança será sobrescrita na próxima compilação

### Implementação Real
- **Servicer**: `libraries/python/neural_hive_specialists/grpc_server.py`
  - Classe `SpecialistServicer` implementa os 3 métodos
  - Converte dict (retornado por `BaseSpecialist`) para protobuf responses
  - Integra observabilidade (OpenTelemetry, métricas, baggage)

### Factory Function
- **Função**: `create_grpc_server_with_observability(specialist, config)`
  - Cria servidor gRPC com interceptors (auth, tracing)
  - Registra `SpecialistServicer` no servidor
  - Configura health check service (gRPC Health v1)

## Fluxo de Chamada

```
Consensus Engine → SpecialistServiceStub → SpecialistServicer → BaseSpecialist → ML Model
                                                    ↓
                                        _build_evaluate_plan_response(dict)
                                                    ↓
                                        EvaluatePlanResponse (protobuf)
```

**Sequência detalhada**:
1. Consensus Engine chama `stub.EvaluatePlan(request)`
2. Stub envia request via gRPC para o Servicer
3. Servicer chama `specialist.evaluate_plan(request)`
4. BaseSpecialist processa e retorna dict
5. Servicer converte dict para protobuf via `_build_evaluate_plan_response()`
6. Response protobuf retorna ao Consensus Engine

## Clients

### Consensus Engine
- **Arquivo**: `services/consensus-engine/src/clients/specialists_grpc_client.py`
- **Classe**: `SpecialistsGrpcClient`
- **Métodos**:
  - `evaluate_plan(specialist_type, cognitive_plan, trace_context)`: Invoca 1 especialista
  - `evaluate_plan_parallel(cognitive_plan, trace_context)`: Invoca 5 em paralelo
  - `health_check_all()`: Verifica saúde de todos

### Uso
```python
client = SpecialistsGrpcClient(config)
await client.initialize()
opinions = await client.evaluate_plan_parallel(cognitive_plan, trace_context)
```

## Observabilidade

### OpenTelemetry
- Spans automáticos via `GrpcInstrumentorServer`
- Atributos: `specialist.type`, `plan.id`, `opinion.confidence_score`, etc.
- Baggage propagation: `intent_id`, `plan_id`, `user_id`

### Métricas Prometheus
- `specialist_evaluations_total{specialist_type, status}`
- `specialist_evaluation_duration_seconds{specialist_type}`
- `specialist_model_predictions_total{specialist_type, model_version}`

### Logs Estruturados
- Todos os logs via `structlog`
- Contexto: `plan_id`, `intent_id`, `specialist_type`, `processing_time_ms`

## Autenticação

### JWT via AuthInterceptor
- **Habilitado**: `config.enable_jwt_auth=True`
- **Endpoints públicos**: `HealthCheck`, `GetCapabilities`
- **Endpoints protegidos**: `EvaluatePlan`
- **Header**: `authorization: Bearer <token>`

### Configuração
```python
config = SpecialistConfig(
    enable_jwt_auth=True,
    jwt_secret_key="...",
    jwt_algorithm="RS256",
    jwt_public_endpoints=["/neural_hive.specialist.SpecialistService/HealthCheck"]
)
```

## Testes

### Integração
- `libraries/python/neural_hive_specialists/tests/integration/test_grpc_integration.py`
- Testa todos os 5 especialistas
- Valida protobuf serialization/deserialization

### Autenticação
- `libraries/python/neural_hive_specialists/tests/test_auth_integration.py`
- Testa JWT válido/inválido/expirado

### Client
- `services/consensus-engine/tests/test_specialists_grpc_client.py`
- Testa client com mocks

## Troubleshooting

### Erro: "Method not implemented!"
- **Causa**: Servicer não registrado no servidor
- **Solução**: Verificar que `PROTO_AVAILABLE=True` e `add_SpecialistServiceServicer_to_server()` foi chamado

### Erro: "Protobuf stubs not available"
- **Causa**: Proto não compilado ou import falhou
- **Solução**: Recompilar proto com `make proto-compile`

### Erro: "UNIMPLEMENTED" no client
- **Causa**: Servidor não iniciado ou endpoint incorreto
- **Solução**: Verificar logs do servidor e conectividade

## Compilação de Protos

### Comando
```bash
python -m grpc_tools.protoc \
  -I schemas/specialist-opinion \
  --python_out=libraries/python/neural_hive_specialists/proto_gen \
  --grpc_python_out=libraries/python/neural_hive_specialists/proto_gen \
  schemas/specialist-opinion/specialist.proto
```

### Makefile Target
```bash
make proto-compile
```

## Referências
- Proto: `schemas/specialist-opinion/specialist.proto`
- Servicer: `libraries/python/neural_hive_specialists/grpc_server.py`
- Client: `services/consensus-engine/src/clients/specialists_grpc_client.py`
- Tests: `libraries/python/neural_hive_specialists/tests/integration/test_grpc_integration.py`
