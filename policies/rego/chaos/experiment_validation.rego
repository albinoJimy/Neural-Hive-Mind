# Chaos Engineering Experiment Validation Policy
#
# Valida experimentos de chaos engineering antes da execução para:
# - Verificar autorização do executor
# - Validar ambiente permitido
# - Verificar janelas de manutenção
# - Proteger namespaces críticos
# - Limitar blast radius
#
# Package: neuralhive.chaos.experiment_validation

package neuralhive.chaos.experiment_validation

import future.keywords.if
import future.keywords.in

# Default deny
default allow = false

# Namespaces protegidos - nunca permitir chaos nestes
protected_namespaces := [
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "cert-manager",
    "istio-system",
    "monitoring",
    "logging",
]

# Ambientes permitidos para chaos engineering
allowed_environments := ["staging", "development", "chaos-test"]

# Ambientes que requerem aprovação especial
approval_required_environments := ["production", "pre-production"]

# Serviços críticos que requerem aprovação OPA
critical_services := [
    "gateway-intencoes",
    "consensus-engine",
    "queen-agent",
    "orchestrator-dynamic",
    "service-registry",
]

# Horário comercial (para restrições em produção)
business_hours_start := 9
business_hours_end := 18

# =============================================================================
# Allow Rules - Define quando experimentos são permitidos
# =============================================================================

# Permitir experimento se todas as condições forem atendidas
allow if {
    # Ambiente deve ser permitido ou ter aprovação especial
    environment_allowed

    # Namespace não pode ser protegido
    not namespace_protected

    # Blast radius dentro do limite
    blast_radius_within_limit

    # Se serviço crítico, requer aprovação
    critical_service_approved

    # Executor deve estar autorizado
    executor_authorized
}

# =============================================================================
# Environment Validation
# =============================================================================

# Ambiente permitido sem aprovação especial
environment_allowed if {
    input.experiment.environment in allowed_environments
}

# Ambiente com aprovação especial (produção)
environment_allowed if {
    input.experiment.environment in approval_required_environments
    input.approval.opa_approved == true
    input.approval.approved_by != ""
}

# =============================================================================
# Namespace Protection
# =============================================================================

# Verifica se qualquer namespace alvo está protegido
namespace_protected if {
    some injection in input.experiment.fault_injections
    injection.target.namespace in protected_namespaces
}

# =============================================================================
# Blast Radius Limits
# =============================================================================

# Blast radius dentro do limite para o ambiente
blast_radius_within_limit if {
    input.experiment.blast_radius_limit <= get_max_blast_radius(input.experiment.environment)
}

# Limites de blast radius por ambiente
get_max_blast_radius(env) := 2 if {
    env == "production"
}

get_max_blast_radius(env) := 5 if {
    env in ["pre-production", "staging"]
}

get_max_blast_radius(env) := 10 if {
    env in ["development", "chaos-test"]
}

get_max_blast_radius(_) := 3

# =============================================================================
# Critical Service Protection
# =============================================================================

# Serviço não é crítico ou tem aprovação
critical_service_approved if {
    not targets_critical_service
}

critical_service_approved if {
    targets_critical_service
    input.approval.opa_approved == true
}

# Verifica se experimento atinge serviço crítico
targets_critical_service if {
    some injection in input.experiment.fault_injections
    injection.target.service_name in critical_services
}

targets_critical_service if {
    some injection in input.experiment.fault_injections
    some label_value in injection.target.labels
    label_value in critical_services
}

# =============================================================================
# Executor Authorization
# =============================================================================

# Executor autorizado se tiver role apropriada
executor_authorized if {
    input.executor.role in ["chaos-engineer", "sre", "platform-admin"]
}

# Executor autorizado por grupo
executor_authorized if {
    "chaos-engineering" in input.executor.groups
}

# =============================================================================
# Time-based Restrictions (Production)
# =============================================================================

# Fora do horário comercial em produção
outside_business_hours if {
    current_hour := time.clock([time.now_ns(), "America/Sao_Paulo"])[0]
    current_hour < business_hours_start
}

outside_business_hours if {
    current_hour := time.clock([time.now_ns(), "America/Sao_Paulo"])[0]
    current_hour >= business_hours_end
}

# Weekend check
is_weekend if {
    day := time.weekday(time.now_ns())
    day in ["Saturday", "Sunday"]
}

# =============================================================================
# Violations - Coleta violações para relatório
# =============================================================================

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.target.namespace in protected_namespaces
    violation := {
        "policy": "experiment_validation",
        "rule": "protected_namespace",
        "msg": sprintf("Namespace protegido não pode ser alvo de chaos: %s", [injection.target.namespace]),
        "severity": "critical"
    }
}

violations[violation] if {
    not input.experiment.environment in allowed_environments
    not input.experiment.environment in approval_required_environments
    violation := {
        "policy": "experiment_validation",
        "rule": "invalid_environment",
        "msg": sprintf("Ambiente não permitido para chaos: %s", [input.experiment.environment]),
        "severity": "high"
    }
}

violations[violation] if {
    input.experiment.environment in approval_required_environments
    not input.approval.opa_approved
    violation := {
        "policy": "experiment_validation",
        "rule": "approval_required",
        "msg": sprintf("Experimento em ambiente %s requer aprovação OPA", [input.experiment.environment]),
        "severity": "high"
    }
}

violations[violation] if {
    input.experiment.blast_radius_limit > get_max_blast_radius(input.experiment.environment)
    violation := {
        "policy": "experiment_validation",
        "rule": "blast_radius_exceeded",
        "msg": sprintf("Blast radius %d excede limite %d para ambiente %s", [
            input.experiment.blast_radius_limit,
            get_max_blast_radius(input.experiment.environment),
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    targets_critical_service
    not input.approval.opa_approved
    violation := {
        "policy": "experiment_validation",
        "rule": "critical_service_not_approved",
        "msg": "Experimento atinge serviço crítico e requer aprovação OPA",
        "severity": "critical"
    }
}

violations[violation] if {
    not executor_authorized
    violation := {
        "policy": "experiment_validation",
        "rule": "executor_not_authorized",
        "msg": sprintf("Executor %s não autorizado para chaos engineering", [input.executor.name]),
        "severity": "critical"
    }
}

violations[violation] if {
    input.experiment.environment == "production"
    not outside_business_hours
    not is_weekend
    not input.approval.business_hours_override
    violation := {
        "policy": "experiment_validation",
        "rule": "business_hours_restriction",
        "msg": "Chaos em produção não permitido durante horário comercial sem override",
        "severity": "high"
    }
}

# =============================================================================
# Metadata
# =============================================================================

metadata := {
    "policy_name": "experiment_validation",
    "version": "1.0.0",
    "description": "Valida experimentos de chaos engineering",
    "owner": "self-healing-engine",
    "protected_namespaces": protected_namespaces,
    "critical_services": critical_services,
    "allowed_environments": allowed_environments
}
