-- Migration 002: Add schedules and schedule_executions tables
-- GAP-06: Scheduler de Workflows

-- Tabela de schedules
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id VARCHAR(255) PRIMARY KEY,
    workflow VARCHAR(255) NOT NULL,
    schedule_type VARCHAR(50) NOT NULL CHECK (schedule_type IN ('cron', 'event', 'resource', 'manual')),
    trigger_data JSONB NOT NULL,
    priority VARCHAR(50) NOT NULL DEFAULT 'medium' CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'disabled', 'completed')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    total_runs INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Índices para schedules
CREATE INDEX idx_schedules_status ON schedules(status) WHERE status = 'active';
CREATE INDEX idx_schedules_workflow ON schedules(workflow);
CREATE INDEX idx_schedules_next_run ON schedules(next_run_at) WHERE status = 'active' AND next_run_at IS NOT NULL;
CREATE INDEX idx_schedules_priority ON schedules(priority) WHERE status = 'active';

-- Tabela de execuções de schedules
CREATE TABLE IF NOT EXISTS schedule_executions (
    execution_id VARCHAR(255) PRIMARY KEY,
    schedule_id VARCHAR(255) NOT NULL,
    workflow_id VARCHAR(255) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    output JSONB,
    FOREIGN KEY (schedule_id) REFERENCES schedules(schedule_id) ON DELETE CASCADE
);

-- Índices para execuções
CREATE INDEX idx_schedule_executions_schedule_id ON schedule_executions(schedule_id);
CREATE INDEX idx_schedule_executions_status ON schedule_executions(status);
CREATE INDEX idx_schedule_executions_started_at ON schedule_executions(started_at DESC);

-- Trigger para atualizar updated_at
CREATE OR REPLACE FUNCTION update_schedules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_schedules_updated_at
    BEFORE UPDATE ON schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_schedules_updated_at();

-- Comentários
COMMENT ON TABLE schedules IS 'Schedules de workflows para execução automática';
COMMENT ON TABLE schedule_executions IS 'Histórico de execuções de schedules';
COMMENT ON COLUMN schedules.schedule_type IS 'Tipo: cron (tempo), event (evento), manual (sob demanda)';
COMMENT ON COLUMN schedules.priority IS 'Prioridade: critical (SLO violations), high (remediation), medium (budgets), low (reports)';
COMMENT ON COLUMN schedules.trigger_data IS 'Configuração do trigger (cron_expression, event_type, parameters)';
COMMENT ON COLUMN schedules.next_run_at IS 'Próxima execução programada (apenas para cron)';
COMMENT ON COLUMN schedules.failure_count IS 'Número de falhas consecutivas (resetado em execução bem-sucedida)';
