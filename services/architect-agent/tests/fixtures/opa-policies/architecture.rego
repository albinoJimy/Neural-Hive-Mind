package architecture

import future.keywords.contains
import future.keywords.if

# Default allow (deny by default)
default allow = false

# Allow if no architecture violations
allow if {
    not count(violations) > 0
}

# List of architectural violations
violations[description] {
    some i
    violation := input.architecture_decision[i]
    is_forbidden_pattern(violation.pattern)
    description := sprintf("Forbidden pattern: %s", [violation.pattern])
}

violations[description] {
    some i
    violation := input.architecture_decision[i]
    not has_required_components(violation.components)
    description := "Missing required components for microservices architecture"
}

# Check if pattern is forbidden
is_forbidden_pattern(pattern) if {
    forbidden_patterns := ["monolithic_database", "tight_coupling"]
    forbidden_patterns[_] == pattern
}

# Check if components satisfy microservices requirements
has_required_components(components) if {
    # Must have API Gateway
    components[name].type == "api_gateway"

    # Must have service discovery
    components[name].type == "service_discovery"
}
