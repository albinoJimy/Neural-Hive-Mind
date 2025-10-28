# Procedimentos Operacionais do Neural Hive-Mind

## Visão Geral

Este documento contém os procedimentos operacionais padrão para o sistema Neural Hive-Mind, incluindo rotinas de manutenção, troubleshooting e resposta a incidentes.

## Procedimentos de Deploy

### Deploy de Fundação
```bash
# Deploy completo da infraestrutura
./scripts/deploy/deploy-foundation.sh

# Deploy com validação específica
VALIDATION_SUITES="security,performance" ./scripts/deploy/deploy-foundation.sh

# Deploy com rollback automático habilitado
ENABLE_AUTO_ROLLBACK=true ./scripts/deploy/deploy-foundation.sh
```

### Validação Pós-Deploy
```bash
# Validação completa
./scripts/validation/validate-comprehensive-suite.sh

# Validação específica
./scripts/validation/validate-cluster-health.sh
./scripts/validation/test-mtls-connectivity.sh
./scripts/validation/test-autoscaler.sh
```

## Monitoramento e Alertas

### Verificações de Saúde do Sistema

#### Verificação Básica
```bash
# Status dos nós
kubectl get nodes

# Status dos pods críticos
kubectl get pods -n neural-hive-mind --field-selector=status.phase!=Running

# Verificação de recursos
kubectl top nodes
kubectl top pods -n neural-hive-mind
```

#### Verificação Avançada
```bash
# Executar suite de validação
./scripts/validation/validate-cluster-health.sh

# Gerar dashboard de saúde
./scripts/validation/generate-health-dashboard.sh

# Verificar conectividade mTLS
./scripts/validation/test-mtls-connectivity.sh
```

### Métricas Críticas

#### SLOs do Sistema
- **Disponibilidade**: ≥ 99.9%
- **Latência P95**: ≤ 500ms
- **Taxa de Erro**: ≤ 0.1%
- **Throughput**: ≥ 1000 req/s

#### Alertas Críticos
- Nós inacessíveis
- Pods em crash loop
- Uso de CPU > 80%
- Uso de memória > 85%
- Certificados expirando em < 30 dias
- Falhas de conectividade mTLS

## Procedimentos de Manutenção

### Manutenção Preventiva Semanal

1. **Verificação de Saúde**
   ```bash
   ./scripts/validation/validate-cluster-health.sh
   ```

2. **Limpeza de Recursos**
   ```bash
   # Limpar pods finalizados
   kubectl delete pods --field-selector=status.phase=Succeeded -A

   # Limpar jobs antigos
   kubectl delete jobs --field-selector=status.conditions[0].type=Complete -A
   ```

3. **Verificação de Certificados**
   ```bash
   # Verificar expiração de certificados
   ./scripts/validation/validate-cluster-health.sh | grep -i certificate
   ```

4. **Teste de Backup**
   ```bash
   ./scripts/validation/test-disaster-recovery.sh
   ```

### Manutenção Preventiva Mensal

1. **Atualização de Imagens**
   ```bash
   # Verificar atualizações disponíveis
   kubectl get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}'
   ```

2. **Limpeza de Logs**
   ```bash
   # Rotacionar logs antigos
   find /var/log/containers -name "*.log" -mtime +30 -delete
   ```

3. **Teste de Disaster Recovery**
   ```bash
   ./scripts/validation/test-disaster-recovery.sh
   ```

4. **Benchmark de Performance**
   ```bash
   ./scripts/validation/validate-performance-benchmarks.sh
   ```

## Troubleshooting

### Problemas Comuns

#### Pods não Inicializam
```bash
# Verificar eventos
kubectl describe pod <pod-name> -n neural-hive-mind

# Verificar logs
kubectl logs <pod-name> -n neural-hive-mind --previous

# Verificar recursos
kubectl top nodes
kubectl describe node <node-name>
```

#### Problemas de Conectividade
```bash
# Teste de conectividade mTLS
./scripts/validation/test-mtls-connectivity.sh

# Verificar políticas de rede
kubectl get networkpolicies -n neural-hive-mind

# Verificar serviços
kubectl get services -n neural-hive-mind
```

#### Alto Uso de Recursos
```bash
# Identificar pods com alto uso
kubectl top pods -n neural-hive-mind --sort-by=cpu
kubectl top pods -n neural-hive-mind --sort-by=memory

# Verificar autoscaler
kubectl get hpa -n neural-hive-mind
kubectl describe hpa <hpa-name> -n neural-hive-mind
```

### Procedimentos de Diagnóstico

