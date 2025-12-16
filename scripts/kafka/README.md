# Scripts de Kafka - Neural Hive Mind

## Visão Geral

Este diretório contém scripts utilitários para testes, validação e diagnóstico de integração com Apache Kafka no projeto Neural Hive Mind.

## Scripts Disponíveis

### `test-eos.py`

Script de teste para validação de Exactly-Once Semantics (EOS) do Kafka.

**Propósito**: Validar configuração de EOS com múltiplos producers e consumers, garantindo que não haja duplicatas ou perda de mensagens.

**Uso**:
```bash
python test-eos.py --bootstrap-servers <kafka-servers> --messages 10000
```

**Parâmetros**:
- `--bootstrap-servers`: Endereço dos bootstrap servers do Kafka
- `--messages`: Número de mensagens para testar (padrão: 10000)

**Exemplo**:
```bash
python test-eos.py --bootstrap-servers kafka-bootstrap.kafka.svc.cluster.local:9092 --messages 5000
```

---

### `debug-ste-kafka-connection.py`

Script de debug para diagnosticar problemas de conexão entre o Semantic Translation Engine (STE) e o Kafka.

**Propósito**: Identificar e diagnosticar problemas comuns como:
- Falhas de conectividade TCP
- Tópicos configurados que não existem no Kafka
- Mismatches de nomenclatura (ex: `intentions.business` vs `intentions-business`)

**Uso**:
```bash
# Executar dentro do pod do STE
kubectl exec -n semantic-translation <pod-name> -- python /app/scripts/debug-ste-kafka-connection.py

# Ou localmente (requer acesso ao Kafka)
python debug-ste-kafka-connection.py
```

**Output**:
- **Console**: Resumo dos resultados com status geral
- **Arquivo**: `/reports/ste-kafka-debug-results.md` (relatório detalhado em Markdown)

**Exit Codes**:
- `0`: Sucesso (todos os tópicos configurados estão disponíveis)
- `1`: Erro (problemas de conectividade ou tópicos faltando)

**Exemplo**:
```bash
# Executar debug no pod do STE
POD_NAME=$(kubectl get pods -n semantic-translation -l app=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n semantic-translation $POD_NAME -- python /app/scripts/debug-ste-kafka-connection.py

# Copiar relatório gerado
kubectl cp semantic-translation/$POD_NAME:/reports/ste-kafka-debug-results.md ./ste-kafka-debug-results.md
```

---

## Pré-requisitos

### Dependências Python
- Python 3.11+
- `confluent-kafka` (instalado via `requirements.txt`)
- `structlog` (para logging estruturado)

### Acesso ao Cluster
- Conectividade de rede ao cluster Kafka
- Permissões para criar/listar tópicos (para `test-eos.py`)
- Permissões para listar tópicos via AdminClient (para `debug-ste-kafka-connection.py`)

### Instalação de Dependências
```bash
pip install confluent-kafka structlog
```

---

## Troubleshooting Comum

### Problema: `UNKNOWN_TOPIC_OR_PART`

**Sintoma**: Consumer não consegue consumir mensagens e log mostra erro `UNKNOWN_TOPIC_OR_PART`.

**Diagnóstico**:
```bash
# Executar script de debug
kubectl exec -n semantic-translation <pod-name> -- python /app/scripts/debug-ste-kafka-connection.py

# Verificar relatório gerado
kubectl cp semantic-translation/<pod-name>:/reports/ste-kafka-debug-results.md ./debug-report.md
```

**Solução**:
- Verificar se os tópicos estão criados no Kafka
- Verificar se há mismatch de nomenclatura (ex: `.` vs `-`)
- Atualizar variável de ambiente `KAFKA_TOPICS` no deployment do STE

---

### Problema: Connection Timeout

**Sintoma**: Não consegue conectar aos bootstrap servers do Kafka.

**Diagnóstico**:
```bash
# Testar DNS
kubectl exec -n semantic-translation <pod-name> -- nslookup kafka-bootstrap.kafka.svc.cluster.local

# Testar conectividade TCP
kubectl exec -n semantic-translation <pod-name> -- telnet kafka-bootstrap.kafka.svc.cluster.local 9092

# Executar script de debug
kubectl exec -n semantic-translation <pod-name> -- python /app/scripts/debug-ste-kafka-connection.py
```

**Solução**:
- Verificar se o Kafka está rodando: `kubectl get pods -n kafka`
- Verificar Network Policies: `kubectl get networkpolicies -n semantic-translation`
- Verificar DNS do cluster: `kubectl get svc -n kafka`

---

### Problema: Duplicatas de Mensagens

**Sintoma**: Mensagens sendo processadas múltiplas vezes.

**Diagnóstico**:
```bash
# Executar teste de EOS
python test-eos.py --bootstrap-servers kafka-bootstrap.kafka.svc.cluster.local:9092 --messages 10000

# Verificar configuração do consumer
kubectl exec -n semantic-translation <pod-name> -- env | grep KAFKA
```

**Solução**:
- Verificar se `enable.idempotence=true` está configurado no producer
- Verificar se `isolation.level=read_committed` está configurado no consumer
- Validar que `transactional.id` é único por instância do producer

---

## Comandos Úteis

### Listar Tópicos no Kafka
```bash
kubectl exec -n kafka kafka-0 -- kafka-topics \
  --bootstrap-server localhost:9092 --list
```

### Descrever Tópico Específico
```bash
kubectl exec -n kafka kafka-0 -- kafka-topics \
  --bootstrap-server localhost:9092 \
  --describe --topic intentions-business
```

### Verificar Consumer Groups
```bash
# Listar todos os consumer groups
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups \
  --bootstrap-server localhost:9092 --list

# Descrever consumer group do STE
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group ste-consumer-group
```

### Ver Logs do STE
```bash
kubectl logs -n semantic-translation deployment/semantic-translation-engine --tail=100 -f
```

### Testar Consumo Manual
```bash
kubectl exec -n kafka kafka-0 -- kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic intentions-business \
  --from-beginning --max-messages 10
```

---

## Referências

### Documentação Externa
- [Confluent Kafka Python Client](https://docs.confluent.io/kafka-clients/python/current/overview.html)
- [Kafka AdminClient API](https://docs.confluent.io/kafka-clients/python/current/overview.html#adminclient)
- [Exactly-Once Semantics (EOS)](https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/)

### Documentação Interna
- [Relatório de Teste E2E Manual](../../reports/teste-e2e-manual-20251124.md) - Resultados de teste end-to-end do sistema
- [Configuração do STE](../../services/semantic-translation-engine/src/config/settings.py) - Settings e validação de tópicos
- [Consumer de Intenções](../../services/semantic-translation-engine/src/consumers/intent_consumer.py) - Implementação do consumer Kafka

---

## Contribuindo

Ao adicionar novos scripts neste diretório:

1. **Nomenclatura**: Use nomes descritivos com formato `kebab-case.py`
2. **Documentação**: Adicione docstring no topo do arquivo explicando propósito, uso e exemplos
3. **Logging**: Use `structlog` para logging estruturado e consistente
4. **Exit Codes**: Retorne `0` para sucesso, `1` para erro
5. **README**: Atualize esta documentação com informações do novo script

---

## Changelog

- **2024-11-24**: Adicionado `debug-ste-kafka-connection.py` para diagnóstico de conexão STE-Kafka
- **2024-XX-XX**: Criado `test-eos.py` para validação de Exactly-Once Semantics
