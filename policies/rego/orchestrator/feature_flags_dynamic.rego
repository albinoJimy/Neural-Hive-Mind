package neuralhive.orchestrator.feature_flags_dynamic

# Feature Flags Dinâmicas via Redis
#
# Esta policy consulta feature flags armazenadas em Redis via data.external.http,
# permitindo atualização dinâmica sem necessidade de redeploy.
#
# Arquitetura:
#   Redis (feature_flags:all) --> OPA (data.external) --> Avaliação
#   Fallback: valores hardcoded se Redis indisponível
#
# Uso:
#   input {
#     flag_name: "intelligent_scheduler"
#     flags: {...}  # flags do Redis ou defaults
#     context: {...}  # contexto da requisição
#   }

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# ============================================================================
# FLAGS PADRÃO (FALLBACK QUANDO REDIS INDISPONÍVEL)
# ============================================================================

default flags := {
    "intelligent_scheduler_enabled": false,
    "burst_capacity_enabled": false,
    "predictive_allocation_enabled": false,
    "auto_scaling_enabled": false,
    "gradual_rollout": false,
    "scheduler_namespaces": ["production", "staging"],
    "burst_threshold": 80,
    "premium_tenants": [],
    "scaling_threshold": 100,
    "experimental_features_enabled": false,
}

# ============================================================================
# RESULTADO PRINCIPAL - DECISÕES BOOLEANAS
# ============================================================================

result := {
    "enable_intelligent_scheduler": enable_intelligent_scheduler,
    "enable_burst_capacity": enable_burst_capacity,
    "enable_predictive_allocation": enable_predictive_allocation,
    "enable_auto_scaling": enable_auto_scaling,
    "enable_experimental_features": enable_experimental_features,
}

# ============================================================================
# FEATURE 1: INTELLIGENT SCHEDULER
# ============================================================================

default enable_intelligent_scheduler := false

enable_intelligent_scheduler if {
    # Flag global habilitada
    input.flags.intelligent_scheduler_enabled == true

    # Namespace permitido
    is_namespace_allowed(input.context.namespace, input.flags.scheduler_namespaces)

    # Risk band permite scheduler (critical/high sempre)
    risk_band_allows_scheduler(input.resource.risk_band)
}

enable_intelligent_scheduler if {
    # Flag global habilitada
    input.flags.intelligent_scheduler_enabled == true

    # Namespace permitido
    is_namespace_allowed(input.context.namespace, input.flags.scheduler_namespaces)

    # Para medium/low, habilitar se não estiver em rollout gradual
    not risk_band_allows_scheduler(input.resource.risk_band)
    input.flags.gradual_rollout != true
}

# ============================================================================
# FEATURE 2: BURST CAPACITY
# ============================================================================

default enable_burst_capacity := false

enable_burst_capacity if {
    # Flag global habilitada
    input.flags.burst_capacity_enabled == true

    # Carga atual abaixo do threshold
    input.context.current_load < input.flags.burst_threshold

    # Tenant é premium
    is_tenant_premium(input.context.tenant_id, input.flags.premium_tenants)
}

enable_burst_capacity if {
    # Flag global habilitada
    input.flags.burst_capacity_enabled == true

    # Carga atual abaixo do threshold
    input.context.current_load < input.flags.burst_threshold

    # Ou risk_band é critical (sempre permitir burst)
    input.resource.risk_band == "critical"
}

# ============================================================================
# FEATURE 3: PREDICTIVE ALLOCATION
# ============================================================================

default enable_predictive_allocation := false

enable_predictive_allocation if {
    # Flag global habilitada
    input.flags.predictive_allocation_enabled == true

    # Acurácia do modelo suficiente
    input.context.model_accuracy > 0.85

    # Namespace em beta testing
    is_namespace_in_beta(input.context.namespace)
}

# ============================================================================
# FEATURE 4: AUTO-SCALING
# ============================================================================

default enable_auto_scaling := false

enable_auto_scaling if {
    # Flag global habilitada
    input.flags.auto_scaling_enabled == true

    # Queue depth acima do threshold
    input.context.queue_depth > input.flags.scaling_threshold

    # Dentro da janela de tempo permitida
    is_within_business_hours(input.context.current_time)
}

