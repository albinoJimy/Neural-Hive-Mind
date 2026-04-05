# SEC-008: Implementação de Validação de Trust Bundle JWT

## Visão Geral

Implementação de validação segura de tokens JWT-SVID no contexto SPIFFE/SPIRE, resolvendo a vulnerabilidade de token substitution attacks.

## Vulnerabilidade Resolvida

**Localização:** `libraries/security/neural_hive_security/spiffe_manager.py:488-495`

**Problema:** O método `get_trust_bundle_keys()` retornava um dicionário de chaves sem validar a estrutura JWK ou assinatura JWT, permitindo ataques de substituição de token.

**Risco:** Token substitution attacks - atacante poderia substituir chave legítima por chave maliciosa.

## Componentes Implementados

### 1. JWKValidator (`jwt/jwk_validator.py`)

Validação de estrutura JWK conforme RFC 7517.

**Funcionalidades:**
- Validação de campos obrigatórios (kty, kid, alg, n/e ou crv/x/y)
- Detecção de JWKs malformados
- Suporte a RSA, EC, OKP (EdDSA)
- Validação de JWKS (conjunto de chaves)

**Exemplo de uso:**
```python
from neural_hive_security.jwt import JWKValidator

validator = JWKValidator()

jwk = {
    "kty": "RSA",
    "kid": "key-123",
    "alg": "RS256",
    "n": "...",
    "e": "AQAB"
}

if validator.validate(jwk):
    # JWK válido
else:
    errors = validator.get_errors()
```

### 2. JWTVerifier (`jwt/jwt_verifier.py`)

Verificação de assinatura e claims JWT.

**Funcionalidades:**
- Verificação de assinatura com PyJWT/python-jose
- Validação de claims: iss, exp, nbf, aud, sub
- Extração e validação de SPIFFE ID
- Proteção contra algorithm confusion attacks
- Proteção contra token substitution attacks

**Exemplo de uso:**
```python
from neural_hive_security.jwt import JWTVerifier

verifier = JWTVerifier(
    trust_domain="neural-hive.local",
    verification_keys={"key-1": jwk_data},
    enable_verification=True
)

result = await verifier.verify(token)
if result.is_valid:
    spiffe_id = result.spiffe_id
else:
    errors = result.errors
```

### 3. KeyCache (`jwt/key_cache.py`)

Cache de chaves públicas com TTL.

**Funcionalidades:**
- Thread-safe com lock
- TTL configurável (padrão: 300 segundos)
- Estatísticas de hits/misses
- Invalidação por key ID ou limpeza total

**Exemplo de uso:**
```python
from neural_hive_security.jwt import KeyCache

cache = KeyCache(ttl_seconds=300)

cache.put("key-1", jwk_data)
key = cache.get("key-1")

stats = cache.get_stats()
# {"hits": 10, "misses": 2, "hit_rate": 0.833, ...}
```

### 4. Métricas Prometheus (`jwt/metrics.py`)

Métricas para observabilidade da verificação JWT.

**Métricas disponíveis:**
- `jwt_verification_attempts_total`: Tentativas de verificação por status
- `jwt_verification_failures_total`: Falhas por motivo
- `jwt_verification_duration_seconds`: Histograma de duração
- `jwk_validation_attempts_total`: Validações JWK por status
- `jwk_cache_size`: Número de chaves em cache
- `spiffe_trust_bundle_updates_total`: Atualizações de trust bundle

## Modificações no Código Existente

### spiffe_manager.py

**Adições:**
1. Import de componentes JWT (controlado por feature flag)
2. Inicialização de JWKValidator e KeyCache em `__init__`
3. Validação de JWKS em `get_trust_bundle()`
4. Cache de chaves com TTL em `get_trust_bundle_keys()`
5. Novos métodos: `get_key_cache()`, `get_jwk_validator()`

**Feature Flag:**
```bash
export ENABLE_JWT_VERIFICATION=true  # Habilita validação JWT
```

### setup.py

**Adições:**
- `PyJWT>=2.8.0`: Verificação de assinatura JWT
- `python-jose>=3.3.0`: Validação de JWK

## Testes

Arquivo: `libraries/security/tests/test_jwk_validator.py`

**Cobertura de testes:**
- Validação de estrutura JWK (RSA, EC, OKP)
- Detecção de campos faltantes
- Verificação de JWT (assinatura, expiração, claims)
- Cache de chaves com TTL
- Token substitution attack
- Key injection attack
- Algorithm confusion attack

**Execução:**
```bash
cd libraries/security
pytest tests/test_jwk_validator.py -v
```

## Integração com Auth Interceptor

O `SPIFFEAuthInterceptor` em `services/service-registry/src/grpc_server/auth_interceptor.py` pode usar o JWTVerifier:

```python
# Inicializar verifier com chaves do SPIFFE Manager
verifier = JWTVerifier(
    trust_domain=settings.SPIFFE_TRUST_DOMAIN,
    verification_keys=spiffe_manager.get_trust_bundle_keys(),
    enable_verification=settings.SPIFFE_VERIFY_PEER
)

# Verificar token
result = await verifier.verify(token)
if result.is_valid:
    spiffe_id = result.spiffe_id
```

## Métricas Prometheus

As métricas são expostas automaticamente quando a biblioteca é importada:

```python
# No serviço FastAPI
from prometheus_client import generate_latest

@app.get("/metrics")
def metrics():
    return generate_latest()
```

## Segurança

### Proteções Implementadas

1. **Algorithm Confusion**: Algoritmo "none" é bloqueado por padrão
2. **Token Substitution**: Verificação de kid no header vs chave usada
3. **Key Injection**: Validação de estrutura JWK antes de usar
4. **Trust Domain Mismatch**: Verificação de issuer e SPIFFE ID
5. **Clock Skew**: Leeway configurável para exp/nbf

### Configuração Recomendada

**Produção:**
```bash
export ENABLE_JWT_VERIFICATION=true
export SPIFFE_VERIFY_PEER=true
export SECURITY_ENVIRONMENT=production
```

**Desenvolvimento:**
```bash
export ENABLE_JWT_VERIFICATION=false  # Validação desabilitada
export SPIFFE_VERIFY_PEER=false
export SECURITY_ENVIRONMENT=development
```

## Performance

- Cache de chaves reduz chamadas ao Workload API
- TTL de 5 minutos balanceia frescura e performance
- Métricas de duração para monitoramento

## Próximos Passos

1. Atualizar AuthInterceptor dos serviços para usar JWTVerifier
2. Configurar feature flag no deployment
3. Monitorar métricas de verificação em produção
4. Documentar procedimentos de rotação de chaves

## Referências

- [RFC 7517 - JSON Web Key (JWK)](https://datatracker.ietf.org/doc/html/rfc7517)
- [RFC 7519 - JSON Web Token (JWT)](https://datatracker.ietf.org/doc/html/rfc7519)
- [SPIFFE JWT-SVID Specification](https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE_Trust_Domain_and_JWT-SVID.md)
- [SEC-008 Ticket](https://github.com/albinoJimy/Neural-Hive-Mind/issues/XXX)
