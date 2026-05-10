# Guia de Migração para Clientes — Unified Gateway

> Spec: [`2026-05-01-unified-gateway-architecture`](../.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md)
> Ticket: TICKET-032
> Audiência: equipas que consomem APIs do Neural-Hive-Mind (NHM) — front-ends, integrações externas, scripts internos.
> Idioma: Português (PT-PT/PT-BR)

---

## TL;DR

**Antes** (mundo "múltiplos gateways"):

- O cliente tinha de escolher manualmente o gateway correto (`gateway-intencoes:8000`, `requirements-engineering:8010`, `doc-ingestion:8018`).
- Cada gateway tinha o seu próprio contrato (body, headers, autenticação).
- Auth e rate-limit eram aplicados de forma inconsistente em cada serviço.

**Depois** (Unified Gateway):

- Um único endpoint: `POST http://unified-gateway:7999/api/v1/nhm/request`.
- Body unificado: `{ "input": "...", "context": {...}, "language": "pt", "flow_type": "..." (opcional) }`.
- Header obrigatório: `Authorization: Bearer <jwt>`.
- O gateway classifica automaticamente o pedido (Fluxo A-F / G / H) e faz proxy para o serviço correcto.

---

## Por que migrar

1. **Endpoint único — `/api/v1/nhm/request`.** Deixa de ser preciso saber se o pedido é "intenção", "geração de requisitos" ou "ingestão documental". O classificador NLU + heurísticas decide.
2. **Classificação automática.** O `flow_type` é inferido a partir do `input` + `context`. O cliente continua a poder forçar `flow_type` (debug/testing), mas a recomendação é deixar o classificador decidir.
3. **Auth/rate-limit centralizados.** JWT validado no gateway com extracção de `tenant_id` e `user_id` (invariante INV-7), rate-limit por tenant em Redis. Os serviços downstream recebem requests já autenticados.
4. **Tracing distribuído end-to-end.** O gateway gera `request_id` (UUID), `trace_id` e `span_id` e propaga-os via headers `X-Tenant-ID`, `X-User-ID`, `X-Session-ID` para os serviços downstream.
5. **Resposta uniforme.** Mesma estrutura `NHMRequestResponse` independentemente do flow executado, simplificando o código cliente.
6. **Streaming SSE built-in.** Para operações longas, o cliente pode subscrever `GET /api/v1/nhm/stream/{request_id}` e receber actualizações em tempo real.

---

## Mapeamento de endpoints antigos → novo

A tabela abaixo lista os endpoints actualmente expostos por cada gateway downstream e o equivalente no Unified Gateway.

