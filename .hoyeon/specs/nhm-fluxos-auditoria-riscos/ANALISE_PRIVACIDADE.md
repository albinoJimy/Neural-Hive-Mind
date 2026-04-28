# Analise de Privacidade e Compliance PII/GDPR/LGPD

**Data:** 2026-04-27
**Responsavel:** T7 - Worker Agent
**Espec:** nhm-fluxos-auditoria-riscos

---

## 1. Resumo Executivo

Esta analise avalia o compliance do Neural Hive Mind (NHM) com requisitos de privacidade GDPR/LGPD, focando em PII (Personally Identifiable Information) em logs, encryption at-rest/in-transit, e politicas de retention/erasure.

**Status Geral:** PARCIALMENTE COMPLIANTE

### Principais Descobertas
- CRITICO: user_id e email sao logados em plaintext sem mascaramento
- CRITICO: Kafka configurado com listener plain sem TLS (port 9092 ativo)
- ALTO: Ausencia de indices TTL para dados PII em MongoDB
- MEDIO: RetentionManager implementado mas nao integrado em todos os servicos
- BAIXO: FieldEncryptor usa AES-128 (deveria ser AES-256)

---

## 2. Identificacao de PII no Sistema

### 2.1 Dados PII Processados

Baseado na analise dos modelos de dados e logs, o NHM processa:

| Tipo PII | Localizacao | Exemplo |
|----------|-------------|---------|
| `user_id` | JWT payload, logs | "test-admin", "user-abc" |
| `email` | JWT payload, logs | "admin@test.com" |
| `name` | JWT payload | "Test Admin" |
| `original_intent_text` | ApprovalRequest | Texto bruto da intent do usuario |
| `plan_id` | Logs, traces | Identificador de plano cognitivo |
| `intent_id` | Logs, traces | Identificador de intent |
| `correlation_id` | Logs distribuidos | ID de correlacao |
| `trace_id` | OpenTelemetry | ID de trace |

### 2.2 Modelos de Dados com PII

**ApprovalRequest** (`services/approval-service/src/models/approval.py`):
```python
class ApprovalRequest(BaseModel):
    approval_id: str
    plan_id: str
    intent_id: str
    original_intent_text: Optional[str]  # PII: texto livre do usuario
    risk_score: float
    risk_band: RiskBand
    approved_by: Optional[str]  # PII: user_id
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]  # PII: pode conter informacao do usuario
    comments: Optional[str]  # PII: pode conter informacao do usuario
    cognitive_plan: dict[str, Any]  # PII: pode conter contexto sensivel
```

**ContinuousFeedback** (`services/approval-service/src/models/continuous_feedback.py`):
```python
class ContinuousFeedback(BaseModel):
    user_id: Optional[str]  # PII: ID do usuario
    observations: str  # PII: texto livre de observacao
    feedback_text: Optional[str]  # PII: texto livre
```

---

## 3. Analise de PII Masking em Logs

### 3.1 Status: NAO COMPLIANTE

#### 3.1.1 user_id Logado em Plaintext

**Localizacao:** `services/approval-service/src/api/routers/approvals.py`

```python
logger.info("Consultando estatisticas de aprovacao", user_id=user["user_id"])
logger.info("Consultando predicao ML", plan_id=plan_id, user_id=user["user_id"])
logger.info("Consultando decisao automatica", plan_id=plan_id, user_id=user["user_id"])
logger.info("Buscando aprovacao", plan_id=plan_id, user_id=user["user_id"])
logger.info("Rejeitando plano", plan_id=plan_id, user_id=user["user_id"], reason=body.reason)
```

**Risco:** ALTO
- user_id pode ser correlacionado com outras fontes para identificar usuarios
- Logs podem ser acessados por多人 com permissao de leitura
- Nao ha mascaramento de caracteres (ex: "u***@***" ou hash)

#### 3.1.2 Email Logado em Plaintext (Debug)

**Localizacao:** `services/approval-service/src/security/auth.py`

```python
logger.debug("Usuario autenticado", user_id=user_info["user_id"], email=user_info.get("email"))
logger.debug("Admin autenticado", user_id=user["user_id"], email=user.get("email"))
```

