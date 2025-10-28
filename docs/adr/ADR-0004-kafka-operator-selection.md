# ADR-0004: Kafka Operator Selection

## Status
Accepted

## Context

O Neural Hive-Mind requer um barramento de eventos robusto para captura e processamento de intenções. Conforme especificado no documento-02-arquitetura-e-topologias-neural-hive-mind.md seção 4.1, necessitamos de:

- **Exactly-once delivery semantics** para garantir consistência
- **Particionamento por domínio** (business, technical, infrastructure, security)
- **Integração nativa com Kubernetes** e service mesh (Istio)
- **mTLS automático** para comunicação segura
- **Observabilidade completa** com métricas e tracing
- **Controle operacional granular** para tuning de performance

### Alternativas Consideradas

1. **Amazon MSK (Managed Streaming for Kafka)**
   - Prós: Gerenciado pela AWS, setup simplificado
   - Contras: Vendor lock-in, controle limitado sobre configurações exactly-once, custos elevados para exactly-once semantics

2. **Google Cloud Pub/Sub**
   - Prós: Exactly-once nativo, serverless
   - Contras: Não é Kafka (diferentes garantias semânticas), vendor lock-in, integração limitada com Kubernetes/Istio

3. **Confluent Operator**
   - Prós: Suporte oficial da Confluent, features enterprise
   - Contras: Licenciamento complexo, overhead de features desnecessárias

4. **Strimzi Operator**
   - Prós: Open source, controle total, integração nativa K8s, observabilidade
   - Contras: Requer mais expertise operacional

## Decision

**Selecionamos o Strimzi Operator** para gerenciar nosso cluster Kafka.

### Justificativas Principais

1. **Exactly-Once Semantics**: Controle granular sobre configurações críticas:
   - `enable.idempotence=true`
   - `acks=all`
   - `min.insync.replicas=2`
   - `transaction.state.log.replication.factor=3`

2. **Integração Kubernetes**:
   - CRDs nativos para Kafka, Topics, Users
   - Integração automática com Istio service mesh
   - PodDisruptionBudgets e resource management nativo

3. **mTLS Automático**:
   - Certificados gerenciados automaticamente
   - Integração com cert-manager
   - Mutual TLS entre brokers e com clientes

4. **Observabilidade**:
   - Métricas Prometheus nativas
   - JMX metrics expostas automaticamente
   - Integração com Jaeger para tracing distribuído

5. **Controle Operacional**:
   - Configuração granular de todos os parâmetros Kafka
   - Rolling updates sem downtime
   - Backup e restore automático

6. **Custos**:
   - Open source sem custos de licenciamento
   - Execução em nossa própria infraestrutura
   - Controle total sobre recursos alocados

## Consequences

### Positivas

- **Controle Total**: Configuração precisa para exactly-once delivery conforme requisitos
- **Integração Nativa**: Service mesh e observabilidade funcionam seamlessly
- **Flexibilidade**: Evolução do cluster conforme necessidades futuras
- **Expertise**: Conhecimento interno sobre Kafka operations
- **Custos Previsíveis**: Sem surpresas de billing de providers

### Negativas

- **Complexidade Operacional**: Requer conhecimento profundo de Kafka operations
- **Responsabilidade**: Gerenciamento de upgrades, patches e troubleshooting
- **Time to Market**: Setup inicial mais complexo que soluções managed

## Implementation Notes

- Configurar cluster multi-zona com 3 brokers para alta disponibilidade
- Implementar exactly-once semantics desde o primeiro deployment
- Configurar integration com stack de observabilidade existente
- Estabelecer runbooks para operações críticas (backup, restore, scaling)
- Implementar testes de chaos engineering para validar resiliência

## References

- [Strimzi Documentation](https://strimzi.io/documentation/)
- documento-02-arquitetura-e-topologias-neural-hive-mind.md, seção 4.1
- [Kafka Exactly-Once Semantics](https://kafka.apache.org/documentation/#semantics)