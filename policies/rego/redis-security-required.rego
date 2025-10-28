# Política OPA para Segurança Redis Obrigatória
# Neural Hive-Mind - Validação de Segurança para Redis Cluster

package neural_hive.redis_security

import rego.v1

# DENY: Services Redis sem autenticação obrigatória
deny contains msg if {
    input.kind == "Service"

    # Service expõe porta Redis (6379)
    some port in input.spec.ports
    port.port == 6379

    # Não tem annotation de autenticação obrigatória
    not object.get(input.metadata.annotations, "redis.security/auth", "") == "required"

    msg := sprintf("Service Redis %s deve ter annotation 'redis.security/auth: required'", [
        input.metadata.name
    ])
}

# DENY: Services Redis sem encryption em trânsito
deny contains msg if {
    input.kind == "Service"

    # Service Redis
    some port in input.spec.ports
    port.port == 6379

    # Em ambiente de produção
    input.metadata.labels["neural-hive.io/environment"] == "prod"

    # Não tem annotation de TLS
    not object.get(input.metadata.annotations, "redis.security/tls", "") == "required"

    msg := sprintf("Service Redis %s em produção deve ter annotation 'redis.security/tls: required'", [
        input.metadata.name
    ])
}

# DENY: Secrets Redis sem tipo apropriado
deny contains msg if {
    input.kind == "Secret"

    # Secret contém credenciais Redis
    some key in object.keys(input.data)
    contains(key, "redis")

    # Tipo não é Opaque
    input.type != "Opaque"

    msg := sprintf("Secret %s com credenciais Redis deve ser tipo 'Opaque'", [
        input.metadata.name
    ])
}

# DENY: Pods conectando ao Redis sem sidecar Istio
deny contains msg if {
    input.kind == "Pod"

    # Pod tem environment variables apontando para Redis
    some container in input.spec.containers
    some env in container.env
    contains(lower(env.name), "redis")

    # Em namespace governado
    input.metadata.namespace in {
        "gateway-intencoes",
        "neural-hive-services"
    }

    # Não tem annotation para injeção Istio
    not object.get(input.metadata.annotations, "sidecar.istio.io/inject", "") == "true"

    msg := sprintf("Pod %s conectando ao Redis deve ter sidecar Istio injetado", [
        input.metadata.name
    ])
}

# DENY: ConfigMaps com configuração Redis insegura
deny contains msg if {
    input.kind == "ConfigMap"

    # ConfigMap contém configuração Redis
    some key in object.keys(input.data)
    contains(lower(key), "redis")

    config_content := input.data[key]

    # Configurações inseguras detectadas
    contains(config_content, "requirepass")
    contains(config_content, "changeme")  # Senha padrão

    msg := sprintf("ConfigMap %s contém configuração Redis com senha insegura", [
        input.metadata.name
    ])
}

# DENY: RedisCluster sem autenticação habilitada
deny contains msg if {
    input.kind == "RedisCluster"

    # Não tem secret de autenticação configurado
    not input.spec.kubernetesConfig.redisSecret

    msg := sprintf("RedisCluster %s deve ter autenticação configurada", [
        input.metadata.name
    ])
}

# DENY: RedisCluster sem TLS em produção
deny contains msg if {
    input.kind == "RedisCluster"

    # Em ambiente de produção
    input.metadata.labels["neural-hive.io/environment"] == "prod"

    # TLS não configurado
    not input.spec.TLS.enabled

    msg := sprintf("RedisCluster %s em produção deve ter TLS habilitado", [
        input.metadata.name
    ])
}

# WARN: Redis sem resource limits pode afetar outros workloads
warn contains msg if {
    input.kind == "RedisCluster"

    # Não tem resource limits definidos
    not input.spec.kubernetesConfig.resources.limits

    msg := sprintf("RedisCluster %s deveria ter resource limits definidos", [
        input.metadata.name
    ])
}