**Risco:** MEDIO
- Log nivel debug pode nao estar activo em producao
- No entanto, quando activo, exibe email completo

#### 3.1.3 Padrao Estruturado em Todos os Servicos

**Padrao identificado em 11+ endpoints:**
- dashboard.py: 4 ocorrencias
- approvals.py: 5 ocorrencias
- continuous_feedback.py: 2 ocorrencias

### 3.2 Componentes de Masking Disponiveis mas NAO Utilizados

O NHM possui bibliotecas de PII masking implementadas:

**PIIMasker** (`libraries/python/neural_hive_specialists/compliance/pii_masker.py`):
- Suporta estrategias: PARTIAL, FULL, HASH, REDACT
- Integracao com spaCy NER para deteccao de PII
- Preserva formato de emails, telefones, etc.

**PIIDetector** (`libraries/python/neural_hive_specialists/compliance/pii_detector.py`):
- Usa Microsoft Presidio para deteccao
- Suporta PERSON, EMAIL_ADDRESS, PHONE_NUMBER, etc.
- Versao Lite disponivel sem dependencia externa

**PROBLEMA:** Estes componentes NAO sao integrados no structlog para mascaramento automatico em logs.

---

## 4. Analise de Encryption At-Rest e In-Transit

### 4.1 Encryption In-Transit (TLS)

#### 4.1.1 Kafka: TLS NAO OBRIGATORIO

**Localizacao:** `k8s/kafka-local.yaml`

```yaml
listeners:
  - name: plain
    port: 9092
    type: internal
    tls: false  # CRITICO: plaintext listener activo
  - name: tls
    port: 9093
    type: internal
    tls: true  # TLS disponivel mas nao obrigatorio
```

**Status:** NAO COMPLIANTE
- Listener plain (9092) permite tráfego sem criptografia
- Nao ha politica de rede para bloquear plaintext
- Services podem estar configurados para usar plaintext

**Requisito GDPR:** "Encryption in-transit (TLS 1.3) para PII"
**Realidade:** TLS disponivel mas nao forcado

#### 4.1.2 OpenTelemetry: TLS Verification Disabled

**Localizacao:** `k8s/approval-service-deployment.yaml`, `k8s/orchestrator-dynamic-deployment.yaml`

```yaml
env:
  - name: OTEL_TLS_VERIFY
    value: "false"  # CRITICO: verificacao TLS desabilitada
```

**Status:** NAO COMPLIANTE
- Dados de tracing/telemetria podem ser interceptados
- PII em traces pode ser exposto

#### 4.1.3 mTLS: Parcialmente Implementado

**Localizacao:** `k8s/opa-gatekeeper/config.yaml`

```yaml
# ConstraintTemplate para Mesh mTLS Required
- name: meshmtlsrequired
  description: "Exige mTLS STRICT para workloads no service mesh"
```

**Status:** PARCIAL
- Template OPA definido mas estado de enforcement desconhecido
- Requer verificacao se PeerAuthentication com mTLS STRICT esta activo

### 4.2 Encryption At-Rest

#### 4.2.1 MongoDB: Status Desconhecido

**Analise:** Nao foram encontradas configuracoes de encryption at-rest para MongoDB.

**Requisito:** "AES-256 at-rest para PII"
**Realidade:** Nao possivel verificar sem acesso a configuracao do cluster MongoDB
- DigitalOcean Managed MongoDB oferece encryption por default
- No entanto, versao on-premise pode nao ter encryption activo

#### 4.2.2 Field-Level Encryption: AES-128 (Nao AES-256)

**Localizacao:** `libraries/python/neural_hive_specialists/compliance/field_encryptor.py`

```python
class FieldEncryptor:
    """
    Criptografa e descriptografa campos sensíveis usando Fernet (AES-128).

    Fernet usa:
    - AES em modo CBC com chave de 128 bits  # CRITICO: 128 bits
    - HMAC SHA256 para autenticação
    """
```

**Status:** PARCIALMENTE COMPLIANTE
- AES-128 e seguro mas nao cumpre requisito "AES-256"
- FieldEncryptor implementado mas uso desconhecido nos servicos
- Chave pode ser gerada automaticamente em `/tmp/` (risco de seguranca)

