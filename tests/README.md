# Neural Hive-Mind Test Suite

## Visão Geral

Suite de testes unificada consolidando 45+ scripts em CLI único.

## Estrutura

```
tests/
├── run-tests.sh              # CLI unificado
├── unit/                     # Testes unitários (Python)
├── integration/              # Testes integração (Python + bash)
├── e2e/                      # Testes E2E
│   ├── phase1/               # E2E Phase 1
│   ├── phase2/               # E2E Phase 2
│   └── specialists/          # E2E Specialists
├── specialists/              # Testes specialists
├── services/                 # Testes serviços
├── performance/              # Testes performance
└── lib/                      # Bibliotecas compartilhadas
```

## Uso do CLI

### Comandos Básicos

```bash
# Executar todos os testes
./tests/run-tests.sh

# Executar testes por tipo
./tests/run-tests.sh --type unit
./tests/run-tests.sh --type integration
./tests/run-tests.sh --type e2e

# Executar testes por fase
./tests/run-tests.sh --type e2e --phase 1
./tests/run-tests.sh --type e2e --phase 2

# Executar testes por componente
./tests/run-tests.sh --component specialists
./tests/run-tests.sh --component gateway
./tests/run-tests.sh --component consensus
```

### Opções Avançadas

```bash
# Com cobertura
./tests/run-tests.sh --type unit --coverage

# Execução paralela
./tests/run-tests.sh --type integration --parallel --jobs 8

# Dry-run (mostrar testes sem executar)
./tests/run-tests.sh --type e2e --dry-run

# Debug mode
./tests/run-tests.sh --type e2e --phase 1 --debug
```

### Via Makefile

```bash
make test                # Todos os testes
make test-unit           # Unit tests
make test-integration    # Integration tests
make test-e2e            # E2E tests
make test-phase1         # Phase 1 tests
make test-phase2         # Phase 2 tests
make test-specialists    # Specialist tests
make test-coverage       # Com cobertura
make test-parallel       # Paralelo
```

## Tipos de Teste

### Unit Tests
- **Localização**: `tests/unit/`
- **Framework**: pytest
- **Duração**: < 1 min
- **Comando**: `./tests/run-tests.sh --type unit`

### Integration Tests
- **Localização**: `tests/integration/`
- **Framework**: pytest + bash
- **Duração**: 5-10 min
- **Comando**: `./tests/run-tests.sh --type integration`

### E2E Tests
- **Localização**: `tests/e2e/`
- **Framework**: pytest + bash
- **Duração**: 30-90 min
- **Comando**: `./tests/run-tests.sh --type e2e`

## Relatórios

Relatórios gerados em `tests/results/`:
- `test-report-YYYYMMDD-HHMMSS.json` - Relatório JSON completo
- `test-summary-YYYYMMDD-HHMMSS.md` - Sumário Markdown
- `pytest-junit.xml` - JUnit XML (pytest)
- `coverage/` - Relatório cobertura HTML

## Troubleshooting

### Testes falhando com timeout
```bash
# Aumentar timeout (default: 600s)
export TEST_TIMEOUT=1200
./tests/run-tests.sh --type e2e
```

### Cleanup de recursos
```bash
# Limpar port-forwards e pods de teste
./tests/run-tests.sh --cleanup-only
```

### Ver logs detalhados
```bash
# Modo debug
./tests/run-tests.sh --type e2e --debug
```
