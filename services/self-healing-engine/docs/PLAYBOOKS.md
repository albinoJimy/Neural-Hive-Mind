# Guia de Playbooks - Self-Healing Engine

> **Versão:** 1.0.0  
> **Última Atualização:** 2026-04-07  
> **Componente:** Runbook Engine

## Visão Geral

Playbooks são scripts YAML automatizados que o Self-Healing Engine executa para remediar incidentes detectados. Cada playbook define uma sequência de ações em diferentes domínios (Kubernetes, Kafka, Database, etc.).

## Estrutura de um Playbook

### Metadados Essenciais

```yaml
playbook_id: "identificador-unico-v1"
playbook_name: "nome_descritivo"
playbook_type: "KUBERNETES" | "ISTIO" | "KAFKA" | "DATABASE" | "GENERAL"
version: "1.0.0"
description: "Descrição clara do que o playbook faz"
```

### Parâmetros e Validação

```yaml
parameters_schema:
  type: object
  properties:
    parametro_exemplo:
      type: string
      description: "Descrição do parâmetro"
  required: [parametro_obrigatorio]
required_capabilities:
  - "kubernetes.pods.delete"  # Capacidades Kubernetes necessárias
timeout_seconds: 300  # Timeout máximo para execução
max_retries: 2  # Tentativas em caso de falha
rollback_playbook: "nome_playbook_rollback"  # Opcional
validation_checks:
  - "check_que_deve_passar"  # Validações após execução
status: "AVAILABLE" | "DEPRECATED" | "TESTING"
```

### Actions (Ações)

Cada playbook contém uma lista de `actions:` que definem as operações:

```yaml
actions:
  - name: "nome_descritivo"
    action: "tipo_de_acao"
    parameters:
      parametro1: "{{ template_var }}"
      parametro2: "valor_fixo"
```

## Tipos de Ação Suportados

### Kubernetes

| Action | Descrição | Parâmetros |
|--------|-----------|------------|
| `delete_pod` | Deleta pod (Kubernetes recria) | `pod_name`, `namespace` |
| `scale_deployment` | Escala deployment | `deployment_name`, `namespace`, `replicas` |
| `wait_for_pod` | Aguarda pod ficar pronto | `pod_name`, `namespace`, `condition`, `timeout` |
| `wait_for_deployment` | Aguarda deployment ficar pronto | `deployment_name`, `namespace`, `timeout` |
| `apply_policy` | Aplica política Istio | `policy_type`, `namespace`, `policy_spec` |

### Kafka

| Action | Descrição | Parâmetros |
|--------|-----------|------------|
| `check_kafka_lag` | Verifica lag de consumidor | `consumer_group`, `topic` |
| `reset_consumer_offset` | Reseta offset de consumidor | `consumer_group`, `topic` |

### Database

| Action | Descrição | Parâmetros |
|--------|-----------|------------|
| `check_database_connection` | Verifica conexão DB | `host`, `port`, `database` |
| `execute_query` | Executa query SQL | `database`, `query` |

### General

| Action | Descrição | Parâmetros |
|--------|-----------|------------|
| `wait` | Aguarda por segundos | `seconds` |
| `log` | Registra mensagem | `message` |
| `notify` | Envia notificação | `channel`, `message` |

## Playbooks Disponíveis

### Deadlock Recovery

**Arquivo:** `deadlock_recovery.yaml`

**Descrição:** Recupera workflows em deadlock através de ações de limpeza e reinicio.

**Ações típicas:**
1. Realocar tickets presos
2. Reiniciar workflow
3. Limpar estado travado

### Memory Leak Detection

**Arquivo:** `memory_leak_detection.yaml`

**Descrição:** Detecta e reporta pods com consumo excessivo de memória.

**Ações típicas:**
1. Coletar métricas do pod
2. Analisar histórico de uso
3. Gerar alerta se threshold excedido

### Pod Restart

**Arquivo:** `restart_pod.yaml`

**Descrição:** Reinicia um pod específico deletando-o (Kubernetes recria).

**Parâmetros:**
- `pod_name` (obrigatório): Nome do pod
- `namespace` (obrigatório): Namespace do pod

**Ações:**
1. `delete_pod`: Deleta o pod
2. `wait_for_pod_recreated`: Aguarda recriação e readiness

### Database Connection Recovery

**Arquivo:** `database_connection_recovery.yaml`

**Descrição:** Tenta reconexão e executa queries de recuperação.

**Ações típicas:**
1. Verificar conexão
2. Executar query de validação
3. Notificar se falha persistir

### Kafka Consumer Lag Recovery

**Arquivo:** `kafka_consumer_lag_recovery.yaml`

**Descrição:** Reseta offset de consumidor e escala grupo de consumo.

**Ações típicas:**
1. Verificar lag de consumidor
2. Resetar offset para início da fila
3. Escalar consumidores se necessário

### SLA Violation Mitigation

**Arquivo:** `sla_violation_mitigation.yaml`