# WARN: Redis sem backup habilitado
warn contains msg if {
    input.kind == "RedisCluster"

    # Em produção
    input.metadata.labels["neural-hive.io/environment"] == "prod"

    # Backup não habilitado
    not object.get(input.metadata.annotations, "neural-hive.io/backup", "") == "enabled"

    msg := sprintf("RedisCluster %s em produção deveria ter backup habilitado", [
        input.metadata.name
    ])
}

# DENY: NetworkPolicies permissivas para Redis
deny contains msg if {
    input.kind == "NetworkPolicy"

    # Policy afeta pods Redis
    some selector_label, selector_value in input.spec.podSelector.matchLabels
    contains(lower(selector_value), "redis")

    # Permite acesso de qualquer namespace
    some rule in input.spec.ingress
    not rule.from

    msg := sprintf("NetworkPolicy %s não deve permitir acesso irrestrito ao Redis", [
        input.metadata.name
    ])
}

# DENY: Redis acessível de namespaces não autorizados
deny contains msg if {
    input.kind == "Service"

    # Service Redis
    some port in input.spec.ports
    port.port == 6379

    # Em namespace Redis
    input.metadata.namespace == "redis-cluster"

    # Não tem annotation de namespaces autorizados
    not object.get(input.metadata.annotations, "neural-hive.io/authorized-namespaces", "")

    msg := sprintf("Service Redis %s deve especificar namespaces autorizados", [
        input.metadata.name
    ])
}

# DENY: Secrets Redis sem encryption at rest
deny contains msg if {
    input.kind == "Secret"

    # Secret com dados Redis confidenciais
    some key in object.keys(input.data)
    key in {"password", "auth-token", "tls-key"}

    # Classificado como confidencial
    input.metadata.labels["neural-hive.io/data-classification"] in {"confidential", "restricted"}

    # Não tem annotation de encryption
    not object.get(input.metadata.annotations, "neural-hive.io/encrypted", "") == "true"

    msg := sprintf("Secret Redis %s classificado como confidencial deve ter encryption extra", [
        input.metadata.name
    ])
}

# ALLOW: Redis com configuração segura
allow if {
    input.kind == "RedisCluster"

    # Tem autenticação configurada
    input.spec.kubernetesConfig.redisSecret

    # TLS habilitado em produção OU não é produção
    tls_ok := input.spec.TLS.enabled == true
    not_prod := input.metadata.labels["neural-hive.io/environment"] != "prod"
    tls_ok or not_prod

    # Tem resource limits
    input.spec.kubernetesConfig.resources.limits
}

# ALLOW: Services Redis com segurança apropriada
allow if {
    input.kind == "Service"

    # Service Redis com autenticação obrigatória
    some port in input.spec.ports
    port.port == 6379
    object.get(input.metadata.annotations, "redis.security/auth", "") == "required"

    # TLS obrigatório em produção OU não é produção
    tls_required := object.get(input.metadata.annotations, "redis.security/tls", "") == "required"
    not_prod := input.metadata.labels["neural-hive.io/environment"] != "prod"
    tls_required or not_prod
}

# Helper para calcular score de segurança Redis
redis_security_score := score if {
    input.kind == "RedisCluster"

    total_checks := 6
    passed_checks := 0

    # Check 1: Autenticação habilitada
    passed_checks := passed_checks + (input.spec.kubernetesConfig.redisSecret != null)

    # Check 2: TLS habilitado (se produção)
    tls_check := true
    tls_check := input.metadata.labels["neural-hive.io/environment"] == "prod"
    tls_check := input.spec.TLS.enabled == true
    passed_checks := passed_checks + tls_check

    # Check 3: Resource limits
    passed_checks := passed_checks + (input.spec.kubernetesConfig.resources.limits != null)

    # Check 4: Backup habilitado
    backup_enabled := object.get(input.metadata.annotations, "neural-hive.io/backup", "") == "enabled"
    passed_checks := passed_checks + backup_enabled

    # Check 5: Persistence habilitada
    passed_checks := passed_checks + (input.spec.storage != null)

    # Check 6: Métricas habilitadas para monitoring
    passed_checks := passed_checks + (input.spec.redisExporter.enabled == true)

    score := (passed_checks * 100) / total_checks
}