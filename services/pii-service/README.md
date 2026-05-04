# PII Service

Serviço centralizado de detecção e mascaramento de informações sensíveis (PII) para Neural Hive-Mind.

## Características

- **Detecção de PII**: 23 tipos de PII suportados (INV-2: 7 tipos requeridos)
- **Mascaramento**: 3 estratégias (MASK_FULL, MASK_PARTIAL, MASK_REDACT)
- **Unmask Reversível**: Suporte para desmascaramento via AES-256-GCM (INV-14)
- **Audit Logging**: Todas as operações registradas em MongoDB (INV-13)
- **API Dupla**: REST (FastAPI) e gRPC
- **Autenticação**: JWT required para operações sensíveis (R-P4)

## Tipos de PII Suportados

### Requeridos (INV-2)
- EMAIL
- PHONE
- CPF
- CNPJ
- CREDIT_CARD
- SSN
- ADDRESS

### Adicionais (23 tipos totais para R-P3)
- IP_ADDRESS
- UUID
- API_KEY
- NIF (Portugal)
- IBAN (Europa)
- PASSPORT
- POSTAL_CODE
- RG (Brasil)
- TITULO_ELEITOR (Brasil)
- BANK_ACCOUNT (Brasil)
- PERSON (via NLP)
- ORG (via NLP)
- DATE (via NLP)

## Estratégias de Mascaramento (INV-2)

- **MASK_FULL**: Substituir por tag (ex: `[EMAIL]`)
- **MASK_PARTIAL**: Mascaramento parcial (ex: `j***@domain.com`)
- **MASK_REDACT**: Remover completamente (vazio)
- **MASK_HASH**: Substituir por hash SHA-256

## Endpoints REST

### Detect
```http
POST /api/v1/pii/detect
Content-Type: application/json
Authorization: Bearer <token>

{
  "text": "João Silva, email joao@example.com",
  "types": ["EMAIL", "PERSON"],
  "min_confidence": 0.7
}
```

### Mask
```http
POST /api/v1/pii/mask
Content-Type: application/json
Authorization: Bearer <token>

{
  "text": "João Silva, email joao@example.com",
  "strategy": "MASK_PARTIAL",
  "enable_reversible": true,
  "enable_audit_log": true
}
```

### Unmask
```http
POST /api/v1/pii/unmask
Content-Type: application/json
Authorization: Bearer <token>

{
  "mask_id": "<encrypted_token>",
  "enable_audit_log": true
}
```

### Health Check
```http
GET /health
```

## Desenvolvimento

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar testes
pytest

# Executar serviço
uvicorn src.main:app --reload --port 8021
```

## Invariants Satisfeitos

- **INV-2**: PII Detection Types - 7 tipos com positions
- **INV-13**: PII Audit Logging - Operações em MongoDB
- **INV-14**: PII Unmask Reversibility - AES-256-GCM

## Requisitos Satisfeitos

- **R-P2**: Extração de PII detection de neural_hive_specialists/compliance
- **R-P3**: 23 PII types, 3 masking strategies
- **R-P4**: Audit logging MongoDB, unmask reversível AES-256-GCM, JWT auth required
