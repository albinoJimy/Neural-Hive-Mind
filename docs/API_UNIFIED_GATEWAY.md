# API — Unified Gateway

Documento de referência para integração com o **Unified Gateway** do Neural Hive Mind (NHM). Cobre autenticação, rate limiting, classificação de fluxos, exemplos cURL e códigos de erro.

> Spec de referência: `.agent-os/specs/2026-05-01-unified-gateway-architecture/`
> Especificação OpenAPI canónica: [`services/unified-gateway/openapi.yaml`](../services/unified-gateway/openapi.yaml)

---

## 1. Visão Geral

O Unified Gateway é o **único ponto de entrada público** do NHM. Todos os clientes — webapps, CLIs, integrações externas — falam apenas com este serviço. O Gateway centraliza:

- **Autenticação JWT** (Bearer token, validação Keycloak)
- **Rate limiting por tenant** (Redis-backed, sliding window)
- **Classificação de intenção** via NLU Service (gRPC) com fallback heurístico
- **Roteamento dinâmico** para os gateways especializados (A-F, G, H)
- **Tracking de status** de requests assíncronos (Redis com TTL de 24h)
- **Streaming SSE** para acompanhamento em tempo real

| Ambiente            | Base URL                                       |
| ------------------- | ---------------------------------------------- |
| Local               | `http://localhost:7999`                        |
| Cluster interno     | `https://unified-gateway.neural-hive.local`    |
| Produção            | `https://api.neural-hive-mind.com`             |

---

## 2. Endpoints Principais

| Método | Path                                  | Descrição                                            | Auth |
| ------ | ------------------------------------- | ---------------------------------------------------- | ---- |
| `GET`  | `/health`                             | Health check geral                                   | —    |
| `GET`  | `/health/ready`                       | Readiness probe (Kubernetes)                         | —    |
| `GET`  | `/health/live`                        | Liveness probe (Kubernetes)                          | —    |
| `GET`  | `/metrics`                            | Métricas Prometheus                                  | —    |
| `POST` | `/api/v1/nhm/request`                 | Endpoint principal — classifica e roteia request     | JWT  |
| `POST` | `/api/v1/nhm/intent/parse`            | Apenas classifica intenção (não executa flow)        | JWT  |
| `POST` | `/api/v1/nhm/batch`                   | Processa até 100 requests em lote                    | JWT  |
| `GET`  | `/api/v1/nhm/status/{request_id}`     | Consulta status de request (polling)                 | JWT  |
| `GET`  | `/api/v1/nhm/stream/{request_id}`     | Stream SSE com atualizações em tempo real            | JWT  |
| `GET`  | `/api/v1/nhm/capabilities`            | Lista capacidades e fluxos suportados                | —    |

---

## 3. Autenticação

O Gateway aceita **JWT Bearer tokens** emitidos pelo Keycloak. O token deve ser enviado no header `Authorization`:

```http
Authorization: Bearer <jwt-token>
```

### Claims requeridos

| Claim         | Descrição                                                        |
| ------------- | ---------------------------------------------------------------- |
| `sub`         | Identificador do usuário (mapeado para `user_id`)                |
| `tenant_id`   | ID do tenant (também aceita `aud`)                               |
| `exp`         | Timestamp de expiração (validado obrigatoriamente)               |
| `roles`       | Lista de roles — usadas para determinar tier de rate limiting    |
| `session_id`  | (opcional) Identificador de sessão; também aceita `sid`          |

### Headers propagados para downstream

Após validação do JWT o Gateway anexa headers de contexto às chamadas para os gateways especializados (invariante INV-7):

- `X-User-ID`
- `X-Tenant-ID`
- `X-Session-ID`
- `X-Auth-Method` (`jwt`, `api_key`, `oauth2`, `none`)
- `X-Authenticated` (`true` / `false`)
- `X-User-Roles` (CSV)

### Paths excluídos da autenticação

