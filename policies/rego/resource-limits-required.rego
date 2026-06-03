# Política Rego: Exigir resource limits e requests em todos os containers
# Previne resource starvation e garante QoS adequado

package neuralhive.resources.limits

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Violação se container não tiver CPU limits
violation contains {"msg": msg} if {
	container := input_containers[_]
	not container.resources.limits.cpu
	msg := sprintf("Container '%v' deve definir CPU limits", [container.name])
}

# Violação se container não tiver memory limits
violation contains {"msg": msg} if {
	container := input_containers[_]
	not container.resources.limits.memory
	msg := sprintf("Container '%v' deve definir memory limits", [container.name])
}

# Violação se container não tiver CPU requests
violation contains {"msg": msg} if {
	container := input_containers[_]
	not container.resources.requests.cpu
	msg := sprintf("Container '%v' deve definir CPU requests", [container.name])
}

# Violação se container não tiver memory requests
violation contains {"msg": msg} if {
	container := input_containers[_]
	not container.resources.requests.memory
	msg := sprintf("Container '%v' deve definir memory requests", [container.name])
}

# Violação se CPU limits exceder máximo permitido
violation contains {"msg": msg} if {
	container := input_containers[_]
	cpu_limit := container.resources.limits.cpu
	cpu_limit_value := parse_cpu(cpu_limit)
	max_cpu := parse_cpu(input.parameters.max_cpu)
	cpu_limit_value > max_cpu
	msg := sprintf("Container '%v' excede CPU limit máximo: %v > %v", [container.name, cpu_limit, input.parameters.max_cpu])
}

# Violação se memory limits exceder máximo permitido
violation contains {"msg": msg} if {
	container := input_containers[_]
	memory_limit := container.resources.limits.memory
	memory_limit_value := parse_memory(memory_limit)
	max_memory := parse_memory(input.parameters.max_memory)
	memory_limit_value > max_memory
	msg := sprintf("Container '%v' excede memory limit máximo: %v > %v", [container.name, memory_limit, input.parameters.max_memory])
}

# Violação se ratio entre limits e requests for muito alto
violation contains {"msg": msg} if {
	container := input_containers[_]
	cpu_limit := parse_cpu(container.resources.limits.cpu)
	cpu_request := parse_cpu(container.resources.requests.cpu)
	ratio := cpu_limit / cpu_request
	ratio > input.parameters.max_ratio
	msg := sprintf("Container '%v' tem ratio CPU limit/request muito alto: %.2f", [container.name, ratio])
}

# Helper: Obter todos os containers
input_containers contains container if {
	container := input.review.object.spec.containers[_]
}

input_containers contains container if {
	container := input.review.object.spec.initContainers[_]
}

input_containers contains container if {
	container := input.review.object.spec.template.spec.containers[_]
}

input_containers contains container if {
	container := input.review.object.spec.template.spec.initContainers[_]
}

# Parser de CPU (converte para millicores)
parse_cpu(str) = result if {
	endswith(str, "m")
	result := to_number(trim_suffix(str, "m"))
}

parse_cpu(str) = result if {
	not endswith(str, "m")
	result := to_number(str) * 1000
}

# Parser de Memory (converte para bytes)
parse_memory(str) = result if {
	endswith(str, "Gi")
	result := ((to_number(trim_suffix(str, "Gi")) * 1024) * 1024) * 1024
}

parse_memory(str) = result if {
	endswith(str, "G")
	result := ((to_number(trim_suffix(str, "G")) * 1000) * 1000) * 1000
}

parse_memory(str) = result if {
	endswith(str, "Mi")
	result := (to_number(trim_suffix(str, "Mi")) * 1024) * 1024
}

parse_memory(str) = result if {
	endswith(str, "M")
	result := (to_number(trim_suffix(str, "M")) * 1000) * 1000
}

parse_memory(str) = result if {
	endswith(str, "Ki")
	result := to_number(trim_suffix(str, "Ki")) * 1024
}

parse_memory(str) = result if {
	endswith(str, "K")
	result := to_number(trim_suffix(str, "K")) * 1000
}

parse_memory(str) = result if {
	result := to_number(str)
}