#### Coleta de Informações
```bash
# Script de coleta automática
./scripts/maintenance/collect-diagnostic-info.sh

# Informações básicas do cluster
kubectl cluster-info
kubectl version
kubectl get nodes -o wide

# Status dos recursos críticos
kubectl get all -n neural-hive-mind
kubectl get pv,pvc -A
```

#### Análise de Logs
```bash
# Logs de sistema
journalctl -u kubelet -n 100
journalctl -u docker -n 100

# Logs de aplicação
kubectl logs -l app=neural-hive-mind -n neural-hive-mind --tail=1000

# Logs de eventos
kubectl get events -n neural-hive-mind --sort-by='.lastTimestamp'
```

## Resposta a Incidentes

### Classificação de Incidentes

#### Severidade 1 (Crítico)
- Sistema completamente indisponível
- Perda de dados
- Falha de segurança

**Tempo de Resposta**: 15 minutos
**Tempo de Resolução**: 1 hora

#### Severidade 2 (Alto)
- Degradação significativa de performance
- Funcionalidades críticas indisponíveis
- Falhas intermitentes

**Tempo de Resposta**: 30 minutos
**Tempo de Resolução**: 4 horas

#### Severidade 3 (Médio)
- Funcionalidades não-críticas indisponíveis
- Performance levemente degradada

**Tempo de Resposta**: 2 horas
**Tempo de Resolução**: 24 horas

### Procedimentos de Escalação

1. **Detecção do Incidente**
   - Alertas automáticos
   - Relatórios de usuários
   - Monitoramento proativo

2. **Avaliação Inicial**
   ```bash
   # Verificação rápida do sistema
   ./scripts/validation/validate-cluster-health.sh --quick

   # Status dos componentes críticos
   kubectl get pods -n neural-hive-mind -o wide
   ```

3. **Contenção**
   - Isolar componentes afetados
   - Implementar workarounds
   - Comunicar status

4. **Investigação e Resolução**
   ```bash
   # Coleta de diagnósticos
   ./scripts/maintenance/collect-diagnostic-info.sh

   # Análise de logs
   kubectl logs -l app=neural-hive-mind -n neural-hive-mind --since=1h
   ```

5. **Recuperação**
   ```bash
   # Rollback se necessário
   helm rollback neural-hive-mind

   # Validação pós-recuperação
   ./scripts/validation/validate-comprehensive-suite.sh
   ```

6. **Post-Mortem**
   - Documentar causa raiz
   - Identificar melhorias
   - Atualizar procedimentos

## Backup e Restore

### Backup Diário
```bash
# Backup automático
./scripts/maintenance/backup-restore.sh backup

# Verificação de backup
./scripts/validation/test-disaster-recovery.sh --backup-only
```

### Restore de Emergência
```bash
# Restore completo
./scripts/maintenance/backup-restore.sh restore --timestamp=<timestamp>

# Restore seletivo
./scripts/maintenance/backup-restore.sh restore --component=<component>
```

## Otimização de Custos

### Análise de Recursos
```bash
# Análise de uso
./scripts/maintenance/cost-optimization.sh analyze

# Recomendações de otimização
./scripts/maintenance/cost-optimization.sh recommend
```

### Implementação de Otimizações
```bash
# Aplicar otimizações automáticas
./scripts/maintenance/cost-optimization.sh optimize --auto

# Aplicar otimizações específicas
./scripts/maintenance/cost-optimization.sh optimize --manual
```

## Segurança

### Verificações de Segurança
```bash
# Scan de vulnerabilidades
./scripts/validation/validate-cluster-health.sh --security-focus

# Verificação de políticas
kubectl get networkpolicies -A
kubectl get podsecuritypolicies
```

### Rotação de Certificados
```bash
# Verificar certificados próximos ao vencimento
./scripts/validation/test-mtls-connectivity.sh --cert-check

# Rotação automática
./scripts/maintenance/certificate-rotation.sh
```

## Documentação de Mudanças

### Registro de Alterações
- Todas as mudanças devem ser documentadas
- Usar formato de changelog estruturado
- Incluir impact assessment
- Documentar procedimentos de rollback

### Aprovação de Mudanças
- Mudanças críticas requerem aprovação
- Teste em ambiente de staging
- Validação pós-implementação obrigatória

## Contatos e Escalação

### Equipe Operacional
- **Plantão 24x7**: operations@neural-hive-mind.com
- **Escalação Técnica**: tech-lead@neural-hive-mind.com
- **Escalação Gerencial**: management@neural-hive-mind.com

### Fornecedores Críticos
- **Cloud Provider**: [Contato do suporte]
- **Monitoramento**: [Contato do vendor]
- **Backup**: [Contato do vendor]