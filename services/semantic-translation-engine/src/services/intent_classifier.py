"""
IntentClassifier - Classifica intents por tipo para decomposição inteligente.

Usa similaridade semântica para identificar o tipo de intent (análise, migração,
implementação, etc.) e direcionar para templates de decomposição apropriados.
"""

import structlog
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = structlog.get_logger(__name__)


class IntentType(Enum):
    """Tipos de intent suportados com templates de decomposição."""

    # Análise e Planejamento
    VIABILITY_ANALYSIS = "viability_analysis"
    TECHNICAL_ASSESSMENT = "technical_assessment"
    SECURITY_AUDIT = "security_audit"
    PERFORMANCE_ANALYSIS = "performance_analysis"

    # Mudanças de Sistema
    MIGRATION = "migration"
    UPGRADE = "upgrade"
    REFACTORING = "refactoring"

    # Implementação
    FEATURE_IMPLEMENTATION = "feature_implementation"
    BUG_FIX = "bug_fix"
    INTEGRATION = "integration"

    # Infraestrutura
    INFRASTRUCTURE_CHANGE = "infrastructure_change"
    SCALING = "scaling"
    DEPLOYMENT = "deployment"

    # Fallback
    GENERIC = "generic"


@dataclass
class IntentClassification:
    """Resultado da classificação de intent."""
    intent_type: IntentType
    confidence: float
    matched_patterns: List[str]
    recommended_task_count: int
    semantic_domains: List[str]  # Domínios semânticos relevantes


