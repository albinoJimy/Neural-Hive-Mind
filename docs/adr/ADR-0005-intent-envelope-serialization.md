# ADR-0005: Intent Envelope Serialization

## Status
Accepted

## Context

O Neural Hive-Mind processa intenções através de diferentes domínios e componentes. Conforme especificado no documento-02-arquitetura-e-topologias-neural-hive-mind.md seção 6, necessitamos de um formato de envelope que atenda:

- **Flexibilidade Semântica**: Suporte a ontologias e vocabulários extensíveis
- **Performance de Transporte**: Serialização eficiente no Kafka
- **Versionamento**: Schema evolution sem breaking changes
- **Interoperabilidade**: Integração futura com Knowledge Graphs
- **Validação**: Contratos rígidos para quality assurance

### Alternativas Consideradas

1. **JSON Puro**
   - Prós: Simplicidade, legibilidade humana
   - Contras: Overhead de rede, sem schema enforcement, sem versionamento

2. **Protocol Buffers**
   - Prós: Performance excelente, versionamento
   - Contras: Menos flexibilidade semântica, curva de aprendizado

3. **Avro Puro**
   - Prós: Schema evolution, performance
   - Contras: Limitações semânticas para ontologias

4. **JSON-LD + Avro (Híbrido)**
   - Prós: Flexibilidade semântica + performance
   - Contras: Complexidade adicional de duas representações

## Decision

**Adotamos JSON-LD como formato primário com Avro como formato de transporte.**

### Arquitetura Híbrida

```
Intent Source → JSON-LD (aplicação) → Avro (Kafka) → JSON-LD (consumidor)
```

### Justificativas

1. **JSON-LD para Semântica**:
   - Suporte nativo a @context e vocabulários
   - Extensibilidade para novos tipos de intenção
   - Preparação para Knowledge Graph integration
   - Validação com JSON Schema + SHACL

2. **Avro para Transporte**:
   - Serialização binária eficiente
   - Schema evolution (backward/forward compatibility)
   - Schema Registry integration
   - Compressão automática

3. **Schema Evolution Strategy**:
   - **Backward Compatibility**: Novos campos opcionais
   - **Forward Compatibility**: Ignorar campos desconhecidos
   - **Semantic Versioning**: Major.Minor.Patch para schemas

## Implementation Details

### JSON-LD Schema Structure

```json
{
  "@context": {
    "nhm": "https://neural-hive-mind.org/ontology/",
    "intent": "nhm:Intent",
    "actor": "nhm:Actor",
    "confidence": "nhm:confidenceScore"
  },
  "@type": "nhm:IntentEnvelope",
  "id": "uuid-v4",
  "version": "1.0.0",
  "actor": {
    "@type": "nhm:Actor",
    "id": "user-123",
    "type": "human"
  },
  "intent": {
    "@type": "nhm:Intent",
    "text": "Deploy new version",
    "domain": "technical",
    "classification": "deployment"
  },
  "confidence": 0.95,
  "context": {},
  "constraints": {},
  "timestamp": "2025-01-01T00:00:00Z"
}
```

### Avro Schema Mapping

```json
{
  "type": "record",
  "name": "IntentEnvelope",
  "namespace": "org.neural_hive_mind.intent",
  "fields": [
    {"name": "id", "type": "string"},
    {"name": "version", "type": "string", "default": "1.0.0"},
    {"name": "actor_id", "type": "string"},
    {"name": "actor_type", "type": "string"},
    {"name": "intent_text", "type": "string"},
    {"name": "intent_domain", "type": {"type": "enum", "name": "Domain", "symbols": ["BUSINESS", "TECHNICAL", "INFRASTRUCTURE", "SECURITY"]}},
    {"name": "confidence", "type": "double"},
    {"name": "context", "type": {"type": "map", "values": "string"}},
    {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

### Conversion Logic

- **JSON-LD → Avro**: Flatten nested objects, map enums, extract @type
- **Avro → JSON-LD**: Reconstruct @context, restore semantic types
- **Validation**: JSON Schema validation before conversion
- **Versioning**: Schema Registry manages Avro evolution

## Migration Strategy

### Phase 1: JSON-LD Foundation
- Implement JSON-LD schemas and validation
- Create examples and documentation
- Test with Gateway de Intenções

### Phase 2: Avro Integration
- Develop Avro schemas with backward compatibility
- Implement conversion logic
- Deploy to Kafka with Schema Registry

### Phase 3: Optimization
- Performance tuning
- Schema evolution testing
- Knowledge Graph integration preparation

## Consequences

### Positivas

- **Flexibilidade Semântica**: Suporte completo a ontologias extensíveis
- **Performance**: Transporte eficiente via Avro no Kafka
- **Versionamento**: Schema evolution sem breaking changes
- **Future-Proof**: Preparado para Knowledge Graph integration
- **Developer Experience**: JSON-LD familiar para desenvolvedores

### Negativas

- **Complexidade**: Duas representações requerem conversão
- **Overhead Computacional**: CPU adicional para conversões
- **Debugging**: Dois formatos para troubleshooting
- **Curva de Aprendizado**: Equipe precisa entender ambos os formatos

## Validation Rules

- JSON-LD deve passar por JSON Schema validation
- Avro deve ser válido contra schema registrado
- Conversões devem ser idempotentes (A→B→A = A)
- Todos os campos obrigatórios preservados na conversão

## References

- [JSON-LD 1.1 Specification](https://www.w3.org/TR/json-ld11/)
- [Apache Avro Specification](https://avro.apache.org/docs/current/spec.html)
- [Confluent Schema Registry](https://docs.confluent.io/platform/current/schema-registry/)
- documento-02-arquitetura-e-topologias-neural-hive-mind.md, seção 6