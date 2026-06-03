# Política Rego: Exigir assinatura de imagens e registries autorizados
# Implementa controle de supply chain seguro

package neuralhive.security.images

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Parâmetros configuráveis (fornecidos via ConstraintTemplate)
# allowed_registries: lista de registries permitidos
# require_signature: booleano para exigir assinatura

# Violação se imagem não for de registry autorizado
violation contains {"msg": msg} if {
	container := input_containers[_]
	image := container.image
	not from_allowed_registry(image)
	msg := sprintf("Container '%v' usa imagem de registry não autorizado: %v", [container.name, image])
}

# Violação se imagem não tiver tag ou usar 'latest'
violation contains {"msg": msg} if {
	container := input_containers[_]
	image := container.image
	has_disallowed_tag(image)
	msg := sprintf("Container '%v' deve usar tag específica (não 'latest'): %v", [container.name, image])
}

# Violação se imagem não estiver assinada (quando signature verification está habilitado)
violation contains {"msg": msg} if {
	input.parameters.require_signature == true
	container := input_containers[_]
	image := container.image
	not is_signed_image(image)
	msg := sprintf("Container '%v' usa imagem não assinada: %v", [container.name, image])
}

# Helper: Obter todos os containers (incluindo init e ephemeral)
input_containers contains container if {
	container := input.review.object.spec.containers[_]
}

input_containers contains container if {
	container := input.review.object.spec.initContainers[_]
}

input_containers contains container if {
	container := input.review.object.spec.ephemeralContainers[_]
}

input_containers contains container if {
	container := input.review.object.spec.template.spec.containers[_]
}

input_containers contains container if {
	container := input.review.object.spec.template.spec.initContainers[_]
}

# Helper: Verificar se imagem é de registry autorizado
from_allowed_registry(image) if {
	registry := input.parameters.allowed_registries[_]
	startswith(image, registry)
}

# Imagens do sistema sempre permitidas
from_allowed_registry(image) if {
	startswith(image, "k8s.gcr.io/")
}

from_allowed_registry(image) if {
	startswith(image, "quay.io/")
}

from_allowed_registry(image) if {
	startswith(image, "gcr.io/istio-")
}

# Helper: Verificar tags não permitidas
has_disallowed_tag(image) if {
	endswith(image, ":latest")
}

has_disallowed_tag(image) if {
	not contains(image, ":")
}

# Helper: Verificar se imagem está assinada (placeholder para integração com Sigstore/Notary)
is_signed_image(image) if {
	# Em produção, isso consultaria um serviço de verificação de assinatura
	# Por enquanto, assumimos que imagens com digest SHA256 estão assinadas
	contains(image, "@sha256:")
}

is_signed_image(image) if {
	# Imagens com tag específica e de registry confiável
	registry := input.parameters.trusted_registries[_]
	startswith(image, registry)
	contains(image, ":")
	not endswith(image, ":latest")
}
