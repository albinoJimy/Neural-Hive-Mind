# Spec Summary (Lite)

Corrigir inconsistência de configuração do Semantic Translation Engine onde o default hardcoded (`cognitive-plans`) diverge da configuração Helm/K8s (`plans.ready`). Alinhar o default do settings.py com `plans.ready` para eliminar dependência silenciosa de env var e garantir comportamento consistente entre ambientes de produção e desenvolvimento local.

**Status Produção:** ✅ Funciona (env var sobrescreve default via ConfigMap)
**Status Local:** ❌ Quebrado (usa default incorreto)
**Risco:** BAIXO (mudança de default, sem breaking changes)
