// MongoDB initialization script for GDPR Erasure Service
// Creates TTL indexes for automatic cleanup of expired requests

db = db.getSiblingDB('nhmgdpr');

// Collection: erasure_requests
// TTL indexes para GDPR compliance

// Index 1: Remover solicitações PENDING_EXPIRED após 7 dias
db.erasure_requests.createIndex(
    { "expires_at": 1 },
    {
        name: "idx_pending_expired_ttl",
        expireAfterSeconds: 0,
        partialFilterExpression: {
            "status": "PENDING_VERIFICATION",
            "expires_at": { $exists: true, $ne: null }
        }
    }
);

// Index 2: Remover solicitações COMPLETED após 90 dias (retenção GDPR)
db.erasure_requests.createIndex(
    { "completed_at": 1 },
    {
        name: "idx_completed_ttl",
        expireAfterSeconds: 90 * 24 * 60 * 60, // 90 dias em segundos
        partialFilterExpression: {
            "status": "COMPLETED",
            "completed_at": { $exists: true, $ne: null }
        }
    }
);

// Index 3: Remover solicitações FAILED após 90 dias
db.erasure_requests.createIndex(
    { "created_at": 1 },
    {
        name: "idx_failed_ttl",
        expireAfterSeconds: 90 * 24 * 60 * 60,
        partialFilterExpression: {
            "status": { $in: ["FAILED", "CANCELLED", "EXPIRED"] },
            "created_at": { $exists: true, $ne: null }
        }
    }
);

// Index 4: Busca por user_id (comum em queries)
db.erasure_requests.createIndex(
    { "user_id": 1, "created_at": -1 },
    { name: "idx_user_created" }
);

// Index 5: Busca por request_id (único)
db.erasure_requests.createIndex(
    { "request_id": 1 },
    { name: "idx_request_id", unique: true }
);

// Index 6: Busca por status (para dashboard de monitoramento)
db.erasure_requests.createIndex(
    { "status": 1, "created_at": -1 },
    { name: "idx_status_created" }
);

// Index 7: Busca por email (para verificação de duplicatas pendentes)
db.erasure_requests.createIndex(
    { "email": 1, "status": 1 },
    {
        name: "idx_email_status",
        partialFilterExpression: {
            "status": "PENDING_VERIFICATION",
            "email": { $exists: true, $ne: null }
        }
    }
);

print('MongoDB indexes created for nhmgdpr.erasure_requests');
