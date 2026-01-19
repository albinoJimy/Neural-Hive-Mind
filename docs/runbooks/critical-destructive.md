# Runbook: Critical Destructive Operations

## Alerta

- **Nome**: CriticalDestructiveOperations / DestructivePlansStuck
- **Severidade**: Critical / Warning
- **Threshold**: >0 operacoes criticas em 10min / Planos criticos sem decisao por 1h

## Sintomas

- Deteccao de operacoes com potencial destrutivo critico
- Planos com operacoes criticas aguardando decisao
- Risco iminente de perda de dados se aprovado incorretamente

## Diagnostico

### 1. Identificar operacoes criticas detectadas

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'increase(neural_hive_destructive_operations_detected_total{severity="critical"}[10m])'
```

### 2. Verificar planos criticos pendentes

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'approval_requests_pending{risk_band="critical"}'
```

### 3. Analisar detalhes nos logs

```bash
kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=500 | grep -i "critical\|severity.*critical"
```

### 4. Identificar planos especificos

```bash
kubectl logs -n neural-hive -l app=approval-service --tail=200 | grep -i "risk_band.*critical"
```

## Resolucao

### Acao Imediata (URGENTE)

1. **NAO aprovar automaticamente** - toda operacao critica requer revisao manual
2. Identificar o plano especifico e suas tasks
3. Contatar responsavel pelo request original
4. Avaliar impacto potencial da operacao

### Checklist de Revisao Manual

- [ ] Operacao e realmente necessaria?
- [ ] Ha backup dos dados afetados?
- [ ] Ambiente correto (nao e producao acidental)?
- [ ] Responsavel confirmou a intencao?
- [ ] Janela de manutencao apropriada?
- [ ] Rollback plan documentado?

### Se Aprovar

1. Documentar justificativa
2. Garantir backup previo
3. Notificar stakeholders
4. Monitorar execucao em tempo real

### Se Rejeitar

1. Documentar motivo da rejeicao
2. Notificar solicitante
3. Sugerir alternativas se aplicavel

## Tipos de Operacoes Criticas

| Operacao | Exemplo | Risco |
|----------|---------|-------|
| DELETE sem WHERE | `DELETE FROM users` | Perda total de dados |
| DROP TABLE/DATABASE | `DROP TABLE orders` | Perda irreversivel |
| TRUNCATE | `TRUNCATE customers` | Perda total de registros |
| rm -rf | `rm -rf /data/*` | Perda de arquivos |
| FORMAT | Formatacao de volume | Perda total |

## Escalacao

Se duvida sobre aprovacao:
1. Contatar Tech Lead
2. Escalar para Security Team se suspeita de ataque
3. Documentar decisao no incident channel

## Referencias

- Dashboard: https://grafana.neural-hive.io/d/approval-monitoring
- Codigo: `services/semantic-translation-engine/src/services/destructive_detector.py`
- RiskScorer: `services/semantic-translation-engine/src/services/risk_scorer.py`
