"""Serviço principal de PII - integra detecção, mascaramento, unmask e audit."""

import hashlib
from datetime import timezone

import structlog
from neural_hive_specialists.compliance.pii_detector import PIIDetectorLite
from neural_hive_specialists.compliance.pii_masker import MaskStrategy, PIIMasker
from neural_hive_specialists.compliance.pii_patterns import PIIType as SpecialistPIIType

from src.config.settings import get_settings
from src.models.pii import (
    MaskResult,
    MaskStrategy,
    PIIType,
    PIIFound,
    PIIUnmaskError,
    PIIServiceError,
)
from src.services.audit import get_audit_logger
from src.services.encryption import get_reversible_mask_service

logger = structlog.get_logger(__name__)

# Mapeamento entre SpecialistPIIType e nosso PIIType
PII_TYPE_MAPPING = {
    SpecialistPIIType.EMAIL: PIIType.EMAIL,
    SpecialistPIIType.PHONE: PIIType.PHONE,
    SpecialistPIIType.CPF: PIIType.CPF,
    SpecialistPIIType.CNPJ: PIIType.CNPJ,
    SpecialistPIIType.CREDIT_CARD: PIIType.CREDIT_CARD,
    SpecialistPIIType.SSN: PIIType.SSN,
    SpecialistPIIType.ADDRESS: PIIType.ADDRESS,
    SpecialistPIIType.IP_ADDRESS: PIIType.IP_ADDRESS,
    SpecialistPIIType.UUID: PIIType.UUID,
    SpecialistPIIType.API_KEY: PIIType.API_KEY,
    SpecialistPIIType.NIF: PIIType.NIF,
    SpecialistPIIType.IBAN: PIIType.IBAN,
    SpecialistPIIType.PASSPORT: PIIType.PASSPORT,
    SpecialistPIIType.POSTAL_CODE: PIIType.POSTAL_CODE,
    SpecialistPIIType.RG: PIIType.RG,
    SpecialistPIIType.TITULO_ELEITOR: PIIType.TITULO_ELEITOR,
    SpecialistPIIType.BANK_ACCOUNT: PIIType.BANK_ACCOUNT,
    SpecialistPIIType.PERSON: PIIType.PERSON,
    SpecialistPIIType.ORG: PIIType.ORG,
    SpecialistPIIType.DATE: PIIType.DATE,
}

# Mapeamento reverso
PII_TYPE_REVERSE_MAPPING = {v: k for k, v in PII_TYPE_MAPPING.items()}

# Mapeamento entre MaskStrategy
MASK_STRATEGY_MAPPING = {
    MaskStrategy.FULL: MaskStrategy.MASK_FULL,
    MaskStrategy.PARTIAL: MaskStrategy.MASK_PARTIAL,
    MaskStrategy.REDACT: MaskStrategy.MASK_REDACT,
    MaskStrategy.HASH: MaskStrategy.MASK_HASH,
}


