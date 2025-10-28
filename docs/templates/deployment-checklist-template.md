# Template de Checklist de Deploy - Neural Hive-Mind

**Data do Deploy:** [YYYY-MM-DD]
**Versão:** [v1.2.3]
**Ambiente:** [Production | Staging | Development]
**Tipo de Deploy:** [Feature | Hotfix | Security | Infrastructure]
**Executado por:** [Nome]
**Aprovado por:** [Tech Lead/Manager]

## Informações do Deploy

### Mudanças Incluídas
- [ ] [Feature/Fix 1] - [Breve descrição]
- [ ] [Feature/Fix 2] - [Breve descrição]
- [ ] [Feature/Fix 3] - [Breve descrição]

### Pull Requests Incluídos
- [ ] PR #[XXX] - [Título] - [Reviewer]
- [ ] PR #[YYY] - [Título] - [Reviewer]
- [ ] PR #[ZZZ] - [Título] - [Reviewer]

### Componentes Afetados
- [ ] API Gateway
- [ ] Neural Engine Core
- [ ] Database Schema
- [ ] Message Queue Configuration
- [ ] Monitoring/Alerting
- [ ] Infrastructure (K8s manifests)
- [ ] Outros: [Especificar]

## Pré-Deploy

### Preparação (T-24h)
- [ ] Code review completo de todas as mudanças
- [ ] Testes automatizados passando (CI/CD)
- [ ] Testes de integração executados
- [ ] Documentação atualizada
- [ ] Release notes preparadas

### Validação de Ambiente (T-2h)
- [ ] Ambiente de staging testado com versão final
- [ ] Testes de regressão executados
- [ ] Performance testing realizado
- [ ] Security scanning concluído
- [ ] Database migrations testadas (se aplicável)

### Preparação Técnica (T-30min)
- [ ] Verificar status do cluster
  ```bash
  kubectl get nodes
  kubectl get pods -n neural-hive-mind
  ```
- [ ] Confirmar métricas baseline
  ```bash
  kubectl top nodes
  kubectl top pods -n neural-hive-mind
  ```
- [ ] Executar health check pré-deploy
  ```bash
  ./scripts/validation/validate-cluster-health.sh
  ```

### Backup Pré-Deploy (T-15min)
- [ ] Executar backup completo
  ```bash
  ./scripts/maintenance/backup-restore.sh backup $(date +%Y%m%d_%H%M%S) pre-deploy
  ```
- [ ] Verificar integridade do backup
  ```bash
  ./scripts/maintenance/backup-restore.sh verify latest
  ```
- [ ] Confirmar backup acessível para rollback

## Deploy

