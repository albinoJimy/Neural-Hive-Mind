-- ClickHouse Schema para ML Predictive Scheduling
--
-- Tabelas para armazenamento de dados históricos de execução, telemetria
-- e métricas para treinamento de modelos Prophet/ARIMA e Q-learning.
--
-- TTL:
-- - execution_logs: 540 dias (18 meses - janela de treinamento Prophet)
-- - telemetry_metrics: 365 dias (1 ano - análise de tendências)

CREATE DATABASE IF NOT EXISTS neural_hive;

-- ========================================
-- Tabela: execution_logs
-- ========================================
-- Logs de execução de tickets para forecasting de carga

CREATE TABLE IF NOT EXISTS neural_hive.execution_logs
(
    timestamp DateTime COMMENT 'Timestamp de conclusão do ticket',
    ticket_id String COMMENT 'ID único do ticket executado',
    task_type String COMMENT 'Tipo de tarefa (processing, analysis, etc.)',
    risk_band String COMMENT 'Banda de risco (low, medium, high, critical)',
    actual_duration_ms UInt32 COMMENT 'Duração real de execução em milissegundos',
    status String COMMENT 'Status final (success, error, timeout)',
    worker_id String COMMENT 'ID do worker que executou',
    resource_cpu Float32 COMMENT 'Uso de CPU durante execução (0-1)',
    resource_memory Float32 COMMENT 'Uso de memória em MB',
    sla_met UInt8 COMMENT 'Se SLA foi cumprido (1=sim, 0=não)',
    queue_depth_at_start UInt32 COMMENT 'Profundidade da fila ao iniciar ticket',
    specialist_type String COMMENT 'Tipo de specialist (business, technical, etc.)',
    priority UInt8 COMMENT 'Prioridade do ticket (1-10)',
    retry_count UInt8 COMMENT 'Número de retries'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, task_type, risk_band)
TTL timestamp + INTERVAL 540 DAY
SETTINGS index_granularity = 8192
COMMENT 'Logs históricos de execução de tickets para forecasting de carga';

-- Índices secundários para queries de treinamento
ALTER TABLE neural_hive.execution_logs
ADD INDEX idx_task_type task_type TYPE set(100) GRANULARITY 4;

ALTER TABLE neural_hive.execution_logs
ADD INDEX idx_risk_band risk_band TYPE set(10) GRANULARITY 4;

ALTER TABLE neural_hive.execution_logs
ADD INDEX idx_status status TYPE set(10) GRANULARITY 4;


-- ========================================
-- Tabela: telemetry_metrics
-- ========================================
-- Métricas de telemetria agregadas para análise de tendências

CREATE TABLE IF NOT EXISTS neural_hive.telemetry_metrics
(
    timestamp DateTime COMMENT 'Timestamp da métrica',
    service String COMMENT 'Nome do serviço (optimizer-agents, orchestrator, etc.)',
    metric_name String COMMENT 'Nome da métrica',
    metric_value Float64 COMMENT 'Valor da métrica',
    labels Map(String, String) COMMENT 'Labels da métrica (task_type, risk_band, etc.)',
    aggregation_window_seconds UInt32 COMMENT 'Janela de agregação em segundos'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, service, metric_name)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
COMMENT 'Métricas de telemetria para análise de tendências e ML';

-- Índice para queries por serviço
ALTER TABLE neural_hive.telemetry_metrics
ADD INDEX idx_service service TYPE set(50) GRANULARITY 4;


-- ========================================
-- Tabela: worker_utilization
-- ========================================
-- Utilização de workers para análise de capacidade

