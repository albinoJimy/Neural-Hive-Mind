"""Domain mapping utilities for the Neural Hive Mind system.

This module provides utilities for normalizing domain values from different
sources and generating standardized Redis pheromone keys.
"""

from typing import Optional

import structlog

from .domain import UnifiedDomain

logger = structlog.get_logger(__name__)

# Valid sources for domain normalization
VALID_SOURCES = frozenset({'intent_envelope', 'scout_signal', 'risk_scoring', 'ontology'})

# Valid pheromone layers
VALID_LAYERS = frozenset({'strategic', 'exploration', 'consensus', 'specialist'})

# Valid pheromone types
VALID_PHEROMONE_TYPES = frozenset({
    'SUCCESS',
    'FAILURE',
    'WARNING',
    'ANOMALY_POSITIVE',
    'ANOMALY_NEGATIVE',
    'CONFIDENCE',
    'RISK',
})


class DomainMapper:
    """Maps domain values between different system components.

    Provides utilities for:
    - Normalizing domain strings from various sources to UnifiedDomain
    - Generating standardized Redis pheromone keys
    - Mapping ontology domain names to UnifiedDomain
    """

    # Mapping from lowercase normalized domain strings to UnifiedDomain
    _domain_mappings: dict[str, UnifiedDomain] = {
        'business': UnifiedDomain.BUSINESS,
        'technical': UnifiedDomain.TECHNICAL,
        'security': UnifiedDomain.SECURITY,
        'infrastructure': UnifiedDomain.INFRASTRUCTURE,
        'behavior': UnifiedDomain.BEHAVIOR,
        'operational': UnifiedDomain.OPERATIONAL,
        'compliance': UnifiedDomain.COMPLIANCE,
        # WORKAROUND: 'general' aparece em algumas mensagens Avro devido a
        # inconsistência na deserialização. Mapeado para BUSINESS como fallback.
        # TODO: Investigar causa raiz do domínio 'general' na deserialização Avro
        'general': UnifiedDomain.BUSINESS,
        'unknown': UnifiedDomain.BUSINESS,
    }

    # Mapping from ontology domain names to UnifiedDomain
    _ontology_mappings: dict[str, UnifiedDomain] = {
        'security-analysis': UnifiedDomain.SECURITY,
        'architecture-review': UnifiedDomain.TECHNICAL,
        'performance-optimization': UnifiedDomain.OPERATIONAL,
        'code-quality': UnifiedDomain.TECHNICAL,
        'code-review': UnifiedDomain.TECHNICAL,
        'dependency-analysis': UnifiedDomain.SECURITY,
        'infrastructure-review': UnifiedDomain.INFRASTRUCTURE,
        'compliance-check': UnifiedDomain.COMPLIANCE,
        'business-analysis': UnifiedDomain.BUSINESS,
        'behavior-analysis': UnifiedDomain.BEHAVIOR,
    }

    @classmethod
    def normalize(cls, domain: str, source: str) -> UnifiedDomain:
        """Normalize a domain string from any source to UnifiedDomain.

        Accepts domain values in various formats (lowercase, uppercase,
        kebab-case) and normalizes them to the canonical UnifiedDomain value.

        Args:
            domain: The domain string to normalize. Can be in any case.
            source: The source system of the domain value. Must be one of:
                - 'intent_envelope': Domain from Intent Envelope messages
                - 'scout_signal': Domain from Scout Agent signals
                - 'risk_scoring': Domain from Risk Scoring calculations
                - 'ontology': Domain from intents taxonomy ontology

        Returns:
            The corresponding UnifiedDomain enum value.

        Raises:
            ValueError: If the domain string is not recognized or source is invalid.
        """
        if source not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{source}'. Must be one of: {sorted(VALID_SOURCES)}"
            )

        # Handle ontology sources separately
        if source == 'ontology':
            return cls.from_ontology(domain)

        # Normalize to lowercase for matching
        normalized = domain.lower().strip()

        # Handle kebab-case by converting to underscore
        normalized = normalized.replace('-', '_')

        # Remove common suffixes that might be appended
        normalized = normalized.replace('_domain', '')

        if normalized in cls._domain_mappings:
            return cls._domain_mappings[normalized]

        # Log warning for ambiguous mappings
        logger.warning(
            'domain_normalization_fallback',
            original_domain=domain,
            normalized=normalized,
            source=source,
        )

        raise ValueError(
            f"Unrecognized domain '{domain}' from source '{source}'. "
            f"Valid domains are: {sorted(cls._domain_mappings.keys())}"
        )

    @classmethod
    def to_pheromone_key(
        cls,
        domain: UnifiedDomain,
        layer: str,
        pheromone_type: str,
        id: Optional[str] = None,
    ) -> str:
        """Generate a standardized Redis pheromone key.

        Creates a consistent key format for storing pheromone trails in Redis:
        pheromone:{layer}:{domain}:{type}:{id?}

        Args:
            domain: The UnifiedDomain for the pheromone trail.
            layer: The pheromone layer. Must be one of:
                - 'strategic': Strategic-level decisions
                - 'exploration': Exploration and discovery
                - 'consensus': Consensus building
                - 'specialist': Specialist-specific trails
            pheromone_type: The type of pheromone. Common types:
                - 'SUCCESS', 'FAILURE', 'WARNING'
                - 'ANOMALY_POSITIVE', 'ANOMALY_NEGATIVE'
                - 'CONFIDENCE', 'RISK'
            id: Optional unique identifier for the specific trail.

        Returns:
            A formatted Redis key string.

        Raises:
            ValueError: If domain is not a UnifiedDomain, or layer/type is invalid.
        """
        if not isinstance(domain, UnifiedDomain):
            raise ValueError(
                f"domain must be a UnifiedDomain enum, got {type(domain).__name__}"
            )

        if layer not in VALID_LAYERS:
            raise ValueError(
                f"Invalid layer '{layer}'. Must be one of: {sorted(VALID_LAYERS)}"
            )

        # Normaliza para uppercase para validação case-insensitive
        normalized_type = pheromone_type.upper()

        if normalized_type not in VALID_PHEROMONE_TYPES:
            raise ValueError(
                f"Invalid pheromone_type '{pheromone_type}'. "
                f"Must be one of: {sorted(VALID_PHEROMONE_TYPES)}"
            )

        # Build the key parts (usa tipo normalizado para consistência)
        key_parts = ['pheromone', layer, domain.value, normalized_type]

        if id is not None:
            key_parts.append(id)

        return ':'.join(key_parts)

    @classmethod
    def from_ontology(cls, ontology_domain: str) -> UnifiedDomain:
        """Map an ontology domain name to UnifiedDomain.

        Maps domain names from the intents_taxonomy.json ontology to their
        corresponding UnifiedDomain values.

        Args:
            ontology_domain: The domain name from the ontology (e.g., 'security-analysis').

        Returns:
            The corresponding UnifiedDomain enum value.

        Raises:
            ValueError: If the ontology domain is not mapped.
        """
        normalized = ontology_domain.lower().strip()

        if normalized in cls._ontology_mappings:
            return cls._ontology_mappings[normalized]

        # Try direct mapping as fallback
        simple_normalized = normalized.replace('-', '_').replace('_', '')
        for key, value in cls._domain_mappings.items():
            if key.replace('_', '') == simple_normalized:
                logger.warning(
                    'ontology_domain_fallback_mapping',
                    original=ontology_domain,
                    mapped_to=value.value,
                )
                return value

        raise ValueError(
            f"Unmapped ontology domain '{ontology_domain}'. "
            f"Known mappings: {sorted(cls._ontology_mappings.keys())}"
        )
