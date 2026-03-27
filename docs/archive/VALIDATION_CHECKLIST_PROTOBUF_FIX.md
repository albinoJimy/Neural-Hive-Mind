# Checklist de Validação - Correção de Protobuf v1.0.10

Este documento fornece um checklist detalhado para validar a correção de incompatibilidade protobuf implementada na versão 1.0.10.

---

## 1. Validações Pré-Deploy

Execute antes de iniciar o processo de rebuild e deploy:

- [ ] Causa raiz confirmada via `PROTOBUF_VERSION_ANALYSIS.md`
- [ ] Análise completa revisada via `ANALISE_DEBUG_GRPC_TYPEERROR.md`
- [ ] Hipóteses descartadas validadas:
  - [ ] Timeout (5000ms) não é o problema
  - [ ] Request construction (linhas 79-89) está correta
  - [ ] Response parsing (linhas 101-213) é robusto
- [ ] Framework de decisão revisado (`DECISION_FRAMEWORK_PROTOBUF_FIX.md`)
- [ ] Opção escolhida (A ou B) definida e documentada
- [ ] Modificações em arquivos aplicadas:
  - [ ] `scripts/generate_protos.sh` modificado conforme opção
  - [ ] `services/consensus-engine/requirements.txt` atualizado
  - [ ] `libraries/python/neural_hive_specialists/requirements.txt` atualizado
  - [ ] Tags de versão em 6 `values.yaml` atualizadas para 1.0.10
- [ ] Equipe notificada sobre deploy iminente
- [ ] Backup de configurações atuais realizado (opcional)

---

## 2. Validações Durante Build

Execute durante o processo de build das imagens:

### Recompilação de Protobuf

- [ ] Script `generate_protos.sh` executado com sucesso
- [ ] Arquivo `specialist_pb2.py` gerado
- [ ] Versão de protobuf no arquivo corresponde à esperada:

```bash
head -20 libraries/python/neural_hive_specialists/proto_gen/specialist_pb2.py | grep "Protobuf Python Version"
```

**Opção A:** Deve mostrar `# Protobuf Python Version: 4.x.x`
**Opção B:** Deve mostrar `# Protobuf Python Version: 6.x.x`

- [ ] Nenhum erro durante compilação protobuf

### Build de Imagens

- [ ] Imagem `consensus-engine:1.0.10` construída com sucesso
- [ ] Imagem `specialist-business:1.0.10` construída com sucesso
- [ ] Imagem `specialist-technical:1.0.10` construída com sucesso
- [ ] Imagem `specialist-behavior:1.0.10` construída com sucesso
- [ ] Imagem `specialist-evolution:1.0.10` construída com sucesso
- [ ] Imagem `specialist-architecture:1.0.10` construída com sucesso
- [ ] Total: 6/6 imagens construídas

**Verificação:**
```bash
docker images | grep "1.0.10"
```

- [ ] Imagens carregadas no cluster (se kind/minikube):

```bash
# Para kind
kind load docker-image neural-hive-mind/consensus-engine:1.0.10 --name neural-hive-cluster
```

---

## 3. Validações Durante Deploy

Execute durante o processo de deploy no Kubernetes:

### Deploy do Consensus Engine

- [ ] Helm upgrade executado sem erros:

```bash
helm upgrade --install consensus-engine helm-charts/consensus-engine/ \
  -n neural-hive --set image.tag=1.0.10 --wait --timeout=5m
```

- [ ] Rollout completado com sucesso:

```bash
kubectl rollout status deployment/consensus-engine -n neural-hive --timeout=5m
```

- [ ] Pods ficaram ready (2/2 running):

```bash
kubectl get pods -n neural-hive -l app.kubernetes.io/name=consensus-engine
```

- [ ] Nenhum pod em CrashLoopBackOff ou Error
- [ ] Logs de startup não mostram erros de importação:

```bash
kubectl logs -n neural-hive -l app.kubernetes.io/name=consensus-engine --tail=50
```

### Deploy dos Specialists

Para cada specialist (business, technical, behavior, evolution, architecture):

- [ ] Helm upgrade executado sem erros
- [ ] Rollout completado com sucesso
- [ ] Pod ficou ready (1/1 running)
- [ ] Nenhum pod em CrashLoopBackOff ou Error
- [ ] Logs de startup sem erros

**Verificação Geral:**
```bash
kubectl get pods -n neural-hive -l 'app in (specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture)'
```

### Verificação de Eventos

- [ ] Nenhum evento de erro recente:

```bash
kubectl get events -n neural-hive --sort-by='.lastTimestamp' | tail -20
```

- [ ] Nenhum evento de OOMKilled, CrashLoopBackOff ou ImagePullBackOff

---

## 4. Validações de Versão em Runtime

