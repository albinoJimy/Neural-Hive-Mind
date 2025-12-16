# Neo4j Intent Seeding Guide

Guia para popular o Neo4j com intents históricos do MongoDB, habilitando queries de similar intents no Semantic Translation Engine.

## Problema Resolvido

O `query_similar_intents()` retorna 0 resultados porque o Neo4j não possui dados históricos de intents. Este script resolve o Issue #2 do relatório E2E, populando o grafo de conhecimento com intents existentes no MongoDB.

## Pré-requisitos

- Python 3.9+
- Acesso ao MongoDB (collection `cognitive_ledger`)
- Acesso ao Neo4j (credenciais)

### Instalação de Dependências

```bash
pip install pymongo neo4j structlog
```

## Uso Básico

### Simulação (Dry Run)

Sempre execute primeiro em modo dry-run para verificar:

```bash
python scripts/seed_neo4j_intents.py \
    --mongodb-uri mongodb://localhost:27017 \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-password <sua-senha> \
    --dry-run
```

### Execução Real

```bash
python scripts/seed_neo4j_intents.py \
    --mongodb-uri mongodb://localhost:27017 \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-password <sua-senha>
```

### Teste com Poucos Registros

```bash
python scripts/seed_neo4j_intents.py \
    --mongodb-uri mongodb://localhost:27017 \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-password <sua-senha> \
    --limit 100
```

### Exemplo Completo (Kubernetes)

```bash
python scripts/seed_neo4j_intents.py \
    --mongodb-uri mongodb://mongodb.neural-hive.svc.cluster.local:27017 \
    --mongodb-database neural_hive \
    --mongodb-collection cognitive_ledger \
    --neo4j-uri bolt://neo4j.neural-hive.svc.cluster.local:7687 \
    --neo4j-user neo4j \
    --neo4j-password <sua-senha> \
    --neo4j-database neo4j \
    --batch-size 200
```

## Parâmetros

