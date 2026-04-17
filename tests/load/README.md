# Load Tests - Doc Ingestion & Data Migration

Testes de carga utilizando Locust para os serviços Doc Ingestion (8018) e Data Migration (8019).

## Índice

- [Instalação](#instalação)
- [Configuração](#configuração)
- [Execução](#execução)
- [Cenários de Teste](#cenários-de-teste)
- [Métricas e Resultados](#métricas-e-resultados)
- [Throughput Target](#throughput-target)

## Instalação

### Dependências

```bash
pip install locust>=2.15.0 httpx>=0.25.0
```

Ou usando o requirements do projeto:

```bash
pip install -r requirements-test.txt
```

## Configuração

### Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `DOC_INGESTION_HOST` | Host do serviço Doc Ingestion | `http://localhost:8018` |
| `DATA_MIGRATION_HOST` | Host do serviço Data Migration | `http://localhost:8019` |
| `USERS` | Número de usuários simultâneos | `10` |
| `SPAWN_RATE` | Taxa de criação de usuários/segundo | `1` |
| `RUN_TIME` | Duração do teste | `5m` |

### Locust Config

O arquivo `locust.conf` contém configurações padrão para execução dos testes.

## Execução

### Via Script (Recomendado)

```bash
# Teste rápido (1 minuto, 5 usuários)
./run_load_test.sh --users 5 --run-time 1m

# Teste normal (5 minutos, 10 usuários)
./run_load_test.sh

# Teste de pico (10 minutos, 30 usuários)
./run_load_test.sh --users 30 --spawn-rate 5 --run-time 10m

# Modo web (interface gráfica)
./run_load_test.sh --web --users 20 --run-time 30m
```

### Via CLI Locust

```bash
# Modo headless
locust -f doc_ingestion_migration_locustfile.py \
  --headless \
  --host http://localhost:8018 \
  -u 10 \
  -r 1 \
  -t 5m

# Modo web
locust -f doc_ingestion_migration_locustfile.py \
  --host http://localhost:8018 \
  --ui
```

## Cenários de Teste

### Doc Ingestion (8018)

| Cenário | Peso | Descrição |
|---------|------|-----------|
| Upload Document | 3 | Upload de arquivo PDF com metadados |
| Check Status | 2 | Verificar status de processamento |
| Get Details | 1 | Obter detalhes completos do documento |
| List Documents | 1 | Listar documentos com paginação |
| Parse Document | 1 | Solicitar parsing do documento |
| Extract Entities | 1 | Solicitar extração de entidades |
| Get Entities | 1 | Obter entidades extraídas |

### Data Migration (8019)

| Cenário | Peso | Descrição |
|---------|------|-----------|
| Create Job | 2 | Criar novo job de migração |
| Get Status | 3 | Verificar status do job |
| List Jobs | 1 | Listar jobs com paginação |
| Get Schema | 1 | Obter mapeamento de schema |
| Start Migration | 1 | Iniciar execução da migração |
| Pause Migration | 1 | Pausar migração em andamento |
| Validate Migration | 1 | Validar dados migrados |

### Usuário Misto

Testa ambos os serviços simultaneamente, simulando um cenário real de uso.

## Métricas e Resultados

### Métricas Coletadas

- **Throughput**: Requisições por segundo
- **Response Time**: Tempo de resposta (p50, p95, p99)
- **Success Rate**: Percentual de requisições bem-sucedidas
- **Error Rate**: Percentual de requisições com erro

### Relatórios

Ao final de cada teste, Locust gera um relatório com:

1. Estatísticas de requisições
2. Distribuição de tempos de resposta
3. Exception breakdown
4. Resumo customizado (por service)

### Histórico de Resultados

Resultados anteriores são armazenados em `results/`.

## Throughput Target

### Doc Ingestion

- **Normal**: 100 documentos/hora (~1.7 docs/min)
- **Peak**: 300 documentos/hora (~5 docs/min)
- **Stress**: 1000 documentos/hora (~16.7 docs/min)

### Data Migration

- **Normal**: 20 jobs/hora (~0.33 jobs/min)
- **Peak**: 60 jobs/hora (~1 job/min)
- **Stress**: 200 jobs/hora (~3.3 jobs/min)

### Interpretação

- **Normal**: Carga esperada em operação padrão
- **Peak**: Carga máxima esperada (3x normal)
- **Stress**: Teste de resistência (10x normal)

## Troubleshooting

### Erro: Connection Refused

Verifique se os serviços estão rodando:

```bash
curl http://localhost:8018/health
curl http://localhost:8019/health
```

### Erro: Module Not Found

Instale as dependências:

```bash
pip install locust>=2.15.0 httpx>=0.25.0
```

### Performance Baixa

1. Verifique recursos da máquina (CPU, memória)
2. Reduza número de usuários
3. Aumente `wait_time` no locustfile

## Desenvolvimento

### Adicionar Novo Cenário

Edite `doc_ingestion_migration_locustfile.py` e adicione um novo método decorado com `@task()`:

```python
@task(1)
def novo_cenario(self):
    with self.client.get("/novo/endpoint", catch_response=True) as response:
        if response.status_code == 200:
            response.success()
        else:
            response.failure(f"Falha: {response.status_code}")
```

### Adicionar Nova Métrica Customizada

Use event handlers no final do arquivo:

```python
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    # Lógica customizada
    pass
```

## Referências

- [Locust Documentation](https://docs.locust.io/)
- [Doc Ingestion API](../../services/doc-ingestion/docs/API.md)
- [Data Migration API](../../services/data-migration/docs/API.md)
