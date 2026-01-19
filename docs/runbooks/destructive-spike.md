# Runbook: Destructive Operations Spike

## Alerta

- **Nome**: DestructiveOperationsSpike
- **Severidade**: Warning
- **Threshold**: >0.5 operacoes destrutivas/segundo por 5 minutos

## Sintomas

- Aumento repentino na deteccao de operacoes destrutivas
- Possivel abuso ou comportamento anomalo
- Bloqueio de multiplos planos para aprovacao

## Diagnostico

### 1. Verificar taxa de deteccao

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'rate(neural_hive_destructive_operations_detected_total[5m])'
```

### 2. Identificar tipos de deteccao

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'sum by (detection_type) (increase(neural_hive_destructive_operations_detected_total[1h]))'
```

### 3. Verificar severidade das deteccoes

```bash
kubectl exec -n monitoring prometheus-0 -- promtool query instant \
  'sum by (severity) (increase(neural_hive_destructive_operations_detected_total[1h]))'
```

### 4. Analisar logs do DestructiveDetector

```bash
kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=200 | grep -i "destructive"
```

### 5. Identificar origem dos planos

```bash
kubectl logs -n neural-hive -l app=semantic-translation-engine --tail=200 | grep -i "plan_id"
```

## Resolucao

### Acao Imediata

1. Avaliar se spike e comportamento legitimo ou anomalia
2. Se anomalia, identificar e bloquear origem
3. Monitorar tendencia em tempo real

### Se Comportamento Legitimo

1. Verificar se aprovadores estao cientes
2. Priorizar revisao de planos destrutivos
3. Comunicar equipe sobre volume alto

### Se Anomalia/Ataque

1. Bloquear origem dos requests suspeitos
2. Revisar logs de autenticacao
3. Escalar para equipe de seguranca

### Acao de Medio Prazo

1. Revisar padroes de deteccao
2. Ajustar thresholds se necessario
3. Implementar rate limiting por origem

## Tipos Comuns de Deteccao

| Tipo | Descricao | Severidade |
|------|-----------|------------|
| delete_all | DELETE sem WHERE | Critical |
| drop_table | DROP TABLE | Critical |
| truncate | TRUNCATE TABLE | High |
| update_all | UPDATE sem WHERE | High |
| rm_rf | rm -rf em paths criticos | Critical |
| format | Formatacao de disco | Critical |

## Referencias

- Dashboard: https://grafana.neural-hive.io/d/approval-monitoring
- Codigo: `services/semantic-translation-engine/src/services/destructive_detector.py`
- Padroes: `services/semantic-translation-engine/src/services/pattern_matcher.py`
