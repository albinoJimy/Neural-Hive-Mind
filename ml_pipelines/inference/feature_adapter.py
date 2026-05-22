"""
Feature Adapter: Bridge entre Feature Extraction Profissional e Approval Predictor Legado

Este adaptador converte a saída do FeatureExtractor profissional para o formato
compatível com o approval_predictor legado, preservando backward compatibility.

Mapeamentos implementados:
- specialist_confidence: Preservado como parâmetro
- Domínios (domain_*): Mapeados de NLPFeatureExtractor
- Ações (action_*): Mapeadas de NLPFeatureExtractor
- Risco (risk_*): Derivados de action_ e has_*
- has_backup/has_verification/has_all: Mapeados de NLPFeatureExtractor
- text_length_*: Preservados de NLPFeatureExtractor
- primary_domain_*/primary_action_*: Derivados via argmax
- simple_risk_score: Calculado de dangerous_count

Usage:
    from ml_pipelines.inference.feature_adapter import FeatureAdapter

    adapter = FeatureAdapter()

    # De texto direto (usa NLPFeatureExtractor)
    features = adapter.extract_legacy_features(
        text="Delete all users",
        cognitive_plan={},
        specialist_confidence=0.7
    )

    # De features profissionais já extraídas
    legacy_features = adapter.to_legacy_format(professional_features)
"""

import re
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

if TYPE_CHECKING:
    from neural_hive_specialists.feature_extraction.nlp_feature_extractor import (
        NLPFeatureExtractor,
    )

logger = structlog.get_logger(__name__)


