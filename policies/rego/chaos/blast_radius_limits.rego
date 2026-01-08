# Chaos Engineering Blast Radius Limits Policy
#
# Define limites granulares de blast radius para diferentes tipos de falhas.
# Garante que experimentos não impactem mais recursos do que o permitido.
#
# Package: neuralhive.chaos.blast_radius_limits

package neuralhive.chaos.blast_radius_limits

import future.keywords.if
import future.keywords.in

# Default deny
default allow = false

# =============================================================================
# Limites por Tipo de Falha e Ambiente
# =============================================================================

# Limites para POD_KILL
pod_kill_limits := {
    "production": {"max_pods": 1, "max_percentage": 10},
    "pre-production": {"max_pods": 2, "max_percentage": 25},
    "staging": {"max_pods": 3, "max_percentage": 50},
    "development": {"max_pods": 5, "max_percentage": 100},
    "chaos-test": {"max_pods": 10, "max_percentage": 100}
}

# Limites para NETWORK_PARTITION
network_partition_limits := {
    "production": {"max_services": 1, "duration_max_seconds": 60},
    "pre-production": {"max_services": 2, "duration_max_seconds": 120},
    "staging": {"max_services": 3, "duration_max_seconds": 300},
    "development": {"max_services": 5, "duration_max_seconds": 600},
    "chaos-test": {"max_services": 10, "duration_max_seconds": 1800}
}

# Limites para NETWORK_LATENCY
network_latency_limits := {
    "production": {"max_latency_ms": 100, "max_percentage": 10},
    "pre-production": {"max_latency_ms": 500, "max_percentage": 25},
    "staging": {"max_latency_ms": 2000, "max_percentage": 50},
    "development": {"max_latency_ms": 5000, "max_percentage": 100},
    "chaos-test": {"max_latency_ms": 10000, "max_percentage": 100}
}

# Limites para CPU_STRESS
cpu_stress_limits := {
    "production": {"max_cores": 1, "max_load_percent": 50},
    "pre-production": {"max_cores": 2, "max_load_percent": 70},
    "staging": {"max_cores": 4, "max_load_percent": 90},
    "development": {"max_cores": 8, "max_load_percent": 100},
    "chaos-test": {"max_cores": 16, "max_load_percent": 100}
}

# Limites para MEMORY_STRESS
memory_stress_limits := {
    "production": {"max_bytes": 268435456, "max_percentage": 25},      # 256MB
    "pre-production": {"max_bytes": 536870912, "max_percentage": 50},   # 512MB
    "staging": {"max_bytes": 1073741824, "max_percentage": 75},         # 1GB
    "development": {"max_bytes": 2147483648, "max_percentage": 90},     # 2GB
    "chaos-test": {"max_bytes": 4294967296, "max_percentage": 100}      # 4GB
}

# Limites para HTTP_ERROR
http_error_limits := {
    "production": {"max_percentage": 5, "duration_max_seconds": 30},
    "pre-production": {"max_percentage": 10, "duration_max_seconds": 60},
    "staging": {"max_percentage": 25, "duration_max_seconds": 300},
    "development": {"max_percentage": 50, "duration_max_seconds": 600},
    "chaos-test": {"max_percentage": 100, "duration_max_seconds": 1800}
}

# Limites para HTTP_DELAY
http_delay_limits := {
    "production": {"max_delay_ms": 500, "max_percentage": 10},
    "pre-production": {"max_delay_ms": 1000, "max_percentage": 25},
    "staging": {"max_delay_ms": 5000, "max_percentage": 50},
    "development": {"max_delay_ms": 10000, "max_percentage": 100},
    "chaos-test": {"max_delay_ms": 30000, "max_percentage": 100}
}

# =============================================================================
# Allow Rules
# =============================================================================

# Permitir se todas as injeções estiverem dentro dos limites
allow if {
    all_injections_within_limits
}

# Todas as injeções devem estar dentro dos limites
all_injections_within_limits if {
    count(input.experiment.fault_injections) > 0
    every injection in input.experiment.fault_injections {
        injection_within_limits(injection, input.experiment.environment)
    }
}

# =============================================================================
# Validation Functions
# =============================================================================

# Validação para POD_KILL
injection_within_limits(injection, env) if {
    injection.fault_type == "pod_kill"
    limits := pod_kill_limits[env]
    injection.target.percentage <= limits.max_percentage
}

# Validação para NETWORK_PARTITION
injection_within_limits(injection, env) if {
    injection.fault_type == "network_partition"
    limits := network_partition_limits[env]
    injection.duration_seconds <= limits.duration_max_seconds
}

# Validação para NETWORK_LATENCY
injection_within_limits(injection, env) if {
    injection.fault_type == "network_latency"
    limits := network_latency_limits[env]
    injection.parameters.latency_ms <= limits.max_latency_ms
    injection.target.percentage <= limits.max_percentage
}

# Validação para CPU_STRESS
injection_within_limits(injection, env) if {
    injection.fault_type == "cpu_stress"
    limits := cpu_stress_limits[env]
    injection.parameters.cpu_cores <= limits.max_cores
    injection.parameters.cpu_load_percent <= limits.max_load_percent
}