| Endpoint antigo                                                          | Novo endpoint unificado                                | `flow_type` inferido | Notas                                                                                              |
| ------------------------------------------------------------------------ | ------------------------------------------------------ | -------------------- | -------------------------------------------------------------------------------------------------- |
| `POST gateway-intencoes:8000/intentions`                                 | `POST unified-gateway:7999/api/v1/nhm/request`         | `A-F`                | Texto/intenção em PT-BR. Body antigo `{text, language, correlation_id, ...}` mapeia para `{input, language, context.correlation_id}`. |
| `POST gateway-intencoes:8000/intentions/voice`                           | `POST unified-gateway:7999/api/v1/nhm/request`         | `A-F`                | Voz transcrita ainda exige pré-processamento no cliente (transcrição → texto). O input final é texto.        |
| `GET gateway-intencoes:8000/intentions/{intent_id}`                      | `GET unified-gateway:7999/api/v1/nhm/status/{request_id}` | n/a               | Consulta de status passou a ser baseada em `request_id` (Redis-backed, TTL 24h).                   |
| `GET gateway-intencoes:8000/status`                                      | `GET unified-gateway:7999/health`                       | n/a                  | Health check segue o standard FastAPI (`/health`, `/health/ready`, `/health/live`).                |
| `POST requirements-engineering:8010/api/v1/requirements/generate`        | `POST unified-gateway:7999/api/v1/nhm/request`         | `G`                  | Geração de requisitos a partir de plano cognitivo. Passa `plan_id` e `plan_text` no `context`.     |
| `POST requirements-engineering:8010/api/v1/requirements`                 | `POST unified-gateway:7999/api/v1/nhm/request`         | `G`                  | Criar requisito manualmente. Passa o payload no `context.requirement`.                             |
| `POST requirements-engineering:8010/api/v1/api-design/generate`          | `POST unified-gateway:7999/api/v1/nhm/request`         | `G`                  | Geração de OpenAPI. Indicar intenção no `input` (ex.: "gerar OpenAPI para serviço X").             |
| `POST requirements-engineering:8010/api/v1/ui-ux-design/generate`        | `POST unified-gateway:7999/api/v1/nhm/request`         | `G`                  | Geração de design UI/UX.                                                                           |
| `GET requirements-engineering:8010/api/v1/requirements`                  | manter no serviço (uso interno)                        | n/a                  | Listagens read-only continuam expostas directamente para integrações internas.                    |
| `POST doc-ingestion:8018/api/v1/documents/upload`                        | `POST unified-gateway:7999/api/v1/nhm/request`         | `H`                  | Upload binário ainda requer multipart directo no `doc-ingestion` (ver "Casos especiais").          |
| `POST doc-ingestion:8018/api/v1/documents/{document_id}/parse`           | `POST unified-gateway:7999/api/v1/nhm/request`         | `H`                  | Disparar parsing do documento. Passar `document_id` no `context`.                                  |
| `POST doc-ingestion:8018/api/v1/documents/{document_id}/extract`         | `POST unified-gateway:7999/api/v1/nhm/request`         | `H`                  | Extracção de entidades.                                                                            |
| `POST doc-ingestion:8018/api/v1/documents/{document_id}/send-to-gateway` | obsoleto                                               | n/a                  | Já não é necessário — o Unified Gateway encadeia o fluxo automaticamente.                          |
| `GET doc-ingestion:8018/api/v1/documents/{document_id}/status`           | `GET unified-gateway:7999/api/v1/nhm/status/{request_id}` | n/a               | Status de jobs assíncronos via `request_id`.                                                       |

> Nota: o Unified Gateway faz proxy para o caminho `/api/v1/process` no gateway downstream (ver `services/unified-gateway/src/api/routers/request.py`). Os gateways downstream estão a ser ajustados para expor este caminho normalizado durante o Sprint 2 da spec. Durante o período de transição os endpoints antigos listados acima continuam a aceitar tráfego directo (ver "Backward compatibility").

---

## Mudanças no payload

### Body antigo (gateway-intencoes)

```json
{
  "text": "Quero analisar os dados de vendas do mês passado",
  "language": "pt-BR",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "constraints": { "priority": "high", "timeout_ms": 5000 },
  "qos": { "max_latency_ms": 2000 }
}
```

### Body novo (Unified Gateway)

```json
{
  "input": "Quero analisar os dados de vendas do mês passado",
  "context": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "domain": "business",
    "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "constraints": { "priority": "high", "timeout_ms": 5000 },
    "qos": { "max_latency_ms": 2000 },
    "metadata": { "client": "web-ui", "version": "2.3.1" }
  },
  "language": "pt",
  "flow_type": null
}
```

### Diferenças principais

| Antes               | Agora                       | Nota                                                                            |
| ------------------- | --------------------------- | ------------------------------------------------------------------------------- |
| `text`              | `input`                     | Renomeado. Limites: 1–10 000 caracteres.                                        |
| `language: "pt-BR"` | `language: "pt"`            | Códigos curtos ISO 639-1 (`pt`, `en`, `es`).                                    |
| `correlation_id`    | `context.correlation_id`    | Movido para dentro de `context`.                                                |
| `constraints`/`qos` | `context.constraints`/`qos` | Movidos para dentro de `context` (passa-os tal e qual).                         |
| n/a                 | `flow_type` (opcional)      | `A-F` / `G` / `H`. Forçar apenas em casos conhecidos. Default: `null` (auto).   |
| n/a                 | `context.metadata`          | Mapa livre `string→any` para tracking custom (cliente, versão, feature flags…). |

### Resposta nova

```json
{
  "request_id": "8f3b2a1c-...-...",
  "flow_type": "A-F",
  "status": "completed",
  "processing_time_ms": 234,
  "data": { "...": "payload específico do flow" },
  "error": null,
  "gateway_used": "gateway-intencoes",
  "trace_id": "abc123def456...",
  "fallback_used": false
}
```

Em caso de erro:

```json
{
  "request_id": "8f3b2a1c-...-...",
  "flow_type": "A-F",
  "status": "error",
  "processing_time_ms": 12,
  "data": null,
  "error": "Mensagem descritiva do erro",
  "gateway_used": null,
  "trace_id": null,
  "fallback_used": false
}
```