class FeatureAdapter:
    """
    Adapter entre FeatureExtractor profissional e formato legado do approval_predictor.

    O approval_predictor espera 30 features em ordem específica. Este adaptador
    converte saídas profissionais (NLPFeatureExtractor, FeatureExtractor) para
    esse formato, garantindo backward compatibility.
    """

    # Ordem de features esperada pelo approval_predictor (30 posições)
    LEGACY_FEATURE_ORDER: ClassVar[list[str]] = [
        "specialist_confidence",
        "domain_security",
        "domain_performance",
        "domain_database",
        "domain_devops",
        "domain_testing",
        "action_create",
        "action_update",
        "action_delete",
        "action_read",
        "action_deploy",
        "has_backup",
        "has_verification",
        "has_all",
        "text_length_chars",
        "text_length_words",
        "risk_high",
        "risk_medium",
        "risk_low",
        "simple_risk_score",
        "primary_domain_security",
        "primary_domain_performance",
        "primary_domain_database",
        "primary_domain_devops",
        "primary_domain_testing",
        "primary_action_create",
        "primary_action_update",
        "primary_action_delete",
        "primary_action_read",
        "primary_action_deploy",
    ]

    # Domínios legados (5)
    LEGACY_DOMAINS: ClassVar[list[str]] = [
        "security",
        "performance",
        "database",
        "devops",
        "testing",
    ]

    # Ações legadas (5)
    LEGACY_ACTIONS: ClassVar[list[str]] = ["create", "update", "delete", "read", "deploy"]

    # Palavras-chave perigosas para risk_score
    DANGEROUS_KEYWORDS: ClassVar[list[str]] = [
        "delete",
        "drop",
        "destroy",
        "remove",
        "disable",
        "without",
        "all",
    ]

    # Regex para detecção de has_backup, has_verification, has_all
    BACKUP_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"\bbackup|save|preserve|restore\b", re.IGNORECASE
    )
    VERIFICATION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"\bverify|validation|check|confirm|test\b", re.IGNORECASE
    )
    ALL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"\ball\b.*\b(users|records|data|tables)\b", re.IGNORECASE
    )

    def __init__(self, nlp_extractor: "NLPFeatureExtractor | None" = None):
        """
        Inicializa o adapter.

        Args:
            nlp_extractor: Instância opcional de NLPFeatureExtractor.
                          Se None, cria uma nova instância.
        """
        self._nlp_extractor = nlp_extractor
        self._extractor_initialized = False

    def _get_nlp_extractor(self) -> "NLPFeatureExtractor":
        """Retorna instância lazy do NLPFeatureExtractor."""
        if not self._extractor_initialized:
            try:
                from neural_hive_specialists.feature_extraction.nlp_feature_extractor import (
                    get_nlp_extractor,
                )

                self._nlp_extractor = get_nlp_extractor()
                self._extractor_initialized = True
                logger.info("NLPFeatureExtractor initialized for FeatureAdapter")
            except ImportError as e:
                logger.warning("NLPFeatureExtractor not available", error=str(e))
                self._extractor_initialized = True  # Mark as tried

        return self._nlp_extractor

    def extract_legacy_features(
        self,
        text: str,
        cognitive_plan: dict[
            str, Any
        ],  # noqa: ARG002 - Mantido para compatibilidade com API futura
        specialist_confidence: float,
    ) -> dict[str, float]:
        """
        Extrai features no formato legado (30 features) usando FeatureExtractor profissional.

        Args:
            text: Texto da intenção do usuário
            cognitive_plan: Plano cognitivo (pode ser vazio, não usado ainda)
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com 30 features no formato legado
        """
        if not text:
            return self._empty_legacy_features()

        # Tentar usar NLPFeatureExtractor profissional
        nlp_extractor = self._get_nlp_extractor()
        if nlp_extractor:
            professional_features = nlp_extractor.extract_features(text)
            result = self.to_legacy_format(professional_features, specialist_confidence)
            # NLPFeatureExtractor não emite features dependentes da forma textual
            # original. Derivar has_* e risk_* a partir do texto preserva
            # paridade com _extract_manual_features e cumpre o contrato de saída.
            self._apply_text_derived_overrides(result, text)
            return result

        # Fallback para extração manual se NLPFeatureExtractor não disponível
        logger.warning("Using manual feature extraction (NLPFeatureExtractor unavailable)")
        return self._extract_manual_features(text, specialist_confidence)

    def to_legacy_format(
        self, professional_features: dict[str, Any], specialist_confidence: float = 0.5
    ) -> dict[str, float]:
        """
        Converte features profissionais para formato legado (30 features).

        Args:
            professional_features: Features do NLPFeatureExtractor
            specialist_confidence: Confiança do especialista

        Returns:
            Dicionário com 30 features no formato legado
        """
        legacy = {}

        # 1. specialist_confidence (input)
        legacy["specialist_confidence"] = specialist_confidence

        # 2. Domínios (domain_*) - Mapear domain_* profissionais
        # NLPFeatureExtractor retorna: domain_security, domain_performance, etc.
        for domain in self.LEGACY_DOMAINS:
            # Profissional retorna float (proporção), converter para 0.0/1.0
            domain_value = professional_features.get(f"domain_{domain}", 0.0)
            legacy[f"domain_{domain}"] = 1.0 if domain_value > 0 else 0.0

        # 3. Ações (action_*) - Mapear action_* profissionais
        # NLPFeatureExtractor retorna contagem, converter para 0.0/1.0
        for action in self.LEGACY_ACTIONS:
            action_value = professional_features.get(f"action_{action}", 0)
            legacy[f"action_{action}"] = 1.0 if action_value > 0 else 0.0

        # 4. Palavras-chave (has_backup, has_verification, has_all)
        # NLPFeatureExtractor tem has_url, has_path, etc. mas não has_backup
        # Vamos derivar de análise de texto ou usar defaults
        # Como NLPFeatureExtractor não tem esses campos exatos, usamos 0.0 como default
        # (poderiam ser derivados de text se necessário)
        legacy["has_backup"] = 0.0
        legacy["has_verification"] = 0.0
        legacy["has_all"] = 0.0

        # 5. Métricas de texto (text_length_*)
        legacy["text_length_chars"] = professional_features.get("text_length_chars", 0)
        legacy["text_length_words"] = professional_features.get("text_length_words", 0)

        # 6. Risco (risk_*) - Derivar de actions
        # risk_high: delete action
        legacy["risk_high"] = legacy.get("action_delete", 0.0)
        # risk_medium: update action
        legacy["risk_medium"] = legacy.get("action_update", 0.0)
        # risk_low: create, read, deploy actions
        legacy["risk_low"] = (
            1.0
            if any(
                legacy.get(f"action_{action}", 0.0) > 0 for action in ["create", "read", "deploy"]
            )
            else 0.0
        )

        # 7. simple_risk_score - Calcular
        dangerous_count = (
            1
            if legacy.get("action_delete", 0.0) > 0
            else 0 + (1 if legacy.get("action_update", 0.0) > 0 else 0) * 0.5
        )
        legacy["simple_risk_score"] = min(1.0, dangerous_count * 0.3)

        # 8. Domínio primário (primary_domain_*) - Argmax de domain_*
        domain_scores = {f"domain_{d}": legacy.get(f"domain_{d}", 0.0) for d in self.LEGACY_DOMAINS}
        primary_domain = (
            max(domain_scores, key=domain_scores.get) if domain_scores else "domain_security"
        )
        primary_domain_name = primary_domain.replace("domain_", "")

        for domain in self.LEGACY_DOMAINS:
            legacy[f"primary_domain_{domain}"] = 1.0 if primary_domain_name == domain else 0.0

        # 9. Ação primária (primary_action_*) - Argmax de action_*
        action_scores = {f"action_{a}": legacy.get(f"action_{a}", 0.0) for a in self.LEGACY_ACTIONS}
        primary_action = (
            max(action_scores, key=action_scores.get) if action_scores else "action_create"
        )
        primary_action_name = primary_action.replace("action_", "")

        for action in self.LEGACY_ACTIONS:
            legacy[f"primary_action_{action}"] = 1.0 if primary_action_name == action else 0.0

        return legacy

    def to_feature_array(self, legacy_features: dict[str, float]) -> list[list[float]]:
        """
        Converte dicionário de features legadas para array ordenado.

        Args:
            legacy_features: Dicionário com 30 features

        Returns:
            Array 2D [[feature1, feature2, ..., feature30]] compatível com sklearn
        """
        return [[legacy_features.get(f, 0.0) for f in self.LEGACY_FEATURE_ORDER]]

    def _apply_text_derived_overrides(self, legacy: dict[str, float], text: str) -> None:
        """
        Sobrepõe features dependentes da forma textual no dicionário legado.

        NLPFeatureExtractor opera sobre tokens normalizados e não consegue
        emitir has_backup/has_verification/has_all nem alinhar risk_*/
        simple_risk_score com as regex usadas em _extract_manual_features.
        Esta helper aplica as mesmas regras a partir do texto original,
        garantindo que ambos os caminhos (NLP e fallback manual) produzem
        as mesmas 9 features sensíveis a vocabulário.
        """
        legacy["has_backup"] = 1.0 if self.BACKUP_PATTERN.search(text) else 0.0
        legacy["has_verification"] = 1.0 if self.VERIFICATION_PATTERN.search(text) else 0.0
        legacy["has_all"] = 1.0 if self.ALL_PATTERN.search(text) else 0.0

        legacy["risk_high"] = (
            1.0
            if re.search(r"\b(delete|drop|destroy|remove|disable)\b", text, re.IGNORECASE)
            else 0.0
        )
        legacy["risk_medium"] = (
            1.0
            if re.search(r"\b(update|change|modify|alter)\b", text, re.IGNORECASE)
            else 0.0
        )
        legacy["risk_low"] = (
            1.0
            if re.search(r"\b(create|add|verify|check|test|backup)\b", text, re.IGNORECASE)
            else 0.0
        )

        text_lower = text.lower()
        dangerous_count = sum(1 for kw in self.DANGEROUS_KEYWORDS if kw in text_lower)
        legacy["simple_risk_score"] = min(1.0, dangerous_count * 0.3)

    def _extract_manual_features(self, text: str, specialist_confidence: float) -> dict[str, float]:
        """
        Extrai features manualmente (fallback sem NLPFeatureExtractor).

        Implementa as mesmas 16 regex do approval_predictor legado.
        """
        features = {"specialist_confidence": specialist_confidence}

        text_lower = text.lower()

        # 1. Domínios (5 regex)
        domain_keywords = {
            "security": r"\b(security|ssl|tls|authentication|authorization|password|login)\b",
            "performance": r"\b(performance|optimize|index|cache|speed|latency|query)\b",
            "database": r"\b(database|db|sql|mongo|query|table|schema|migration)\b",
            "devops": r"\b(deploy|container|docker|kubernetes|ci/cd|pipeline|build)\b",
            "testing": r"\b(test|testing|unit|integration|e2e|coverage)\b",
        }

        for domain, pattern in domain_keywords.items():
            features[f"domain_{domain}"] = 1.0 if re.search(pattern, text, re.IGNORECASE) else 0.0

        # 2. Ações (5 regex)
        action_keywords = {
            "create": r"\b(create|add|insert|new|make)\b",
            "update": r"\b(update|modify|change|edit|alter)\b",
            "delete": r"\b(delete|drop|remove|destroy|clean)\b",
            "read": r"\b(get|fetch|select|read|query|find)\b",
            "deploy": r"\b(deploy|release|publish|ship)\b",
        }

        for action, pattern in action_keywords.items():
            features[f"action_{action}"] = 1.0 if re.search(pattern, text, re.IGNORECASE) else 0.0

        # 3. Palavras-chave (3 regex)
        features["has_backup"] = 1.0 if self.BACKUP_PATTERN.search(text) else 0.0
        features["has_verification"] = 1.0 if self.VERIFICATION_PATTERN.search(text) else 0.0
        features["has_all"] = 1.0 if self.ALL_PATTERN.search(text) else 0.0

        # 4. Métricas de texto
        features["text_length_chars"] = len(text)
        features["text_length_words"] = len(text.split())

        # 5. Risco (3 regex)
        features["risk_high"] = (
            1.0
            if re.search(r"\b(delete|drop|destroy|remove|disable)\b", text, re.IGNORECASE)
            else 0.0
        )
        features["risk_medium"] = (
            1.0 if re.search(r"\b(update|change|modify|alter)\b", text, re.IGNORECASE) else 0.0
        )
        features["risk_low"] = (
            1.0
            if re.search(r"\b(create|add|verify|check|test|backup)\b", text, re.IGNORECASE)
            else 0.0
        )

        # 6. simple_risk_score
        dangerous_count = sum(1 for kw in self.DANGEROUS_KEYWORDS if kw in text_lower)
        features["simple_risk_score"] = min(1.0, dangerous_count * 0.3)

        # 7. Domínio primário
        domain_scores = {
            k.replace("domain_", ""): v for k, v in features.items() if k.startswith("domain_")
        }
        primary_domain = max(domain_scores, key=domain_scores.get) if domain_scores else "security"
        for domain in self.LEGACY_DOMAINS:
            features[f"primary_domain_{domain}"] = 1.0 if primary_domain == domain else 0.0

        # 8. Ação primária
        action_scores = {
            k.replace("action_", ""): v for k, v in features.items() if k.startswith("action_")
        }
        primary_action = max(action_scores, key=action_scores.get) if action_scores else "create"
        for action in self.LEGACY_ACTIONS:
            features[f"primary_action_{action}"] = 1.0 if primary_action == action else 0.0

        return features

    def _empty_legacy_features(self) -> dict[str, float]:
        """Retorna features legadas vazias com defaults."""
        return {f: 0.0 for f in self.LEGACY_FEATURE_ORDER}

    def get_feature_names(self) -> list[str]:
        """Retorna lista de nomes de features legadas."""
        return self.LEGACY_FEATURE_ORDER.copy()

    def validate_features(self, features: dict[str, float]) -> bool:
        """
        Valida se o dicionário de features contém todas as 30 features esperadas.

        Args:
            features: Dicionário de features para validar

        Returns:
            True se válido, False caso contrário
        """
        missing = [f for f in self.LEGACY_FEATURE_ORDER if f not in features]
        if missing:
            logger.warning("Invalid features: missing fields", missing=missing)
            return False
        return True


# Singleton para uso na aplicação
_adapter_instance: FeatureAdapter | None = None


def get_feature_adapter() -> FeatureAdapter:
    """Retorna instância singleton do FeatureAdapter."""
    global _adapter_instance  # noqa: PLW0603 - Singleton pattern
    if _adapter_instance is None:
        _adapter_instance = FeatureAdapter()
    return _adapter_instance
