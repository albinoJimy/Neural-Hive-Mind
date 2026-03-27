# Spec Requirements Document

> Spec: P01 — Segurança Crítica
> Created: 2026-03-27
> Status: Planning
> Priority: CRÍTICA

---

## Overview

Remover credenciais hardcoded e configurações inseguras do Gateway de Intenções para mitigar riscos de segurança imediatos. JWT secret hardcoded e CORS wildcard representam vulnerabilidades críticas que permitem falsificação de tokens e ataques de origem cruzada.

---

## User Stories

### Como operador de segurança
Eu quero que segredos JWT sejam geridos via environment variables
Para que não haja credenciais hardcoded no código fonte

**Workflow:**
1. Sistema inicia e valida variáveis de ambiente obrigatórias
2. Se faltarem, lança erro com mensagem clara
3. Se presentes, usa valores para configuração

### Como desenvolvedor
Eu quero configurar origens CORS permitidas
Para que apenas domínios aprovados possam acessar a API

**Workflow:**
1. Desenvolvedor define `CORS_ORIGINS` no .env
2. Sistema aplica regras de CORS apenas para essas origens
3. Requisições de outras origens são rejeitadas

---

## Spec Scope

1. **JWT Secret via Environment** — Remover hardcoded secret em `auth.py`
2. **CORS Configuration** — Configurar origens permitidas via environment
3. **Startup Validation** — Validar variáveis obrigatórias no startup
4. **Environment Template** — Criar `.env.example` com template
5. **Documentation** — Atualizar README com instruções

---

## Out of Scope

- Implementação de rotação de segredos (futuro)
- Integração com Vault para segredos (futuro)
- Rate limiting (já implementado)
- Autenticação multifator (fora de escopo)

---

## Expected Deliverable

1. Gateway inicia sem credenciais hardcoded
2. Gateway rejeita startup se variáveis obrigatórias faltarem
3. `.env.example` presente com template completo
4. README atualizado com instruções de setup
5. Todos testes existentes passam
