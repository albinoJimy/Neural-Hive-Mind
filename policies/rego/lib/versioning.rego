# Policy Versioning Library
# Sistema de versionamento avançado para políticas OPA
# Suporte a versões semânticas, múltiplas versões ativas e depreciação

package neuralhive.policy.versioning

import future.keywords.in
import future.keywords.contains
import future.keywords.if
import future.keywords.every

# ==============================================================================
# VERSÕES SEMÂNTICAS
# ==============================================================================

# Versão atual da biblioteca de versionamento
current_library_version := "2.0.0"

# Estrutura de versão semântica
# format: "major.minor.patch"
# major: mudanças incompatíveis na API
# minor: funcionalidades backwards-compatible
# patch: correções de bugs backwards-compatible

# Parse versão semântica
parse_version(version_string) := version if {
    regex.split("^(\\d+)\\.(\\d+)\\.(\\d+)$", version_string)
    parts := regex.split("^(\\d+)\\.(\\d+)\\.(\\d+)$", version_string)
    version := {
        "major": parts[1],
        "minor": parts[2],
        "patch": parts[3],
        "original": version_string,
        "is_valid": true,
    }
}

# Versão padrão para políticas sem versão explícita
default_policy_version := "1.0.0"

# ==============================================================================
# METADADOS DE POLÍTICA
# ==============================================================================

# Metadados padrão para todas as políticas
policy_metadata(policy_id) := metadata if {
    # Extrair versão da política se disponível
    policy_version := data.policies[policy_id].metadata.version | default_policy_version

    metadata := {
        "policy_id": policy_id,
        "version": policy_version,
        "library_version": current_library_version,
        "created_at": data.policies[policy_id].metadata.created_at | "unknown",
        "updated_at": data.policies[policy_id].metadata.updated_at | "unknown",
        "author": data.policies[policy_id].metadata.author | "unknown",
        "status": data.policies[policy_id].metadata.status | "active",
        "compatibility": get_compatibility_range(policy_id),
    }
}

# Obter range de compatibilidade da política
get_compatibility_range(policy_id) := range if {
    min_version := data.policies[policy_id].metadata.compatibility.min_version | "1.0.0"
    max_version := data.policies[policy_id].metadata.compatibility.max_version | "2.x"
    range := [min_version, max_version]
}

# ==============================================================================
# COMPARAÇÃO DE VERSÕES
# ==============================================================================

# Comparar duas versões
# Retorna: -1 se v1 < v2, 0 se v1 == v2, 1 se v1 > v2
compare_versions(v1, v2) := result if {
    v1_parsed := parse_version(v1)
    v2_parsed := parse_version(v2)

    v1_major := to_number(v1_parsed.major)
    v1_minor := to_number(v1_parsed.minor)
    v1_patch := to_number(v1_parsed.patch)

    v2_major := to_number(v2_parsed.major)
    v2_minor := to_number(v2_parsed.minor)
    v2_patch := to_number(v2_parsed.patch)

    result := -1 if { v1_major < v2_major }
    result := 1 if { v1_major > v2_major }
    result := -1 if { v1_major == v2_major; v1_minor < v2_minor }
    result := 1 if { v1_major == v2_major; v1_minor > v2_minor }
    result := -1 if { v1_major == v2_major; v1_minor == v2_minor; v1_patch < v2_patch }
    result := 1 if { v1_major == v2_major; v1_minor == v2_minor; v1_patch > v2_patch }
    result := 0 # versões iguais
}

# Verificar se versão é maior ou igual a mínima requerida
version_meets_min_required(current, required) := meets if {
    compare_versions(current, required) >= 0
    meets := true
}

# Verificar se versão está dentro de um range
version_in_range(version, min_version, max_version) := in_range if {
    version_meets_min_required(version, min_version)

    # Para max_version com "x" (ex: "2.x"), considerar apenas major
    not regex.matches(".*\\.x$", max_version)
    version_meets_min_required(max_version, version)
    in_range := true
}

version_in_range(version, min_version, max_version) := in_range if {
    version_meets_min_required(version, min_version)

    # Max version com "x" - apenas major matters
    regex.matches("^(\\d+)\\.x$", max_version)
    max_parts := regex.split("^(\\d+)\\.x$", max_version)
    version_parsed := parse_version(version)
    to_number(version_parsed.major) == to_number(max_parts[1])
    in_range := true
}

# ==============================================================================
# ESTADO DE POLÍTICA
# ==============================================================================

# Estados possíveis de uma política
policy_statuses := ["active", "deprecated", "experimental", "retired"]

# Verificar se política está ativa
is_policy_active(policy_id) := active if {
    status := data.policies[policy_id].metadata.status | "active"
    status == "active"
    active := true
}

# Verificar se política está depreciada
is_policy_deprecated(policy_id) := deprecated if {
    status := data.policies[policy_id].metadata.status
    status == "deprecated"
    deprecated := true
}

# Obter versão ativa de uma política
get_active_version(policy_id) := version if {
    # Se não há multi-versioning, retornar versão única
    not data.policies[policy_id].versions
    version := data.policies[policy_id].metadata.version | default_policy_version
}

get_active_version(policy_id) := version if {
    # Com multi-versioning, retornar versão marcada como active
    some v, policy_data in data.policies[policy_id].versions
    policy_data.status == "active"
    version := v
}

# ==============================================================================
# MULTI-VERSIONING
# ==============================================================================

# Obter todas as versões disponíveis de uma política
get_all_versions(policy_id) := versions if {
    versions := [version |
        some v, _ in data.policies[policy_id].versions
        version := v
    ]
}

