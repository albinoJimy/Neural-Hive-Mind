# Versioning Library Tests
# Testes para o sistema de versionamento avançado de políticas OPA

package neuralhive.policy.versioning_test

import future.keywords.in
import future.keywords.contains
import future.keywords.if
import future.keywords.every

import data.neuralhive.policy.versioning

# ==============================================================================
# TEST DATA
# ==============================================================================

# Mock policies data for testing
mock_policies := {
    "security_policies": {
        "metadata": {
            "version": "2.0.0",
            "created_at": "2026-04-01",
            "updated_at": "2026-04-07",
            "author": "Security Team",
            "status": "active",
            "compatibility": {
                "min_version": "1.0.0",
                "max_version": "2.x",
            },
        },
    },
    "resource_policies": {
        "metadata": {
            "version": "1.5.0",
            "status": "active",
            "compatibility": {
                "min_version": "1.0.0",
                "max_version": "2.0.0",
            },
        },
    },
    "old_security_policies": {
        "metadata": {
            "version": "1.0.0",
            "status": "deprecated",
            "compatibility": {
                "min_version": "1.0.0",
                "max_version": "1.5.0",
            },
        },
    },
}

# ==============================================================================
# PARSE VERSION TESTS
# ==============================================================================

test_parse_valid_version {
    result := parse_version("2.1.3")
    result.major == "2"
    result.minor == "1"
    result.patch == "3"
    result.original == "2.1.3"
    result.is_valid == true
}

test_parse_default_version {
    result := parse_version("1.0.0")
    result.major == "1"
    result.minor == "0"
    result.patch == "0"
}

test_parse_version_with_leading_zeros {
    result := parse_version("1.02.003")
    result.major == "1"
    result.minor == "02"
    result.patch == "003"
}

# ==============================================================================
# COMPARE VERSIONS TESTS
# ==============================================================================

test_compare_equal_versions {
    compare_versions("1.0.0", "1.0.0") == 0
}

test_compare_major_version_higher {
    compare_versions("2.0.0", "1.0.0") == 1
}

test_compare_major_version_lower {
    compare_versions("1.0.0", "2.0.0") == -1
}

test_compare_minor_version_higher {
    compare_versions("1.2.0", "1.1.0") == 1
}

test_compare_minor_version_lower {
    compare_versions("1.1.0", "1.2.0") == -1
}

test_compare_patch_version_higher {
    compare_versions("1.0.1", "1.0.0") == 1
}

test_compare_patch_version_lower {
    compare_versions("1.0.0", "1.0.1") == -1
}

# ==============================================================================
# VERSION MEETS MIN REQUIRED TESTS
# ==============================================================================

test_version_meets_min_required_true {
    version_meets_min_required("2.0.0", "1.0.0")
}

test_version_meets_min_required_false {
    not version_meets_min_required("1.0.0", "2.0.0")
}

test_version_meets_min_required_equal {
    version_meets_min_required("1.5.0", "1.5.0")
}

# ==============================================================================
# VERSION IN RANGE TESTS
# ==============================================================================

test_version_in_range_exact {
    version_in_range("1.5.0", "1.0.0", "2.0.0")
}

test_version_in_range_with_wildcard {
    version_in_range("1.5.0", "1.0.0", "1.x")
}

test_version_in_range_wildcard_match {
    version_in_range("1.9.9", "1.x", "1.x")
}

test_version_not_in_range_too_low {
    not version_in_range("0.9.0", "1.0.0", "2.0.0")
}

test_version_not_in_range_too_high {
    not version_in_range("2.1.0", "1.0.0", "2.0.0")
}

test_version_not_in_range_wildcard_mismatch {
    not version_in_range("2.0.0", "1.0.0", "1.x")
}

# ==============================================================================
# POLICY STATUS TESTS
# ==============================================================================

test_policy_statuses_enum {
    policy_statuses[_]
    policy_statuses[i]
    policy_statuses[i] == "active"
}

test_is_policy_active_with_status {
    is_policy_active("security_policies") with mock_policies
}

test_is_policy_deprecated {
    is_policy_deprecated("old_security_policies") with mock_policies
}

# ==============================================================================
# VERSION KEY TESTS
# ==============================================================================

test_version_key_format {
    key := version_key("security_policies", "2.0.0")
    key == "security_policies@2.0.0"
}

test_version_key_different_policy {
    key1 := version_key("policy_a", "1.0.0")
    key2 := version_key("policy_b", "1.0.0")
    key1 != key2
}

test_version_key_different_version {
    key1 := version_key("security_policies", "1.0.0")
    key2 := version_key("security_policies", "2.0.0")
    key1 != key2
}

# ==============================================================================
# FORMAT VERSION FOR LOGGING TESTS
# ==============================================================================

test_format_version_for_logging_active {
    formatted := format_version_for_logging("security_policies") with mock_policies
    contains(formatted, "security_policies@2.0.0")
    contains(formatted, "active")
}

test_format_version_for_logging_deprecated {
    formatted := format_version_for_logging("old_security_policies") with mock_policies
    contains(formatted, "old_security_policies@1.0.0")
    contains(formatted, "deprecated")
}

# ==============================================================================
# VALIDATION TESTS
# ==============================================================================

test_is_valid_version_true {
    is_valid_version("1.0.0")
}

test_is_valid_version_with_patch {
    is_valid_version("1.2.3")
}

test_is_valid_version_large_numbers {
    is_valid_version("100.200.300")
}

test_is_valid_version_invalid_format {
    not is_valid_version("invalid")
}

test_is_valid_version_missing_minor {
    not is_valid_version("1.0")
}

test_is_valid_version_missing_patch {
    not is_valid_version("1")
}