`/health*`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`.

---

## 4. Rate Limiting

Rate limiting é aplicado **por tenant** antes de qualquer chamada downstream (invariante INV-8). O backend é Redis com algoritmo de **janela deslizante de 1 minuto** e contador atómico (`INCR` + `EXPIRE`).

### Tiers

O tier é deduzido a partir das `roles` no JWT:

| Tier         | Trigger (role) | Limite (req/min) | Burst |
| ------------ | -------------- | ---------------- | ----- |
| `trial`      | `trial`        | 10               | 15    |
| `default`    | (qualquer)     | 100              | 150   |
| `enterprise` | `enterprise`   | 1000             | 1500  |

Se nenhuma role corresponder, aplica-se `default`. Requests não autenticados usam `tenant_id = "anonymous"` com limites do tier `default`.

### Headers de resposta

Em **todas** as respostas (sucesso ou 429):

| Header                   | Descrição                                              |
| ------------------------ | ------------------------------------------------------ |
| `X-RateLimit-Limit`      | Limite total da janela actual                          |
| `X-RateLimit-Remaining`  | Requests restantes na janela                           |
| `X-RateLimit-Reset`      | Unix timestamp em que a janela expira                  |
| `Retry-After`            | (apenas em 429) segundos até a janela reiniciar        |

### Exemplo de resposta 429

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1746878400
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded. Try again in 42s",
  "retry_after": 42
}
```

### Fail-open

Se o Redis estiver indisponível, o rate limiter falha em modo **open** (request é permitido). Isto é registado em logs e métricas para alerta operacional.

---

## 5. Fluxos de Classificação

O Gateway classifica cada request num de 3 *flow types* a partir do texto e de heurísticas (com fallback a partir do NLU Service quando este está em circuit-breaker). O `flow_type` final aparece em `data.flow_type` na resposta e é o critério de roteamento.

| Flow   | Domínio                                | Quando é escolhido                                                         | Gateway downstream                |
| ------ | -------------------------------------- | -------------------------------------------------------------------------- | --------------------------------- |
| `A-F`  | Cognitive Pipeline (BUSINESS)          | Análise de dados, dashboards, relatórios, perguntas analíticas             | `gateway-intencoes:8000`          |
| `G`    | Code Generation (TECHNICAL)            | Geração de código, scaffolding de apps, IaC, requisitos técnicos           | `requirements-engineering:8010`   |
| `H`    | Migration (INFRASTRUCTURE / SECURITY)  | Modernização de legado, migração entre stacks, auditoria de docs antigos   | `doc-ingestion:8018`              |

### Override explícito

Para debugging/testing é possível forçar um flow via campo `flow_type` no body — a classificação NLU é ignorada e a confiança fica em `1.0` com `reasoning = "Flow type explícito fornecido"`.

### Domínios NLU

Os domínios reportados pelo NLU Service são `BUSINESS`, `TECHNICAL`, `INFRASTRUCTURE`, `SECURITY`. O mapeamento para flow types é feito pelo `IntentClassifier` interno e pode incluir alternativas (campo `alternative` na resposta detalhada).

---

## 6. Exemplos cURL

### 6.1 `POST /api/v1/nhm/request`

```bash
curl -X POST "https://api.neural-hive-mind.com/api/v1/nhm/request" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Quero analisar as vendas do trimestre passado por região",
    "language": "pt",
    "context": {
      "domain": "business",
      "session_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  }'
```

**Resposta (200):**

```json
{
  "request_id": "7f3e9a2b-1c4d-4e6f-9a8b-2d3e4f5a6b7c",
  "flow_type": "A-F",
  "status": "completed",
  "processing_time_ms": 1247,
  "data": {
    "summary": "Vendas do Q1: ...",
    "charts": [...]
  },
  "gateway_used": "gateway-intencoes",
  "trace_id": "abc123...",
  "fallback_used": false
}
```

### 6.2 `GET /api/v1/nhm/status/{request_id}` (polling)

```bash
curl -X GET "https://api.neural-hive-mind.com/api/v1/nhm/status/7f3e9a2b-1c4d-4e6f-9a8b-2d3e4f5a6b7c" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Resposta — request ainda em processamento:**

```json
{
  "request_id": "7f3e9a2b-1c4d-4e6f-9a8b-2d3e4f5a6b7c",
  "exists": true,
  "status": {
    "request_id": "7f3e9a2b-1c4d-4e6f-9a8b-2d3e4f5a6b7c",
    "status": "processing",
    "flow_type": null,
    "processing_time_ms": null,
    "created_at": "2026-05-10T12:34:56.123Z",
    "completed_at": null,
    "error": null,
    "gateway_used": null,
    "data": null
  }
}
```

**Resposta — request expirado / inexistente:**

```json
{
  "request_id": "7f3e9a2b-1c4d-4e6f-9a8b-2d3e4f5a6b7c",
  "exists": false,
  "status": null
}
```

> Status são persistidos no Redis com TTL de **24h** (`STATUS_TTL_SECONDS = 86400`). Após esse período, `exists` retorna `false`.

### 6.3 `GET /api/v1/nhm/stream/{request_id}` (Server-Sent Events)

```bash
curl -N -X GET "https://api.neural-hive-mind.com/api/v1/nhm/stream/7f3e9a2b-1c4d-4e6f-9a8b-2d3e4f5a6b7c?timeout=60" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Accept: text/event-stream"
```

> `-N` desactiva buffering no cURL; é essencial para SSE.

**Stream típico:**

```
event: connected
data: {"request_id":"7f3e9a2b-...","message":"Stream connected"}
retry: 3000