# Obter política específica por versão
get_policy_version(policy_id, version) := policy_data if {
    data.policies[policy_id].versions[version]
    policy_data := data.policies[policy_id].versions[version]
}

# Obter versão mais recente de uma política
get_latest_version(policy_id) := latest if {
    versions := get_all_versions(policy_id)
    # Ordenar versões e pegar a maior
    latest := max(versions)
}

# Obter versão compatível com uma versão de cliente solicitada
get_compatible_version(policy_id, client_version) := version if {
    # Tentar encontrar versão exata primeiro
    get_policy_version(policy_id, client_version)
    version := client_version
}

get_compatible_version(policy_id, client_version) := version if {
    # Se não existe versão exata, encontrar versão compatível mais recente
    all_versions := get_all_versions(policy_id)

    # Filtrar versões compatíveis
    compatible_versions := [v |
        some v in all_versions
        policy_metadata := get_policy_metadata(policy_id, v)
        version_in_range(client_version, policy_metadata.compatibility[0], policy_metadata.compatibility[1])
    ]

    # Retornar versão mais recente entre as compatíveis
    compatible_versions
    version := max(compatible_versions)
}

# Obter metadados de uma versão específica
get_policy_metadata(policy_id, version) := metadata if {
    data.policies[policy_id].versions[version]
    metadata := data.policies[policy_id].versions[version].metadata
}

# ==============================================================================
# DEPRECIAÇÃO E MIGRAÇÃO
# ==============================================================================

# Políticas depreciadas por versão
deprecated_policies := {
    "security_policies": {
        "1.0.0": {
            "deprecated_at": "2026-03-01",
            "replaced_by": "security_policies@2.0.0",
            "migration_guide": "Updated to use new threat model",
        }
    }
}

# Verificar se uma versão específica está depreciada
is_version_deprecated(policy_id, version) := deprecated if {
    deprecated_policies[policy_id][version]
    deprecated := true
}

# Obter informações de depreciação
get_deprecation_info(policy_id, version) := info if {
    is_version_deprecated(policy_id, version)
    info := deprecated_policies[policy_id][version]
}

# Obter guia de migração
get_migration_guide(old_policy_id, old_version) := guide if {
    get_deprecation_info(old_policy_id, old_version)
    guide := get_deprecation_info(old_policy_id, old_version).migration_guide
}

get_migration_guide(old_policy_id, old_version) := guide if {
    # Guia de migração padrão
    is_version_deprecated(old_policy_id, old_version)
    guide := sprintf("Migrate %s@%s to %s", [
        old_policy_id,
        old_version,
        get_deprecation_info(old_policy_id, old_version).replaced_by
    ])
}

# ==============================================================================
# VALIDAÇÃO DE VERSÃO
# ==============================================================================

# Validar formato de versão
is_valid_version(version) := valid if {
    parse_version(version)
    version.is_valid == true
    valid := true
}

# Validar que política tem versão mínima requerida
validate_policy_version(policy_id) := valid if {
    version := data.policies[policy_id].metadata.version
    is_valid_version(version)
    valid := true
}

# Resultado de validação de versão
version_validation_result(policy_id) := result if {
    version := data.policies[policy_id].metadata.version | default_policy_version
    parsed := parse_version(version)

    result := {
        "valid": parsed.is_valid,
        "version": parsed.original,
        "major": parsed.major,
        "minor": parsed.minor,
        "patch": parsed.patch,
        "warnings": get_version_warnings(policy_id),
    }
}

# Obter avisos sobre a versão
get_version_warnings(policy_id) := warnings if {
    version := data.policies[policy_id].metadata.version
    parsed := parse_version(version)

    warnings := [] if { parsed.is_valid == false }

    warnings := [w |
        is_policy_deprecated(policy_id, version)
        w := sprintf("Version %s is deprecated", [version])
    ]

    warnings := [] if {
        not is_policy_deprecated(policy_id, version)
    }
}

# ==============================================================================
# CHAVE DE VERSÃO (para cache busting)
# ==============================================================================

# Gerar chave única para combinação política + versão
version_key(policy_id, version) := key if {
    key := sprintf("%s@%s", [policy_id, version])
}

# Gerar hash de versão para validação de cache
version_hash(policy_id, version) := hash if {
    metadata := get_policy_metadata(policy_id, version)
    # Hash simples baseado em versão + timestamp
    hash := sprintf("%s-%s", [version, metadata.updated_at])
}

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

# Obter versão formatada para logging
format_version_for_logging(policy_id) := formatted if {
    version := data.policies[policy_id].metadata.version | default_policy_version
    status := data.policies[policy_id].metadata.status | "active"
    formatted := sprintf("%s@%s (%s)", [policy_id, version, status])
}

# Exportar dados de versão para resposta HTTP
version_to_response(policy_id, version) := response if {
    metadata := get_policy_metadata(policy_id, version)

    response := {
        "policy_id": policy_id,
        "version": version,
        "status": metadata.status,
        "created_at": metadata.created_at,
        "updated_at": metadata.updated_at,
        "author": metadata.author,
        "compatibility": metadata.compatibility,
    }
}

# Obter estatísticas de versão
version_stats := stats if {
    # Contar políticas por estado
    stats := {
        "total_policies": count([p | data.policies[p]]),
        "active_policies": count([p | is_policy_active(p)]),
        "deprecated_policies": count([p | is_policy_deprecated(p)]),
        "library_version": current_library_version,
    }
}