### Início do Deploy (T-0)
- [ ] **[HH:MM]** Confirmar Go/No-Go para deploy
- [ ] **[HH:MM]** Notificar início do deploy (Slack #deployments)
- [ ] **[HH:MM]** Atualizar status page (se downtime esperado)

### Database Changes (Se Aplicável)
- [ ] **[HH:MM]** Executar backup específico da database
  ```bash
  ./scripts/maintenance/backup-restore.sh backup $(date +%Y%m%d_%H%M%S) data
  ```
- [ ] **[HH:MM]** Aplicar migrations de database
  ```bash
  # Comando específico de migration
  kubectl exec -it [db-pod] -n neural-hive-mind -- [migration-command]
  ```
- [ ] **[HH:MM]** Verificar integridade dos dados pós-migration
- [ ] **[HH:MM]** Confirmar performance da database

### Infrastructure Changes
- [ ] **[HH:MM]** Aplicar mudanças de infraestrutura (se aplicável)
  ```bash
  kubectl apply -f k8s/infrastructure/
  ```
- [ ] **[HH:MM]** Verificar recursos criados/atualizados
- [ ] **[HH:MM]** Confirmar configurações de rede
- [ ] **[HH:MM]** Validar políticas de segurança

### Application Deploy
- [ ] **[HH:MM]** Executar deploy da aplicação
  ```bash
  ./scripts/deploy/deploy-foundation.sh --version=[NEW_VERSION]
  ```
- [ ] **[HH:MM]** Monitorar rollout dos deployments
  ```bash
  kubectl rollout status deployment/neural-engine -n neural-hive-mind
  kubectl rollout status deployment/api-gateway -n neural-hive-mind
  ```
- [ ] **[HH:MM]** Verificar pods em estado Running
  ```bash
  kubectl get pods -n neural-hive-mind
  ```

### Configuration Updates
- [ ] **[HH:MM]** Aplicar ConfigMaps atualizados
  ```bash
  kubectl apply -f k8s/configs/
  ```
- [ ] **[HH:MM]** Atualizar Secrets (se necessário)
- [ ] **[HH:MM]** Restart pods para aplicar configs (se necessário)
  ```bash
  kubectl rollout restart deployment/[deployment-name] -n neural-hive-mind
  ```

## Validação Pós-Deploy

### Smoke Tests (T+5min)
- [ ] **[HH:MM]** API Gateway respondendo
  ```bash
  curl -f http://api-gateway.neural-hive-mind.svc.cluster.local/health
  ```
- [ ] **[HH:MM]** Neural Engine processando requests
  ```bash
  curl -f http://neural-engine.neural-hive-mind.svc.cluster.local/health
  ```
- [ ] **[HH:MM]** Database acessível
- [ ] **[HH:MM]** Conectividade entre serviços

### Functional Tests (T+10min)
- [ ] **[HH:MM]** Executar testes de conectividade mTLS
  ```bash
  ./scripts/validation/test-mtls-connectivity.sh
  ```
- [ ] **[HH:MM]** Validar autenticação e autorização
- [ ] **[HH:MM]** Testar endpoints críticos
- [ ] **[HH:MM]** Verificar funcionalidades novas/alteradas

### Performance Tests (T+15min)
- [ ] **[HH:MM]** Executar benchmark de performance
  ```bash
  ./scripts/validation/validate-performance-benchmarks.sh --quick
  ```
- [ ] **[HH:MM]** Verificar latência P95 < 500ms
- [ ] **[HH:MM]** Confirmar throughput > 1000 req/s
- [ ] **[HH:MM]** Validar taxa de erro < 0.1%

### Integration Tests (T+20min)
- [ ] **[HH:MM]** Testar integração com sistemas externos
- [ ] **[HH:MM]** Validar fluxos end-to-end críticos
- [ ] **[HH:MM]** Verificar processamento de mensagens
- [ ] **[HH:MM]** Confirmar sincronização de dados

### Security Validation (T+25min)
- [ ] **[HH:MM]** Verificar certificados válidos
  ```bash
  ./scripts/validation/test-mtls-connectivity.sh --cert-check
  ```
- [ ] **[HH:MM]** Confirmar políticas de rede aplicadas
- [ ] **[HH:MM]** Validar controles de acesso
- [ ] **[HH:MM]** Verificar logs de auditoria

### Comprehensive Validation (T+30min)
- [ ] **[HH:MM]** Executar suite completa de validação
  ```bash
  ./scripts/validation/validate-comprehensive-suite.sh
  ```
- [ ] **[HH:MM]** Confirmar todos os testes passando
- [ ] **[HH:MM]** Verificar saúde geral do cluster
  ```bash
  ./scripts/validation/validate-cluster-health.sh
  ```

## Monitoramento Pós-Deploy

### Monitoramento Imediato (T+1h)
- [ ] **[HH:MM]** Monitorar dashboards de application
- [ ] **[HH:MM]** Verificar alertas ativos
- [ ] **[HH:MM]** Analisar logs por erros
- [ ] **[HH:MM]** Confirmar métricas dentro dos SLAs

### Métricas de Baseline
| Métrica | Antes Deploy | Após Deploy | Status |
|---------|--------------|-------------|--------|
| CPU Usage | [X%] | [Y%] | ✅/❌ |
| Memory Usage | [X%] | [Y%] | ✅/❌ |
| Response Time P95 | [Xms] | [Yms] | ✅/❌ |
| Error Rate | [X%] | [Y%] | ✅/❌ |
| Throughput | [X req/s] | [Y req/s] | ✅/❌ |

### Monitoramento Extendido (T+24h)
- [ ] Acompanhar métricas por 24h
- [ ] Verificar padrões de uso
- [ ] Monitorar alertas tardios
- [ ] Analisar logs de aplicação

## Comunicação

### Durante o Deploy
- [ ] **[HH:MM]** Início do deploy notificado
- [ ] **[HH:MM]** Updates de progresso (a cada 15min se downtime)
- [ ] **[HH:MM]** Problemas reportados imediatamente
- [ ] **[HH:MM]** Conclusão do deploy notificada

### Canais de Comunicação
- [ ] Slack #deployments
- [ ] Email para stakeholders
- [ ] Status page atualizado
- [ ] Documentação de mudanças

### Release Notes
- [ ] Funcionalidades adicionadas
- [ ] Bugs corrigidos
- [ ] Mudanças de API (se aplicável)
- [ ] Impactos conhecidos
- [ ] Instruções especiais

## Rollback Plan

### Critérios para Rollback
- [ ] Taxa de erro > 1%
- [ ] Latência P95 > 1000ms
- [ ] Funcionalidade crítica quebrada
- [ ] Problemas de segurança
- [ ] Database corruption

### Procedimento de Rollback

#### Application Rollback
```bash
# Rollback via Helm
helm rollback neural-hive-mind

# Verificar status
kubectl rollout status deployment/neural-engine -n neural-hive-mind
```

#### Database Rollback (Se Necessário)
```bash
# Restore do backup pré-deploy
./scripts/maintenance/backup-restore.sh restore [pre-deploy-timestamp]

# Verificar integridade
./scripts/validation/test-disaster-recovery.sh --data-integrity
```

#### Validação Pós-Rollback
- [ ] Executar smoke tests
- [ ] Verificar funcionalidades críticas
- [ ] Confirmar métricas baseline
- [ ] Notificar conclusão do rollback

## Documentação

### Atualizações Necessárias
- [ ] README.md atualizado
- [ ] API documentation atualizada
- [ ] Operational procedures atualizados
- [ ] Troubleshooting guide atualizado
- [ ] Monitoring runbook atualizado

### Arquivamento
- [ ] Logs do deploy arquivados
- [ ] Configurações versionadas
- [ ] Evidências de testes salvadas
- [ ] Métricas de baseline documentadas

## Pós-Deploy

### Limpeza (T+1h)
- [ ] **[HH:MM]** Limpar recursos temporários
- [ ] **[HH:MM]** Remover backups antigos (se aplicável)
- [ ] **[HH:MM]** Atualizar inventário de versões
- [ ] **[HH:MM]** Confirmar status page atualizado

### Follow-up (T+24h)
- [ ] Revisar logs de 24h para anomalias
- [ ] Confirmar estabilidade das métricas
- [ ] Coletar feedback dos usuários
- [ ] Documentar lições aprendidas

### Action Items
| Item | Descrição | Responsável | Prazo |
|------|-----------|-------------|-------|
| [1] | [Ação de follow-up] | [Nome] | [Data] |
| [2] | [Melhoria identificada] | [Nome] | [Data] |

## Assinaturas

**Deploy Executado por:** [Nome] - [Data/Hora]
**Validado por:** [Tech Lead] - [Data/Hora]
**Aprovado para Produção:** [Manager] - [Data/Hora]

## Log de Atividades

| Horário | Atividade | Status | Observações |
|---------|-----------|--------|-------------|
| [HH:MM] | Início do deploy | ✅ | [Observações] |
| [HH:MM] | Database migration | ✅ | [Observações] |
| [HH:MM] | Application deploy | ✅ | [Observações] |
| [HH:MM] | Smoke tests | ✅ | [Observações] |
| [HH:MM] | Performance tests | ✅ | [Observações] |
| [HH:MM] | Deploy concluído | ✅ | [Observações] |

## Observações e Notas

### Problemas Encontrados
[Documentar qualquer problema encontrado durante o deploy]

### Soluções Aplicadas
[Documentar soluções para problemas encontrados]

### Melhorias Identificadas
[Documentar oportunidades de melhoria no processo]

---

**Notas Importantes:**
1. NUNCA fazer deploy direto em produção sem passar por staging
2. SEMPRE ter backup válido antes de qualquer deploy
3. SEMPRE ter plano de rollback preparado
4. Monitorar sistema por pelo menos 1h após deploy
5. Documentar TODOS os problemas e soluções

**Última Atualização:** [Data]
**Versão:** 1.0