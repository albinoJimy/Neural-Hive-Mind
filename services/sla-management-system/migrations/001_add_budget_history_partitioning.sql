-- Migração: Adiciona particionamento temporal para error_budgets
-- Descrição: Converte tabela error_budgets para particionada por mês,
--            adiciona índices otimizados e view materializada para agregações diárias

-- Início da transação
BEGIN;

-- 1. Criar nova tabela particionada
CREATE TABLE IF NOT EXISTS error_budgets_partitioned (
    budget_id VARCHAR(255) NOT NULL,
    slo_id VARCHAR(255) NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    calculated_at TIMESTAMP NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    sli_value FLOAT NOT NULL,
    slo_target FLOAT NOT NULL,
    error_budget_total FLOAT NOT NULL,
    error_budget_consumed FLOAT NOT NULL,
    error_budget_remaining FLOAT NOT NULL,
    status VARCHAR(50) NOT NULL,
    burn_rates JSONB,
    violations_count INTEGER DEFAULT 0,
    last_violation_at TIMESTAMP,
    metadata JSONB,
    PRIMARY KEY (budget_id, calculated_at)
) PARTITION BY RANGE (calculated_at);

-- 2. Criar partições retroativas (últimos 6 meses) e futuras (próximos 3 meses)
-- Partição julho 2025
CREATE TABLE IF NOT EXISTS error_budgets_y2025m07 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');

-- Partição agosto 2025
CREATE TABLE IF NOT EXISTS error_budgets_y2025m08 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

-- Partição setembro 2025
CREATE TABLE IF NOT EXISTS error_budgets_y2025m09 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

-- Partição outubro 2025
CREATE TABLE IF NOT EXISTS error_budgets_y2025m10 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

-- Partição novembro 2025
CREATE TABLE IF NOT EXISTS error_budgets_y2025m11 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

-- Partição dezembro 2025
CREATE TABLE IF NOT EXISTS error_budgets_y2025m12 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

-- Partição janeiro 2026
CREATE TABLE IF NOT EXISTS error_budgets_y2026m01 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Partição fevereiro 2026
CREATE TABLE IF NOT EXISTS error_budgets_y2026m02 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- Partição março 2026
CREATE TABLE IF NOT EXISTS error_budgets_y2026m03 PARTITION OF error_budgets_partitioned
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- 3. Criar índices compostos otimizados
CREATE INDEX IF NOT EXISTS idx_error_budgets_part_slo_calc_status
ON error_budgets_partitioned(slo_id, calculated_at DESC, status);

CREATE INDEX IF NOT EXISTS idx_error_budgets_part_service_calc
ON error_budgets_partitioned(service_name, calculated_at DESC);

CREATE INDEX IF NOT EXISTS idx_error_budgets_part_calc_at
ON error_budgets_partitioned(calculated_at DESC);

-- 4. Função para auto-criação de partições
CREATE OR REPLACE FUNCTION create_budget_partition_if_not_exists()
RETURNS TRIGGER AS $$
DECLARE
    partition_name TEXT;
    partition_start DATE;
    partition_end DATE;
BEGIN
    -- Calcular nome e limites da partição
    partition_start := date_trunc('month', NEW.calculated_at)::DATE;
    partition_end := (partition_start + INTERVAL '1 month')::DATE;
    partition_name := 'error_budgets_y' || to_char(partition_start, 'YYYY') || 'm' || to_char(partition_start, 'MM');

    -- Tentar criar partição se não existir
    BEGIN
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF error_budgets_partitioned
             FOR VALUES FROM (%L) TO (%L)',
            partition_name, partition_start, partition_end
        );
    EXCEPTION WHEN duplicate_table THEN
        -- Partição já existe, ignorar
        NULL;
    END;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. Criar trigger para auto-criação de partições
DROP TRIGGER IF EXISTS trigger_create_budget_partition ON error_budgets_partitioned;
CREATE TRIGGER trigger_create_budget_partition
    BEFORE INSERT ON error_budgets_partitioned
    FOR EACH ROW
    EXECUTE FUNCTION create_budget_partition_if_not_exists();