| Parâmetro | Obrigatório | Default | Descrição |
|-----------|-------------|---------|-----------|
| `--mongodb-uri` | Sim | - | URI de conexão MongoDB |
| `--mongodb-database` | Não | `neural_hive` | Nome do database MongoDB |
| `--mongodb-collection` | Não | `cognitive_ledger` | Collection com planos cognitivos |
| `--neo4j-uri` | Sim | - | URI de conexão Neo4j (bolt://) |
| `--neo4j-user` | Não | `neo4j` | Usuário Neo4j |
| `--neo4j-password` | Sim | - | Senha Neo4j |
| `--neo4j-database` | Não | `neo4j` | Database Neo4j |
| `--batch-size` | Não | `100` | Intents por batch |
| `--limit` | Não | - | Limitar número de intents |
| `--dry-run` | Não | `false` | Simular sem modificar Neo4j |

## Fluxo de Execução

1. **Conecta ao MongoDB** - Verifica conectividade
2. **Busca intents** - Query na collection `cognitive_ledger`
3. **Conecta ao Neo4j** - Verifica conectividade
4. **Cria Intent nodes** - Processa em batches com MERGE (idempotente)
5. **Cria índices** - Para queries eficientes
6. **Valida seed** - Conta nodes criados
7. **Exibe resumo** - Estatísticas finais

## Schema Neo4j

### Intent Node

```
(:Intent {
    id: String,           // ID único do intent
    text: String,         // Texto original do intent (para busca CONTAINS)
    domain: String,       // Domínio (ex: "vendas", "suporte", "unknown")
    confidence: Float,    // Confiança (0.0-1.0)
    timestamp: String,    // Data/hora do processamento
    plan_id: String,      // ID do plano cognitivo gerado
    outcome: String,      // "success" ou "error"
    keywords: String,     // Keywords extraídos (top 5, para busca)
    seeded_at: DateTime   // Timestamp do seed
})
```

**Nota**: O domínio usa `'unknown'` como fallback consistente em todo o sistema (seed, persistência e queries).

### Índices Criados

```cypher
CREATE INDEX intent_id_idx IF NOT EXISTS FOR (i:Intent) ON (i.id)
CREATE INDEX intent_domain_idx IF NOT EXISTS FOR (i:Intent) ON (i.domain)
CREATE INDEX intent_timestamp_idx IF NOT EXISTS FOR (i:Intent) ON (i.timestamp)
```

### Queries de Verificação

```cypher
-- Contar total de Intent nodes
MATCH (i:Intent) RETURN count(i) as total

-- Listar intents por domínio
MATCH (i:Intent)
RETURN i.domain, count(*) as total
ORDER BY total DESC

-- Buscar intents recentes
MATCH (i:Intent)
WHERE i.timestamp IS NOT NULL
RETURN i.id, i.domain, i.timestamp
ORDER BY i.timestamp DESC
LIMIT 10

-- Similar intents (query usada pelo STE)
MATCH (i:Intent {domain: "vendas"})
WHERE i.text CONTAINS "produto"
RETURN i.id, i.text, i.outcome
ORDER BY i.timestamp DESC
LIMIT 5
```

## Troubleshooting

### Erro de Conexão MongoDB

```
Falha ao conectar ao MongoDB
```

**Soluções:**
- Verificar URI e credenciais
- Testar conectividade: `mongosh <uri>`
- Verificar se MongoDB está rodando

### Erro de Conexão Neo4j

```
Falha ao conectar ao Neo4j
```

**Soluções:**
- Verificar URI (bolt:// não http://)
- Verificar porta (7687 para bolt)
- Verificar credenciais
- Testar: `cypher-shell -a <uri> -u neo4j -p <senha>`

### Timeout em Grandes Volumes

**Soluções:**
- Reduzir `--batch-size` (ex: 50)
- Usar `--limit` para processar em partes
- Executar em horário de menor carga

### Intents Duplicados

O script é **idempotente** - usa `MERGE` ao invés de `CREATE`. Executar múltiplas vezes não cria duplicatas.

## Manutenção

### Executar Periodicamente

Para backfill de novos intents, agende execução periódica:

```bash
# Cron job diário às 3h
0 3 * * * /usr/bin/python3 /path/to/seed_neo4j_intents.py \
    --mongodb-uri mongodb://... \
    --neo4j-uri bolt://... \
    --neo4j-password ... \
    >> /var/log/neo4j-seed.log 2>&1
```

### Limpar Dados do Neo4j

```cypher
-- CUIDADO: Remove TODOS os Intent nodes
MATCH (i:Intent) DETACH DELETE i

-- Remover apenas intents antigos (> 30 dias)
MATCH (i:Intent)
WHERE i.timestamp < datetime() - duration('P30D')
DETACH DELETE i
```

### Verificar Integridade

```cypher
-- Intents sem domain
MATCH (i:Intent)
WHERE i.domain IS NULL OR i.domain = ''
RETURN count(i)

-- Intents sem plan_id
MATCH (i:Intent)
WHERE i.plan_id IS NULL
RETURN i.id, i.domain
```

## Integração com STE

### Após o Seed

Após executar o seed, o `query_similar_intents()` retornará resultados:

```python
# Antes do seed
similar_intents = await neo4j.query_similar_intents("criar relatório", "vendas")
# Retorna: []

# Após o seed
similar_intents = await neo4j.query_similar_intents("criar relatório", "vendas")
# Retorna: [{"id": "...", "text": "...", "outcome": "success", ...}]
```

### Persistência Automática

Novos intents são automaticamente persistidos pelo orchestrator após o processamento bem-sucedido. O seed é necessário apenas para:

1. **Bootstrap inicial** - Popular com dados históricos
2. **Backfill** - Recuperar intents de antes da implementação da persistência

### Verificar no STE

Após o seed, verifique os logs do STE:

```
# Antes do seed
WARNING: Nenhum similar intent encontrado no Neo4j

# Após o seed
INFO: Similar intents encontrados | count=3 | similar_ids=['intent-123', 'intent-456']
```