class PIIService:
    """
    Serviço principal de PII.

    Implementa:
    - R-P2: Extração de PII detection de neural_hive_specialists/compliance
    - R-P3: 23 PII types, 3 masking strategies (MASK_FULL, MASK_PARTIAL, MASK_REDACT)
    - R-P4: Audit logging MongoDB, unmask reversível AES-256-GCM, JWT auth required
    """

    def __init__(self):
        """Inicializa serviço PII."""
        settings = get_settings()

        # Inicializar masker do neural_hive_specialists
        specialist_strategy = MaskStrategy.PARTIAL
        if settings.PII_DEFAULT_STRATEGY == "MASK_FULL":
            specialist_strategy = MaskStrategy.FULL
        elif settings.PII_DEFAULT_STRATEGY == "MASK_REDACT":
            specialist_strategy = MaskStrategy.REDACT
        elif settings.PII_DEFAULT_STRATEGY == "MASK_HASH":
            specialist_strategy = MaskStrategy.HASH

        self.masker = PIIMasker(
            strategy=specialist_strategy,
            enable_spacy=settings.PII_ENABLE_SPACY,
        )
        self.detector = PIIDetectorLite()

        # Serviços de suporte
        self.reversible_mask = get_reversible_mask_service()
        self.audit_logger = get_audit_logger()

        self.enabled = settings.PII_DETECTION_ENABLED

        logger.info(
            "pii_service_initialized",
            enabled=self.enabled,
            strategy=settings.PII_DEFAULT_STRATEGY,
        )

    def detect(
        self,
        text: str,
        types_to_detect: list[PIIType] | None = None,
        min_confidence: float = 0.0,
    ) -> list[PIIFound]:
        """
        Detecta PII em texto (INV-2: 7 tipos com positions).

        Args:
            text: Texto para analisar
            types_to_detect: Tipos específicos para detectar (todos se None)
            min_confidence: Confiança mínima

        Returns:
            Lista de PII detectado com posições
        """
        if not self.enabled or not text:
            return []

        # Mapear tipos para specialist
        specialist_types = None
        if types_to_detect:
            specialist_types = [
                PII_TYPE_REVERSE_MAPPING[t] for t in types_to_detect if t in PII_TYPE_REVERSE_MAPPING
            ]

        # Detectar usando PIIDetectorLite
        detected = self.detector.detect_pii(text)

        # Converter para PIIFound com positions
        result = []
        for item in detected:
            pii_type = PIIType(item["entity_type"])

            # Filtrar por confiança
            if item.get("score", 1.0) < min_confidence:
                continue

            # Filtrar por tipos solicitados
            if types_to_detect and pii_type not in types_to_detect:
                continue

            result.append(
                PIIFound(
                    type=pii_type,
                    value=item["value"],
                    start=item["start"],
                    end=item["end"],
                    confidence=item.get("score", 1.0),
                )
            )

        logger.debug(
            "pii_detected",
            text_length=len(text),
            found_count=len(result),
        )

        return result

    async def mask(
        self,
        text: str,
        strategy: MaskStrategy = MaskStrategy.MASK_PARTIAL,
        types_to_mask: list[PIIType] | None = None,
        enable_reversible: bool = False,
        requestor_id: str = "anonymous",
        tenant_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
        enable_audit_log: bool = True,
    ) -> tuple[str, list[PIIFound], list[MaskResult], str | None]:
        """
        Mascara PII em texto (R-P3: 3 strategies, R-P4: audit log).

        Args:
            text: Texto para mascarar
            strategy: Estratégia de mascaramento
            types_to_mask: Tipos específicos para mascarar
            enable_reversible: Habilitar unmask reversível (INV-14)
            requestor_id: ID do solicitante
            tenant_id: ID do tenant
            user_id: ID do usuário
            correlation_id: ID de correlação
            enable_audit_log: Habilitar audit log (INV-13)

        Returns:
            Tupla (masked_text, detected_pii, mask_results, mask_id)
        """
        if not self.enabled or not text:
            return text, [], [], None

        # Mapear tipos para specialist
        specialist_types = None
        if types_to_mask:
            specialist_types = [
                PII_TYPE_REVERSE_MAPPING[t] for t in types_to_mask if t in PII_TYPE_REVERSE_MAPPING
            ]

        # Mapear estratégia
        specialist_strategy = MASK_STRATEGY_MAPPING.get(strategy, MaskStrategy.PARTIAL)

        # Detectar e mascarar
        detected = self.detect(text, types_to_mask)

        if not detected:
            if enable_audit_log:
                # Log mesmo sem detecção
                text_hash = hashlib.sha256(text.encode()).hexdigest()
                await self.audit_logger.log_detect_operation(
                    text_hash=text_hash,
                    pii_types_found=[],
                    requestor_id=requestor_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            return text, [], [], None

        # Aplicar mascaramento
        mask_result = self.masker.mask(text, specialist_types, specialist_strategy)

        # Converter entidades detectadas
        pii_found = []
        mask_results = []
        mask_id = None

        for entity in mask_result.entities:
            our_type = PII_TYPE_MAPPING.get(entity.type, PIIType.PII_UNKNOWN)

            pii_found.append(
                PIIFound(
                    type=our_type,
                    value=entity.value,
                    start=entity.start,
                    end=entity.end,
                    confidence=entity.confidence,
                    masked_value=entity.masked_value,
                )
            )

            mask_results.append(
                MaskResult(
                    type=our_type,
                    original_value=entity.value,
                    masked_value=entity.masked_value or "",
                    start=entity.start,
                    end=entity.end,
                    strategy_used=strategy,
                )
            )

        # Criar token de unmask reversível se solicitado
        if enable_reversible and strategy == MaskStrategy.MASK_REDACT:
            # Criar token composto com todas as entidades
            # Para simplificar, vamos criar um token por entidade
            # Em produção, pode-se criar um token com todas as entidades
            pii_types_str = [p.type.value for p in pii_found]
            combined_value = "|".join([f"{p.type.value}:{p.value}" for p in pii_found])
            mask_id, _ = self.reversible_mask.create_mask_token(
                original_value=combined_value,
                pii_type=",".join(pii_types_str),
                requestor_id=requestor_id,
            )

        # Audit log (INV-13)
        if enable_audit_log:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            masked_hash = hashlib.sha256(mask_result.text.encode()).hexdigest()
            pii_types_found = [p.type.value for p in pii_found]

            await self.audit_logger.log_mask_operation(
                text_hash=text_hash,
                pii_types_found=pii_types_found,
                strategy=strategy.value,
                masked_text_hash=masked_hash,
                requestor_id=requestor_id,
                tenant_id=tenant_id,
                user_id=user_id,
                correlation_id=correlation_id,
                mask_id=mask_id,
            )

        logger.info(
            "pii_masked",
            entities_count=len(pii_found),
            strategy=strategy.value,
            reversible=enable_reversible,
        )

        return mask_result.text, pii_found, mask_results, mask_id

    async def unmask(
        self,
        mask_id: str,
        masked_text: str | None = None,
        requestor_id: str = "anonymous",
        tenant_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
        enable_audit_log: bool = True,
    ) -> tuple[str, bool, str | None]:
        """
        Remove máscara de PII (INV-14: AES-256-GCM reversible unmask).

        Args:
            mask_id: ID do mascaramento (token criptografado)
            masked_text: Texto mascarado (para validação)
            requestor_id: ID do solicitante
            tenant_id: ID do tenant
            user_id: ID do usuário
            correlation_id: ID de correlação
            enable_audit_log: Habilitar audit log (INV-13)

        Returns:
            Tupla (original_text, success, error_message)
        """
        try:
            # Descriptografar token
            original_value, pii_type = self.reversible_mask.unmask(mask_id, requestor_id)

            # Audit log (INV-13)
            if enable_audit_log:
                await self.audit_logger.log_unmask_operation(
                    mask_id=mask_id,
                    pii_type=pii_type,
                    success=True,
                    requestor_id=requestor_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )

            logger.info(
                "pii_unmasked",
                pii_type=pii_type,
                requestor_id=requestor_id,
            )

            return original_value, True, None

        except PIIUnmaskError as e:
            # Audit log de falha
            if enable_audit_log:
                await self.audit_logger.log_unmask_operation(
                    mask_id=mask_id,
                    pii_type="unknown",
                    success=False,
                    requestor_id=requestor_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                    error_message=str(e),
                )

            logger.warning("pii_unmask_failed", error=str(e))
            return "", False, str(e)

    def get_capabilities(self) -> dict:
        """
        Retorna capacidades do serviço.

        Returns:
            Dict com tipos suportados, estratégias, etc.
        """
        settings = get_settings()

        return {
            "supported_types": [t.value for t in PIIType],
            "supported_strategies": [s.value for s in MaskStrategy],
            "supports_reversible_unmask": settings.UNMASK_ENABLED,
            "supports_audit_log": True,
            "version": settings.VERSION,
        }


# Singleton
_pii_service: PIIService | None = None


def get_pii_service() -> PIIService:
    """Retorna instância singleton do PII Service."""
    global _pii_service
    if _pii_service is None:
        _pii_service = PIIService()
    return _pii_service