class IntentClassifier:
    """
    Classifica intents usando similaridade semântica e padrões linguísticos.

    Estratégia:
    1. Extrai verbos de ação e substantivos-chave
    2. Calcula similaridade com conceitos de cada tipo de intent
    3. Retorna classificação com confiança e recomendações
    """

    # Padrões linguísticos por tipo de intent (português e inglês)
    INTENT_PATTERNS = {
        IntentType.VIABILITY_ANALYSIS: {
            "keywords": [
                "analisar viabilidade", "análise de viabilidade", "avaliar viabilidade",
                "feasibility analysis", "viability assessment", "evaluate feasibility",
                "estudo de viabilidade", "análise técnica", "avaliar possibilidade"
            ],
            "action_verbs": ["analisar", "avaliar", "estudar", "analyze", "assess", "evaluate"],
            "recommended_tasks": 8,
            "domains": ["security", "architecture", "performance", "quality"]
        },
        IntentType.TECHNICAL_ASSESSMENT: {
            "keywords": [
                "avaliação técnica", "assessment técnico", "análise de impacto",
                "technical assessment", "impact analysis", "technical review",
                "revisão técnica", "parecer técnico"
            ],
            "action_verbs": ["avaliar", "revisar", "analisar", "assess", "review", "analyze"],
            "recommended_tasks": 6,
            "domains": ["architecture", "performance", "quality"]
        },
        IntentType.SECURITY_AUDIT: {
            "keywords": [
                "auditoria de segurança", "análise de segurança", "security audit",
                "penetration test", "vulnerability assessment", "avaliação de vulnerabilidades",
                "revisão de segurança", "compliance check"
            ],
            "action_verbs": ["auditar", "verificar", "testar", "audit", "test", "verify"],
            "recommended_tasks": 7,
            "domains": ["security", "quality"]
        },
        IntentType.MIGRATION: {
            "keywords": [
                "migração", "migrar", "migration", "migrate",
                "mover para", "transferir para", "move to", "transfer to",
                "upgrade para", "atualizar para"
            ],
            "action_verbs": ["migrar", "mover", "transferir", "migrate", "move", "transfer"],
            "recommended_tasks": 8,
            "domains": ["security", "architecture", "performance"]
        },
        IntentType.FEATURE_IMPLEMENTATION: {
            "keywords": [
                "implementar", "criar", "desenvolver", "adicionar",
                "implement", "create", "develop", "add", "build",
                "nova funcionalidade", "new feature"
            ],
            "action_verbs": ["implementar", "criar", "desenvolver", "implement", "create", "build"],
            "recommended_tasks": 5,
            "domains": ["architecture", "quality"]
        },
        IntentType.INFRASTRUCTURE_CHANGE: {
            "keywords": [
                "infraestrutura", "infrastructure", "scaling", "auto-scaling",
                "kubernetes", "docker", "cloud", "deploy", "deployment",
                "provisionamento", "provisioning"
            ],
            "action_verbs": ["provisionar", "escalar", "deployar", "provision", "scale", "deploy"],
            "recommended_tasks": 6,
            "domains": ["architecture", "performance"]
        },
        IntentType.REFACTORING: {
            "keywords": [
                "refatorar", "refactoring", "reestruturar", "restructure",
                "melhorar código", "improve code", "technical debt",
                "dívida técnica", "clean code"
            ],
            "action_verbs": ["refatorar", "reestruturar", "melhorar", "refactor", "restructure"],
            "recommended_tasks": 5,
            "domains": ["architecture", "quality"]
        },
        IntentType.PERFORMANCE_ANALYSIS: {
            "keywords": [
                "performance", "desempenho", "otimização", "optimization",
                "benchmark", "profiling", "latência", "latency",
                "throughput", "cache"
            ],
            "action_verbs": ["otimizar", "analisar", "melhorar", "optimize", "analyze", "improve"],
            "recommended_tasks": 6,
            "domains": ["performance", "architecture"]
        },
        IntentType.INTEGRATION: {
            "keywords": [
                "integração", "integration", "conectar", "connect",
                "api", "webhook", "sincronizar", "sync",
                "interoperabilidade"
            ],
            "action_verbs": ["integrar", "conectar", "sincronizar", "integrate", "connect", "sync"],
            "recommended_tasks": 5,
            "domains": ["architecture", "security"]
        }
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa classificador de intents.

        Args:
            config: Configuração opcional com thresholds customizados
        """
        self.config = config or {}
        self.min_confidence = self.config.get('intent_classification_min_confidence', 0.3)
        self._model = None
        self._pattern_embeddings_cache: Dict[str, np.ndarray] = {}

        logger.info(
            "IntentClassifier initialized",
            min_confidence=self.min_confidence,
            supported_types=len(self.INTENT_PATTERNS)
        )

    @property
    def model(self):
        """Lazy loading do modelo de embeddings."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            model_name = self.config.get(
                'embeddings_model',
                'paraphrase-multilingual-MiniLM-L12-v2'
            )
            logger.info("Loading embeddings model for IntentClassifier", model=model_name)
            self._model = SentenceTransformer(model_name)
        return self._model

    def classify(self, intent_text: str, context: Optional[Dict[str, Any]] = None) -> IntentClassification:
        """
        Classifica intent por tipo.

        Args:
            intent_text: Texto da intent
            context: Contexto adicional (domínio, prioridade, etc.)

        Returns:
            IntentClassification com tipo, confiança e recomendações
        """
        intent_lower = intent_text.lower()
        context = context or {}

        # Passo 1: Matching por padrões linguísticos
        pattern_scores = self._score_by_patterns(intent_lower)

        # Passo 2: Matching semântico (se padrões não forem conclusivos)
        best_pattern_score = max(pattern_scores.values()) if pattern_scores else 0

        if best_pattern_score < 0.5:
            semantic_scores = self._score_by_semantics(intent_text)
            # Combinar scores
            combined_scores = {}
            for intent_type in IntentType:
                if intent_type == IntentType.GENERIC:
                    continue
                pattern_score = pattern_scores.get(intent_type, 0)
                semantic_score = semantic_scores.get(intent_type, 0)
                # Peso maior para semântico se padrões fracos
                combined_scores[intent_type] = pattern_score * 0.4 + semantic_score * 0.6
        else:
            combined_scores = pattern_scores

        # Passo 3: Selecionar melhor classificação
        if not combined_scores or max(combined_scores.values()) < self.min_confidence:
            return self._create_generic_classification(intent_text)

        best_type = max(combined_scores, key=combined_scores.get)
        best_score = combined_scores[best_type]

        # Passo 4: Enriquecer com contexto
        if context.get('domain') == 'security':
            # Boost para tipos relacionados a segurança
            if best_type in [IntentType.SECURITY_AUDIT, IntentType.MIGRATION]:
                best_score = min(1.0, best_score * 1.2)

        # Obter padrões e recomendações
        pattern_config = self.INTENT_PATTERNS.get(best_type, {})
        matched_patterns = self._find_matched_patterns(intent_lower, best_type)

        classification = IntentClassification(
            intent_type=best_type,
            confidence=best_score,
            matched_patterns=matched_patterns,
            recommended_task_count=pattern_config.get('recommended_tasks', 5),
            semantic_domains=pattern_config.get('domains', ['architecture', 'quality'])
        )

        logger.info(
            "Intent classified",
            intent_type=best_type.value,
            confidence=best_score,
            recommended_tasks=classification.recommended_task_count,
            matched_patterns=matched_patterns[:3]  # Log só os 3 primeiros
        )

        return classification

    def _score_by_patterns(self, intent_lower: str) -> Dict[IntentType, float]:
        """Calcula score por matching de padrões linguísticos."""
        scores = {}

        for intent_type, config in self.INTENT_PATTERNS.items():
            keyword_matches = sum(
                1 for kw in config['keywords']
                if kw.lower() in intent_lower
            )
            verb_matches = sum(
                1 for verb in config['action_verbs']
                if verb.lower() in intent_lower
            )

            # Normalizar scores
            keyword_score = min(keyword_matches / 2, 1.0)  # 2+ keywords = máximo
            verb_score = min(verb_matches / 1, 1.0)  # 1+ verb = máximo

            # Score combinado (keywords mais importantes)
            scores[intent_type] = keyword_score * 0.7 + verb_score * 0.3

        return scores

    def _score_by_semantics(self, intent_text: str) -> Dict[IntentType, float]:
        """Calcula score por similaridade semântica."""
        scores = {}

        # Obter embedding da intent
        intent_embedding = self.model.encode([intent_text], convert_to_numpy=True)[0]

        for intent_type, config in self.INTENT_PATTERNS.items():
            # Obter embeddings dos keywords (cached)
            cache_key = f"keywords_{intent_type.value}"
            if cache_key not in self._pattern_embeddings_cache:
                keywords = config['keywords']
                self._pattern_embeddings_cache[cache_key] = self.model.encode(
                    keywords, convert_to_numpy=True
                )

            keyword_embeddings = self._pattern_embeddings_cache[cache_key]

            # Calcular similaridade máxima
            from sklearn.metrics.pairwise import cosine_similarity
            similarities = cosine_similarity([intent_embedding], keyword_embeddings)[0]
            max_similarity = float(np.max(similarities))

            scores[intent_type] = max_similarity

        return scores

    def _find_matched_patterns(self, intent_lower: str, intent_type: IntentType) -> List[str]:
        """Encontra padrões que deram match."""
        matched = []
        config = self.INTENT_PATTERNS.get(intent_type, {})

        for kw in config.get('keywords', []):
            if kw.lower() in intent_lower:
                matched.append(kw)

        for verb in config.get('action_verbs', []):
            if verb.lower() in intent_lower:
                matched.append(f"verb:{verb}")

        return matched

    def _create_generic_classification(self, intent_text: str) -> IntentClassification:
        """Cria classificação genérica quando nenhum padrão detectado."""
        logger.warning(
            "No intent pattern matched, using generic classification",
            intent_preview=intent_text[:50]
        )

        return IntentClassification(
            intent_type=IntentType.GENERIC,
            confidence=0.5,
            matched_patterns=[],
            recommended_task_count=4,
            semantic_domains=['architecture', 'quality']
        )

    def get_decomposition_hints(self, classification: IntentClassification) -> Dict[str, Any]:
        """
        Retorna hints para decomposição baseado na classificação.

        Args:
            classification: Classificação do intent

        Returns:
            Dicionário com hints para o DecompositionTemplate
        """
        return {
            "intent_type": classification.intent_type.value,
            "recommended_task_count": classification.recommended_task_count,
            "semantic_domains": classification.semantic_domains,
            "confidence": classification.confidence,
            "should_use_template": classification.confidence >= self.min_confidence
        }