Verificar que as versões de protobuf em runtime correspondem à escolha (A ou B):

### Consensus Engine

```bash
POD=$(kubectl get pods -n neural-hive -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n neural-hive $POD -- pip show protobuf | grep Version
```

- [ ] **Opção A:** Versão mostra `4.x.x`
- [ ] **Opção B:** Versão mostra `6.x.x`

### Specialists

```bash
for specialist in business technical behavior evolution architecture; do
  echo "=== specialist-${specialist} ==="
  POD=$(kubectl get pods -n neural-hive -l app=specialist-${specialist} -o jsonpath='{.items[0].metadata.name}')
  kubectl exec -n neural-hive $POD -- pip show protobuf | grep Version
done
```

- [ ] Todos os 5 specialists mostram versão consistente
- [ ] **Opção A:** Todos mostram `4.x.x`
- [ ] **Opção B:** Todos mostram `6.x.x`

### Verificação de grpcio

```bash
# Consensus Engine
kubectl exec -n neural-hive $POD -- pip show grpcio | grep Version

# Specialist Business (exemplo)
POD=$(kubectl get pods -n neural-hive -l app=specialist-business -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n neural-hive $POD -- pip show grpcio | grep Version
```

- [ ] **Opção A:** grpcio versão `1.60.x`
- [ ] **Opção B:** grpcio versão `1.73.x`

---

## 5. Validações de Compatibilidade

### Análise Completa de Versões

Se disponível, executar script de análise:

```bash
./scripts/debug/run-full-version-analysis.sh
```

- [ ] Exit code: 0 (sucesso)
- [ ] Nenhuma incompatibilidade crítica detectada
- [ ] Relatório mostra versões consistentes em todos os componentes

### Comparação de Arquivos Protobuf

Verificar que todos os componentes usam a mesma versão compilada:

```bash
# MD5 hash do specialist_pb2.py (deve ser idêntico em todos)
find . -name "specialist_pb2.py" -exec md5sum {} \;
```

- [ ] Todos os arquivos têm o mesmo MD5 hash
- [ ] Consistência entre componentes garantida

---

## 6. Validações Funcionais - Teste gRPC Isolado

Objetivo: Validar que TypeError foi resolvido ao acessar `evaluated_at.seconds`

### Execução do Teste

```bash
python3 scripts/debug/test-grpc-isolated.py
```

### Verificações Críticas

- [ ] Teste executado sem exceções
- [ ] Response não é `None` ✓
- [ ] Response é do tipo `EvaluatePlanResponse` ✓
- [ ] Campo `evaluated_at` existe ✓
- [ ] Campo `evaluated_at` é do tipo `Timestamp` ✓
- [ ] **Acesso a `evaluated_at.seconds` NÃO gera TypeError** ✓ ✓ ✓
- [ ] **Acesso a `evaluated_at.nanos` NÃO gera TypeError** ✓ ✓ ✓
- [ ] Conversão para datetime bem-sucedida ✓
- [ ] Timestamp convertido é válido (não é 1970-01-01)

### Resultados

- [ ] Taxa de sucesso: 100% (5/5 specialists testados)
- [ ] Arquivo de resultados gerado: `/tmp/test_grpc_isolated_results.json`
- [ ] Nenhum TypeError registrado nos logs

**Comando de Verificação:**
```bash
cat /tmp/test_grpc_isolated_results.json | jq '.summary'
```

---

## 7. Validações Funcionais - Teste gRPC Abrangente

Objetivo: Validar correção em múltiplos cenários de payload

### Execução do Teste

```bash
# Testar specialist-business (exemplo)
python3 scripts/debug/test-grpc-comprehensive.py --specialist business
```

### Cenários de Payload Testados

- [ ] Simple payload ✓
- [ ] Complex payload ✓
- [ ] Special characters payload ✓
- [ ] Edge case payload ✓
- [ ] Minimal payload ✓

### Verificações

- [ ] Todos os cenários passaram (5/5 ou 25/25 se testar todos os specialists)
- [ ] Nenhum TypeError em nenhum cenário
- [ ] Timestamps válidos em todas as respostas
- [ ] Relatório gerado em `/tmp/grpc-comprehensive-tests/TEST_RESULTS_*.md`

### Análise de Resultados

```bash
# Verificar relatório
cat /tmp/grpc-comprehensive-tests/TEST_RESULTS_*.md
```

- [ ] Taxa de sucesso: 100%
- [ ] Nenhum erro de serialização/deserialização
- [ ] Latências dentro do esperado (<500ms)

---

## 8. Validações de Logs

### Verificar Ausência de TypeErrors

```bash
kubectl logs -n neural-hive -l app.kubernetes.io/name=consensus-engine --tail=500 | grep -i "typeerror"
```

