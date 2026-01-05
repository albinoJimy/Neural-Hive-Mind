# Default policy for integration testing
package policy

default allow = false

# Allow admin users
allow {
    input.user == "admin"
}

# Allow read actions for any authenticated user
allow {
    input.action == "read"
    input.user != ""
}

# Deny delete actions for non-admin
deny[msg] {
    input.action == "delete"
    input.user != "admin"
    msg := "Only admin users can delete resources"
}

# Violations array for integration testing
violations[violation] {
    deny[msg]
    violation := {"message": msg, "rule": "access_control"}
}
