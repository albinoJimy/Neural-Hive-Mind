# Política OPA para Governança de Dados Obrigatória
# Neural Hive-Mind - Validação de Tags de Governança

package neural_hive.data_governance

import rego.v1

# Recursos que manipulam dados devem ter tags de governança
required_governance_labels := {
    "neural-hive.io/data-owner",
    "neural-hive.io/data-classification",
    "neural-hive.io/sla-tier"
}

# Classificações de dados válidas
valid_classifications := {
    "public",
    "internal",
    "confidential",
    "restricted"
}

# SLA tiers válidos
valid_sla_tiers := {
    "bronze",
    "silver",
    "gold",
    "platinum"
}

# Recursos que precisam de governança de dados
data_handling_resources := {
    "Service",
    "ConfigMap",
    "Secret",
    "ApiAsset",
    "DataAsset"
}

# Namespaces que requerem governança rigorosa
governed_namespaces := {
    "gateway-intencoes",
    "redis-cluster",
    "auth",
    "neural-hive-services"
}

# DENY: Recursos sem tags obrigatórias de governança
deny contains msg if {
    # Recurso que manipula dados
    input.kind in data_handling_resources

    # Em namespace governado
    input.metadata.namespace in governed_namespaces

    # Falta alguma tag obrigatória
    missing_labels := required_governance_labels - object.get(input.metadata, "labels", {})
    count(missing_labels) > 0

    msg := sprintf("Recurso %s/%s deve ter tags de governança obrigatórias: %v", [
        input.kind,
        input.metadata.name,
        missing_labels
    ])
}

# DENY: Classificação de dados inválida
deny contains msg if {
    input.kind in data_handling_resources
    input.metadata.namespace in governed_namespaces

    classification := object.get(input.metadata.labels, "neural-hive.io/data-classification", "")
    classification != ""
    not classification in valid_classifications

    msg := sprintf("Recurso %s/%s tem classificação inválida '%s'. Valores permitidos: %v", [
        input.kind,
        input.metadata.name,
        classification,
        valid_classifications
    ])
}

# DENY: SLA tier inválido
deny contains msg if {
    input.kind in data_handling_resources
    input.metadata.namespace in governed_namespaces

    sla_tier := object.get(input.metadata.labels, "neural-hive.io/sla-tier", "")
    sla_tier != ""
    not sla_tier in valid_sla_tiers

    msg := sprintf("Recurso %s/%s tem SLA tier inválido '%s'. Valores permitidos: %v", [
        input.kind,
        input.metadata.name,
        sla_tier,
        valid_sla_tiers
    ])
}

# DENY: Data owner deve seguir padrão team-*
deny contains msg if {
    input.kind in data_handling_resources
    input.metadata.namespace in governed_namespaces

    owner := object.get(input.metadata.labels, "neural-hive.io/data-owner", "")
    owner != ""
    not startswith(owner, "team-")

    msg := sprintf("Recurso %s/%s deve ter data-owner no formato 'team-*', encontrado: '%s'", [
        input.kind,
        input.metadata.name,
        owner
    ])
}

# WARN: Recursos com dados confidenciais devem ter PII fields documentados
warn contains msg if {
    input.kind == "ApiAsset"

    classification := object.get(input.spec, "classification", "")
    classification in {"confidential", "restricted"}

    # Não tem pii_fields definido ou está vazio
    pii_fields := object.get(input.spec, "pii_fields", [])
    count(pii_fields) == 0

    msg := sprintf("ApiAsset %s classificado como '%s' deveria documentar campos PII", [
        input.metadata.name,
        classification
    ])
}

# WARN: Services expostas publicamente devem ter classificação apropriada
warn contains msg if {
    input.kind == "Service"
    input.spec.type in {"LoadBalancer", "NodePort"}

    classification := object.get(input.metadata.labels, "neural-hive.io/data-classification", "")
    classification in {"confidential", "restricted"}

    msg := sprintf("Service %s está exposto publicamente mas classificado como '%s'", [
        input.metadata.name,
        classification
    ])
}

# DENY: Secrets com dados confidenciais devem ter encryption extra
deny contains msg if {
    input.kind == "Secret"

    classification := object.get(input.metadata.labels, "neural-hive.io/data-classification", "")
    classification in {"confidential", "restricted"}

    # Não tem annotation de encryption extra
    not object.get(input.metadata.annotations, "neural-hive.io/encrypted", false)

    msg := sprintf("Secret %s classificado como '%s' deve ter encryption adicional", [
        input.metadata.name,
        classification
    ])
}

# DENY: ConfigMaps não devem conter dados sensíveis
deny contains msg if {
    input.kind == "ConfigMap"

    # Buscar por padrões de dados sensíveis
    sensitive_patterns := {
        "password",
        "secret",
        "key",
        "token",
        "credential"
    }

    # Verificar se alguma chave contém padrões sensíveis
    some key, value in input.data
    some pattern in sensitive_patterns
    contains(lower(key), pattern)

    msg := sprintf("ConfigMap %s contém dados potencialmente sensíveis na chave '%s'", [
        input.metadata.name,
        key
    ])
}

# ALLOW: Recursos que passam em todas as validações
allow if {
    # Não é um recurso que precisa de governança
    not input.kind in data_handling_resources
}

allow if {
    # Não está em namespace governado
    not input.metadata.namespace in governed_namespaces
}

allow if {
    # Tem todas as tags obrigatórias válidas
    input.kind in data_handling_resources
    input.metadata.namespace in governed_namespaces

    # Todas as tags obrigatórias presentes
    missing_labels := required_governance_labels - object.get(input.metadata, "labels", {})
    count(missing_labels) == 0

    # Classificação válida
    classification := object.get(input.metadata.labels, "neural-hive.io/data-classification", "")
    classification in valid_classifications

    # SLA tier válido
    sla_tier := object.get(input.metadata.labels, "neural-hive.io/sla-tier", "")
    sla_tier in valid_sla_tiers

    # Data owner válido
    owner := object.get(input.metadata.labels, "neural-hive.io/data-owner", "")
    startswith(owner, "team-")
}

# Helper para calcular compliance score
compliance_score := score if {
    input.kind in data_handling_resources

    total_checks := 5
    passed_checks := 0

    # Check 1: Tags obrigatórias
    missing_labels := required_governance_labels - object.get(input.metadata, "labels", {})
    passed_checks := passed_checks + (count(missing_labels) == 0)

    # Check 2: Classificação válida
    classification := object.get(input.metadata.labels, "neural-hive.io/data-classification", "")
    passed_checks := passed_checks + (classification in valid_classifications)

    # Check 3: SLA tier válido
    sla_tier := object.get(input.metadata.labels, "neural-hive.io/sla-tier", "")
    passed_checks := passed_checks + (sla_tier in valid_sla_tiers)

    # Check 4: Data owner válido
    owner := object.get(input.metadata.labels, "neural-hive.io/data-owner", "")
    passed_checks := passed_checks + startswith(owner, "team-")

    # Check 5: PII fields documentados (se aplicável)
    has_pii_docs := true
    passed_checks := passed_checks + has_pii_docs

    score := (passed_checks * 100) / total_checks
}