- [ ] Nenhum resultado encontrado (grep retorna exit code 1)
- [ ] Logs não mostram `'int' object has no attribute 'seconds'`

### Verificar Logs de Specialists

```bash
kubectl logs -n neural-hive -l 'app in (specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture)' --tail=500 | grep -i "error"
```

- [ ] Nenhum erro relacionado a timestamp
- [ ] Logs mostram criação de timestamp bem-sucedida:
  - `Timestamp created seconds=XXXXXXXX nanos=XXXXXXXXX`

### Verificar Conversão de Timestamps

```bash
kubectl logs -n neural-hive -l app.kubernetes.io/name=consensus-engine --tail=200 | grep "Timestamp converted"
```

- [ ] Múltiplas ocorrências de conversão bem-sucedida
- [ ] Valores de seconds e nanos são válidos
- [ ] Nenhuma conversão resultou em erro

---

## 9. Validações de Métricas

### Métricas de Erro gRPC

```bash
POD=$(kubectl get pods -n neural-hive -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n neural-hive $POD -- curl -s localhost:8080/metrics | grep grpc_client_errors
```

- [ ] Contador de erros está estável ou zero
- [ ] Nenhum aumento significativo após deploy

### Métricas de Sucesso gRPC

```bash
kubectl exec -n neural-hive $POD -- curl -s localhost:8080/metrics | grep grpc_client_success
```

- [ ] Contador de sucessos está aumentando
- [ ] Taxa de sucesso > 95%

### Latência gRPC

```bash
kubectl exec -n neural-hive $POD -- curl -s localhost:8080/metrics | grep grpc_client_duration
```

- [ ] Latência p50 < 200ms
- [ ] Latência p95 < 500ms
- [ ] Latência p99 < 1000ms
- [ ] Nenhuma degradação de performance após deploy

---

## 10. Validações de Integração E2E

### Teste E2E Completo

Se disponível, executar teste end-to-end:

```bash
python3 test-fluxo-completo-e2e.py
```

### Verificações

- [ ] Teste executado sem exceções
- [ ] Fluxo completo funciona:
  - [ ] Gateway recebe intent
  - [ ] Semantic Translation processa intent
  - [ ] Consensus Engine invoca specialists
  - [ ] Todos os 5 specialists respondem
  - [ ] Consensus é calculado
  - [ ] Resposta final é retornada
- [ ] Resposta contém pareceres de todos os 5 specialists
- [ ] Timestamps em todos os pareceres são válidos
- [ ] Nenhum erro de serialização/deserialização
- [ ] Tempo total de resposta < 5 segundos

### Validação Manual

Se teste automatizado não estiver disponível, testar manualmente:

```bash
# 1. Enviar intent via gateway
curl -X POST http://gateway-intencoes.neural-hive.svc.cluster.local:8000/api/v1/intents \
  -H "Content-Type: application/json" \
  -d '{"description": "Implementar sistema de autenticação", "complexity": "high"}'

# 2. Verificar logs do consensus-engine
kubectl logs -n neural-hive -l app.kubernetes.io/name=consensus-engine --tail=100

# 3. Verificar que não há TypeErrors
```

- [ ] Intent processado com sucesso
- [ ] Nenhum erro nos logs
- [ ] Response contém pareceres válidos

---

## 11. Checklist de Monitoramento Contínuo

Após deploy bem-sucedido, monitorar por 24-48 horas:

### Primeiras 2 Horas

- [ ] Verificar logs a cada 30 minutos
- [ ] Nenhum TypeError detectado
- [ ] Pods não reiniciaram inesperadamente
- [ ] Métricas de erro estáveis

### Primeiras 24 Horas

- [ ] Executar testes gRPC a cada 6 horas
- [ ] Monitorar métricas de erro
- [ ] Verificar performance não degradou
- [ ] Confirmar que todos os fluxos funcionam

### 24-48 Horas

- [ ] Sistema estável por período prolongado
- [ ] Nenhum incidente relacionado a protobuf
- [ ] Feedback da equipe é positivo
- [ ] Considerar correção como definitiva

---

## 12. Checklist de Rollback (Se Necessário)

Execute apenas se validações críticas falharem:

### Quando Considerar Rollback

- [ ] TypeError persiste após deploy
- [ ] Pods em CrashLoopBackOff
- [ ] Incompatibilidades de versão detectadas
- [ ] Testes gRPC falham >20%
- [ ] Erros de importação de protobuf nos logs
- [ ] Métricas de erro aumentam significativamente

### Procedimento de Rollback

```bash
# 1. Rollback Consensus Engine
helm rollback consensus-engine -n neural-hive

# 2. Rollback Specialists
for specialist in business technical behavior evolution architecture; do
  helm rollback specialist-${specialist} -n neural-hive
done

# 3. Aguardar pods voltarem ao estado anterior
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=consensus-engine -n neural-hive --timeout=5m
kubectl wait --for=condition=ready pod -l 'app in (specialist-business,specialist-technical,specialist-behavior,specialist-evolution,specialist-architecture)' -n neural-hive --timeout=5m
```

