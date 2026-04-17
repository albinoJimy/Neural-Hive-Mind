# Fluxo H - Setup Desenvolvimento Local

> **Versão:** 1.0  
> **Data:** 2026-04-17  
> **Para:** Desenvolvedores e Engenheiros de DevOps

---

## Visão Geral

Este guia descreve como configurar o ambiente de desenvolvimento local para o Fluxo H (Legacy Migration System) usando Docker Compose.

---

## Pré-requisitos

### Software Necessário

- Docker 20.10+ 
- Docker Compose 2.0+
- Python 3.12+ (para desenvolvimento local)
- make (opcional, para comandos de atalho)

### Verificar Instalação

```bash
docker --version
docker-compose --version
python3 --version
```

---

## Setup Inicial

### 1. Clonar Repositório

```bash
git clone https://github.com/albinoJimy/Neural-Hive-Mind.git
cd Neural-Hive-Mind
```

### 2. Configurar Variáveis de Ambiente

```bash
# Criar ficheiro .env.local para desenvolvimento
cat > .env.local << 'EOF'
# LLM API Keys (opcional - para Entity Extraction)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Database Credentials (para produção usar valores seguros)
POSTGRES_USER=legacy_user
POSTGRES_PASSWORD=legacy_pass
POSTGRES_DB=legacy_db

# S3/MinIO (para desenvolvimento usar defaults)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
EOF
```

### 3. Construir Imagens Docker

```bash
# Construir apenas imagens do Fluxo H
docker-compose -f docker-compose-fluxo-h.yml build
```

---

## Iniciar Serviços

### Modo Desenvolvimento

```bash
# Iniciar todos os serviços
docker-compose -f docker-compose-fluxo-h.yml up -d

# Verificar status dos serviços
docker-compose -f docker-compose-fluxo-h.yml ps
```

### Serviços Iniciados

| Serviço | Porta | Descrição | Health Check |
|---------|-------|-----------|--------------|
| doc-ingestion | 8018 | Parse e extração de entidades | http://localhost:8018/health |
| data-migration | 8019 | Migração de dados | http://localhost:8019/health |
| postgres-legacy | 5432 | Base legada | pg_isready |
| kafka-connect | 8083 | Debezium CDC | http://localhost:8083/connectors |
| mongodb | 27017 | Document storage | - |
| kafka | 9092 | Messaging broker | - |
| minio | 9000, 9001 | S3-compatible storage | http://localhost:9001 |

---

## Verificar Setup

### 1. Health Checks

```bash
# Verificar Doc Ingestion Service
curl http://localhost:8018/health

# Verificar Data Migration System
curl http://localhost:8019/health

# Verificar Kafka Connect
curl http://localhost:8083/connectors

# Verificar PostgreSQL Legacy
docker exec -it $(docker-compose -f docker-compose-fluxo-h.yml ps -q postgres-legacy) \
  psql -U legacy_user -d legacy_db -c "SELECT version();"
```

### 2. Verificar Base de Dados Legada

```bash
# Conectar ao PostgreSQL
docker exec -it $(docker-compose -f docker-compose-fluxo-h.yml ps -q postgres-legacy) \
  psql -U legacy_user -d legacy_db

# No psql:
\dt                          # Listar tabelas
SELECT COUNT(*) FROM users;  # Contar usuários
\q                           # Sair
```

### 3. Verificar Kafka Topics

```bash
# Listar tópicos criados
docker exec -it $(docker-compose -f docker-compose-fluxo-h.yml ps -q kafka) \
  kafka-topics --bootstrap-server localhost:9092 --list
```

---

## Testar Fluxo H

### 1. Upload de Documento

```bash
# Fazer upload de um documento PDF de teste
curl -X POST http://localhost:8018/api/v1/documents/upload \
  -F "file=@tests/fixtures/sample.pdf" \
  -F "uploaded_by=test_user" \
  -F "project=test_project"
```

### 2. Parse Documento

```bash
# Iniciar parsing do documento
DOCUMENT_ID="<id_do_documento>"
curl -X POST http://localhost:8018/api/v1/documents/${DOCUMENT_ID}/parse
```

### 3. Extrair Entidades

```bash
# Extrair entidades usando LLM
curl -X POST http://localhost:8018/api/v1/documents/${DOCUMENT_ID}/extract \
  -H "Content-Type: application/json"
```

### 4. Criar Job de Migração

```bash
# Criar job de migração de dados
curl -X POST http://localhost:8019/api/v1/migrations/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "source_db": {
      "type": "postgresql",
      "host": "postgres-legacy",
      "port": 5432,
      "database": "legacy_db",
      "tables": ["users", "orders", "products"]
    },
    "target_db": {
      "type": "mongodb",
      "connection_string": "mongodb://mongodb:27017",
      "database": "new_system"
    },
    "strategy": "hybrid"
  }'
```

---

## Monitorar Serviços

### Logs

