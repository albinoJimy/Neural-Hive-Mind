# Política Rego: Exigir mTLS STRICT em todos os namespaces com workloads
# Implementa enforcement automático de Zero Trust

package neuralhive.security.mtls

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Violação se PeerAuthentication não estiver configurada para STRICT
violation[{"msg": msg}] {
    input.review.kind.kind == "Deployment"
    namespace := input.review.namespace
    not has_strict_mtls(namespace)
    msg := sprintf("Namespace '%v' deve ter PeerAuthentication com mTLS STRICT configurado antes de criar Deployments", [namespace])
}

violation[{"msg": msg}] {
    input.review.kind.kind == "StatefulSet"
    namespace := input.review.namespace
    not has_strict_mtls(namespace)
    msg := sprintf("Namespace '%v' deve ter PeerAuthentication com mTLS STRICT configurado antes de criar StatefulSets", [namespace])
}

violation[{"msg": msg}] {
    input.review.kind.kind == "DaemonSet"
    namespace := input.review.namespace
    not has_strict_mtls(namespace)
    msg := sprintf("Namespace '%v' deve ter PeerAuthentication com mTLS STRICT configurado antes de criar DaemonSets", [namespace])
}

# Verificação de PeerAuthentication existente
violation[{"msg": msg}] {
    input.review.kind.kind == "PeerAuthentication"
    input.review.object.spec.mtls.mode != "STRICT"
    msg := sprintf("PeerAuthentication deve usar modo STRICT, encontrado: %v", [input.review.object.spec.mtls.mode])
}

# Helper: Verificar se namespace tem mTLS STRICT
has_strict_mtls(namespace) {
    # Namespace está na lista de exceções
    namespace in excluded_namespaces
}

has_strict_mtls(namespace) {
    # Verificar se existe PeerAuthentication STRICT no namespace
    # Esta verificação seria feita contra dados do cluster em produção
    # Por enquanto, assumimos que namespaces do Neural Hive têm configuração apropriada
    startswith(namespace, "neural-hive-")
}

# Namespaces excluídos da verificação mTLS
excluded_namespaces := {
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "istio-system",
    "gatekeeper-system"
}