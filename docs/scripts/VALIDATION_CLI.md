# CLI de Validação Unificado

## Visão Geral

O `scripts/validate.sh` é o CLI unificado que consolida **75+ scripts de validação** em uma interface consistente.

## Uso Básico

```bash
# Validar tudo
./scripts/validate.sh --target all

# Validar specialists
./scripts/validate.sh --target specialists

# Validar observabilidade
./scripts/validate.sh --target observability
```

## Targets Disponíveis

| Target | Descrição | Scripts Consolidados |
|--------|-----------|---------------------|
| `infrastructure` | Infraestrutura (Kafka, Redis, MongoDB, Neo4j) | 5 scripts |
| `services` | Serviços (Gateway, Consensus, Memory Layer) | 15 scripts |
| `specialists` | Specialists (health, models, inference) | 5 scripts |
| `security` | Segurança (Vault, SPIRE, mTLS, OPA) | 7 scripts |
| `observability` | Observabilidade (Prometheus, Grafana, Jaeger) | 8 scripts |
| `performance` | Performance (SLOs, benchmarks) | 5 scripts |
| `phase` | Validação por fase | 5 scripts |
| `e2e` | End-to-end | 5 scripts |
| `all` | Validação completa | Todos |

## Opções

- `--phase <1|2|all>` - Validar fase específica
- `--component <NAME>` - Validar componente específico
- `--namespace <NS>` - Namespace Kubernetes
- `--report <FORMAT>` - Formato: console, json, html, all
- `--report-file <FILE>` - Arquivo de saída
- `--fix` - Tentar corrigir problemas
- `--verbose` - Modo verbose
- `--quick` - Modo rápido (pula testes longos)

## Exemplos

### Validação Completa com Relatório HTML
```bash
./scripts/validate.sh --target all --report html --report-file /tmp/report.html
```

### Validar Specialist Específico
```bash
./scripts/validate.sh --target specialists --component business --verbose
```

### Validação Rápida de Infraestrutura
```bash
./scripts/validate.sh --target infrastructure --quick
```

### Validar Fase 2
```bash
./scripts/validate.sh --target phase --phase 2
```

### Validação CI/CD
```bash
./scripts/validate.sh --target all --report json --report-file validation.json
```

## Relatórios

### Console (padrão)
Output colorido no terminal com resumo de testes.

### JSON
```json
{
  "report_metadata": {
    "script_name": "validate.sh",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "test_results": {
    "business_pod_status": {
      "status": "PASS",
      "criticality": "high",
      "score": 7
    }
  },
  "summary": {
    "total_tests": 50,
    "passed_tests": 48,
    "failed_tests": 2,
    "health_percentage": 96
  }
}
```

### HTML
Relatório visual com gráficos, tabelas e status coloridos.

## Integração com CI/CD

```yaml
# .github/workflows/validation.yml
- name: Validar Neural Hive-Mind
  run: |
    ./scripts/validate.sh --target all --report json --report-file validation.json
    
- name: Upload Relatório
  uses: actions/upload-artifact@v3
  with:
    name: validation-report
    path: validation.json
```

## Migração de Scripts Antigos

| Script Antigo | Novo Comando |
|---------------|--------------|
| `validate-all-specialists.sh` | `validate.sh --target specialists` |
| `validate-observability.sh` | `validate.sh --target observability` |
| `validate-phase2-deployment.sh` | `validate.sh --target phase --phase 2` |
| `validate-infrastructure-local.sh` | `validate.sh --target infrastructure` |

## Troubleshooting

### Erro: "Target inválido"
Verifique se o target está correto: `infrastructure`, `services`, `specialists`, `security`, `observability`, `performance`, `phase`, `e2e`, `all`

### Erro: "Namespace não encontrado"
Especifique o namespace: `--namespace <NS>`

### Testes falhando
Use `--verbose` para ver detalhes: `./scripts/validate.sh --target all --verbose`