```bash
# Ver todos os logs
docker-compose -f docker-compose-fluxo-h.yml logs -f

# Ver logs de um serviço específico
docker-compose -f docker-compose-fluxo-h.yml logs -f doc-ingestion
docker-compose -f docker-compose-fluxo-h.yml logs -f data-migration

# Ver logs de múltiplos serviços
docker-compose -f docker-compose-fluxo-h.yml logs -f doc-ingestion data-migration
```

### Métricas

```bash
# Entrar num container para debug
docker exec -it $(docker-compose -f docker-compose-fluxo-h.yml ps -q doc-ingestion) bash

# Dentro do container:
python -m pytest tests/
pip list
```

---

## Troubleshooting

### Problema: Portas já em uso

**Sintoma:** Error binding port

```bash
# Verificar o que está a usar as portas
netstat -tuln | grep -E '8018|8019|5432|9000'

# Solução: Alterar portas no docker-compose-fluxo-h.yml
```

### Problema: Serviços não iniciam

**Sintoma:** Container restart loop

```bash
# Verificar logs do serviço com problema
docker-compose -f docker-compose-fluxo-h.yml logs <service-name>

# Verificar eventos do container
docker inspect <container-id>
```

### Problema: Debezium connector falha

**Sintoma:** CDC Pipeline não funciona

```bash
# Verificar status do connector
curl http://localhost:8083/connectors/data-migration-connector/status

# Verificar logs do Debezium
docker-compose -f docker-compose-fluxo-h.yml logs kafka-connect | grep ERROR

# Recrear connector
curl -X DELETE http://localhost:8083/connectors/data-migration-connector
# Recriar connector via API
```

### Problema: LLM API timeout

**Sintoma:** Entity extraction falha

```bash
# Verificar se API keys estão configuradas
docker-compose -f docker-compose-fluxo-h.yml exec doc-ingestion env | grep API_KEY

# Testar conectividade com LLM API
docker-compose -f docker-compose-fluxo-h.yml exec doc-ingestion \
  curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

---

## Parar Serviços

```bash
# Parar todos os serviços (preserva volumes)
docker-compose -f docker-compose-fluxo-h.yml down

# Parar e remover volumes (cuida: apaga dados!)
docker-compose -f docker-compose-fluxo-h.yml down -v

# Verificar containers parados
docker ps -a
```

---

## Desenvolvimento Local

### Editar Código

```bash
# Código fonte é montado como volume
# Pode editar diretamente em services/doc-ingestion/src ou services/data-migration/src
# Alterações são refletidas nos containers (necessita restart)

# Para ver alterações em Python, restart do serviço
docker-compose -f docker-compose-fluxo-h.yml restart doc-ingestion
```

### Testes Locais

```bash
# Entrar no container Doc Ingestion
docker exec -it $(docker-compose -f docker-compose-fluxo-h.yml ps -q doc-ingestion) bash

# Dentro do container:
cd /app
pytest tests/unit/test_pdf_parser.py -v
pytest tests/integration/test_e2e_doc_ingestion_flow.py -v
```

### Debug

```bash
# Habilitar debug mode (já está no docker-compose)
# Serviços iniciam com DEBUG=true

# Ver código em execução
docker exec -it $(docker-compose -f docker-compose-fluxo-h.yml ps -q doc-ingestion) \
  python -m pdb /app/src/main.py
```

---

## Integração com Serviços Existentes

O Fluxo H depende de outros serviços do Neural Hive Mind:

### Serviços Opcionais

Se já tiver estes serviços a correr, comente as seções correspondentes no `docker-compose-fluxo-h.yml`:

- Gateway Intenções (porta 8000)
- Orchestrator Dynamic (porta 8003)
- Service Registry (porta 50051, 8007)

### Integração

```bash
# Verificar se serviços externos estão acessíveis
curl http://localhost:8000/health  # Gateway
curl http://localhost:8003/health  # Orchestrator
curl http://localhost:50051        # Service Registry gRPC
```

---

## Limpar Recursos

```bash
# Remover containers e networks
docker-compose -f docker-compose-fluxo-h.yml down

# Remover volumes (apagar dados de teste)
docker-compose -f docker-compose-fluxo-h.yml down -v

# Limpar imagens Docker (opcional)
docker rmi $(docker images | grep fluxo-h | awk '{print $3}')
```

---

## Próximos Passos

Após setup completo:

1. ✅ **Testar Doc Ingestion** - Upload e parse de documentos
2. ✅ **Testar Entity Extraction** - Extração de entidades com LLM
3. ✅ **Testar Data Migration** - Criação de job de migração
4. ✅ **Testar CDC Pipeline** - Configurar connector Debezium
5. ✅ **Testar Cutover** - Migração gradual com rollback

---

## Referências

- [Fluxo H - Implementation Plan](../superpowers/plans/2026-04-16-fluxo-h-implementation-plan.md)
- [Fluxo H - Runbooks](../operations/fluxo-h-runbooks.md)
- [Fluxo H - Troubleshooting](../operations/troubleshooting-fluxo-h.md)
- [Architecture Doc](../ANALISE_FLUXOS.md)

---

**Suporte:** Operations Team  
**Última atualização:** 2026-04-17