- [ ] Rollback executado com sucesso
- [ ] Pods voltaram ao estado anterior
- [ ] Sistema voltou a funcionar (mesmo com TypeError)
- [ ] Causa da falha documentada
- [ ] Plano de correção revisado

---

## 13. Documentação Pós-Deploy

Após validação completa e bem-sucedida:

### Atualizar Documentos

- [ ] Atualizar `ANALISE_DEBUG_GRPC_TYPEERROR.md`:
  - [ ] Adicionar seção "Resolução Implementada"
  - [ ] Documentar opção escolhida (A ou B)
  - [ ] Adicionar timestamp de deploy
  - [ ] Documentar resultados de validação
  - [ ] Atualizar status para "✅ RESOLVIDO"

- [ ] Atualizar `PROTOBUF_VERSION_ANALYSIS.md`:
  - [ ] Adicionar seção "Implementação Concluída"
  - [ ] Documentar versões finais de protobuf
  - [ ] Confirmar compatibilidade

- [ ] Criar/Revisar relatório de deploy:
  - [ ] `DEPLOYMENT_REPORT_PROTOBUF_FIX_*.md` gerado
  - [ ] Relatório revisado pela equipe
  - [ ] Aprovação final obtida

### Comunicação

- [ ] Equipe notificada sobre conclusão do deploy
- [ ] Stakeholders informados sobre resolução
- [ ] Documentação compartilhada com equipe

### Fechamento de Tickets

- [ ] Ticket GRPC-DEBUG-001 fechado
- [ ] Ticket GRPC-DEBUG-002 fechado
- [ ] Ticket GRPC-DEBUG-003 fechado
- [ ] Comentários finais adicionados aos tickets

---

## Critérios de Sucesso Final

O deploy é considerado bem-sucedido se:

✅ **Problema Principal Resolvido:**
- Nenhum TypeError ao acessar `evaluated_at.seconds` ou `evaluated_at.nanos`
- Testes gRPC isolados passam 100% (5/5 specialists)
- Testes gRPC abrangentes passam 100% (25/25 cenários)

✅ **Estabilidade do Sistema:**
- Todos os 6 componentes deployados com versão 1.0.10
- Todos os pods ficam ready (sem CrashLoopBackOff)
- Logs não mostram erros relacionados a timestamp
- Métricas de erro de gRPC estáveis ou zero

✅ **Compatibilidade de Versões:**
- Versões de protobuf consistentes em todos os componentes
- Análise de versões não detecta incompatibilidades
- Arquivos protobuf compilados correspondem ao runtime

✅ **Validação Funcional:**
- Teste E2E completo funciona sem erros
- Fluxo Gateway → Semantic Translation → Consensus → Specialists operacional
- Pareceres de todos os 5 specialists recebidos corretamente

✅ **Monitoramento:**
- Sistema estável por 48 horas
- Nenhum incidente relacionado
- Feedback da equipe positivo

---

## Critérios de Falha (Requer Ação)

O deploy é considerado falho se:

❌ **TypeError Persiste:**
- Erros ao acessar `evaluated_at.seconds` continuam
- Logs mostram `'int' object has no attribute 'seconds'`

❌ **Instabilidade:**
- Pods em CrashLoopBackOff
- Reinícios frequentes de pods
- OOMKilled ou outros erros de recursos

❌ **Incompatibilidades:**
- Versões de protobuf inconsistentes
- Erros de importação nos logs
- Análise de versões detecta problemas

❌ **Falha Funcional:**
- Testes gRPC falham >20%
- Fluxo E2E não funciona
- Specialists não respondem

❌ **Performance:**
- Latência aumentou significativamente
- Métricas de erro aumentaram
- Taxa de sucesso < 95%

**Ação:** Se qualquer critério de falha for atendido, execute rollback imediatamente e investigue causa raiz.

---

## Referências

- Framework de Decisão: [DECISION_FRAMEWORK_PROTOBUF_FIX.md](DECISION_FRAMEWORK_PROTOBUF_FIX.md)
- Análise de Debug: [ANALISE_DEBUG_GRPC_TYPEERROR.md](ANALISE_DEBUG_GRPC_TYPEERROR.md)
- Análise de Versões: [PROTOBUF_VERSION_ANALYSIS.md](PROTOBUF_VERSION_ANALYSIS.md)
- Script de Deploy: `scripts/deploy/rebuild-and-deploy-protobuf-fix.sh`

---

**Última Atualização:** 2025-11-10
**Versão:** 1.0
**Status:** Pronto para Uso
