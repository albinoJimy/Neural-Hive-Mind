from prometheus_client import Counter, Histogram, Gauge

# Decisões consolidadas
consensus_decisions_total = Counter(
    'neural_hive_consensus_decisions_total',
    'Total de decisões consolidadas',
    ['domain', 'decision', 'method']
)

# Duração do consenso
consensus_duration_seconds = Histogram(
    'neural_hive_consensus_duration_seconds',
    'Duração do processo de consenso',
    ['domain'],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Divergência entre especialistas
specialist_divergence_histogram = Histogram(
    'neural_hive_specialist_divergence',
    'Distribuição de divergência entre especialistas',
    ['domain'],
    buckets=[0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5]
)

# Confiança agregada
aggregated_confidence_histogram = Histogram(
    'neural_hive_aggregated_confidence',
    'Distribuição de confiança agregada',
    ['domain'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Risco agregado
aggregated_risk_histogram = Histogram(
    'neural_hive_aggregated_risk',
    'Distribuição de risco agregado',
    ['domain'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Fallback usado
fallback_used_total = Counter(
    'neural_hive_consensus_fallback_used_total',
    'Total de vezes que fallback determinístico foi usado',
    ['domain', 'reason']
)

# Unanimidade
unanimous_decisions_total = Counter(
    'neural_hive_unanimous_decisions_total',
    'Total de decisões unânimes',
    ['domain', 'decision']
)

# Revisão humana requerida
human_review_required_total = Counter(
    'neural_hive_human_review_required_total',
    'Total de decisões que requerem revisão humana',
    ['domain', 'reason']
)

# Feromônios publicados
pheromones_published_total = Counter(
    'neural_hive_pheromones_published_total',
    'Total de feromônios publicados',
    ['specialist_type', 'domain', 'pheromone_type']
)

# Força de feromônios
pheromone_strength_gauge = Gauge(
    'neural_hive_pheromone_strength',
    'Força atual de feromônios',
    ['specialist_type', 'domain', 'pheromone_type']
)

# Pesos dinâmicos aplicados
dynamic_weights_gauge = Gauge(
    'neural_hive_specialist_dynamic_weight',
    'Peso dinâmico aplicado ao especialista',
    ['specialist_type', 'domain']
)

# Tempo de convergência
convergence_time_histogram = Histogram(
    'neural_hive_consensus_convergence_time_ms',
    'Tempo de convergência do consenso em milliseconds',
    ['domain'],
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000, 5000]
)

# Violações de compliance
compliance_violations_total = Counter(
    'neural_hive_compliance_violations_total',
    'Total de violações de compliance',
    ['domain', 'violation_type']
)


class ConsensusMetrics:
    '''Wrapper para métricas de consenso com métodos de conveniência'''

    @staticmethod
    def observe_consensus_duration(duration: float, domain: str):
        '''Observa duração de consenso'''
        consensus_duration_seconds.labels(domain=domain).observe(duration)

    @staticmethod
    def observe_divergence(divergence: float, domain: str):
        '''Observa divergência'''
        specialist_divergence_histogram.labels(domain=domain).observe(divergence)

    @staticmethod
    def observe_confidence(confidence: float, domain: str):
        '''Observa confiança agregada'''
        aggregated_confidence_histogram.labels(domain=domain).observe(confidence)

    @staticmethod
    def observe_risk(risk: float, domain: str):
        '''Observa risco agregado'''
        aggregated_risk_histogram.labels(domain=domain).observe(risk)

    @staticmethod
    def increment_decisions(domain: str, decision: str, method: str):
        '''Incrementa contador de decisões'''
        consensus_decisions_total.labels(
            domain=domain,
            decision=decision,
            method=method
        ).inc()

    @staticmethod
    def increment_fallback_used(domain: str, reason: str = 'compliance_violation'):
        '''Incrementa contador de fallback'''
        fallback_used_total.labels(domain=domain, reason=reason).inc()

    @staticmethod
    def increment_unanimous(domain: str, decision: str):
        '''Incrementa contador de decisões unânimes'''
        unanimous_decisions_total.labels(domain=domain, decision=decision).inc()

    @staticmethod
    def increment_human_review(domain: str, reason: str):
        '''Incrementa contador de revisão humana'''
        human_review_required_total.labels(domain=domain, reason=reason).inc()

    @staticmethod
    def increment_pheromone(specialist_type: str, domain: str, pheromone_type: str):
        '''Incrementa contador de feromônios'''
        pheromones_published_total.labels(
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type
        ).inc()

    @staticmethod
    def set_pheromone_strength(specialist_type: str, domain: str, pheromone_type: str, strength: float):
        '''Define força de feromônio'''
        pheromone_strength_gauge.labels(
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type
        ).set(strength)

    @staticmethod
    def set_dynamic_weight(specialist_type: str, domain: str, weight: float):
        '''Define peso dinâmico'''
        dynamic_weights_gauge.labels(
            specialist_type=specialist_type,
            domain=domain
        ).set(weight)

    @staticmethod
    def observe_convergence_time(time_ms: int, domain: str):
        '''Observa tempo de convergência'''
        convergence_time_histogram.labels(domain=domain).observe(time_ms)

    @staticmethod
    def increment_compliance_violation(domain: str, violation_type: str):
        '''Incrementa contador de violações de compliance'''
        compliance_violations_total.labels(
            domain=domain,
            violation_type=violation_type
        ).inc()
