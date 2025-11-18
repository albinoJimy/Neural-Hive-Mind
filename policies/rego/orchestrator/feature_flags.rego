package neuralhive.orchestrator.feature_flags

# Resultado principal - decisões booleanas sobre features
result := {
    "enable_intelligent_scheduler": enable_intelligent_scheduler,
    "enable_burst_capacity": enable_burst_capacity,
    "enable_predictive_allocation": enable_predictive_allocation,
    "enable_auto_scaling": enable_auto_scaling,
    "enable_experimental_features": enable_experimental_features
}

# Feature 1: Intelligent Scheduler
default enable_intelligent_scheduler := false
enable_intelligent_scheduler {
    # Flag global habilitada
    input.flags.intelligent_scheduler_enabled == true

    # Namespace permitido
    namespace := input.context.namespace
    is_namespace_allowed(namespace, input.flags.scheduler_namespaces)

    # Para critical/high, sempre habilitar se flag global está ativa
    ticket := input.resource
    risk_band := ticket.risk_band
    risk_band_allows_scheduler(risk_band)
}

enable_intelligent_scheduler {
    # Flag global habilitada
    input.flags.intelligent_scheduler_enabled == true

    # Namespace permitido
    namespace := input.context.namespace
    is_namespace_allowed(namespace, input.flags.scheduler_namespaces)

    # Para medium/low, habilitar se não estiver em rollout gradual
    ticket := input.resource
    risk_band := ticket.risk_band
    not risk_band_allows_scheduler(risk_band)
    not input.flags.gradual_rollout
}

# Feature 2: Burst Capacity
default enable_burst_capacity := false
enable_burst_capacity {
    # Flag global habilitada
    input.flags.burst_capacity_enabled == true

    # Carga atual está abaixo do threshold
    current_load := input.context.current_load
    threshold := input.flags.burst_threshold
    current_load < threshold

    # Tenant é premium
    tenant_id := input.context.tenant_id
    is_tenant_premium(tenant_id, input.flags.premium_tenants)
}

enable_burst_capacity {
    # Flag global habilitada
    input.flags.burst_capacity_enabled == true

    # Carga atual está abaixo do threshold
    current_load := input.context.current_load
    threshold := input.flags.burst_threshold
    current_load < threshold

    # Ou risk_band é critical (sempre permitir burst)
    ticket := input.resource
    risk_band := ticket.risk_band
    risk_band == "critical"
}

# Feature 3: Predictive Allocation
default enable_predictive_allocation := false
enable_predictive_allocation {
    # Flag global habilitada
    input.flags.predictive_allocation_enabled == true

    # Acurácia do modelo suficiente
    model_accuracy := input.context.model_accuracy
    model_accuracy > 0.85

    # Namespace em beta testing
    namespace := input.context.namespace
    is_namespace_in_beta(namespace)
}

# Feature 4: Auto-scaling
default enable_auto_scaling := false
enable_auto_scaling {
    # Flag global habilitada
    input.flags.auto_scaling_enabled == true

    # Queue depth acima do threshold
    queue_depth := input.context.queue_depth
    threshold := input.flags.scaling_threshold
    queue_depth > threshold

    # Dentro da janela de tempo permitida
    current_time := input.context.current_time
    is_within_business_hours(current_time)
}

# Feature 5: Experimental Features
default enable_experimental_features := false
enable_experimental_features {
    # Namespace de desenvolvimento/staging
    namespace := input.context.namespace
    is_development_namespace(namespace)
}

enable_experimental_features {
    # Tenant optou por early access
    tenant_id := input.context.tenant_id
    is_early_access_tenant(tenant_id)
}

# Helpers

is_namespace_allowed(namespace, allowed_list) {
    allowed_list[_] == namespace
}

is_tenant_premium(tenant_id, premium_list) {
    premium_list[_] == tenant_id
}

is_tenant_premium(tenant_id, premium_list) {
    # Se lista vazia, nenhum tenant é premium
    count(premium_list) == 0
    false
}

risk_band_allows_scheduler(risk_band) {
    risk_band == "critical"
}

risk_band_allows_scheduler(risk_band) {
    risk_band == "high"
}

is_namespace_in_beta(namespace) {
    namespace == "staging"
}

is_namespace_in_beta(namespace) {
    namespace == "beta"
}

is_development_namespace(namespace) {
    namespace == "development"
}

is_development_namespace(namespace) {
    namespace == "dev"
}

is_development_namespace(namespace) {
    namespace == "staging"
}

is_early_access_tenant(tenant_id) {
    # Implementar lógica de early access
    # Por enquanto, sempre false
    false
}

is_within_business_hours(current_time) {
    # Simplificado: sempre permitir por enquanto
    # TODO: Implementar lógica de horário comercial
    true
}
