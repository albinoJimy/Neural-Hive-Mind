# Property-Based Tests com Hypothesis

Este diretório contém testes property-based usando o framework Hypothesis.

## O que são Property-Based Tests?

Testes property-based verificam propriedades invariantes do código que devem ser verdadeiras para **qualquer** entrada válida, em vez de testar casos específicos. O Hypothesis gera centenas de exemplos aleatórios para encontrar edge cases que testes manuais poderiam perder.

## Arquivos

- `test_execution_ticket_properties.py` - Testes para o modelo ExecutionTicket
- `test_scheduler_properties.py` - Testes para IntelligentScheduler

## Como Rodar

### Rodar todos os testes property-based
```bash
pytest tests/property/ -v
```

### Rodar com mais exemplos (para hunting de bugs)
```bash
pytest tests/property/ --hypothesis-max-examples=1000 -v
```

### Rodar com saída verbosa (para debug)
```bash
pytest tests/property/ --hypothesis-verbosity=verbose -v
```

### Rodar um teste específico
```bash
pytest tests/property/test_execution_ticket_properties.py::TestExecutionTicketProperties::test_calculate_hash_is_deterministic -v
```

## Integração CI/CD

Para adicionar os testes property-based ao pipeline CI/CD, adicione o seguinte step após os testes unitários:

```yaml
- name: Run property-based tests
  run: |
    cd services/orchestrator-dynamic
    pytest tests/property/ --hypothesis-max-examples=200 --hypothesis-derandomize
```

### Flags recomendadas para CI/CD

- `--hypothesis-max-examples=200` - Mais exemplos que o padrão (100) para melhor cobertura
- `--hypothesis-derandomize` - Execuções determinísticas para reprodutibilidade
- `--hypothesis-print-blob=false` - Evita logs muito grandes

## Escrita de Novos Testes

### Template básico

```python
from hypothesis import given, settings, Phase
from hypothesis import strategies as st

class TestMyProperties:
    @given(st.integers(), st.integers())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_commutative_property(self, a, b):
        """Property: a + b == b + a"""
        assert a + b == b + a
```

### Estratégias comuns

```python
# Strings
st.text(min_size=1, max_size=100)

# Integers
st.integers(min_value=0, max_value=1000)

# Floats (sem NaN/infinito)
st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Lists
st.lists(st.integers(), max_size=10)

# Dictionaries
st.dictionaries(keys=st.text(), values=st.integers())

# Enumerations
st.sampled_from([MyEnum.A, MyEnum.B, MyEnum.C])

# UUIDs
st.uuids()

# Composites (estruturas complexas)
@st.composite
def my_strategy(draw):
    x = draw(st.integers())
    y = draw(st.text())
    return MyObject(x=x, y=y)
```

## Referências

- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [Property-Based Testing](https://hypothesis.works/articles/what-is-property-based-testing/)
