# Runbook: High Approval Time

## Sintomas
- Alerta: `HighApprovalTime` disparado
- Tempo médio de aprovação > 1 hora
- Backlog de aprovações pendentes

## Diagnóstico

### 1. Verificar Fila de Aprovações
```bash
# Consultar aprovações pendentes
mongo neural_hive --eval '
db.approvals.count({status: "pending"})
'
```

### 2. Analisar Distribuição de Tempos
```bash
# Ver percentis de approval time
curl -s "http://prometheus:9090/api/v1/query?query=histogram_quantile(0.95,%20rate(neural_hive_approval_time_seconds_bucket[1h]))"
```

### 3. Verificar Disponibilidade de Revisores
```bash
# Verificar usuários ativos no approval-service
kubectl logs -n neural-hive-mind -l app=approval-service --tail=100 | grep "user_id"
```

## Resolução

### Opção 1: Aumentar Auto-Approval Rate
Reduzir carga de revisões manuais:

```yaml
# Ajustar threshold em specialist-config.yaml
data:
  auto-approval-confidence-threshold: "0.85"
```

### Opção 2: Escalar Revisores
Se backlog é grande:

- Notificar equipe de revisores
- Considerar adicionar mais revisores
- Priorizar planos críticos

### Opção 3: Otimizar Processo de Revisão
- Melhorar UI de aprovação
- Adicionar filtros e busca
- Implementar aprovação em lote

## Prevenção
- Monitorar fila de aprovações pendentes
- Configurar alertas para backlog > 50
- Balancear auto-approval vs revisão manual