#### 4.2.3 Redis: Status Desconhecido

**Analise:** Nao foram encontradas configuracoes de encryption at-rest para Redis.

**Risco:** ALTO se Redis conter dados PII sem encryption
- Redis nao tem encryption at-rest nativo (requer solucao externa)
- Dados em Redis podem ser dumpados sem criptografia

---

## 5. Analise de Politicas de Retention e Right to Erasure

### 5.1 RetentionManager: Implementado mas Parcial

**Localizacao:** `libraries/python/neural_hive_specialists/ledger/retention_manager.py`

```python
# Políticas padrão GDPR-compliant
RetentionPolicy(
    name="high_risk_extended",
    retention_days=365,  # 1 ano para alto risco
    apply_to_recommendations=["reject"],
    mask_sensitive_fields=True,
    delete_after_retention=False,
),
RetentionPolicy(
    name="standard_retention",
    retention_days=90,  # 90 dias padrão
    apply_to_recommendations=["approve", "conditional"],
    mask_sensitive_fields=True,
    delete_after_retention=False,
),
```

**Status:** PARCIALMENTE COMPLIANTE
- Framework implementado com politicas de retention
- Integracao com PIIDetector e FieldEncryptor
- Script de execucao disponivel (`scripts/run_retention_policies.py`)

**GAPS:**
1. RetentionManager nao integrado em todos os servicos
2. Politicas de retention nao configuradas para approval-service
3. Indices TTL ausentes em colecoes PII

### 5.2 Indices TTL: Implementacao Parcial

**Localizacao:** `services/approval-service/src/database/migrations/m001_active_learning_schema.py`

```python
# TTL implementado para active_learning_queue
await collection.create_index(
    "expires_at", name="idx_expires_at", expireAfterSeconds=3600  # 1 hora
)
```

**Status:** PARCIALMENTE COMPLIANTE
- Active learning queue tem TTL de 1 hora
- Outras colecoes (`plan_approvals`, `specialist_feedback`) SEM TTL

**GAPS CRITICOS:**
- `plan_approvals`: dados de approval com PII sem retention
- `specialist_feedback`: dados de feedback com PII sem retention
- `cognitive_ledger`: opinioes com PII sem retention

### 5.3 Right to Erasure: NAO Implementado

**Requisito GDPR:** "Os titulares dos dados têm o direito de obter do responsável pelo tratamento a eliminação dos seus dados pessoais"

**Status:** NAO COMPLIANTE
- Nao foram encontrados endpoints para "right to erasure"
- Nao ha documentacao de processo para solicitacao de erasure
- RetentionManager tem `delete_after_retention=False` (nao deleta por default)

**Gap:** Usuario nao pode solicitar exclusao dos seus dados manualmente

---

## 6. Compliance GDPR/LGPD: Gap Analysis

### 6.1 Artigo 25 - Privacy by Design

| Aspecto | Status | Gap |
|---------|--------|-----|
| Data minimization | PARCIAL | PII em logs pode nao ser necessario |
| Purpose limitation | PARCIAL | PII coletado para多个 fins |
| Privacy by default | NAO | Logs com PII sao default |
| Encryption in-transit | PARCIAL | TLS nao obrigatorio no Kafka |
| Encryption at-rest | DESCONHECIDO | Status do MongoDB/Redis desconhecido |

### 6.2 Artigo 32 - Security of Processing

| Aspecto | Status | Gap |
|---------|--------|-----|
| Pseudonymization | PARCIAL | PIIMasker implementado mas nao usado |
| Encryption in-transit | PARCIAL | TLS disponivel mas nao forcado |
| Encryption at-rest | DESCONHECIDO | AES-128 em campos, DB desconhecido |
| Confidentiality | PARCIAL | PII em logs acessiveis a多人 |
| Integrity | PARCIAL | Audit trails mas com PII |

### 6.3 Artigo 16 - Right to Rectification

| Aspecto | Status | Gap |
|---------|--------|-----|
| Correcao de dados | NAO | Endpoint nao encontrado |
| Atualizacao de PII | PARCIAL | Aprovacoes podem ser revertidas mas nao corrigidas |

