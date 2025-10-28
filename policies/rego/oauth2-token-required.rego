# Política OPA para Tokens OAuth2 Obrigatórios
# Neural Hive-Mind - Validação de Autenticação OAuth2

package neural_hive.oauth2_security

import rego.v1

# Services que requerem autenticação OAuth2
oauth2_required_services := {
    "gateway-intencoes",
    "neural-hive-api",
    "intention-processor"
}

# Endpoints que sempre requerem autenticação
protected_paths := {
    "/api/",
    "/intentions/",
    "/admin/",
    "/internal/"
}

# Endpoints que podem ser públicos
public_paths := {
    "/health",
    "/metrics",
    "/ready",
    "/auth/callback"
}

# DENY: Services críticos sem annotation de autenticação
deny contains msg if {
    input.kind == "Service"

    # Service é crítico
    input.metadata.name in oauth2_required_services

    # Não tem annotation de autenticação obrigatória
    not object.get(input.metadata.annotations, "auth.neural-hive/required", "") == "true"

    msg := sprintf("Service %s deve ter annotation 'auth.neural-hive/required: true'", [
        input.metadata.name
    ])
}

# DENY: Ingress sem validação JWT para paths protegidos
deny contains msg if {
    input.kind == "Ingress"

    # Ingress para service protegido
    some rule in input.spec.rules
    some path in rule.http.paths
    service_name := path.backend.service.name
    service_name in oauth2_required_services

    # Path é protegido
    some protected_path in protected_paths
    startswith(path.path, protected_path)

    # Não tem annotation de autenticação
    not object.get(input.metadata.annotations, "nginx.ingress.kubernetes.io/auth-url", "")

    msg := sprintf("Ingress %s deve ter validação JWT para path protegido %s", [
        input.metadata.name,
        path.path
    ])
}

# DENY: VirtualService Istio sem RequestAuthentication
deny contains msg if {
    input.kind == "VirtualService"

    # VirtualService para host que requer autenticação
    some host in input.spec.hosts
    contains(host, "gateway")

    # HTTP route para path protegido
    some http_route in input.spec.http
    some match in http_route.match
    some protected_path in protected_paths
    startswith(match.uri.prefix, protected_path)

    # Não há referência a RequestAuthentication no namespace
    # Esta validação seria complementada por validação externa
    msg := sprintf("VirtualService %s precisa de RequestAuthentication para paths protegidos", [
        input.metadata.name
    ])
}

# DENY: AuthorizationPolicy sem validação de claims JWT
deny contains msg if {
    input.kind == "AuthorizationPolicy"

    # Policy para service que requer OAuth2
    selector := input.spec.selector.matchLabels
    some label_key, label_value in selector
    label_value in oauth2_required_services

    # Tem regras mas não valida claims JWT
    some rule in input.spec.rules
    not rule.when

    msg := sprintf("AuthorizationPolicy %s deve validar claims JWT obrigatórios", [
        input.metadata.name
    ])
}

# WARN: RequestAuthentication sem cache JWKS configurado
warn contains msg if {
    input.kind == "RequestAuthentication"

    # Para realm neural-hive
    some jwt_rule in input.spec.jwtRules
    contains(jwt_rule.issuer, "neural-hive")

    # Não tem cache configurado
    not jwt_rule.jwks_cache_duration

    msg := sprintf("RequestAuthentication %s deveria ter cache JWKS configurado", [
        input.metadata.name
    ])
}

# DENY: Deployment sem variáveis OAuth2 necessárias
deny contains msg if {
    input.kind == "Deployment"

    # Deployment de service que requer OAuth2
    app_name := input.metadata.labels["app"]
    app_name in oauth2_required_services

    # Container principal
    main_container := input.spec.template.spec.containers[0]

    # Variáveis OAuth2 obrigatórias
    required_env_vars := {
        "KEYCLOAK_URL",
        "KEYCLOAK_REALM",
        "KEYCLOAK_CLIENT_ID"
    }

    # Variáveis definidas no container
    defined_vars := {var.name | some var in main_container.env}

    # Variáveis faltando
    missing_vars := required_env_vars - defined_vars
    count(missing_vars) > 0

    msg := sprintf("Deployment %s deve ter variáveis OAuth2: %v", [
        input.metadata.name,
        missing_vars
    ])
}

# DENY: ConfigMap com configuração OAuth2 insegura
deny contains msg if {
    input.kind == "ConfigMap"

    # ConfigMap contém configuração OAuth2
    some key in object.keys(input.data)
    contains(lower(key), "oauth")

    config_content := input.data[key]

    # Configurações inseguras
    insecure_patterns := {
        "client_secret",
        "password",
        "secret_key"
    }

    some pattern in insecure_patterns
    contains(lower(config_content), pattern)

    msg := sprintf("ConfigMap %s não deve conter secrets OAuth2 em texto plano", [
        input.metadata.name
    ])
}

