# Neural Hive Observability - Testes

Este diretório contém os testes unitários e de integração para a biblioteca `neural_hive_observability`.

## Estrutura de Arquivos

```
tests/
├── test_observability.py          # Testes gerais e de integração
├── test_kafka_instrumentation.py  # Testes de instrumentação Kafka
├── test_context.py                # Testes específicos do ContextManager
├── test_grpc_instrumentation.py   # Testes de instrumentação gRPC
├── test_exporters.py              # Testes de exportadores
└── README.md                      # Esta documentação
```

## Executando os Testes

### Todos os testes

```bash
cd libraries/python/neural_hive_observability
pytest tests/ -v
```

### Testes específicos

```bash
# Testes de validação do ContextManager
pytest tests/test_context.py -v

# Testes de instrumentação Kafka
pytest tests/test_kafka_instrumentation.py -v

# Apenas testes de integração
pytest tests/test_observability.py::TestIntegration -v
```

### Com cobertura de código

```bash
pytest tests/ -v --cov=neural_hive_observability --cov-report=html
```

## Categorias de Testes

### Testes de Validação

Verificam que erros de configuração são detectados e reportados corretamente:

- `TestContextManagerValidation` - Validação do `ContextManager.__init__`
- `TestInstrumentedKafkaProducerValidation` - Validação dos instrumentadores Kafka

Estes testes garantem comportamento fail-fast com mensagens de erro claras quando:
- `config` é `None`
- `config` não é uma instância de `ObservabilityConfig`
- `service_name` é `None`, vazio ou apenas espaços em branco

### Testes de Programação Defensiva

Verificam que código defensivo previne erros em runtime:

- `TestContextManagerDefensiveProgramming` - Verificações de `hasattr()`/`getattr()`

### Testes de Integração

Verificam o fluxo completo end-to-end:

- `TestIntegration` - Inicialização, instrumentação e uso conjunto

## Fixtures Utilizadas

### pytest-asyncio

Para testes assíncronos com `async/await`:

```python
@pytest.mark.asyncio
async def test_async_consumer():
    async for msg in consumer:
        assert msg is not None
```

### caplog

Para verificar logging durante testes:

```python
def test_logging(self, caplog):
    with caplog.at_level(logging.DEBUG):
        do_something()

    assert "expected message" in caplog.text
```

## Padrões de Mock

### Mock de ObservabilityConfig

Para testar validação sem acionar `__post_init__`:

```python
from unittest.mock import patch

with patch.object(ObservabilityConfig, '__post_init__', lambda self: None):
    config = ObservabilityConfig(service_name=None)
```

### Mock de módulos Kafka

Para simular confluent-kafka ou aiokafka sem instalá-los:

```python
import sys
import types

class FakeConfluentProducer:
    pass

fake_module = types.SimpleNamespace(Producer=FakeConfluentProducer)
sys.modules["confluent_kafka"] = fake_module

try:
    # Testes aqui
finally:
    sys.modules.pop("confluent_kafka", None)
```

### Mock de config global

Para testar comportamento quando config global não está disponível:

```python
from unittest.mock import patch

with patch('neural_hive_observability.kafka_instrumentation._config', None):
    result = instrument_kafka_producer(producer, None)
```

## Boas Práticas

1. **Sempre limpar estado global** - Use `try/finally` ou fixtures para garantir cleanup
2. **Testar mensagens de erro** - Verifique que exceções contêm informações úteis
3. **Testar logging** - Use `caplog` para verificar que erros são logados antes de exceções
4. **Isolar testes** - Cada teste deve ser independente dos outros
5. **Documentar intenção** - Docstrings devem explicar o que está sendo testado

## Debugging

Para executar com output detalhado:

```bash
pytest tests/ -v -s --log-cli-level=DEBUG
```

Para executar um único teste:

```bash
pytest tests/test_context.py::TestContextManagerValidation::test_context_manager_raises_value_error_when_config_is_none -v -s
```

## Cobertura Mínima Esperada

- `context.py`: > 90%
- `kafka_instrumentation.py`: > 90%
- `config.py`: > 85%
- `__init__.py`: > 80%

## Contribuindo

Ao adicionar novos testes:

1. Siga a nomenclatura `test_<funcionalidade>_<cenario>`
2. Adicione docstring explicativa
3. Agrupe em classes por funcionalidade testada
4. Use fixtures para setup/teardown complexo
5. Verifique que testes são idempotentes (podem rodar múltiplas vezes)
