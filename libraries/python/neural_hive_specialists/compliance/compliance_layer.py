"""
Camada de compliance que orquestra PII detection, encryption e audit logging.
"""
import structlog
import time
import copy
from typing import Dict, Any, Tuple, Optional

from .pii_detector import PIIDetector
from .field_encryptor import FieldEncryptor
from .audit_logger import AuditLogger

logger = structlog.get_logger(__name__)


class ComplianceLayer:
    """
    Orquestra operações de compliance para especialistas.

    Funcionalidades:
    1. Detecção e anonimização de PII em planos cognitivos
    2. Criptografia de campos sensíveis em documentos de opinião
    3. Audit logging de operações de compliance
    4. Degradação graciosa quando componentes falham

    Uso:
        compliance = ComplianceLayer(config, specialist_type, metrics)

        # Sanitizar plano antes de feature extraction
        sanitized_plan, pii_metadata = compliance.sanitize_cognitive_plan(plan)

        # Criptografar opinião antes de persistir
        encrypted_opinion = compliance.encrypt_opinion_fields(opinion_doc)
    """

    def __init__(self, config, specialist_type: str, metrics):
        """
        Inicializa ComplianceLayer.

        Args:
            config: SpecialistConfig
            specialist_type: Tipo do especialista
            metrics: SpecialistMetrics para registrar métricas
        """
        self.config = config
        self.specialist_type = specialist_type
        self.metrics = metrics
        self.enabled = config.enable_compliance_layer

        if not self.enabled:
            logger.info("ComplianceLayer desabilitado por configuração")
            return

        # Inicializar componentes
        try:
            self.pii_detector = (
                PIIDetector(config) if config.enable_pii_detection else None
            )
            self.field_encryptor = (
                FieldEncryptor(config) if config.enable_field_encryption else None
            )
            self.audit_logger = (
                AuditLogger(config, specialist_type)
                if config.enable_audit_logging
                else None
            )

            logger.info(
                "ComplianceLayer inicializada com sucesso",
                specialist_type=specialist_type,
                pii_detection=config.enable_pii_detection,
                field_encryption=config.enable_field_encryption,
                audit_logging=config.enable_audit_logging,
            )

        except Exception as e:
            logger.error(
                "Falha ao inicializar ComplianceLayer - compliance desabilitado",
                error=str(e),
            )
            self.enabled = False

    def sanitize_cognitive_plan(
        self, plan: Dict[str, Any], language: str = "pt"
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Detecta e anonimiza PII em plano cognitivo.

        Campos varridos:
        - tasks[].description
        - tasks[].parameters (valores de dict)
        - metadata (valores de dict)

        Args:
            plan: Dicionário do plano cognitivo
            language: Código de idioma (pt, en)

        Returns:
            Tupla (plano_sanitizado, metadados_pii)

        Exemplo de metadados_pii:
            {
                'entities_detected': [
                    {'field': 'tasks[0].description', 'entity_type': 'PERSON', ...},
                    ...
                ],
                'anonymization_applied': True,
                'duration_seconds': 0.250
            }
        """
        if not self.enabled or not self.pii_detector:
            return plan, {}

        try:
            start_time = time.time()

            # Usar deepcopy para evitar mutação do plano original
            sanitized_plan = copy.deepcopy(plan)
            all_entities = []

            # Varrer task descriptions
            if "tasks" in sanitized_plan:
                for i, task in enumerate(sanitized_plan["tasks"]):
                    if "description" in task and task["description"]:
                        field_name = f"tasks[{i}].description"

                        anonymized_text, entities = self.pii_detector.anonymize_text(
                            task["description"], language
                        )

                        if entities:
                            task["description"] = anonymized_text

                            # Adicionar contexto aos metadados
                            for entity in entities:
                                entity["field"] = field_name
                            all_entities.extend(entities)

                    # Varrer parameters se for dict
                    if "parameters" in task and isinstance(task["parameters"], dict):
                        for param_key, param_value in task["parameters"].items():
                            if isinstance(param_value, str) and param_value:
                                field_name = f"tasks[{i}].parameters.{param_key}"

                                (
                                    anonymized_text,
                                    entities,
                                ) = self.pii_detector.anonymize_text(
                                    param_value, language
                                )

                                if entities:
                                    task["parameters"][param_key] = anonymized_text

                                    for entity in entities:
                                        entity["field"] = field_name
                                    all_entities.extend(entities)

            # Varrer metadata
            if "metadata" in sanitized_plan and isinstance(
                sanitized_plan["metadata"], dict
            ):
                for meta_key, meta_value in sanitized_plan["metadata"].items():
                    if isinstance(meta_value, str) and meta_value:
                        field_name = f"metadata.{meta_key}"

                        anonymized_text, entities = self.pii_detector.anonymize_text(
                            meta_value, language
                        )

                        if entities:
                            sanitized_plan["metadata"][meta_key] = anonymized_text

                            for entity in entities:
                                entity["field"] = field_name
                            all_entities.extend(entities)

            duration = time.time() - start_time

            # Construir metadados
            pii_metadata = {
                "entities_detected": all_entities,
                "anonymization_applied": len(all_entities) > 0,
                "duration_seconds": duration,
            }

            # Registrar métricas
            if all_entities:
                for entity in all_entities:
                    if hasattr(self.metrics, "increment_pii_entities_detected"):
                        self.metrics.increment_pii_entities_detected(
                            entity.get("entity_type", "UNKNOWN")
                        )

                if hasattr(self.metrics, "increment_pii_anonymization"):
                    self.metrics.increment_pii_anonymization(
                        self.config.pii_anonymization_strategy
                    )

            if hasattr(self.metrics, "observe_pii_detection_duration"):
                self.metrics.observe_pii_detection_duration(duration)

            # Audit log se PII detectado
            if all_entities and self.audit_logger:
                self.audit_logger.log_pii_detection(
                    plan_id=plan.get("plan_id", "unknown"),
                    entities_detected=all_entities,
                    anonymization_applied=True,
                )

            if all_entities:
                logger.info(
                    "PII detectado e anonimizado em plano cognitivo",
                    plan_id=plan.get("plan_id"),
                    entities_count=len(all_entities),
                    duration_seconds=duration,
                )

            return sanitized_plan, pii_metadata

        except Exception as e:
            logger.error(
                "Erro ao sanitizar plano cognitivo - retornando plano original",
                plan_id=plan.get("plan_id"),
                error=str(e),
            )

            if hasattr(self.metrics, "increment_pii_detection_error"):
                self.metrics.increment_pii_detection_error("sanitization_error")

            return plan, {}

    def encrypt_opinion_fields(self, opinion_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Criptografa campos sensíveis em documento de opinião.

        Campos criptografados por padrão:
        - correlation_id
        - trace_id
        - span_id
        - intent_id

        Args:
            opinion_doc: Documento de opinião

        Returns:
            Documento com campos criptografados e metadados de criptografia
        """
        if not self.enabled or not self.field_encryptor:
            return opinion_doc

        try:
            start_time = time.time()

            encrypted_doc = self.field_encryptor.encrypt_dict(
                opinion_doc, self.config.fields_to_encrypt
            )

            duration = time.time() - start_time

            # Adicionar metadados de criptografia
            encrypted_doc["_compliance"] = {
                "encrypted_fields": self.config.fields_to_encrypt,
                "encryption_algorithm": self.config.encryption_algorithm,
                "encryption_version": "1.0",
                "encrypted_at": time.time(),
            }

            # Registrar métricas
            for field in self.config.fields_to_encrypt:
                if field in opinion_doc and opinion_doc[field]:
                    if hasattr(self.metrics, "increment_fields_encrypted"):
                        self.metrics.increment_fields_encrypted(field)

            if hasattr(self.metrics, "observe_encryption_duration"):
                self.metrics.observe_encryption_duration("encrypt", duration)

            # Audit log
            if self.audit_logger:
                for field in self.config.fields_to_encrypt:
                    if field in opinion_doc and opinion_doc[field]:
                        self.audit_logger.log_encryption_operation(
                            operation="encrypt", field_name=field, success=True
                        )

            logger.debug(
                "Campos de opinião criptografados",
                opinion_id=opinion_doc.get("opinion_id"),
                fields_encrypted=self.config.fields_to_encrypt,
                duration_seconds=duration,
            )

            return encrypted_doc

        except Exception as e:
            logger.error(
                "Erro ao criptografar campos de opinião - retornando documento sem criptografia",
                opinion_id=opinion_doc.get("opinion_id"),
                error=str(e),
            )

            if hasattr(self.metrics, "increment_encryption_error"):
                self.metrics.increment_encryption_error("encryption_error")

            # Audit log de falha
            if self.audit_logger:
                self.audit_logger.log_encryption_operation(
                    operation="encrypt", field_name="bulk", success=False, error=str(e)
                )

            return opinion_doc

    def decrypt_opinion_fields(self, opinion_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Descriptografa campos de documento de opinião (para auditoria).

        Args:
            opinion_doc: Documento com campos criptografados

        Returns:
            Documento com campos descriptografados
        """
        if not self.enabled or not self.field_encryptor:
            return opinion_doc

        try:
            start_time = time.time()

            # Obter campos criptografados dos metadados
            fields_to_decrypt = opinion_doc.get("_compliance", {}).get(
                "encrypted_fields"
            )
            if not fields_to_decrypt:
                fields_to_decrypt = self.config.fields_to_encrypt

            decrypted_doc = self.field_encryptor.decrypt_dict(
                opinion_doc, fields_to_decrypt
            )

            duration = time.time() - start_time

            # Registrar métricas
            for field in fields_to_decrypt:
                if field in opinion_doc:
                    if hasattr(self.metrics, "increment_fields_decrypted"):
                        self.metrics.increment_fields_decrypted(field)

            if hasattr(self.metrics, "observe_encryption_duration"):
                self.metrics.observe_encryption_duration("decrypt", duration)

            logger.debug(
                "Campos de opinião descriptografados",
                opinion_id=opinion_doc.get("opinion_id"),
                fields_decrypted=fields_to_decrypt,
                duration_seconds=duration,
            )

            return decrypted_doc

        except Exception as e:
            logger.error(
                "Erro ao descriptografar campos de opinião",
                opinion_id=opinion_doc.get("opinion_id"),
                error=str(e),
            )

            if hasattr(self.metrics, "increment_encryption_error"):
                self.metrics.increment_encryption_error("decryption_error")

            return opinion_doc

    def get_compliance_metadata(self) -> Dict[str, Any]:
        """
        Retorna metadados de configuração de compliance.

        Returns:
            Dicionário com versões e configurações
        """
        if not self.enabled:
            return {"enabled": False}

        return {
            "enabled": True,
            "pii_detection": {
                "enabled": self.config.enable_pii_detection,
                "languages": self.config.pii_detection_languages,
                "entities": self.config.pii_entities_to_detect,
                "strategy": self.config.pii_anonymization_strategy,
            },
            "field_encryption": {
                "enabled": self.config.enable_field_encryption,
                "algorithm": self.config.encryption_algorithm,
                "fields": self.config.fields_to_encrypt,
            },
            "audit_logging": {
                "enabled": self.config.enable_audit_logging,
                "collection": self.config.audit_log_collection,
                "retention_days": self.config.audit_log_retention_days,
            },
        }
