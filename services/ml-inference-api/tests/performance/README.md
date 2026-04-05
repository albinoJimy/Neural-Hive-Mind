# Testes de Performance - ML Inference API

Testes de performance conforme especificado no **ML-001-08**.

## Estrutura

```
tests/performance/
├── __init__.py
├── conftest.py           # Fixtures para testes de performance
├── test_latency.py       # Testes de latência (p50, p95, p99)
├── test_throughput.py    # Testes de throughput
├── test_concurrent.py    # Testes de concorrência
├── test_memory.py        # Testes de uso de memória
├── generate_report.py    # Script para gerar relatório consolidado
└── README.md             # Este arquivo
```

## Targets do Spec

| Métrica | Target |
|---------|--------|
| Latência p50 | < 50ms |
| Latência p99 | < 200ms |
| Throughput | > 1000 req/s |
| Eficiência Batch | 10x mais eficiente que individual |

## Instalação de Dependências

```bash
# Instalar dependências de performance
pip install -e ".[performance]"

# Ou instalar manualmente
pip install pytest pytest-asyncio pytest-benchmark pytest-json-report memory-profiler locust
```

## Execução dos Testes

### Executar todos os testes de performance

```bash
# Sem cobertura (mais rápido para performance)
pytest tests/performance/ -m performance --no-cov -v

# Com coverage
pytest tests/performance/ -m performance -v
```

### Executar apenas testes específicos

```bash
# Apenas latência
pytest tests/performance/test_latency.py -v

# Apenas throughput
pytest tests/performance/test_throughput.py -v

# Apenas concorrência
pytest tests/performance/test_concurrent.py -v

# Apenas memória
pytest tests/performance/test_memory.py -v
```

### Executar teste específico

```bash
pytest tests/performance/test_latency.py::test_api_predict_latency_p50 -v
```

## Gerar Relatório

O script `generate_report.py` gera um relatório consolidado em HTML ou texto.

```bash
# Gerar relatório HTML (executa testes automaticamente)
python tests/performance/generate_report.py --output performance_report.html --format html

# Gerar relatório em texto
python tests/performance/generate_report.py --output performance_report.txt --format text

# Gerar relatório sem executar testes (usa resultado anterior)
python tests/performance/generate_report.py --no-run --output performance_report.html
```

## Fixtures Disponíveis

### `performance_client`
Cliente HTTP assíncrono com mocks para máxima velocidade de teste.

### `sample_request_data`
Dados de request padrão para testes.

### `batch_request_factory`
Factory para criar batches de diferentes tamanhos.

```python
def create_batch(size: int) -> list[dict]:
    """Cria batch de requests com dados variados."""
```

### `latency_metrics`
Coletor de métricas de latência com métodos para p50, p95, p99.

### `performance_targets`
Dicionário com os targets do spec.

### `memory_profiler`
Fixture para profiling de memória (requer `memory_profiler` instalado).

## Marcadores

Use marcadores pytest para selecionar testes:

```bash
# Apenas testes de performance
pytest -m performance

# Excluir testes de performance
pytest -m "not performance"
```

## Notas Importantes

### Ambiente de Teste

Os testes usam mocks do `ApprovalPredictor` para garantir:
- Execução rápida e consistente
- Reprodutibilidade dos resultados
- Independência de hardware/modelo ML

Para configurar latência simulada, use a variável de ambiente:
```bash
export MOCK_LATENCY_MS=1  # 1ms de latência simulada
```

### Interpretação de Resultados

- **Valores absolutos** podem variar com a carga da máquina
- **Tendências** são mais importantes que valores absolutos
- **Comparações** (ex: paralelo vs sequencial) são confiáveis
- **Targets** são baseados em specs do projeto ML-001-08

### Testes de Memória

Os testes de memória (`test_memory.py`) requerem `memory_profiler`.
Se não estiver instalado, estes testes serão pulados automaticamente.

## Troubleshooting

### Erro "No module named 'memory_profiler'"

```bash
pip install memory-profiler
```

### Testes muito lentos

Use `--no-cov` para desabilitar cobertura:
```bash
pytest tests/performance/ -m performance --no-cov
```

### Erro "asyncio_mode"

Certifique-se que `pytest-asyncio` está instalado e configurado:
```bash
pip install pytest-asyncio>=0.23.0
```

## Integração CI/CD

Para CI/CD, execute apenas um subconjunto de testes de performance
para manter builds rápidos:

```bash
# Apenas testes críticos de latência
pytest tests/performance/test_latency.py::test_api_predict_latency_p50 -v --no-cov
pytest tests/performance/test_latency.py::test_api_predict_latency_p99 -v --no-cov

# Apenas teste crítico de throughput
pytest tests/performance/test_throughput.py::test_api_throughput_burst -v --no-cov
```

## Referências

- Spec ML-001-08: Performance Tests
- Documentação pytest: https://docs.pytest.org/
- pytest-benchmark: https://pytest-benchmark.readthedocs.io/
- memory_profiler: https://pypi.org/project/memory-profiler/