**Descrição:** Mitiga violações de SLA através de ações corretivas.

**Ações típicas:**
1. Identificar SLO violado
2. Executar ação de mitigação
3. Notificar stakeholders

## Como Usar Playbooks

### 1. Via Self-Healing Engine

Playbooks são executados automaticamente quando incidentes são detectados:

```python
# O DetectionService detecta problema
await detection_service.trigger_remediation(trigger)
```

### 2. Via API (manual)

```bash
curl -X POST http://self-healing-engine:8000/api/v1/remediation/execute \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_name": "restart_pod",
    "context": {
      "pod_name": "worker-1",
      "namespace": "default"
    }
  }'
```

### 3. Via PlaybookExecutor (direto)

```python
from src.services.playbook_executor import PlaybookExecutor

executor = PlaybookExecutor(playbooks_dir="playbooks/")
result = await executor.execute_playbook(
    playbook_name="restart_pod",
    context={"pod_name": "worker-1", "namespace": "default"}
)
```

## Criando Playbooks Customizados

### Estrutura Mínima

```yaml
playbook_id: "meu-playbook-v1"
playbook_name: "meu_playbook"
playbook_type: "KUBERNETES"
version: "1.0.0"
description: "Descrição clara do propósito"
parameters_schema:
  type: object
  properties:
    meu_param:
      type: string
  required: [meu_param]
required_capabilities: ["kubernetes.pods.delete"]
timeout_seconds: 120
max_retries: 1
validation_checks:
  - "check_sucesso"
status: "AVAILABLE"
actions:
  - name: "minha_acao"
    action: "tipo_acao_suportado"
    parameters:
      param1: "{{ meu_param }}"
```

### Melhores Práticas

1. **Nomes descritivos:** Use `nome_descritivo` em snake_case
2. **Parâmetros template:** Use `{{ var }}` para parâmetros dinâmicos
3. **Validação:** Sempre inclua `validation_checks` apropriadas
4. **Timeout:** Defina `timeout_seconds` realista baseado na operação
5. **Rollback:** Especifique `rollback_playbook` se aplicável
6. **Testes:** Crie testes para validar playbook antes de usar em produção

## Validação de Playbooks

O PlaybookExecutor valida playbooks antes da execução:

- ✅ Estrutura YAML válida
- ✅ `playbook_name` presente e não vazio
- ✅ `actions` não vazio (mínimo 1 ação)
- ✅ Timeout dentro dos limites (1-3600s)
- ✅ Action types suportados
- ✅ Parâmetros obrigatórios presentes

Playbooks que falham na validação não são executados.

## Troubleshooting

### Playbook não é encontrado
- Verifique se o arquivo YAML existe em `playbooks/`
- Confirme se `playbook_name` corresponde ao nome do arquivo

### Validação falha
- Verifique se todos os parâmetros obrigatórios estão presentes
- Confirme se actions são tipos suportados
- Verifique se timeout é válido

### Execução falha
- Verifique logs em `self-healing-engine` pod
- Confira se capacidades necessárias estão disponíveis
- Valide se templates estão sendo preenchidos corretamente

## Exemplos Práticos

### Exemplo 1: Playbook simples

```yaml
playbook_id: "restart-simple-v1"
playbook_name: "restart_simple"
playbook_type: "KUBERNETES"
version: "1.0.0"
description: "Reinicia pod simples"
parameters_schema:
  type: object
  properties:
    pod_name:
      type: string
    namespace:
      type: string
  required: [pod_name, namespace]
timeout_seconds: 60
actions:
  - name: "delete_and_wait"
    action: "delete_pod"
    parameters:
      pod_name: "{{ pod_name }}"
      namespace: "{{ namespace }}"
  - name: "verify_ready"
    action: "wait_for_pod"
    parameters:
      pod_name: "{{ pod_name }}"
      namespace: "{{ namespace }}"
      timeout: 50
      condition: "ready"
```

### Exemplo 2: Playbook com múltiplas ações

```yaml
playbook_id: "complex-recovery-v1"
playbook_name: "complex_recovery"
playbook_type: "GENERAL"
version: "1.0.0"
description: "Recuperação complexa com múltiplas etapas"
actions:
  - name: "verificar_conexao"
    action: "check_database_connection"
    parameters:
      host: "{{ db_host }}"
      port: "{{ db_port }}"
      database: "{{ db_name }}"
  - name: "executar_query_limpeza"
    action: "execute_query"
    parameters:
      database: "{{ db_name }}"
      query: "DELETE FROM temp_table WHERE created_at < NOW() - INTERVAL '7 days'"
  - name: "notificar_sucesso"
    action: "notify"
    parameters:
      channel: "ops-team"
      message: "Limpeza concluída com sucesso"
```

## Integração com OPA

A execução de playbooks pode ser validada via Open Policy Agent antes da execução. Veja `docs/SECURITY_POLICIES.md` para detalhes.