# Validação para MEMORY_STRESS
injection_within_limits(injection, env) if {
    injection.fault_type == "memory_stress"
    limits := memory_stress_limits[env]
    injection.parameters.memory_bytes <= limits.max_bytes
}

# Validação para HTTP_ERROR
injection_within_limits(injection, env) if {
    injection.fault_type == "http_error"
    limits := http_error_limits[env]
    injection.target.percentage <= limits.max_percentage
    injection.duration_seconds <= limits.duration_max_seconds
}

# Validação para HTTP_DELAY
injection_within_limits(injection, env) if {
    injection.fault_type == "http_delay"
    limits := http_delay_limits[env]
    injection.parameters.http_delay_ms <= limits.max_delay_ms
    injection.target.percentage <= limits.max_percentage
}

# Fallback para tipos de falha não listados (permitir com aviso)
injection_within_limits(injection, _) if {
    not injection.fault_type in ["pod_kill", "network_partition", "network_latency", "cpu_stress", "memory_stress", "http_error", "http_delay"]
}

# =============================================================================
# Violations
# =============================================================================

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "pod_kill"
    limits := pod_kill_limits[input.experiment.environment]
    injection.target.percentage > limits.max_percentage
    violation := {
        "policy": "blast_radius_limits",
        "rule": "pod_kill_percentage_exceeded",
        "msg": sprintf("POD_KILL: percentage %d excede limite %d para %s", [
            injection.target.percentage,
            limits.max_percentage,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "network_partition"
    limits := network_partition_limits[input.experiment.environment]
    injection.duration_seconds > limits.duration_max_seconds
    violation := {
        "policy": "blast_radius_limits",
        "rule": "network_partition_duration_exceeded",
        "msg": sprintf("NETWORK_PARTITION: duração %ds excede limite %ds para %s", [
            injection.duration_seconds,
            limits.duration_max_seconds,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "network_latency"
    limits := network_latency_limits[input.experiment.environment]
    injection.parameters.latency_ms > limits.max_latency_ms
    violation := {
        "policy": "blast_radius_limits",
        "rule": "network_latency_exceeded",
        "msg": sprintf("NETWORK_LATENCY: latência %dms excede limite %dms para %s", [
            injection.parameters.latency_ms,
            limits.max_latency_ms,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "cpu_stress"
    limits := cpu_stress_limits[input.experiment.environment]
    injection.parameters.cpu_cores > limits.max_cores
    violation := {
        "policy": "blast_radius_limits",
        "rule": "cpu_stress_cores_exceeded",
        "msg": sprintf("CPU_STRESS: cores %d excede limite %d para %s", [
            injection.parameters.cpu_cores,
            limits.max_cores,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "memory_stress"
    limits := memory_stress_limits[input.experiment.environment]
    injection.parameters.memory_bytes > limits.max_bytes
    violation := {
        "policy": "blast_radius_limits",
        "rule": "memory_stress_exceeded",
        "msg": sprintf("MEMORY_STRESS: bytes %d excede limite %d para %s", [
            injection.parameters.memory_bytes,
            limits.max_bytes,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "http_error"
    limits := http_error_limits[input.experiment.environment]
    injection.target.percentage > limits.max_percentage
    violation := {
        "policy": "blast_radius_limits",
        "rule": "http_error_percentage_exceeded",
        "msg": sprintf("HTTP_ERROR: percentage %d excede limite %d para %s", [
            injection.target.percentage,
            limits.max_percentage,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

violations[violation] if {
    some injection in input.experiment.fault_injections
    injection.fault_type == "http_delay"
    limits := http_delay_limits[input.experiment.environment]
    injection.parameters.http_delay_ms > limits.max_delay_ms
    violation := {
        "policy": "blast_radius_limits",
        "rule": "http_delay_exceeded",
        "msg": sprintf("HTTP_DELAY: delay %dms excede limite %dms para %s", [
            injection.parameters.http_delay_ms,
            limits.max_delay_ms,
            input.experiment.environment
        ]),
        "severity": "high"
    }
}

# =============================================================================
# Helper Functions
# =============================================================================

# Retorna os limites aplicáveis para um tipo de falha e ambiente
get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "pod_kill"
    limits := pod_kill_limits[env]
}

get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "network_partition"
    limits := network_partition_limits[env]
}

get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "network_latency"
    limits := network_latency_limits[env]
}

get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "cpu_stress"
    limits := cpu_stress_limits[env]
}

get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "memory_stress"
    limits := memory_stress_limits[env]
}

get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "http_error"
    limits := http_error_limits[env]
}

get_limits_for_fault(fault_type, env) := limits if {
    fault_type == "http_delay"
    limits := http_delay_limits[env]
}

# =============================================================================
# Metadata
# =============================================================================

metadata := {
    "policy_name": "blast_radius_limits",
    "version": "1.0.0",
    "description": "Define limites de blast radius por tipo de falha e ambiente",
    "owner": "self-healing-engine",
    "fault_types_covered": [
        "pod_kill",
        "network_partition",
        "network_latency",
        "cpu_stress",
        "memory_stress",
        "http_error",
        "http_delay"
    ]
}
