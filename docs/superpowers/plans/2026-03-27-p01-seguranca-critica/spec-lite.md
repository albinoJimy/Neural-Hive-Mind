# Spec Summary (Lite)

Remover JWT secret hardcoded e CORS wildcard do gateway-intencoes. Implementar environment variables obrigatórias com startup validation e template .env.example.

**Risco crítico:** JWT secret "secret" e CORS "*" permitem falsificação de tokens e ataques cross-origin.

**Solucão:** Environment variables obrigatórias com validação no startup.