event: status
data: {"request_id":"7f3e9a2b-...","status":"processing","flow_type":null,...}

event: keep-alive
data: {"timestamp":"2026-05-10T12:35:01.456Z"}

event: completed
data: {"request_id":"7f3e9a2b-...","status":"completed","flow_type":"A-F","processing_time_ms":1247,...}

event: end
data: {"request_id":"7f3e9a2b-...","message":"Stream ended"}
```

### Tipos de evento SSE

| Evento       | Significado                                                       | Encerra o stream? |
| ------------ | ----------------------------------------------------------------- | ----------------- |
| `connected`  | Handshake inicial. Inclui `retry: 3000` (cliente reconecta em 3s) | não               |
| `status`     | Status mudou e ainda está em `processing`                         | não               |
| `completed`  | Request concluído com sucesso                                     | **sim**           |
| `error`      | Request falhou. Payload tem `error` preenchido                    | **sim**           |
| `keep-alive` | Heartbeat a cada 5s para manter a conexão                         | não               |
| `timeout`    | Stream excedeu o `timeout` configurado                            | **sim**           |
| `end`        | Evento final antes de o servidor fechar a conexão                 | **sim**           |

### Parâmetros de query

- `timeout` (int, 5–300, default 30) — duração máxima do stream em segundos.

### Headers de resposta

`Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (este último desactiva buffering em proxies nginx/ingress).

---

## 7. Códigos de Erro

| Status | `error`                  | Causa                                                              |
| ------ | ------------------------ | ------------------------------------------------------------------ |
| `400`  | `validation_error`       | Body inválido, `request_id` malformado, parâmetros fora de gama    |
| `401`  | `authentication_error`   | Header `Authorization` ausente, malformado ou JWT inválido/expirado |
| `429`  | `rate_limit_error`       | Tier excedido. Header `Retry-After` indica segundos até reset      |
| `500`  | `internal_error`         | Erro interno (ex. falha ao consultar Redis no endpoint de status)  |
| `503`  | `service_unavailable`    | Circuit breaker aberto para o gateway downstream alvo              |

### Estrutura de erro

```json
{
  "error": "authentication_error",
  "message": "Token has expired",
  "details": {},
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-05-10T12:34:56.789Z"
}
```

### Headers em situações específicas

- **401:** `WWW-Authenticate: Bearer realm="unified-gateway"`
- **429:** `Retry-After`, `X-RateLimit-*`
- **503:** `X-Circuit-State: open | half_open | closed`

---

## 8. Padrões de Integração

### Polling vs SSE

- **Polling** (`GET /status/{id}`) — recomendado para clientes simples ou quando a infraestrutura intermédia não suporta long-lived connections.
- **SSE** (`GET /stream/{id}`) — recomendado para UI interactiva. Lembre-se de configurar reconexão automática (o servidor envia `retry: 3000` no evento `connected`).

### Fluxo recomendado

1. Cliente envia `POST /api/v1/nhm/request` e recebe `request_id`.
2. Cliente abre stream SSE em `GET /stream/{request_id}` ou inicia polling em `GET /status/{request_id}`.
3. Cliente trata eventos `completed`/`error` e fecha a conexão.
4. Em caso de queda do stream, cliente reconecta usando o `retry` hint ou recorre ao polling.

---

## 9. Referências

- **OpenAPI canónica:** [`services/unified-gateway/openapi.yaml`](../services/unified-gateway/openapi.yaml)
- **Routers (código):**
  - [`src/api/routers/request.py`](../services/unified-gateway/src/api/routers/request.py)
  - [`src/api/routers/status.py`](../services/unified-gateway/src/api/routers/status.py)
  - [`src/api/routers/stream.py`](../services/unified-gateway/src/api/routers/stream.py)
- **Middlewares:**
  - [`src/middleware/jwt_auth.py`](../services/unified-gateway/src/middleware/jwt_auth.py)
  - [`src/middleware/rate_limit.py`](../services/unified-gateway/src/middleware/rate_limit.py)
- **Spec da arquitectura:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/`
- **Invariantes citadas:** INV-7 (propagação de contexto downstream), INV-8 (rate limiting + Retry-After).
