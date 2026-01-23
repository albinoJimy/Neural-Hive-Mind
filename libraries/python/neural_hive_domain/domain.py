"""Unified domain definitions for the Neural Hive Mind system.

This module provides a centralized enum for all domain types used across
the system, ensuring consistency between Intent Envelopes, Scout Agents,
Risk Scoring, and other components.
"""

from enum import Enum


class UnifiedDomain(str, Enum):
    """Unified domain types for the Neural Hive Mind system.

    This enum standardizes domain definitions across all components:
    - Intent Envelope processing
    - Scout Agent signals
    - Risk scoring calculations
    - Pheromone trail management
    - Specialist routing

    Inherits from str and Enum for JSON serialization compatibility
    and Pydantic model integration.

    Domains:
        BUSINESS: Business logic, requirements, and process analysis.
        TECHNICAL: Code quality, architecture, and technical implementation.
        SECURITY: Security vulnerabilities, authentication, and authorization.
        INFRASTRUCTURE: Deployment, scaling, and infrastructure concerns.
        BEHAVIOR: Runtime behavior patterns and anomaly detection.
        OPERATIONAL: Performance optimization and operational efficiency.
        COMPLIANCE: Regulatory compliance and policy adherence.
    """

    BUSINESS = 'BUSINESS'
    TECHNICAL = 'TECHNICAL'
    SECURITY = 'SECURITY'
    INFRASTRUCTURE = 'INFRASTRUCTURE'
    BEHAVIOR = 'BEHAVIOR'
    OPERATIONAL = 'OPERATIONAL'
    COMPLIANCE = 'COMPLIANCE'

    def __str__(self) -> str:
        """Return the string value of the domain."""
        return self.value