-- 6. Migrar dados e fazer swap de nomes (se tabela original existir)
DO $$
BEGIN
    -- Verificar se já foi migrada (error_budgets é particionada)
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_partitioned_table pt ON c.oid = pt.partrelid
        WHERE c.relname = 'error_budgets'
    ) THEN
        RAISE NOTICE 'Tabela error_budgets já está particionada. Pulando migração.';
        RETURN;
    END IF;

    -- Verificar se tabela original existe e não é particionada
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'error_budgets' AND table_schema = 'public') THEN
        -- Copiar dados para tabela particionada
        INSERT INTO error_budgets_partitioned
        SELECT * FROM error_budgets
        ON CONFLICT (budget_id, calculated_at) DO NOTHING;

        -- Swap de nomes: original -> backup, particionada -> original
        ALTER TABLE error_budgets RENAME TO error_budgets_backup;
        ALTER TABLE error_budgets_partitioned RENAME TO error_budgets;

        RAISE NOTICE 'Migração concluída: error_budgets_backup contém dados originais, error_budgets agora é particionada.';
    ELSE
        -- Tabela original não existe, apenas renomear particionada
        ALTER TABLE IF EXISTS error_budgets_partitioned RENAME TO error_budgets;
        RAISE NOTICE 'Tabela error_budgets criada como particionada (sem dados para migrar).';
    END IF;
END $$;

-- 7. Criar view materializada para agregações diárias
-- Nota: A view aponta para 'error_budgets' que é a tabela particionada após o swap
CREATE MATERIALIZED VIEW IF NOT EXISTS error_budgets_daily_summary AS
SELECT
    slo_id,
    service_name,
    date_trunc('day', calculated_at)::DATE as summary_date,
    AVG(error_budget_remaining) as avg_remaining,
    MIN(error_budget_remaining) as min_remaining,
    MAX(error_budget_remaining) as max_remaining,
    AVG(error_budget_consumed) as avg_consumed,
    MAX(error_budget_consumed) as max_consumed,
    STDDEV(error_budget_remaining) as stddev_remaining,
    COUNT(*) as sample_count,
    COUNT(*) FILTER (WHERE status = 'EXHAUSTED') as violations_count,
    AVG((burn_rates->0->>'rate')::FLOAT) as avg_burn_rate_1h
FROM error_budgets
WHERE calculated_at >= NOW() - INTERVAL '90 days'
GROUP BY slo_id, service_name, date_trunc('day', calculated_at)
WITH DATA;

-- Criar índice único para refresh concorrente
CREATE UNIQUE INDEX IF NOT EXISTS idx_error_budgets_daily_summary_unique
ON error_budgets_daily_summary(slo_id, summary_date);

-- Índice adicional para queries por service_name
CREATE INDEX IF NOT EXISTS idx_error_budgets_daily_summary_service
ON error_budgets_daily_summary(service_name, summary_date DESC);

-- 9. Criar tabela para tracking de refresh da view
CREATE TABLE IF NOT EXISTS materialized_view_refresh_log (
    view_name VARCHAR(255) PRIMARY KEY,
    last_refresh_at TIMESTAMP NOT NULL DEFAULT NOW(),
    refresh_duration_ms INTEGER,
    rows_affected INTEGER
);

-- Inserir registro inicial
INSERT INTO materialized_view_refresh_log (view_name, last_refresh_at)
VALUES ('error_budgets_daily_summary', NOW())
ON CONFLICT (view_name) DO UPDATE SET last_refresh_at = NOW();

-- 10. Função para refresh da view materializada com logging
CREATE OR REPLACE FUNCTION refresh_error_budgets_daily_summary()
RETURNS void AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    row_count INTEGER;
BEGIN
    start_time := clock_timestamp();

    REFRESH MATERIALIZED VIEW CONCURRENTLY error_budgets_daily_summary;

    end_time := clock_timestamp();

    SELECT COUNT(*) INTO row_count FROM error_budgets_daily_summary;

    UPDATE materialized_view_refresh_log
    SET last_refresh_at = NOW(),
        refresh_duration_ms = EXTRACT(MILLISECONDS FROM (end_time - start_time))::INTEGER,
        rows_affected = row_count
    WHERE view_name = 'error_budgets_daily_summary';
END;
$$ LANGUAGE plpgsql;

COMMIT;
