"""
Description Quality Validator - Wrapper para validador compartilhado

Este módulo re-exporta o validador de qualidade de descrições do módulo
compartilhado neural_hive_specialists.validation para manter compatibilidade
com imports existentes no STE.

O validador real está em:
libraries/python/neural_hive_specialists/validation/description_validator.py
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Adicionar path para o módulo compartilhado
_lib_path = Path(__file__).parent.parent.parent.parent.parent.parent / "libraries" / "python"
if str(_lib_path) not in sys.path:
    sys.path.insert(0, str(_lib_path))

# Tentar importar do módulo compartilhado
_using_shared_module = False
try:
    from neural_hive_specialists.validation.description_validator import (
        DescriptionQualityValidator,
        get_validator,
    )
    _using_shared_module = True
except ImportError:
    pass

# Fallback: definir localmente se o módulo compartilhado não estiver disponível
if not _using_shared_module:
    import re
    import structlog

    logger = structlog.get_logger()
    logger.warning(
        "using_fallback_description_validator",
        reason="neural_hive_specialists.validation module not found"
    )

    class DescriptionQualityValidator:
        """Fallback validator quando módulo compartilhado não está disponível."""

        DOMAIN_KEYWORDS: Dict[str, List[str]] = {
            'security-analysis': [
                'auth', 'security', 'validate', 'encrypt', 'audit', 'permission',
                'credential', 'token', 'sanitize', 'injection', 'access', 'role'
            ],
            'architecture-review': [
                'service', 'interface', 'pattern', 'design', 'module', 'component',
                'api', 'integration', 'layer', 'dependency', 'contract', 'schema'
            ],
            'performance-optimization': [
                'cache', 'index', 'optimize', 'parallel', 'async', 'batch',
                'latency', 'throughput', 'memory', 'pool', 'query', 'buffer'
            ],
            'code-quality': [
                'test', 'error', 'log', 'document', 'refactor', 'lint',
                'coverage', 'exception', 'debug', 'trace', 'monitor', 'metric'
            ],
            'business-logic': [
                'workflow', 'kpi', 'cost', 'efficiency', 'process', 'metric',
                'rule', 'policy', 'compliance', 'approval', 'transaction', 'pipeline'
            ]
        }

        SECURITY_KEYWORDS: Dict[str, List[str]] = {
            'confidential': ['encrypt', 'auth', 'audit', 'permission', 'sanitize'],
            'restricted': ['encrypt', 'auth', 'audit', 'permission', 'sanitize'],
            'internal': ['validate', 'verify', 'check', 'access'],
            'public': []
        }

        QOS_KEYWORDS: Dict[str, List[str]] = {
            'exactly_once': ['idempotent', 'transaction', 'rollback', 'dedup'],
            'at_least_once': ['retry', 'acknowledge', 'redelivery'],
            'at_most_once': ['fire-and-forget', 'best-effort'],
        }

        MIN_WORDS = 15
        MAX_WORDS = 50

        def __init__(self):
            pass

        def validate_description(
            self,
            description: str,
            domain: str,
            security_level: Optional[str] = None,
            qos: Optional[str] = None
        ) -> Dict:
            """Validação simplificada de fallback."""
            words = description.split()
            word_count = len(words)
            issues = []

            # Score de comprimento
            if word_count < 10:
                length_score = 0.0
                issues.append(f"Descrição muito curta ({word_count} palavras)")
            elif word_count < self.MIN_WORDS:
                length_score = 0.5 * (word_count / self.MIN_WORDS)
            elif word_count <= self.MAX_WORDS:
                length_score = 1.0
            else:
                length_score = 0.7

            # Score de domínio
            keywords = self.DOMAIN_KEYWORDS.get(domain, [])
            description_lower = description.lower()
            found = sum(1 for kw in keywords if kw in description_lower)
            if found >= 3:
                domain_score = 1.0
            elif found >= 1:
                domain_score = 0.5
            else:
                domain_score = 0.0
                issues.append(f"Nenhuma keyword de domínio para {domain}")

            # Score de segurança
            security_score = 1.0
            if security_level in ['confidential', 'restricted']:
                sec_kws = self.SECURITY_KEYWORDS.get(security_level, [])
                sec_found = sum(1 for kw in sec_kws if kw in description_lower)
                if sec_found >= 2:
                    security_score = 1.0
                elif sec_found == 1:
                    security_score = 0.6
                else:
                    security_score = 0.2
                    issues.append(f"Faltam keywords de segurança para {security_level}")

            # Score final
            score = 0.25 * length_score + 0.35 * domain_score + 0.20 * security_score + 0.20

            return {
                'score': round(score, 3),
                'issues': issues,
                'suggestions': [],
                'metrics': {
                    'word_count': word_count,
                    'length_score': round(length_score, 3),
                    'domain_score': round(domain_score, 3),
                    'security_score': round(security_score, 3),
                    'domain_keywords_found': found
                }
            }

        def suggest_improvements(self, description: str, context: Dict) -> str:
            """Sugestão simplificada de fallback."""
            domain = context.get('domain', 'code-quality')
            security_level = context.get('security_level', 'internal')
            priority = context.get('priority', 'normal')

            return f"Enhanced {description} ({domain}, {security_level}, {priority} priority)"

    _validator_instance: Optional[DescriptionQualityValidator] = None

    def get_validator() -> DescriptionQualityValidator:
        """Obtém ou cria a instância singleton do validador."""
        global _validator_instance
        if _validator_instance is None:
            _validator_instance = DescriptionQualityValidator()
        return _validator_instance

# Re-exportar para manter API
__all__ = ['DescriptionQualityValidator', 'get_validator']