CREATE TABLE IF NOT EXISTS neural_hive.worker_utilization
(
    timestamp DateTime COMMENT 'Timestamp da amostra',
    worker_id String COMMENT 'ID do worker',
    active_tasks UInt16 COMMENT 'Número de tarefas ativas',
    cpu_usage Float32 COMMENT 'Uso de CPU (0-1)',
    memory_usage_mb Float32 COMMENT 'Uso de memória em MB',
    network_rx_mbps Float32 COMMENT 'Tráfego de rede recebido (Mbps)',
    network_tx_mbps Float32 COMMENT 'Tráfego de rede enviado (Mbps)',
    is_available UInt8 COMMENT 'Se worker está disponível (1=sim, 0=não)',
    specialist_type String COMMENT 'Tipo de specialist do worker'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, worker_id)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192
COMMENT 'Utilização de workers para planejamento de capacidade';


-- ========================================
-- Tabela: queue_snapshots
-- ========================================
-- Snapshots da fila de tickets para análise de padrões

CREATE TABLE IF NOT EXISTS neural_hive.queue_snapshots
(
    timestamp DateTime COMMENT 'Timestamp do snapshot',
    queue_depth UInt32 COMMENT 'Profundidade total da fila',
    avg_wait_time_ms UInt32 COMMENT 'Tempo médio de espera em milissegundos',
    tickets_by_priority Map(UInt8, UInt32) COMMENT 'Distribuição de tickets por prioridade',
    tickets_by_task_type Map(String, UInt32) COMMENT 'Distribuição de tickets por tipo de tarefa',
    tickets_by_risk_band Map(String, UInt32) COMMENT 'Distribuição de tickets por banda de risco',
    active_workers UInt16 COMMENT 'Número de workers ativos',
    available_capacity Float32 COMMENT 'Capacidade disponível estimada (0-1)'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY timestamp
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192
COMMENT 'Snapshots periódicos da fila para análise de padrões';


-- ========================================
-- Tabela: ml_model_performance
-- ========================================
-- Performance de modelos ML em produção

CREATE TABLE IF NOT EXISTS neural_hive.ml_model_performance
(
    timestamp DateTime COMMENT 'Timestamp da avaliação',
    model_name String COMMENT 'Nome do modelo (load_predictor_60m, scheduling_optimizer, etc.)',
    model_version String COMMENT 'Versão do modelo (hash ou timestamp)',
    metric_name String COMMENT 'Nome da métrica (mape, reward, accuracy, etc.)',
    metric_value Float64 COMMENT 'Valor da métrica',
    evaluation_samples UInt32 COMMENT 'Número de amostras avaliadas',
    horizon_minutes UInt32 COMMENT 'Horizonte de previsão (para modelos de forecast)',
    task_type String COMMENT 'Tipo de tarefa (para segmentação)',
    risk_band String COMMENT 'Banda de risco (para segmentação)'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, model_name)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
COMMENT 'Performance de modelos ML para monitoramento e retreinamento';


-- ========================================
-- Tabela: scheduling_decisions
-- ========================================
-- Decisões de agendamento tomadas (para Q-learning)

CREATE TABLE IF NOT EXISTS neural_hive.scheduling_decisions
(
    timestamp DateTime COMMENT 'Timestamp da decisão',
    decision_id String COMMENT 'ID único da decisão',
    state_hash String COMMENT 'Hash do estado (queue_depth, workers, load_forecast)',
    action String COMMENT 'Ação tomada (INCREASE_WORKER_POOL, etc.)',
    confidence Float32 COMMENT 'Confiança da recomendação (0-1)',
    reward Float32 COMMENT 'Reward observado após ação',
    sla_compliance_before Float32 COMMENT 'SLA compliance antes da ação',
    sla_compliance_after Float32 COMMENT 'SLA compliance depois da ação',
    throughput_before Float32 COMMENT 'Throughput antes da ação',
    throughput_after Float32 COMMENT 'Throughput depois da ação',
    was_applied UInt8 COMMENT 'Se decisão foi aplicada (1=sim, 0=rejeitada)',
    rejection_reason String COMMENT 'Motivo de rejeição (se aplicável)',
    source String COMMENT 'Fonte da decisão (ml_model, heuristic, manual)'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, action)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
COMMENT 'Decisões de agendamento para análise de política RL';


-- ========================================
-- Views Materializadas
-- ========================================

-- View: hourly_ticket_volume
-- Agregação horária de volume de tickets por tipo/risco
CREATE MATERIALIZED VIEW IF NOT EXISTS neural_hive.hourly_ticket_volume
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(timestamp_hour)
ORDER BY (timestamp_hour, task_type, risk_band)
POPULATE
AS SELECT
    toStartOfHour(timestamp) AS timestamp_hour,
    task_type,
    risk_band,
    count() AS ticket_count,
    avg(actual_duration_ms) AS avg_duration_ms,
    avg(resource_cpu) AS avg_cpu_usage,
    avg(resource_memory) AS avg_memory_mb,
    sum(sla_met) AS sla_met_count,
    count() - sum(sla_met) AS sla_missed_count
FROM neural_hive.execution_logs
GROUP BY timestamp_hour, task_type, risk_band;


-- View: daily_worker_stats
-- Estatísticas diárias de workers
CREATE MATERIALIZED VIEW IF NOT EXISTS neural_hive.daily_worker_stats
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(timestamp_day)
ORDER BY (timestamp_day, worker_id)
POPULATE
AS SELECT
    toStartOfDay(timestamp) AS timestamp_day,
    worker_id,
    specialist_type,
    avgState(active_tasks) AS avg_active_tasks_state,
    avgState(cpu_usage) AS avg_cpu_usage_state,
    avgState(memory_usage_mb) AS avg_memory_mb_state,
    sumState(toUInt64(is_available)) AS available_samples_state
FROM neural_hive.worker_utilization
GROUP BY timestamp_day, worker_id, specialist_type;


-- ========================================
-- Queries de Exemplo para Treinamento
-- ========================================

-- Query 1: Dados históricos para Prophet (18 meses, agregação horária)
-- SELECT
--     toStartOfHour(timestamp) AS ds,
--     count() AS y,
--     task_type,
--     risk_band
-- FROM neural_hive.execution_logs
-- WHERE timestamp >= now() - INTERVAL 540 DAY
--   AND task_type = 'processing'
--   AND risk_band = 'medium'
-- GROUP BY ds, task_type, risk_band
-- ORDER BY ds;

-- Query 2: Features para Q-learning (estado atual)
-- SELECT
--     count() AS current_queue_depth,
--     avg(actual_duration_ms) AS avg_task_duration_ms,
--     countIf(status = 'error') / count() AS error_rate,
--     countIf(sla_met = 1) / count() AS sla_compliance_rate
-- FROM neural_hive.execution_logs
-- WHERE timestamp >= now() - INTERVAL 1 HOUR;

-- Query 3: Validação de qualidade de dados (gaps, outliers)
-- SELECT
--     toStartOfHour(timestamp) AS hour,
--     count() AS sample_count,
--     avg(actual_duration_ms) AS avg_duration,
--     quantile(0.95)(actual_duration_ms) AS p95_duration,
--     quantile(0.99)(actual_duration_ms) AS p99_duration
-- FROM neural_hive.execution_logs
-- WHERE timestamp >= now() - INTERVAL 7 DAY
-- GROUP BY hour
-- ORDER BY hour
-- HAVING sample_count < 10;  -- Detectar gaps

-- Query 4: Análise de bottlenecks históricos
-- SELECT
--     toStartOfHour(timestamp) AS hour,
--     avg(queue_depth) AS avg_queue_depth,
--     max(queue_depth) AS max_queue_depth,
--     avg(avg_wait_time_ms) AS avg_wait_time_ms
-- FROM neural_hive.queue_snapshots
-- WHERE timestamp >= now() - INTERVAL 30 DAY
--   AND queue_depth > 100  -- Threshold de bottleneck
-- GROUP BY hour
-- ORDER BY avg_queue_depth DESC;
