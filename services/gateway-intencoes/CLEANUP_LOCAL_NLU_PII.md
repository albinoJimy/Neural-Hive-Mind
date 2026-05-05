# Cleanup de Implementações Locais NLU/PII

**Data:** 2026-05-05
**Status:** Pronto para execução após T17 confirmado (100% tráfego no Unified Gateway)

---

## Contexto

Como parte da Unified Gateway Architecture (T11), as implementações locais de NLU e PII foram substituídas por serviços gRPC dedicados:

| Componente | Implementação Local | Novo Serviço gRPC |
|------------|---------------------|-------------------|
| NLU | nlu_pipeline.py + pipelines/nlu/ | nlu-service:8020 |
| PII | PIIDetectorLite (local) | pii-service:8021 |

---

## Arquivos a Remover

### NLU Local (~3.308 LOC)

| Arquivo | LOC | Descrição |
|---------|-----|-----------|
| `src/pipelines/nlu_pipeline.py` | 1.302 | Implementação local antiga |
| `src/pipelines/nlu_pipeline_v2.py` | 393 | Versão 2 antiga |
| `src/pipelines/nlu/` | 1.613 | Diretório com classificadores locais |
| `tests/unit/test_nlu_pipeline.py` | ~200 | Testes da implementação local |

**Total a remover:** ~3.308 LOC

### PII Local (~500 LOC estimado)

| Arquivo | LOC | Descrição |
|---------|-----|-----------|
| `src/services/pii_detector_lite.py` | ~400 | PII detection local |
| `tests/unit/test_pii_detector.py` | ~100 | Testes PII local |

---

## Arquivos a MANTER

✅ **MANTER** - Nova implementação via gRPC:
- `src/pipelines/nlu_pipeline_service.py` (157 LOC) - **NOVO, usa gRPC**
- `src/grpc_clients/nlu_client.py` - Cliente gRPC do NLU Service
- `src/grpc_clients/pii_client.py` - Cliente gRPC do PII Service
- `src/services/nlu_service_adapter.py` - Adapter para NLU Service
- `tests/unit/test_nlu_components.py` - Testes do adapter

---

## Procedimento de Remoção

### 1. Backup (opcional)

```bash
# Criar branch de backup
git checkout -b backup/local-nlu-pii-removal

# Criar tarball
tar -czf local-nlu-pii-backup.tar.gz \
  services/gateway-intencoes/src/pipelines/nlu_pipeline.py \
  services/gateway-intencoes/src/pipelines/nlu_pipeline_v2.py \
  services/gateway-intencoes/src/pipelines/nlu/ \
  services/gateway-intencoes/tests/unit/test_nlu_pipeline.py
```

### 2. Remover arquivos

```bash
# Remover implementações locais NLU
rm services/gateway-intencoes/src/pipelines/nlu_pipeline.py
rm services/gateway-intencoes/src/pipelines/nlu_pipeline_v2.py
rm -rf services/gateway-intencoes/src/pipelines/nlu/
rm services/gateway-intencoes/tests/unit/test_nlu_pipeline.py

# Remover implementações locais PII (se existirem)
rm services/gateway-intencoes/src/services/pii_detector_lite.py
rm services/gateway-intencoes/tests/unit/test_pii_detector.py
```

### 3. Verificar referências

```bash
# Verificar se não há mais referências
grep -r "nlu_pipeline\.py\|pipelines\.nlu\|PIIDetectorLite" \
  services/gateway-intencoes/src --include="*.py"
```

### 4. Executar testes

```bash
cd services/gateway-intencoes
pytest tests/unit/test_nlu_components.py -v  # Deve passar (usa adapter)
pytest tests/integration/ -v  # Integração com NLU Service
```

### 5. Commit

```bash
git add services/gateway-intencoes
git commit -m "refactor(gateway-intencoes): T18 remove local NLU/PII implementations

- Remove nlu_pipeline.py (1.302 LOC)
- Remove nlu_pipeline_v2.py (393 LOC)
- Remove pipelines/nlu/ directory (1.613 LOC)
- Removes ~3.308 LOC of duplicated NLU code
- Keeps nlu_pipeline_service.py (gRPC client)

Local implementations replaced by NLU Service (:8020) and PII Service (:8021)
via gRPC as per Unified Gateway Architecture T11.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Validação Pós-Remoção

### Health Check

```bash
# Verificar se gateway-intencoes ainda funciona
kubectl exec -n fluxo-a deployment/gateway-intencoes -- \
  curl -s http://localhost:8000/health

# Verificar se NLU Service está respondendo
kubectl exec -n nlu deployment/nlu-service -- \
  curl -s http://localhost:8021/health
```

### Teste de Integração

```bash
# Teste completo do fluxo A-F
curl -X POST http://gateway-intencoes:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"text": "Quero analisar os dados de vendas"}'
```

---

## Rollback

Se necessário:

```bash
# Restaurar do backup
tar -xzf local-nlu-pii-backup.tar.gz

# Ou reverter commit
git revert <commit-hash>
```

---

## Impacto

### Código Removido

- **NLU Local:** ~3.308 LOC
- **PII Local:** ~500 LOC
- **Total:** ~3.808 LOC

### Benefícios

1. **Eliminação de duplicação** - Lógica NLU/PII em um único lugar
2. **Consistência** - Mesma versão de NLP usada por todos os fluxos
3. **Manutenibilidade** - Updates em um único serviço
4. **Escalabilidade** - NLU/PII services escalam independentemente

---

## Dependências

- T17 deve estar confirmado (100% tráfego no Unified Gateway)
- NLU Service (:8020) deve estar saudável
- PII Service (:8021) deve estar saudável
- Testes de integração devem passar

---

## Próximos Passos

Após remoção bem-sucedida:

1. Atualizar documentação do gateway-intencoes
2. Remover referências nos READMEs
3. Atualizar diagramas de arquitetura
4. Remover approval-gateway service do cluster
