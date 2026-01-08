# Neural Hive Specialists Library

Biblioteca Python para implementação de especialistas no Neural Hive-Mind.

## Visão Geral

Esta biblioteca fornece a infraestrutura base para criar especialistas que avaliam planos cognitivos. Cada especialista analisa planos sob uma perspectiva específica (arquitetura, comportamento, negócios, etc.) e emite pareceres estruturados.

## Instalação

```bash
pip install -e libraries/python/neural_hive_specialists
```

## Arquitetura gRPC

### Fluxo de Chamada

```
1. Cliente gRPC → Envia EvaluatePlanRequest para porta do especialista
2. SpecialistServicer (grpc_server.py) → Recebe request, extrai contexto
3. BaseSpecialist (base_specialist.py) → Orquestra pipeline completo
4. Especialista Concreto → Implementa _evaluate_plan_internal()
5. SpecialistServicer → Converte dict para protobuf response
6. Cliente gRPC ← Recebe EvaluatePlanResponse
```

### Métodos Implementados

| Método | Descrição | Implementação |
|--------|-----------|---------------|
| `EvaluatePlan` | Avalia plano cognitivo | `SpecialistServicer.EvaluatePlan()` → `BaseSpecialist.evaluate_plan()` |
| `HealthCheck` | Verifica saúde do serviço | `SpecialistServicer.HealthCheck()` → `BaseSpecialist.health_check()` |
| `GetCapabilities` | Retorna capacidades | `SpecialistServicer.GetCapabilities()` → `BaseSpecialist.get_capabilities()` |

### Pipeline de Avaliação (BaseSpecialist.evaluate_plan)

1. **Deserialização** - Converte bytes para dict (JSON/Avro)
2. **Validação de Schema** - Valida estrutura do plano
3. **Sanitização PII** - Remove dados sensíveis (se habilitado)
4. **Verificação de Cache** - Consulta cache Redis
5. **Inferência ML** - Modelo MLflow ou fallback heurístico
6. **Explainability** - Gera explicações SHAP/LIME
7. **Persistência** - Salva parecer no ledger MongoDB
8. **Métricas** - Atualiza contadores Prometheus
9. **Cache** - Armazena resultado para reuso

## Implementando Novo Especialista

Para criar um novo especialista:

### 1. Herdar de BaseSpecialist

```python
from neural_hive_specialists import BaseSpecialist

class MySpecialist(BaseSpecialist):
    """Especialista customizado."""

    def _get_specialist_type(self) -> str:
        """Retorna identificador único do especialista."""
        return "my_specialist"

    def _load_model(self):
        """Carrega modelo ML do MLflow (ou retorna None para heurísticas)."""
        if self.mlflow_client is None:
            return None

        try:
            return self.mlflow_client.load_model(
                self.config.mlflow_model_name,
                self.config.mlflow_model_stage
            )
        except Exception:
            return None  # Fallback para heurísticas

    def _evaluate_plan_internal(
        self,
        cognitive_plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Implementa lógica de avaliação específica."""
        tasks = cognitive_plan.get('tasks', [])

        # Sua lógica de análise aqui
        confidence_score = self._analyze_tasks(tasks)
        risk_score = 1.0 - confidence_score

        return {
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'recommendation': 'approve' if confidence_score > 0.8 else 'review_required',
            'reasoning_summary': 'Análise concluída com sucesso',
            'reasoning_factors': [
                {
                    'factor_name': 'custom_metric',
                    'weight': 0.5,
                    'score': confidence_score,
                    'description': 'Métrica customizada'
                }
            ],
            'mitigations': []
        }
```

### 2. Criar Configuração

```python
from neural_hive_specialists.config import SpecialistConfig

class MySpecialistConfig(SpecialistConfig):
    """Configuração específica do especialista."""
    custom_threshold: float = 0.7
```

### 3. Criar Servidor gRPC

```python
from neural_hive_specialists import create_grpc_server_with_observability

# Instanciar especialista
config = MySpecialistConfig()
specialist = MySpecialist(config)

# Criar e iniciar servidor
grpc_server = create_grpc_server_with_observability(specialist, config)
grpc_server.start()
grpc_server.wait_for_termination()
```

## Especialistas Disponíveis

| Especialista | Tipo | Porta | Análise |
|--------------|------|-------|---------|
| Architecture | `architecture` | 50051 | Design patterns, SOLID, coupling/cohesion |
| Behavior | `behavior` | 50052 | UX, acessibilidade, tempos de resposta |
| Business | `business` | 50053 | Workflows, KPIs, custos |
| Evolution | `evolution` | 50054 | Manutenibilidade, escalabilidade, tech debt |
| Technical | `technical` | 50055 | Segurança, arquitetura, performance |

## Estrutura de Resposta

### EvaluatePlanResponse

```protobuf
message EvaluatePlanResponse {
    string opinion_id = 1;
    string specialist_type = 2;
    string specialist_version = 3;
    SpecialistOpinion opinion = 4;
    int32 processing_time_ms = 5;
    google.protobuf.Timestamp evaluated_at = 6;
}

message SpecialistOpinion {
    double confidence_score = 1;    // 0.0-1.0
    double risk_score = 2;          // 0.0-1.0
    string recommendation = 3;       // approve, reject, review_required, conditional
    string reasoning_summary = 4;
    repeated ReasoningFactor reasoning_factors = 5;
    string explainability_token = 6;
    repeated MitigationSuggestion mitigations = 7;
    map<string, string> metadata = 8;
}
```

## Observabilidade

Cada chamada gRPC é instrumentada com:

- **OpenTelemetry Tracing** - Spans automáticos via `GrpcInstrumentorServer`
- **Prometheus Metrics** - Latência, taxa de sucesso, scores
- **Structured Logging** - Logs JSON com contexto completo

### Métricas Expostas

- `specialist_evaluation_duration_seconds` - Histograma de latência
- `specialist_evaluation_total` - Contador de avaliações
- `specialist_confidence_score` - Gauge de confiança
- `specialist_risk_score` - Gauge de risco

## Segurança

- **JWT Authentication** - Via `AuthInterceptor` (opcional)
- **mTLS** - Suporte via SPIFFE/SPIRE
- **Tenant Isolation** - Propagação de `x-tenant-id` via metadata
- **PII Sanitization** - Remoção automática de dados sensíveis

## Testes

### Unitários

```bash
cd libraries/python/neural_hive_specialists
pytest tests/test_grpc_server.py -v
```

### Integração

```bash
# Requer especialistas rodando
pytest tests/integration/test_grpc_integration.py -v -m integration
```

### E2E

```bash
python scripts/debug/test-grpc-comprehensive.py --specialist architecture
```

## Desenvolvimento

### Regenerar Protobuf Stubs

```bash
cd libraries/python/neural_hive_specialists
python -m grpc_tools.protoc \
    -I proto \
    --python_out=proto_gen \
    --grpc_python_out=proto_gen \
    proto/specialist.proto
```

### Executar Especialista Localmente

```bash
cd services/specialist-architecture
python src/main.py
```
