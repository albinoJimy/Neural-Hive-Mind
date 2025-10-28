"""
Métricas Prometheus para Gateway de Intenções - Schema Padronizado Neural Hive-Mind

IMPORTANT: All metrics use coarse-grained labels only to prevent high cardinality.
intent_id and plan_id are NEVER used as metric labels.
Use trace_id exemplars for correlation instead of high-cardinality labels.
"""
from prometheus_client import Counter, Histogram, Gauge

# Métricas de requisições - Schema padronizado
# NOTE: Using only coarse-grained labels (domain, channel, status)
intent_counter = Counter(
    'neural_hive_requests_total',
    'Total de requisições processadas no Neural Hive-Mind',
    ['neural_hive_component', 'neural_hive_layer', 'domain', 'channel', 'status']
)

# Métricas de latência de captura (Fluxo A) - Schema padronizado
latency_histogram = Histogram(
    'neural_hive_captura_duration_seconds',
    'Duração da captura de intenções (Fluxo A)',
    ['neural_hive_component', 'neural_hive_layer', 'domain', 'channel'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')]
)

# Métricas de confidence - Schema padronizado
confidence_histogram = Histogram(
    'neural_hive_intent_confidence',
    'Distribuição de confiança das intenções',
    ['neural_hive_component', 'neural_hive_layer', 'domain', 'channel'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Métricas de sistema
active_connections = Gauge(
    'gateway_active_connections',
    'Conexões ativas no gateway'
)

# Métricas de roteamento por confiança - Schema padronizado
low_confidence_routed_counter = Counter(
    'neural_hive_low_confidence_routed_total',
    'Intenções roteadas para validação devido à baixa confiança',
    ['neural_hive_component', 'neural_hive_layer', 'domain', 'channel', 'route_target']
)

# Métricas de tamanho de mensagens
message_size_histogram = Histogram(
    'intention_envelope_bytes',
    'Tamanho das envelopes de intenção em bytes',
    ['domain'],
    buckets=[1024, 4096, 16384, 65536, 262144, 1048576, 4194304, float('inf')]  # 1KB to 4MB+
)

message_size_gauge = Gauge(
    'intention_envelope_max_bytes',
    'Tamanho máximo recente das envelopes de intenção em bytes'
)

# Métricas de erro de tamanho de mensagem
record_too_large_counter = Counter(
    'intentions_record_too_large_total',
    'Total de intenções rejeitadas por exceder limite de tamanho',
    ['domain']
)

def setup_metrics():
    """Configurar métricas"""
    pass  # Métricas já configuradas