# ============================================================================
# FEATURE 5: EXPERIMENTAL FEATURES
# ============================================================================

default enable_experimental_features := false

enable_experimental_features if {
    # Namespace de desenvolvimento/staging
    is_development_namespace(input.context.namespace)
}

enable_experimental_features if {
    # Tenant optou por early access
    is_early_access_tenant(input.context.tenant_id)
}

enable_experimental_features if {
    # Flag explicitamente habilitada
    input.flags.experimental_features_enabled == true
}

# ============================================================================
# HELPERS - FUNÇÕES UTILITÁRIAS
# ============================================================================

# Verifica se namespace está na lista permitida
is_namespace_allowed(namespace, allowed_list) if {
    allowed_list[_] == namespace
}

# Verifica se tenant é premium
is_tenant_premium(tenant_id, premium_list) if {
    premium_list[_] == tenant_id
}

# Risk bands que sempre permitem scheduler
risk_band_allows_scheduler(risk_band) if {
    risk_band == "critical"
}

risk_band_allows_scheduler(risk_band) if {
    risk_band == "high"
}

# Namespaces em beta testing
is_namespace_in_beta(namespace) if {
    namespace == "staging"
}

is_namespace_in_beta(namespace) if {
    namespace == "beta"
}

# Namespaces de desenvolvimento
is_development_namespace(namespace) if {
    namespace == "development"
}

is_development_namespace(namespace) if {
    namespace == "dev"
}

is_development_namespace(namespace) if {
    namespace == "staging"
}

# Tenants com early access
is_early_access_tenant(tenant_id) if {
    # Implementar lógica de early access
    # Por enquanto, sempre false
    false
}

# Verifica se está dentro de horário comercial
is_within_business_hours(current_time) if {
    # Simplificado: sempre permitir por enquanto
    # TODO: Implementar lógica de horário comercial
    true
}

# ============================================================================
# AVALIAÇÃO DINÂMICA DE FLAG (PARA INTEGRAÇÃO REDIS)
# ============================================================================

# Avalia uma flag específica baseado em input dinâmico
default is_enabled := false

is_enabled if {
    flag_name := input.flag_name
    all_flags := input.flags

    # Flag está globalmente habilitada
    all_flags[flag_name] == true

    # Avaliar condições adicionais baseadas no contexto
    eval_context_conditions(flag_name, input.context)
}

# Avalia condições de contexto para cada flag
eval_context_conditions("intelligent_scheduler_enabled", context) if {
    # Verificar namespace
    context.namespace in ["production", "staging"]
}

eval_context_conditions("burst_capacity_enabled", context) if {
    # Verificar carga
    context.current_load < 80
}

eval_context_conditions("predictive_allocation_enabled", context) if {
    # Verificar acurácia do modelo
    context.model_accuracy > 0.85
}

eval_context_conditions("auto_scaling_enabled", context) if {
    # Verificar queue depth
    context.queue_depth > 100
}

# Condição default se não houver restrições específicas
eval_context_conditions(flag_name, context) if {
    # Se não houver condições específicas, permite
    not context.restricted
}

# ============================================================================
# HASH DETERMINÍSTICO PARA PERCENTAGE ROLLOUT
# ============================================================================

# Calcula hash SHA256 e converte para número 0-1
hash_value(value, seed) := hash if {
    h := sha256(concat(seed, ":", value))
    hash := to_number(substr(h, 0, 8), 16) / 4294967296
}

# Avalia rollout baseado em porcentagem
is_percentage_rollout(percentage, value) := result if {
    hash := hash_value(value, "rollout")
    result := hash * 100 < percentage
}

# ============================================================================
# VALIDAÇÃO DE INPUT
# ============================================================================

# Verifica se input contém campos mínimos necessários
valid_input if {
    input.flags
    input.context
}

# Retorna erro se input inválido
default validation_error := ""

validation_error := "Missing required field: flags" if {
    not input.flags
}

validation_error := "Missing required field: context" if {
    input.flags
    not input.context
}
