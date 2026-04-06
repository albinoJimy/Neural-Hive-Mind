package neuralhive.orchestrator.authz

import future.keywords.contains
import future.keywords.if
import future.keywords.in

default allow := false

# Endpoints públicos - sempre permitem sem autenticação
public_paths := [
    "/health",
    "/healthz",
    "/ready",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/static",
]

# Regra 1: Paths públicos são sempre permitidos
allow if {
    path := input.request.path
    some public_path in public_paths
    startswith(path, public_path)
}

# Regra 2: Admins podem acessar tudo
allow if {
    input.user.role == "admin"
}

# Regra 3: Developers podem fazer GET em APIs
allow if {
    input.user.role == "developer"
    input.request.method == "GET"
    startswith(input.request.path, "/api/")
    tenant_isolation_valid(input.request.path, input.user)
}

# Regra 4: Tenantes autenticados podem acessar recursos próprios
allow if {
    is_authenticated(input.user)
    not input.user.role in ["admin", "developer", "worker"]  # Admin, developer, worker têm regras próprias
    input.request.method in ["GET", "POST", "PUT", "DELETE"]
    startswith(input.request.path, "/api/v1/")
    not is_admin_endpoint(input.request.path)  # Admin endpoints bloqueados
    tenant_isolation_valid(input.request.path, input.user)
}

# Regra 4b: Endpoints genéricos são permitidos para usuários autenticados
allow if {
    is_authenticated(input.user)
    is_generic_api_endpoint(input.request.path)
    input.request.method in ["GET", "POST", "PUT", "DELETE"]
}

# Regra 5: Workers (service accounts) podem acessar endpoints específicos
allow if {
    input.user.role == "worker"
    input.request.method in ["GET", "POST"]
    startswith(input.request.path, "/api/v1/workers/")
}

# Regra 6: Service Registry pode registrar/desregistrar workers
allow if {
    input.user.role == "service-registry"
    input.request.method in ["POST", "DELETE"]
    input.request.path == "/api/v1/workers/register"
}

# =============================================================================
# Helper Functions
# =============================================================================

# Verifica se o usuário está autenticado (não é anonymous)
is_authenticated(user) if {
    user.id != "anonymous"
    user.id != ""
    user.id != null
}

# Verifica se path é um endpoint administrativo
is_admin_endpoint(path) if {
    parts := split(path, "/")
    count(parts) >= 4
    parts[3] in ["admin", "delete", "sudo", "internal"]
}

# Helper: Verifica se endpoint é genérico (sem tenant_id no path)
is_generic_api_endpoint(path) if {
    parts := split(path, "/")
    # Endpoints como /api/v1/workflows, /api/v1/tickets (sem tenant_id)
    count(parts) == 4  # ["", "api", "v1", "endpoint"]
}

# Verifica isolamento de tenant - o tenant_id no path deve corresponder ao tenant do usuário
tenant_isolation_valid(path, user) if {
    # Extrair tenant_id do path: /api/v1/{tenant_id}/...
    # Array split: ["", "api", "v1", "{tenant_id}", ...]
    # Índice [3] contém o tenant_id
    parts := split(path, "/")
    count(parts) >= 5
    path_tenant_id := parts[3]
    path_tenant_id == user.tenant_id
}
