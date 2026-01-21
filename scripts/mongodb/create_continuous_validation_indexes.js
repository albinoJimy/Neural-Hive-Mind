// Criar índices para collection model_predictions
// Executar: mongosh neural_hive_orchestration < create_continuous_validation_indexes.js

db = db.getSiblingDB('neural_hive_orchestration');

// Índice composto para queries de janela temporal
db.model_predictions.createIndex(
  { model_name: 1, timestamp: -1, actual: 1 },
  { name: 'idx_model_timestamp_actual' }
);

// Índice para queries por ticket_id
db.model_predictions.createIndex(
  { ticket_id: 1 },
  { name: 'idx_ticket_id' }
);

// Índice TTL para limpeza automática (90 dias)
db.model_predictions.createIndex(
  { timestamp: 1 },
  { expireAfterSeconds: 7776000, name: 'idx_ttl_90days' }
);

// Índice para queries de error_rate e latência
db.model_predictions.createIndex(
  { model_name: 1, had_error: 1, timestamp: -1 },
  { name: 'idx_model_error_timestamp' }
);

print('Índices criados com sucesso para model_predictions');

// Verificar índices criados
printjson(db.model_predictions.getIndexes());
