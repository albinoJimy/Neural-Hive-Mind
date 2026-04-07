#!/usr/bin/env python3
"""
Gerador de Intenções Diversas para Coleta de Feedback

Este script gera intenções de teste variadas para aumentar
o dataset de feedbacks com features NLP.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Dict


# Categorias de intenções para cobertura balanceada
INTENTION_CATEGORIES = {
    "approve_low_risk": [
        "Create API endpoint for user registration with validation",
        "Add logging to authentication module for debugging",
        "Update CSS styles for improved readability on mobile",
        "Create unit tests for payment calculation module",
        "Add password reset functionality with email verification",
        "Create database index for faster user lookups by email",
        "Implement caching layer for frequently accessed data",
        "Add input validation to prevent SQL injection in forms",
        "Create backup script for daily database dumps",
        "Add rate limiting to API endpoints to prevent abuse",
        "Implement pagination for large result sets",
        "Add search functionality with filters for user list",
        "Create health check endpoint for monitoring",
        "Add error handling for network failures in API calls",
        "Implement retry logic with exponential backoff",
        "Add unit tests for new authentication flow",
        "Create dashboard for admin user management",
        "Add data export functionality in CSV format",
        "Implement email notification system for alerts",
        "Add API documentation with OpenAPI specification",
        "Create configuration file loader with validation",
        "Add feature flag system for gradual rollouts",
        "Implement session timeout for inactive users",
        "Add audit logging for sensitive operations",
    ],
    "approve_security_improvements": [
        "Enable HTTPS for all API endpoints",
        "Add two-factor authentication for admin accounts",
        "Implement CSRF protection for form submissions",
        "Add input sanitization to prevent XSS attacks",
        "Encrypt sensitive data at rest in database",
        "Implement proper password hashing with bcrypt",
        "Add security headers (CSP, X-Frame-Options, etc.)",
        "Implement API key rotation mechanism",
        "Add role-based access control for permissions",
        "Enable audit logging for authentication events",
        "Implement secure session management",
        "Add parameterized queries to prevent SQL injection",
    ],
    "reject_destructive": [
        "Delete all users from the database",
        "Drop the production database tables",
        "Remove all authentication checks from API",
        "Disable SSL certificate validation",
        "Delete all log files from the server",
        "Remove all backups from storage",
        "Drop the indexes from the users table",
        "Disable all security middleware",
        "Delete the admin account",
        "Remove encryption from sensitive fields",
        "Turn off all monitoring and alerting",
        "Delete the entire application cache",
        "Remove all rate limiting from API",
        "Drop the events table from database",
        "Delete all API keys from the system",
        "Disable firewall rules on server",
        "Remove all validation from forms",
        "Delete all test data without backup",
        "Turn off database replication",
        "Remove error handling from code",
    ],
    "reject_risky": [
        "Grant admin privileges to all authenticated users",
        "Remove password requirement for login",
        "Disable account lockout after failed attempts",
        "Allow SQL queries directly from user input",
        "Store passwords in plain text",
        "Remove all API rate limits",
        "Disable HTTPS in production environment",
        "Allow file uploads without validation",
        "Remove CSRF tokens from forms",
        "Disable session timeout for all users",
        "Allow access to all endpoints without auth",
        "Store credit card numbers without encryption",
        "Remove logging from authentication module",
        "Disable backup automation",
        "Allow shell command execution from API",
        "Remove input length validation",
        "Disable API authentication entirely",
        "Remove security headers from responses",
    ],
    "review_ambiguous": [
        "Update the user profile data structure",
        "Modify the authentication flow",
        "Change the database schema for users",
        "Refactor the payment processing module",
        "Optimize the query performance",
        "Update the caching strategy",
        "Modify the API response format",
        "Change the session management approach",
        "Refactor the notification system",
        "Update the error handling logic",
    ],
}


def generate_intention_requests(category: str, count: int = 5) -> List[Dict]:
    """
    Gera requests de intenção para uma categoria.

    Args:
        category: Nome da categoria
        count: Número de intenções a gerar

    Returns:
        Lista de dicionários com dados da intenção
    """
    intentions = INTENTION_CATEGORIES.get(category, [])
    requests = []

    for text in intentions[:count]:
        plan_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        # Determinar risk_band baseado na categoria
        if "approve_low_risk" in category:
            risk_band = "low"
            risk_score = 0.2
        elif "approve_security" in category:
            risk_band = "low"
            risk_score = 0.3
        elif "reject_destructive" in category:
            risk_band = "critical"
            risk_score = 0.95
        elif "reject_risky" in category:
            risk_band = "high"
            risk_score = 0.85
        else:  # review_ambiguous
            risk_band = "medium"
            risk_score = 0.5

        request = {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "original_intent_text": text,
            "correlation_id": correlation_id,
            "risk_score": risk_score,
            "risk_band": risk_band,
            "tasks": [
                {"task_id": f"task-{plan_id[:8]}-1", "task_type": "execute", "description": text}
            ],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        requests.append(request)

    return requests


def main():
    """Gera todas as intenções de teste."""
    print("=" * 60)
    print("Gerador de Intenções Diversas")
    print("=" * 60)
    print()

    all_requests = []
    total_by_category = {}

    for category in INTENTION_CATEGORIES.keys():
        requests = generate_intention_requests(category, count=5)
        all_requests.extend(requests)
        total_by_category[category] = len(requests)

        print(f"{category}: {len(requests)} intenções")

    print()
    print(f"Total gerado: {len(all_requests)} intenções")
    print()
    print("Distribuicao esperada:")
    print("  - Aprovar (low risk): ~50%")
    print("  - Rejeitar (high/critical risk): ~35%")
    print("  - Revisar (medium risk): ~15%")
    print()

    # Salvar para arquivo JSON
    import json

    output_file = "/tmp/diverse_intentions.json"
    with open(output_file, "w") as f:
        json.dump(all_requests, f, indent=2)

    print(f"Salvo em: {output_file}")
    print()
    print("Para usar:")
    print(
        "1. Copiar para o pod: kubectl cp /tmp/diverse_intentions.json approval-service-<pod>:/tmp/"
    )
    print("2. Inserir no MongoDB:")
    print('   kubectl exec -n approval approval-service-<pod> -- python3 -c ""')
    print("   import json, uuid")
    print("   from pymongo import MongoClient")
    print("   from datetime import datetime, timezone")
    print("   client = MongoClient('mongodb://...')")
    print("   db = client['neural_hive']")
    print("   with open('/tmp/diverse_intentions.json') as f:")
    print("       data = json.load(f)")
    print("   for req in data:")
    print("       req['approval_id'] = str(uuid.uuid4())")
    print("       req['requested_at'] = datetime.now(timezone.utc).isoformat()")
    print("       db['plan_approvals'].insert_one(req)")
    print('   "' "")


if __name__ == "__main__":
    main()