---

## Mudanças nos headers

| Header                                 | Antes                                          | Agora                                  |
| -------------------------------------- | ---------------------------------------------- | -------------------------------------- |
| `Authorization: Bearer <jwt>`          | Opcional/inconsistente entre gateways          | **Obrigatório** (HTTP 401 se ausente). |
| `X-Tenant-ID`                          | Por vezes lido directamente do body            | Extraído do JWT pelo gateway.          |
| `X-User-ID`                            | Por vezes lido directamente do body            | Extraído do JWT pelo gateway.          |
| `X-Session-ID`                         | Não normalizado                                | Propagado a partir do `context`.       |
| `X-Correlation-ID` / `X-Request-ID`    | Por vezes lido do header                       | Use `context.correlation_id` no body.  |
| `Retry-After` (resposta)               | Inconsistente                                  | Devolvido em 429.                      |
| `WWW-Authenticate: Bearer` (resposta)  | Inconsistente                                  | Devolvido em 401.                      |
| `X-Circuit-State` (resposta)           | n/a                                            | Devolvido em 503 (`open`/`half_open`). |

> Em ambiente de **desenvolvimento** o gateway aceita JWT sem verificação de assinatura (apenas formato + `exp`). Em **produção** a verificação é completa contra a chave pública configurada (`JWT_AUTH_REQUIRED=true`, `ENVIRONMENT=production`).

---

## Backward compatibility

Durante o período de transição:

- **Os gateways antigos (`gateway-intencoes:8000`, `requirements-engineering:8010`, `doc-ingestion:8018`) continuam a aceitar requests directos.** Não há corte abrupto.
- Não existe uma data limite rígida para a deprecação — depende do roadmap interno e da migração de cada consumer. Acompanhe as `decisions.md` da spec.
- A recomendação é **migrar progressivamente**:
  1. Apontar primeiro os fluxos de baixo risco (jobs batch, integrações internas).
  2. Validar em staging.
  3. Migrar produção.
- Internamente (serviço-a-serviço dentro do cluster Kubernetes) os endpoints antigos podem continuar a ser usados, mas todos os clientes externos devem passar pelo Unified Gateway.
- O gateway antigo `approval-gateway` está marcado para **deprecação** (consolidado em `approval-service` via Approval Core Package).

---

## Exemplos de código

### Antes — cURL para `gateway-intencoes:8000/intentions`

```bash
curl -X POST http://gateway-intencoes:8000/intentions \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Quero analisar os dados de vendas do mês passado",
    "language": "pt-BR",
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

### Depois — cURL para `unified-gateway:7999/api/v1/nhm/request`

```bash
curl -X POST http://unified-gateway:7999/api/v1/nhm/request \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...' \
  -d '{
    "input": "Quero analisar os dados de vendas do mês passado",
    "context": {
      "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
      "domain": "business"
    },
    "language": "pt"
  }'
```

### Antes — Python `requests` (chamada directa a `requirements-engineering`)

```python
import requests

response = requests.post(
    "http://requirements-engineering:8010/api/v1/requirements/generate",
    params={
        "plan_id": "plan-123",
        "plan_text": "Sistema deve permitir registo de utilizadores...",
    },
    timeout=10,
)
response.raise_for_status()
data = response.json()
print(data["requirements_set_id"], data["total"])
```

### Depois — Python `requests` (Unified Gateway)

```python
import os
import requests

GATEWAY_URL = os.environ["NHM_GATEWAY_URL"]   # ex.: http://unified-gateway:7999
JWT = os.environ["NHM_JWT"]

payload = {
    "input": "Gerar requisitos a partir do plano cognitivo plan-123",
    "context": {
        "plan_id": "plan-123",
        "plan_text": "Sistema deve permitir registo de utilizadores...",
    },
    "language": "pt",
    # flow_type omitido — deixar o classificador decidir (vai resolver para "G").
}

response = requests.post(
    f"{GATEWAY_URL}/api/v1/nhm/request",
    json=payload,
    headers={"Authorization": f"Bearer {JWT}"},
    timeout=10,
)
response.raise_for_status()
data = response.json()
print(data["request_id"], data["flow_type"], data["status"])
```

### Depois — Python `httpx` async

```python
import asyncio
import os