### 6.4 Artigo 17 - Right to Erasure

| Aspecto | Status | Gap |
|---------|--------|-----|
| Delecao de dados | NAO | Endpoint nao implementado |
| Retention policies | PARCIAL | RetentionManager existe mas sem delete |
| TTL indexes | PARCIAL | Apenas em active_learning_queue |

---

## 7. Recomendacoes de Mitigacao

### 7.1 Prioridade CRITICA

#### 7.1.1 Implementar PII Masking em Logs

**Acao:**
```python
# Criar processor structlog customizado
from neural_hive_specialists.compliance import PIIMasker

masker = PIIMasker(strategy=MaskStrategy.PARTIAL)

def pii_mask_processor(logger, log_method, event_dict):
    # Mask user_id and email
    if "user_id" in event_dict:
        event_dict["user_id"] = masker.mask(event_dict["user_id"]).text
    if "email" in event_dict:
        event_dict["email"] = masker.mask(event_dict["email"]).text
    return event_dict

# Configurar structlog
structlog.configure(
    processors=[
        pii_mask_processor,  # Adicionar no inicio
        # ... outros processors
    ]
)
```

**Esforco:** 2-3 dias
**Impacto:** Elimina exposicao de PII em logs

#### 7.1.2 Forcar TLS em Kafka

**Acao:**
```yaml
# k8s/kafka-local.yaml
listeners:
  # - name: plain  # REMOVER listener plaintext
  #   port: 9092
  #   tls: false
  - name: tls
    port: 9093
    type: internal
    tls: true
    authentication:
      type: tls  # Forcar autenticacao TLS
```

**Esforco:** 1 dia
**Impacto:** Garante encryption in-transit para mensagens Kafka

#### 7.1.3 Implementar Indices TTL para Colecoes PII

**Acao:**
```python
# Migration para plan_approvals
await db.plan_approvals.create_index(
    "requested_at",
    name="idx_requested_at_ttl",
    expireAfterSeconds=63072000  # 2 anos em segundos
)

# Migration para specialist_feedback
await db.specialist_feedback.create_index(
    "created_at",
    name="idx_created_at_ttl",
    expireAfterSeconds=63072000
)
```

**Esforco:** 1-2 dias
**Impacto:** Garante compliance com retention max 2 anos

### 7.2 Prioridade ALTA

#### 7.2.1 Implementar Right to Erasure Endpoint

**Acao:**
```python
# services/approval-service/src/api/routers/privacy.py

@router.delete("/api/v1/privacy/data/{user_id}")
async def request_data_erasure(user_id: str, current_user: dict = Depends(get_current_user)):
    """
    GDPR/LGPD Article 17: Right to erasure
    
    Executa erasure de todos os dados PII associados ao user_id:
    - Anonimiza plan_approvals (user_id -> hash)
    - Mascara specialist_feedback (text -> <REDACTED>)
    - Marca cognitive_ledger (mask_sensitive_fields=True)
    """
    # Implementar erasure em 3 colecoes
```

**Esforco:** 3-5 dias
**Impacto:** Compliance GDPR/LGPD Article 17

#### 7.2.2 Atualizar FieldEncryptor para AES-256

**Acao:**
```python
# Substituir Fernet (AES-128) por criptografia AES-256
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class FieldEncryptor:
    def __init__(self, config):
        # Usar AES-256 em vez de Fernet
        self.key_size = 32  # 256 bits
        self.cipher = AESGCM(self._load_or_generate_key_256())
```

**Esforco:** 2-3 dias
**Impacto:** Cumpre requisito "AES-256 at-rest"

#### 7.2.3 Habilitar OTEL_TLS_VERIFY em Producao

**Acao:**
```yaml
# k8s/*-deployment.yaml
env:
  - name: OTEL_TLS_VERIFY
    value: "true"  # Alterar para true em producao
```

**Esforco:** 1 hora
**Impacto:** Garante integridade de telemetria

### 7.3 Prioridade MEDIA

#### 7.3.1 Integrar RetentionManager nos Servicos Core

**Acao:**
- Integrar RetentionManager no approval-service
- Configurar CronJob Kubernetes para execucao diaria
- Configurar alertas para falhas de retention

