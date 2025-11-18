# Checklist de Deploy e Validação - Governança e Compliance

## Pré-Deploy

### Infraestrutura
- [ ] MongoDB deployado e acessível (para ledger queries)
- [ ] Redis deployado e acessível (para pheromone queries)
- [ ] Prometheus deployado (para métricas de compliance)
- [ ] Consensus Engine deployado (para gerar decisões com hash)
- [ ] Specialists deployados (para gerar opiniões)
- [ ] Semantic Translation Engine deployado (para gerar planos)

### Ferramentas CLI
- [ ] kubectl instalado e conectado ao cluster
- [ ] helm instalado (v3.10+)
- [ ] jq instalado (para parsing JSON)
- [ ] mongosh ou mongo CLI disponível
- [ ] redis-cli disponível

### Arquivos de Configuração
- [ ] `environments/dev/helm-values/opa-gatekeeper-values.yaml` existe
- [ ] `helm-charts/opa-gatekeeper/Chart.yaml` existe
- [ ] `policies/constraint-templates/` contém 4+ templates
- [ ] `policies/constraints/` contém 2+ constraints aplicáveis

---

## Deploy OPA Gatekeeper

### Execução do Script
- [ ] Executar `./scripts/deploy/deploy-opa-gatekeeper-local.sh` (default namespace: `opa-gatekeeper`)
- [ ] Namespace `opa-gatekeeper` criado
- [ ] Labels aplicados: `neural.hive/component=gatekeeper`, `neural.hive/layer=governanca`
- [ ] Helm chart instalado com sucesso (exit code 0)
- [ ] Pods criados: controller-manager, audit

### Status dos Pods
- [ ] Controller Manager: Running 1/1 Ready
- [ ] Audit: Running 1/1 Ready
- [ ] Restarts: 0
- [ ] Age: > 2 minutos

### Webhooks e CRDs
- [ ] ValidatingWebhookConfiguration criado: `gatekeeper-validating-webhook-configuration`
- [ ] CRD criado: `constrainttemplates.templates.gatekeeper.sh`
- [ ] CRD criado: `configs.config.gatekeeper.sh`
- [ ] Webhook respondendo (verificar logs)

---

## Aplicar Políticas de Compliance

### ConstraintTemplates
- [ ] Aplicar: `kubectl apply -f policies/constraint-templates/`
- [ ] Template criado: `neuralhivemtlsrequired`
- [ ] Template criado: `neuralhiveimagesignature`
- [ ] Template criado: `datagovernancevalidation`
- [ ] Template criado: `redissecurityvalidation`
- [ ] Template criado: `resourcelimitsrequired` (novo)
- [ ] Status: Todos com `.status.created: true`

### Constraints
- [ ] Aplicar: `kubectl apply -f policies/constraints/data-governance-validation.yaml`
- [ ] Aplicar: `kubectl apply -f policies/constraints/enforce-resource-limits.yaml`
- [ ] Pular: `enforce-mtls-strict.yaml` (requer Istio)
- [ ] Pular: `enforce-signed-images.yaml` (requer Sigstore)
- [ ] Constraint criado: `data-governance-validation`
- [ ] Constraint criado: `enforce-resource-limits`
- [ ] Enforcement action: `warn` (não `deny`)

### Validação de Políticas
- [ ] Executar: `./scripts/validation/validate-policy-enforcement.sh`
- [ ] OPA Gatekeeper validado
- [ ] Violações consultadas
- [ ] Relatório gerado

---

## Validar Explicabilidade no Ledger

### Collection: consensus_decisions
- [ ] Total de decisões: `db.consensus_decisions.countDocuments({})`
- [ ] Decisões com explainability_token: `db.consensus_decisions.countDocuments({explainability_token: {$exists: true, $ne: ""}})`
- [ ] Coverage: 100% (todas as decisões têm token)

### Collection: explainability_ledger
- [ ] Total de explicações: `db.explainability_ledger.countDocuments({})`
- [ ] Explicações com token indexado

### Collection: explainability_ledger_v2
- [ ] Total de explicações v2: `db.explainability_ledger_v2.countDocuments({})`
- [ ] Schema v2 validado (campos obrigatórios presentes)

### Correlação Decisões ↔ Explicações
- [ ] Para cada decisão, existe explicação correspondente
- [ ] Query: `db.explainability_ledger.findOne({explainability_token: "<token>"})`
- [ ] Coverage: 100%

---

## Confirmar Integridade com Hashes SHA-256

### Collection: consensus_decisions
- [ ] Total de decisões: N
- [ ] Decisões com hash: `db.consensus_decisions.countDocuments({hash: {$exists: true, $ne: ""}})`
- [ ] Coverage: 100% (todas têm hash)

### Verificação de Integridade (Amostra)
- [ ] Executar: `python3 scripts/governance/verify-hash-integrity.py --collection consensus_decisions --sample-size 10`
- [ ] Hashes válidos: 10/10 (100%)
- [ ] Nenhum hash inválido detectado

### Collection: cognitive_ledger
- [ ] Planos com hash: `db.cognitive_ledger.countDocuments({hash: {$exists: true}})`
- [ ] Verificação de integridade: 100% válido

### Collection: specialist_opinions
- [ ] Opiniões com content_hash: `db.specialist_opinions.countDocuments({content_hash: {$exists: true}})`
- [ ] Verificação de integridade: 100% válido

### Imutabilidade
- [ ] Decisões marcadas como immutable: `db.consensus_decisions.countDocuments({immutable: true})`
- [ ] Coverage: 100%