# DENY: Service Account sem RBAC para OAuth2
deny contains msg if {
    input.kind == "ServiceAccount"

    # ServiceAccount usado por service OAuth2
    sa_name := input.metadata.name
    some service in oauth2_required_services
    contains(service, sa_name)

    # Não tem annotation de RBAC
    not object.get(input.metadata.annotations, "neural-hive.io/rbac-required", "") == "true"

    msg := sprintf("ServiceAccount %s deve ter RBAC configurado", [
        input.metadata.name
    ])
}

# WARN: Secrets OAuth2 sem rotação automática
warn contains msg if {
    input.kind == "Secret"

    # Secret contém dados OAuth2
    some key in object.keys(input.data)
    key in {"client-secret", "jwt-secret", "signing-key"}

    # Não tem annotation de rotação
    not object.get(input.metadata.annotations, "neural-hive.io/rotation-enabled", "") == "true"

    msg := sprintf("Secret OAuth2 %s deveria ter rotação automática", [
        input.metadata.name
    ])
}

# DENY: EnvoyFilter sem validação JWT
deny contains msg if {
    input.kind == "EnvoyFilter"

    # Filter para workloads protegidos
    some workload_selector in input.spec.workloadSelector.labels
    workload_selector in oauth2_required_services

    # Não configura JWT validation
    not input.spec.configPatches

    msg := sprintf("EnvoyFilter %s deve configurar validação JWT", [
        input.metadata.name
    ])
}

# ALLOW: Services com autenticação OAuth2 apropriada
allow if {
    input.kind == "Service"

    # Service requer OAuth2 e está configurado
    input.metadata.name in oauth2_required_services
    object.get(input.metadata.annotations, "auth.neural-hive/required", "") == "true"
}

# ALLOW: RequestAuthentication configurado corretamente
allow if {
    input.kind == "RequestAuthentication"

    # Para realm neural-hive
    some jwt_rule in input.spec.jwtRules
    contains(jwt_rule.issuer, "neural-hive")

    # JWKS URI configurado
    jwt_rule.jwksUri

    # Audiences definidos
    count(jwt_rule.audiences) > 0
}

# ALLOW: AuthorizationPolicy com validação JWT
allow if {
    input.kind == "AuthorizationPolicy"

    # Policy com validação de claims
    some rule in input.spec.rules
    rule.when

    # Valida issuer
    some condition in rule.when
    condition.key == "request.auth.claims[iss]"
}

# Helper para validar token JWT (simulação)
valid_jwt_token(token) if {
    # Em produção, isso seria validado contra JWKS do Keycloak
    # Aqui apenas verificamos formato básico
    parts := split(token, ".")
    count(parts) == 3

    # Header base64
    header := parts[0]
    count(header) > 0

    # Payload base64
    payload := parts[1]
    count(payload) > 0

    # Signature
    signature := parts[2]
    count(signature) > 0
}

# Helper para extrair claims do JWT (simulação)
jwt_claims(token) := claims if {
    parts := split(token, ".")
    # Em produção, decodificar base64 e JSON
    claims := {"iss": "keycloak", "aud": "gateway-intencoes"}
}

# Função auxiliar para calcular score OAuth2
oauth2_security_score := score if {
    input.kind == "Deployment"
    app_name := input.metadata.labels["app"]
    app_name in oauth2_required_services

    total_checks := 5
    passed_checks := 0

    # Check 1: Variáveis OAuth2 obrigatórias
    main_container := input.spec.template.spec.containers[0]
    required_env_vars := {"KEYCLOAK_URL", "KEYCLOAK_REALM", "KEYCLOAK_CLIENT_ID"}
    defined_vars := {var.name | some var in main_container.env}
    missing_vars := required_env_vars - defined_vars
    passed_checks := passed_checks + (count(missing_vars) == 0)

    # Check 2: Service annotation
    service_annotation := object.get(input.metadata.annotations, "auth.neural-hive/required", "") == "true"
    passed_checks := passed_checks + service_annotation

    # Check 3: HTTPS obrigatório
    https_only := object.get(input.metadata.annotations, "neural-hive.io/https-only", "") == "true"
    passed_checks := passed_checks + https_only

    # Check 4: Security context apropriado
    security_context := input.spec.template.spec.securityContext
    secure := security_context.runAsNonRoot == true
    passed_checks := passed_checks + secure

    # Check 5: Resource limits
    limits_set := main_container.resources.limits != null
    passed_checks := passed_checks + limits_set

    score := (passed_checks * 100) / total_checks
}