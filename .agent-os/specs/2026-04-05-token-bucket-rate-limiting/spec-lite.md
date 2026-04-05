# Spec Summary (Lite)

Implementar rate limiting hierárquico (tenant > user > endpoint) usando Token Bucket algorithm no Orchestrator Dynamic, substituindo dependência do OPA para throttling simples. Integra com neural_hive_resilience.TokenBucketRateLimiter, usa Redis para estado distribuído, expõe métricas Prometheus e configura via Pydantic Settings.