---

## Executar Testes de Governança

### Teste Completo
- [ ] Executar: `./tests/governance-compliance-test.sh`
- [ ] FASE 1: OPA Gatekeeper validado
- [ ] FASE 2: Políticas de compliance validadas
- [ ] FASE 3: Integridade do ledger verificada
- [ ] FASE 4: Explicabilidade validada
- [ ] FASE 5: Feromônios validados
- [ ] FASE 6: Métricas de governança validadas
- [ ] FASE 7: Dashboards verificados
- [ ] FASE 8: Alertas verificados
- [ ] FASE 9: Testes de violação executados
- [ ] FASE 10: Relatório gerado

### Resultados
- [ ] JSON: `tests/results/governance-compliance-report-<timestamp>.json`
- [ ] Markdown: `tests/results/governance-compliance-summary-<timestamp>.md`
- [ ] Taxa de sucesso: 100% (10/10 fases)

---

## Gerar Relatório de Compliance

### Executar Geração
- [ ] Executar: `./scripts/governance/generate-compliance-report.sh --input-json tests/results/governance-compliance-report-<timestamp>.json`
- [ ] Relatório executivo gerado: `tests/results/GOVERNANCE_COMPLIANCE_EXECUTIVE_REPORT.md`

### Conteúdo do Relatório
- [ ] Executive Summary com Overall Governance Score
- [ ] Scores por categoria (Auditability, Explainability, Compliance, Integrity)
- [ ] Detailed Findings (PASSED/FAILED/WARNING)
- [ ] SLO Compliance Table
- [ ] Recommendations
- [ ] Next Steps

### Scores Esperados (Fase 1)
- [ ] Auditabilidade: 100%
- [ ] Explicabilidade: 100%
- [ ] Compliance: ≥98%
- [ ] Integridade: 100%
- [ ] Overall: ≥99%

---

## Validar Métricas Prometheus

### Métricas de Auditabilidade
- [ ] `neural_hive_ledger_writes_total` > 0
- [ ] `neural_hive_ledger_write_failures_total` = 0
- [ ] Auditability Score ≥ 95%

### Métricas de Explicabilidade
- [ ] `neural_hive_explainability_tokens_generated_total` > 0
- [ ] `neural_hive_consensus_decisions_total` > 0
- [ ] Explainability Coverage ≥ 99%

### Métricas de Compliance
- [ ] `gatekeeper_constraint_violations{enforcement_action="deny"}` = 0
- [ ] `gatekeeper_constraint_violations{enforcement_action="warn"}` < 50
- [ ] Compliance Score ≥ 98%

### Métricas de Consenso
- [ ] Specialist Divergence (p95) < 5%
- [ ] Aggregated Confidence (p50) ≥ 0.8
- [ ] Consensus Latency (p95) < 120ms
- [ ] Fallback Rate < 3%

---

## Validar Dashboards e Alertas

### Dashboards Grafana
- [ ] Dashboard importado: `governance-executive-dashboard`
- [ ] Dashboard importado: `consensus-governance`
- [ ] Dashboard importado: `data-governance`
- [ ] Painéis mostrando dados (pode levar alguns minutos)

### Alertas Prometheus
- [ ] PrometheusRule aplicado: `neural-hive-governance-alerts`
- [ ] Alertas configurados: 16 regras (6 grupos)
- [ ] Alertas firing: 0 (sistema saudável)
- [ ] Alertas pending: 0

---

## Troubleshooting (se necessário)

### OPA Gatekeeper
- [ ] Logs verificados (sem erros críticos)
- [ ] Webhook respondendo
- [ ] Audit funcionando

### Políticas
- [ ] ConstraintTemplates aceitos
- [ ] Constraints aplicados
- [ ] Violações detectadas corretamente

### Ledger
- [ ] MongoDB acessível
- [ ] Collections existem
- [ ] Hashes válidos
- [ ] Explicações presentes

### Feromônios
- [ ] Redis acessível
- [ ] Keys pheromone:* existem
- [ ] TTL configurado
- [ ] Decay funcionando

---

## Pós-Deploy

### Documentação
- [ ] Atualizar `STATUS_DEPLOY_ATUAL.md` com status de governança
- [ ] Registrar versão do OPA Gatekeeper (v3.14.0)
- [ ] Documentar políticas aplicadas
- [ ] Documentar scores de compliance

### Próximos Passos
- [ ] Monitorar violações por 7 dias (modo warn)
- [ ] Remediar violações identificadas
- [ ] Transição para enforcement mode `deny` (após validação)
- [ ] Deploy de Istio mTLS (Fase 2)
- [ ] Deploy de Sigstore (Fase 2)

---

## Critérios de Aceitação Final

### Mínimo para Sucesso
- [ ] OPA Gatekeeper deployado e operacional
- [ ] 2+ políticas aplicadas (resource limits, data governance)
- [ ] 0 violações críticas (deny)
- [ ] 100% de decisões com hash SHA-256
- [ ] 100% de decisões com explainability_token
- [ ] Relatório de compliance gerado

### Ideal (100% Completo)
- [ ] 4+ políticas aplicadas (incluindo mTLS, image signature)
- [ ] Dashboards de governança importados no Grafana
- [ ] Alertas de governança configurados no Prometheus
- [ ] Métricas de governança dentro dos SLOs
- [ ] Documentação completa

---

**Status Final**: ⬜ Não Iniciado | 🟡 Em Progresso | ✅ Completo | ❌ Falhou

**Data de Conclusão**: __________

**Responsável**: __________

**Observações**: __________