import httpx

GATEWAY_URL = os.environ["NHM_GATEWAY_URL"]
JWT = os.environ["NHM_JWT"]


async def submit_request(input_text: str) -> dict:
    payload = {
        "input": input_text,
        "context": {"domain": "business"},
        "language": "pt",
    }
    headers = {"Authorization": f"Bearer {JWT}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{GATEWAY_URL}/api/v1/nhm/request",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    result = asyncio.run(
        submit_request("Quero analisar os dados de vendas do mês passado")
    )
    print(result)
```

---

## Streaming (SSE)

Para operações longas (geração de código, parsing de documentos grandes, planos cognitivos complexos) o cliente pode obter actualizações em tempo real via Server-Sent Events.

**Fluxo recomendado:**

1. Submete o pedido em `POST /api/v1/nhm/request`. Recebe `request_id`.
2. Subscreve `GET /api/v1/nhm/stream/{request_id}` para receber eventos SSE.
3. Em alternativa, faz polling em `GET /api/v1/nhm/status/{request_id}` (intervalo recomendado: 2–5 s).

**Eventos SSE emitidos pelo gateway:**

- `connected` — stream estabelecido.
- `status` — status intermédio (`processing`).
- `completed` — request concluído com sucesso.
- `error` — request falhou.
- `keep-alive` — heartbeat de 5 s.
- `timeout` — timeout do stream (default 30 s, configurável até 300 s via `?timeout=`).
- `end` — stream terminado.

**Exemplo Python `httpx`:**

```python
import httpx
import json

REQUEST_ID = "8f3b2a1c-..."

with httpx.stream(
    "GET",
    f"{GATEWAY_URL}/api/v1/nhm/stream/{REQUEST_ID}?timeout=120",
    headers={"Authorization": f"Bearer {JWT}", "Accept": "text/event-stream"},
    timeout=None,
) as response:
    response.raise_for_status()
    event = None
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data = json.loads(line[len("data:"):].strip())
            print(event, data)
            if event in {"completed", "error", "timeout", "end"}:
                break
```

> Quando usar SSE: tarefas que ultrapassem ~5 s de processamento. Para tudo abaixo disso, basta esperar pela resposta síncrona do `POST /api/v1/nhm/request`.

---

## Erros comuns na migração

| HTTP status | Causa típica                                                                       | Como resolver                                                                                                  |
| ----------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **401**     | Falta o header `Authorization: Bearer …` ou JWT inválido/expirado                  | Confirmar que o JWT é emitido pelo Keycloak configurado e que tem `sub`, `tenant_id`, `user_id`, `exp` válidos. |
| **400**     | Body inválido (`input` em falta, demasiado longo, ou `flow_type` não reconhecido)  | Validar contra o schema `NHMRequest`. `input` é obrigatório (1–10 000 chars).                                  |
| **429**     | Rate-limit excedido para o tenant                                                  | Respeitar `Retry-After`. Se o tenant precisa de mais quota, abrir ticket de operações.                         |
| **503**     | Circuit breaker aberto para o gateway downstream (header `X-Circuit-State: open`)  | Tentar novamente após backoff exponencial. Se persistir, é uma falha do serviço downstream — abrir incidente.  |
| **500**     | Erro interno (NLU service indisponível, Redis down, etc.)                          | Verificar `/health` do gateway e dos serviços `nlu_service`, `redis`, `kafka`.                                 |

**Anti-padrões frequentes:**

- ❌ Forçar `flow_type` "para garantir" — perde o benefício da classificação automática.
- ❌ Continuar a chamar `gateway-intencoes:8000` directamente em código novo.
- ❌ Passar `tenant_id`/`user_id` no body — esses campos são extraídos do JWT.
- ❌ Tratar `request_id` como opcional — é a chave para SSE/status/tracing.

---

## Checklist de migração

- [ ] Inventariar todos os locais no código cliente que chamam `gateway-intencoes:8000`, `requirements-engineering:8010` ou `doc-ingestion:8018`.
- [ ] Obter um JWT válido do Keycloak para o ambiente alvo (dev/staging/prod) e armazená-lo de forma segura (variável de ambiente, secret manager).
- [ ] Substituir o URL base por `unified-gateway:7999` (interno) ou `https://api.neural-hive-mind.com` (externo).
- [ ] Renomear `text` → `input`, mover `correlation_id`/`constraints`/`qos` para dentro de `context`.
- [ ] Adicionar header `Authorization: Bearer <jwt>` em todas as chamadas.
- [ ] Remover lógica cliente que decidia "qual gateway chamar" — deixar o classificador automático tratar disso.
- [ ] Para operações longas (>5 s), passar a usar SSE via `/api/v1/nhm/stream/{request_id}` ou polling em `/api/v1/nhm/status/{request_id}`.
- [ ] Adicionar tratamento explícito para 401 (renovar JWT) e 429 (respeitar `Retry-After`).
- [ ] Validar end-to-end em staging antes de promover para produção.
- [ ] Activar tracing e validar que `trace_id`/`span_id` aparecem em Jaeger/Tempo.

---

## FAQ

### 1. Preciso de mudar URLs internos serviço-a-serviço?

Não imediatamente. O Unified Gateway é primariamente para **clientes externos** (front-ends, integrações, scripts). Comunicações internas entre serviços dentro do cluster Kubernetes podem continuar a usar os endpoints directos durante o período de transição. Avaliar caso-a-caso conforme os serviços downstream forem refactorizados.

### 2. Como faço staging vs produção?

O endpoint difere apenas no host:

- **Local/dev:** `http://localhost:7999`
- **Cluster interno:** `http://unified-gateway:7999` ou `https://unified-gateway.neural-hive.local`
- **Produção:** `https://api.neural-hive-mind.com`

O resto do contrato (paths, body, headers) é idêntico. O JWT tem de ser emitido pelo Keycloak do ambiente correspondente.

### 3. Tenho de forçar `flow_type` em algum caso?

Apenas para **debug**, **testes** ou casos em que sabes que o classificador está a errar (e nesse caso abre um ticket para ajustar a heurística/NLU). Em produção, deixar `flow_type` a `null` é a recomendação.

### 4. Como migro o upload de documentos (multipart)?

O upload binário continua a precisar de chamada directa ao `doc-ingestion:8018/api/v1/documents/upload` (multipart), porque o Unified Gateway recebe JSON. O fluxo recomendado é:

1. Upload do ficheiro directamente para `doc-ingestion`. Recebes um `document_id`.
2. Disparar o pipeline (`parse`/`extract`) via `POST /api/v1/nhm/request` passando `document_id` no `context`.

Esta limitação está documentada na spec e pode ser endereçada num sprint futuro (presigned upload através do gateway).

### 5. Como obtenho um JWT?

Via Keycloak (`keycloak.neural-hive.local`):

```bash
curl -X POST 'https://keycloak.neural-hive.local/realms/nhm/protocol/openid-connect/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' \
  -d 'client_id=<your-client>' \
  -d 'client_secret=<your-secret>'
```

O `access_token` da resposta é o JWT a colocar em `Authorization: Bearer <token>`.

### 6. O `correlation_id` do pedido antigo continua a ser respeitado?

Sim — passa-o em `context.correlation_id`. O gateway emite-o no log estruturado, propaga-o para os serviços downstream via headers e adiciona-o aos eventos Kafka publicados pelo Response Processor. Adicionalmente, o gateway gera sempre um `request_id` próprio (UUID) que é a chave canónica para SSE/status. Trata-os como complementares: `request_id` é interno do NHM, `correlation_id` é a chave do lado do cliente.

---

## Referências

- Spec: [`.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`](../.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md)
- OpenAPI do Unified Gateway: [`services/unified-gateway/openapi.yaml`](../services/unified-gateway/openapi.yaml)
- Routers (fonte de verdade dos contratos):
  - [`services/unified-gateway/src/api/routers/request.py`](../services/unified-gateway/src/api/routers/request.py)
  - [`services/unified-gateway/src/api/routers/status.py`](../services/unified-gateway/src/api/routers/status.py)
  - [`services/unified-gateway/src/api/routers/stream.py`](../services/unified-gateway/src/api/routers/stream.py)
- Documentos relacionados:
  - [`docs/ARQUITETURA_COEXISTENCIA_FLUXOS_2026-05-01.md`](./ARQUITETURA_COEXISTENCIA_FLUXOS_2026-05-01.md)
  - [`docs/CODE_REVIEW_UNIFIED_GATEWAY_SPEC_2026-05-06.md`](./CODE_REVIEW_UNIFIED_GATEWAY_SPEC_2026-05-06.md)
