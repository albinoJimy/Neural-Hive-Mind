# Verificações Implementadas

Este documento descreve as implementações realizadas baseadas nos comentários de verificação do código.

## 1. Arquivos de Valores Helm para Dev

**Problema:** Workflows de CI/CD referenciavam arquivos de valores para ambiente de desenvolvimento que não existiam.

**Solução Implementada:**
- `environments/dev/gateway-values.yaml`: Configurações específicas para desenvolvimento do gateway (recursos reduzidos, debug habilitado, réplica única)
- `environments/dev/kafka-values.yaml`: Configurações de tópicos Kafka para desenvolvimento (replicação single, retenção menor, partições reduzidas)

**Arquivos Modificados:**
- `environments/dev/gateway-values.yaml` (criado)
- `environments/dev/kafka-values.yaml` (criado)

## 2. Gateamento por Confiança

**Problema:** Intenções com baixa confiança eram publicadas diretamente nos tópicos principais ao invés de serem roteadas para validação manual.

**Solução Implementada:**
- Lógica de gateamento baseada no campo `requires_manual_validation` do pipeline NLU
- Intenções com baixa confiança são roteadas para o tópico `intentions.validation`
- Métricas adicionadas para rastrear roteamentos por baixa confiança
- Respostas da API incluem informações sobre validação quando aplicável

**Arquivos Modificados:**
- `services/gateway-intencoes/src/main.py`: Lógica de gateamento em ambos endpoints (texto e voz)
- `services/gateway-intencoes/src/kafka/producer.py`: Parâmetro `topic_override` adicionado
- `services/gateway-intencoes/src/observability/metrics.py`: Métrica `low_confidence_routed_counter`

## 3. Controle de Tamanho de Mensagem

**Problema:** Não havia controle nem telemetria para envelopes que excedem limites de tamanho do Kafka.

**Solução Implementada:**
- Limite de `max.message.bytes` aumentado de 1MB para 4MB em todos os tópicos
- Métricas de tamanho de envelope implementadas: histograma, gauge e contador de erros
- Tratamento específico para erros `RECORD_TOO_LARGE` com retorno HTTP 413
- Aviso em log quando envelope atinge 90% do limite (3.5MB)

**Arquivos Modificados:**
- `helm-charts/kafka-topics/values.yaml`: Limites de tamanho atualizados
- `environments/dev/kafka-values.yaml`: Limites de tamanho atualizados
- `services/gateway-intencoes/src/kafka/producer.py`: Medição de tamanho e tratamento de erros
- `services/gateway-intencoes/src/observability/metrics.py`: Métricas de tamanho adicionadas
- `services/gateway-intencoes/src/main.py`: Tratamento de erro HTTP 413

## 4. ACLs Kafka com Privilégios Mínimos

**Problema:** ACLs utilizavam `operation: All` com padrão `prefix`, concedendo permissões excessivas.

**Solução Implementada:**
- ACLs específicas por operação e tópico com `patternType: literal`
- Usuário separado para gateway produtor (`gateway-producer`) com permissões apenas de Write/Describe
- Topic manager limitado a operações Create/Alter/Describe/DescribeConfigs
- Usuários consumidores opcionais com permissões Read-only
- Gateway excluído do tópico de auditoria (não escreve diretamente)

**Arquivos Modificados:**
- `helm-charts/kafka-topics/templates/kafka-topics.yaml`: Estrutura de ACL reescrita
- `helm-charts/kafka-topics/values.yaml`: Definições de usuários adicionadas
- `environments/dev/kafka-values.yaml`: Usuários simplificados para desenvolvimento

## Validação

Todas as alterações mantêm compatibilidade com o comportamento existente para casos de sucesso, adicionando apenas as melhorias de segurança, monitoramento e tratamento de erros necessárias.