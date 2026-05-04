# Unified Gateway

Gateway unificado do Neural Hive-Mind na porta 7999.

## Descrição

O Unified Gateway é o ponto único de entrada para todos os clientes do Neural Hive-Mind. Ele implementa:

- **Autenticação JWT** (INV-7): Valida tokens e extrai `user_id`, `tenant_id` para passar downstream
- **Rate Limiting** (INV-8): Rate limiting por tenant com Redis, retorna HTTP 429 com `Retry-After`
- **Health Checks** (INV-10): Endpoint `/health` retorna `{status, version}`
- **Tracing Distribuído** (INV-11): Propaga `traceparent` header entre serviços

## Endpoints

### Health Check

```
GET /health
```

Retorna:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Root

```
GET /
```

Retorna informações do serviço.

## Configuração

Variáveis de ambiente:

- `PORT`: Porta do serviço (padrão: 7999)
- `ENVIRONMENT`: Ambiente (development/production)
- `RATE_LIMIT_REDIS_URL`: URL do Redis para rate limiting
- `JWT_SECRET`: Secret para validação JWT (development apenas)

## Executando Localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar serviço
uvicorn src.main:app --host 0.0.0.0 --port 7999 --reload
```

## Testes

```bash
pytest
```

## Docker

```bash
docker build -t unified-gateway .
docker run -p 7999:7999 unified-gateway
```

## Invariants Implementados

- **INV-7**: JWT tokens validados extraem `user_id`, `tenant_id` para downstream
- **INV-8**: Rate limiting por tenant antes de serviços downstream, retorna HTTP 429
- **INV-10**: Health check com `{status, version}` JSON
- **INV-11**: Tracing distribuído propagado via `traceparent`