**Esforco:** 3-4 dias
**Impacto:** Automatiza retention policies

#### 7.3.2 Auditar Encryption At-Rest em MongoDB/Redis

**Acao:**
- Documentar versao e configuracao de MongoDB
- Verificar se encryption at-rest esta activo
- Para Redis: implementar solucao de encryption (ex: Redis Enterprise)

**Esforco:** 1-2 dias (investigacao)
**Impacto:** Clarifica status de compliance

---

## 8. Matriz de Riscos

| ID | Risco | Probabilidade | Impacto | Score | Prioridade |
|----|-------|---------------|---------|-------|------------|
| PII-1 | user_id logado em plaintext | ALTA | ALTO | 9 | CRITICA |
| PII-2 | Kafka plaintext listener activo | MEDIA | ALTO | 7 | ALTA |
| PII-3 | Sem indices TTL para dados PII | ALTA | ALTO | 9 | CRITICA |
| PII-4 | Right to erasure nao implementado | BAIXA | CRITICO | 8 | ALTA |
| PII-5 | AES-128 em vez de AES-256 | BAIXA | MEDIO | 4 | MEDIA |
| PII-6 | OTEL_TLS_VERIFY=false | MEDIA | MEDIO | 6 | ALTA |
| PII-7 | FieldEncryptor nao integrado | ALTA | MEDIO | 6 | MEDIA |

---

## 9. Verificacao de Sub-Requirements

### R-T5.1: PII Masking em Logs

**Given:** Servicos fazem logging com structlog (observability)
**When:** Analisando logs de todos os servicos para detectar PII em plaintext
**Then:** Identificar servicos sem PII masking/redaction em logs

**Status:** GAP IDENTIFICADO
- Todos os servicos core usam structlog
- user_id e email sao logados em plaintext
- PIIMasker existe mas nao esta integrado no structlog

### R-T5.2: Encryption At-Rest e In-Transit

**Given:** Target AES-256 at-rest, TLS 1.3 in-transit para PII
**When:** Verificando configuracao de encryption em MongoDB, Redis, Kafka
**Then:** Identificar datastores sem encryption activa ou com versoes deprecated de TLS

**Status:** GAP IDENTIFICADO
- Kafka: TLS disponivel mas plaintext listener activo (9092)
- MongoDB: status desconhecido (requer investigacao)
- Redis: status desconhecido (requer investigacao)
- Field-level encryption: AES-128 (nao AES-256)

### R-T5.3: Retention e Right to Erasure

**Given:** GDPR/LGPD requer retention max 2 anos apos fim relacao
**When:** Analisando politicas de retention em execution tickets e outros dados PII
**Then:** Identificar dados sem politica de retention explicita ou sem mecanismo de erasure

**Status:** GAP IDENTIFICADO
- RetentionManager implementado mas nao integrado
- Indices TTL apenas em active_learning_queue
- Right to erasure nao implementado
- Colecoes PII sem retention explicita

### R-B6.1: Compliance GDPR/LGPD

**Given:** Sistema processa PII basico (nomes, emails, identificadores)
**When:** Riscos de privacidade sao analisados
**Then:** Os seguintes requisitos devem ser verificados (right to erasure, data minimization, purpose limitation, retention max 2 anos, encryption)

**Status:** PARCIALMENTE COMPLIANTE
- Encryption at-rest: status desconhecido
- Encryption in-transit: parcial (TLS nao forcado)
- Right to erasure: nao implementado
- Retention max 2 anos: nao aplicado via TTL
- Data minimization: PII em logs desnecessario

---

## 10. Conclusao

O Neural Hive Mind possui frameworks de privacidade implementados (PIIMasker, PIIDetector, FieldEncryptor, RetentionManager) mas a integracao destes componentes nos servicos e insuficiente para garantir compliance GDPR/LGPD.

**Principais gaps:**
1. PII logado em plaintext sem mascaramento
2. TLS nao obrigatorio no Kafka
3. Ausencia de indices TTL para dados PII
4. Right to erasure nao implementado

**Recomendacao prioritaria:** Implementar PII masking em logs e forcado TLS em Kafka antes de ir para producao com dados PII reais.
