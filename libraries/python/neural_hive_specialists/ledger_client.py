"""
Cliente para persistência de pareceres no ledger cognitivo (MongoDB).
"""

import hashlib
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import structlog
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
from tenacity import retry, stop_after_attempt, wait_exponential
from circuitbreaker import CircuitBreaker, CircuitBreakerError
from queue import Queue, Full, Empty

from .config import SpecialistConfig
from .ledger import OpinionDocumentV2, Opinion, DigitalSigner, SchemaVersionManager
from .ledger.query_api import LedgerQueryAPI
from .compliance import AuditLogger, FieldEncryptor

logger = structlog.get_logger()


class LedgerClient:
    """Cliente para gerenciar ledger cognitivo no MongoDB."""

    def __init__(self, config: SpecialistConfig, metrics=None):
        self.config = config
        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None
        self._metrics = metrics
        self._opinion_buffer: Queue = Queue(maxsize=config.ledger_buffer_size)
        self._buffer_max_size = config.ledger_buffer_size
        self._circuit_breaker_state = 'closed'
        self._was_open = False
        self._last_save_was_buffered = False

        # Initialize digital signer if enabled
        self.digital_signer: Optional[DigitalSigner] = None
        if config.enable_digital_signature:
            signer_config = {
                'private_key_path': config.ledger_private_key_path,
                'public_key_path': config.ledger_public_key_path
            }
            try:
                self.digital_signer = DigitalSigner(signer_config)
                logger.info(
                    "Digital signer initialized",
                    has_private_key=self.digital_signer.private_key is not None,
                    has_public_key=self.digital_signer.public_key is not None
                )
            except Exception as e:
                logger.error("Failed to initialize digital signer", error=str(e))
                self.digital_signer = None

        # Store schema configuration
        self.enable_schema_validation = config.enable_schema_validation
        self.ledger_schema_version = config.ledger_schema_version

        # Initialize query API if enabled
        self._query_api: Optional[LedgerQueryAPI] = None
        if config.enable_query_api:
            query_config = {
                'mongodb_uri': config.mongodb_uri,
                'mongodb_database': config.mongodb_database,
                'mongodb_opinions_collection': config.mongodb_opinions_collection,
                'query_cache_ttl_seconds': config.query_cache_ttl_seconds
            }
            try:
                self._query_api = LedgerQueryAPI(query_config)
                logger.info("LedgerQueryAPI initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize LedgerQueryAPI", error=str(e))
                self._query_api = None

        # Initialize Compliance components
        self.audit_logger: Optional[AuditLogger] = None
        self.field_encryptor: Optional[FieldEncryptor] = None

        if config.enable_audit_logging:
            try:
                self.audit_logger = AuditLogger(
                    config=config,
                    specialist_type='ledger_client'
                )
                logger.info("AuditLogger initialized in LedgerClient")
            except Exception as e:
                logger.error("Failed to initialize AuditLogger", error=str(e))

        if config.enable_field_encryption:
            try:
                self.field_encryptor = FieldEncryptor(config=config)
                logger.info("FieldEncryptor initialized in LedgerClient")
            except Exception as e:
                logger.error("Failed to initialize FieldEncryptor", error=str(e))

        # Initialize circuit breaker state in metrics
        if metrics:
            metrics.set_circuit_breaker_state('ledger', 'closed')

        # Initialize circuit breakers conditionally
        self._save_opinion_breaker = None
        self._get_opinion_breaker = None
        self._get_opinions_by_plan_breaker = None
        self._get_opinions_by_intent_breaker = None
        self._verify_integrity_breaker = None

        if config.enable_circuit_breaker:
            self._save_opinion_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=PyMongoError,
                name='ledger_save_opinion'
            )
            self._get_opinion_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=PyMongoError,
                name='ledger_get_opinion'
            )
            self._get_opinions_by_plan_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=PyMongoError,
                name='ledger_get_opinions_by_plan'
            )
            self._get_opinions_by_intent_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=PyMongoError,
                name='ledger_get_opinions_by_intent'
            )
            self._verify_integrity_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=PyMongoError,
                name='ledger_verify_integrity'
            )

        logger.info(
            "Ledger client initialized",
            database=config.mongodb_database,
            collection=config.mongodb_opinions_collection,
            buffer_max_size=self._buffer_max_size
        )

        # Inicializar conexão e índices
        self._initialize()

    @property
    def client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB."""
        if self._client is None:
            self._client = MongoClient(
                self.config.mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
        return self._client

    @property
    def collection(self):
        """Obtém collection de pareceres."""
        if self._collection is None:
            self._db = self.client[self.config.mongodb_database]
            self._collection = self._db[self.config.mongodb_opinions_collection]
        return self._collection

    def _initialize(self):
        """Inicializa conexão e cria índices."""
        try:
            # Criar índices
            self._create_indexes()
            logger.info("Ledger indexes created successfully")
        except Exception as e:
            logger.warning("Failed to create ledger indexes", error=str(e))

    def _create_indexes(self):
        """Cria índices otimizados no MongoDB."""
        try:
            # Índice único no opinion_id
            self.collection.create_index(
                [("opinion_id", ASCENDING)],
                unique=True,
                name="idx_opinion_id"
            )

            # Índice no plan_id para consultas por plano
            self.collection.create_index(
                [("plan_id", ASCENDING)],
                name="idx_plan_id"
            )

            # Índice no intent_id para rastreamento
            self.collection.create_index(
                [("intent_id", ASCENDING)],
                name="idx_intent_id"
            )

            # Índice composto specialist_type + evaluated_at (v2)
            self.collection.create_index(
                [("specialist_type", ASCENDING), ("evaluated_at", DESCENDING)],
                name="idx_specialist_evaluated_at"
            )

            # Índice no correlation_id para correlação (mantido para backward compatibility)
            self.collection.create_index(
                [("correlation_id", ASCENDING)],
                name="idx_correlation_id"
            )

            # Índice no correlation_id_hash para buscas eficientes com hash
            self.collection.create_index(
                [("correlation_id_hash", ASCENDING)],
                name="idx_correlation_id_hash"
            )

            # Índice no domínio (v2)
            self.collection.create_index(
                [("opinion.metadata.domain", ASCENDING)],
                name="idx_domain"
            )

            # Índices para multi-tenancy
            # Índice composto tenant_id + opinion_id (único por tenant)
            self.collection.create_index(
                [("tenant_id", ASCENDING), ("opinion_id", ASCENDING)],
                unique=True,
                name="idx_tenant_opinion_id"
            )

            # Índice composto tenant_id + plan_id
            self.collection.create_index(
                [("tenant_id", ASCENDING), ("plan_id", ASCENDING)],
                name="idx_tenant_plan_id"
            )

            # Índice composto tenant_id + specialist_type + evaluated_at
            self.collection.create_index(
                [("tenant_id", ASCENDING), ("specialist_type", ASCENDING), ("evaluated_at", DESCENDING)],
                name="idx_tenant_specialist_evaluated_at"
            )

            # Índice nos fatores de raciocínio (v2)
            self.collection.create_index(
                [("opinion.reasoning_factors.factor_name", ASCENDING)],
                name="idx_reasoning_factors"
            )

            # Índice na versão do schema (v2)
            self.collection.create_index(
                [("schema_version", ASCENDING)],
                name="idx_schema_version"
            )

            # Índice na assinatura digital (sparse, v2)
            self.collection.create_index(
                [("digital_signature", ASCENDING)],
                sparse=True,
                name="idx_digital_signature"
            )

        except PyMongoError as e:
            logger.error("Failed to create indexes", error=str(e))
            raise

    def _on_circuit_breaker_state_change(self, old_state: str, new_state: str):
        """Callback para mudanças de estado do circuit breaker."""
        if self._metrics:
            self._metrics.set_circuit_breaker_state('ledger', new_state)
            self._metrics.increment_circuit_breaker_transition('ledger', old_state, new_state)

        logger.info(
            "Circuit breaker state changed",
            client='ledger',
            old_state=old_state,
            new_state=new_state
        )

        # Tentar flush do buffer quando recuperar
        if new_state == 'half-open':
            self.flush_buffered_opinions()

    def save_opinion(
        self,
        opinion: Dict[str, Any],
        plan_id: str,
        intent_id: str,
        specialist_type: str,
        correlation_id: str,
        specialist_version: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> str:
        """
        Salva parecer no ledger com hash SHA-256.

        Args:
            opinion: Parecer estruturado do especialista
            plan_id: ID do plano cognitivo
            intent_id: ID da intenção original
            specialist_type: Tipo do especialista
            correlation_id: ID de correlação
            specialist_version: Versão do especialista (opcional, default do config)
            trace_id: ID de trace OpenTelemetry (opcional)
            span_id: ID de span OpenTelemetry (opcional)
            processing_time_ms: Tempo de processamento em ms (opcional, será calculado se None)
            tenant_id: ID do tenant (opcional, default do config)

        Returns:
            opinion_id: ID único do parecer
        """
        if self.config.enable_circuit_breaker and self._save_opinion_breaker:
            return self._save_opinion_breaker.call(
                self.save_opinion_impl, opinion, plan_id, intent_id, specialist_type, correlation_id,
                specialist_version, trace_id, span_id, processing_time_ms, tenant_id
            )
        else:
            return self.save_opinion_impl(
                opinion, plan_id, intent_id, specialist_type, correlation_id,
                specialist_version, trace_id, span_id, processing_time_ms, tenant_id
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def save_opinion_impl(
        self,
        opinion: Dict[str, Any],
        plan_id: str,
        intent_id: str,
        specialist_type: str,
        correlation_id: str,
        specialist_version: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> str:
        """
        Implementação interna de save_opinion com OpinionDocumentV2 e assinatura digital.

        Args:
            opinion: Parecer estruturado do especialista
            plan_id: ID do plano cognitivo
            intent_id: ID da intenção original
            specialist_type: Tipo do especialista
            correlation_id: ID de correlação
            specialist_version: Versão do especialista (opcional, default do config)
            trace_id: ID de trace OpenTelemetry (opcional)
            span_id: ID de span OpenTelemetry (opcional)
            processing_time_ms: Tempo de processamento em ms (opcional, será calculado se None)
            tenant_id: ID do tenant (opcional, default do config)

        Returns:
            opinion_id: ID único do parecer
        """
        try:
            import time
            start_save_time = time.time()

            # Gerar opinion_id único
            opinion_id = str(uuid.uuid4())

            # Construir Opinion object (com backward compatibility)
            from .ledger import ReasoningFactor, Mitigation

            # Preparar dados da opinião com defaults sensatos para campos obrigatórios
            opinion_data = {
                'confidence_score': opinion.get('confidence_score', 0.0),
                'risk_score': opinion.get('risk_score', 0.0),
                'recommendation': opinion.get('recommendation', 'review_required'),
                'reasoning_summary': opinion.get('reasoning_summary', 'No summary provided'),
                'reasoning_factors': [],
                'explainability_token': opinion.get('explainability_token', ''),
                'explainability': opinion.get('explainability', {}),
                'mitigations': [],
                'metadata': opinion.get('metadata', {})
            }

            # Converter reasoning_factors com normalização de campos
            for factor in opinion.get('reasoning_factors', []):
                if isinstance(factor, dict):
                    # Normalizar 'factor' -> 'factor_name' para backward compatibility
                    if 'factor' in factor and 'factor_name' not in factor:
                        factor = {**factor, 'factor_name': factor['factor']}
                    # Garantir campos obrigatórios
                    factor.setdefault('factor_name', 'unknown')
                    factor.setdefault('weight', 0.0)
                    factor.setdefault('score', 0.0)
                    opinion_data['reasoning_factors'].append(factor)
                else:
                    # Já é um ReasoningFactor
                    opinion_data['reasoning_factors'].append(factor.dict() if hasattr(factor, 'dict') else factor)

            # Converter mitigations
            for m in opinion.get('mitigations', []):
                if isinstance(m, dict):
                    opinion_data['mitigations'].append(m)
                else:
                    opinion_data['mitigations'].append(m.dict() if hasattr(m, 'dict') else m)

            # Validar e construir Opinion usando Pydantic
            try:
                # Tentar usar model_validate (Pydantic v2)
                if hasattr(Opinion, 'model_validate'):
                    opinion_obj = Opinion.model_validate(opinion_data)
                else:
                    # Fallback para Pydantic v1
                    opinion_obj = Opinion(**opinion_data)
            except Exception as e:
                logger.error(
                    "Failed to validate Opinion with Pydantic",
                    error=str(e),
                    opinion_data=opinion_data
                )
                raise ValueError(f"Opinion validation failed: {e}")

            # Construir OpinionDocumentV2
            opinion_doc = OpinionDocumentV2(
                schema_version=self.ledger_schema_version,
                opinion_id=opinion_id,
                plan_id=plan_id,
                intent_id=intent_id,
                specialist_type=specialist_type,
                specialist_version=specialist_version or self.config.specialist_version,
                opinion=opinion_obj,
                correlation_id=correlation_id,
                trace_id=trace_id,
                span_id=span_id,
                evaluated_at=datetime.utcnow(),
                processing_time_ms=processing_time_ms if processing_time_ms is not None else int((time.time() - start_save_time) * 1000),
                buffered=False,
                content_hash=''  # Will be calculated by DigitalSigner
            )

            # Convert to dict for MongoDB
            document = opinion_doc.dict()

            # Adicionar tenant_id ao documento para multi-tenancy
            document['tenant_id'] = tenant_id or self.config.default_tenant_id

            # Calcular correlation_id_hash para permitir buscas (antes de qualquer criptografia)
            if self.config.enable_correlation_hash and correlation_id:
                correlation_id_hash = hashlib.sha256(correlation_id.encode('utf-8')).hexdigest()
                document['correlation_id_hash'] = correlation_id_hash
                logger.debug(
                    "correlation_id_hash calculated",
                    opinion_id=opinion_id,
                    hash_prefix=correlation_id_hash[:8]
                )

            # Validate schema if enabled
            if self.enable_schema_validation:
                is_valid = SchemaVersionManager.validate_document(document)
                if not is_valid:
                    logger.error(
                        "Schema validation failed",
                        opinion_id=opinion_id,
                        schema_version=self.ledger_schema_version
                    )
                    raise ValueError("Opinion document schema validation failed")

            # PASSO 1: Encrypt sensitive fields ANTES de assinar (para garantir integridade do documento persistido)
            if self.field_encryptor:
                try:
                    document = self.field_encryptor.encrypt_dict(
                        document,
                        self.config.fields_to_encrypt
                    )
                    logger.debug(
                        "Opinion fields encrypted",
                        opinion_id=opinion_id,
                        fields=self.config.fields_to_encrypt
                    )
                except Exception as e:
                    logger.error(
                        "Failed to encrypt opinion fields - continuing without encryption",
                        opinion_id=opinion_id,
                        error=str(e)
                    )

            # PASSO 2: Sign document APÓS criptografia (assinatura deve refletir o documento persistido)
            if self.digital_signer:
                try:
                    document = self.digital_signer.sign_document(document)
                    logger.debug(
                        "Opinion signed successfully",
                        opinion_id=opinion_id,
                        signature_algorithm=document.get('signature_algorithm')
                    )
                except Exception as e:
                    logger.error(
                        "Failed to sign opinion document",
                        opinion_id=opinion_id,
                        error=str(e)
                    )
                    # Continue without signature if signing fails
            else:
                # Calculate hash manually if no digital signer
                document['content_hash'] = self._calculate_content_hash(document)

            # PASSO 3: Maintain backward compatibility - keep legacy hash field (após criptografia)
            document['hash'] = self._calculate_hash({
                'opinion_id': opinion_id,
                'plan_id': plan_id,
                'intent_id': intent_id,
                'specialist_type': specialist_type,
                'correlation_id': correlation_id,
                'opinion_data': opinion,
                'timestamp': document['evaluated_at']
            })

            # Inserir no MongoDB
            self.collection.insert_one(document)

            # Audit log opinion persistence
            if self.audit_logger:
                try:
                    self.audit_logger.log_data_access(
                        accessed_by=f"specialist:{specialist_type}",
                        resource_type='opinion',
                        resource_id=opinion_id,
                        action='create',
                        metadata={
                            'plan_id': plan_id,
                            'intent_id': intent_id,
                            'recommendation': opinion.get('recommendation'),
                            'buffered': False
                        }
                    )
                except Exception as e:
                    logger.error("Failed to audit log opinion persistence", error=str(e))

            # Mark as not buffered
            self._last_save_was_buffered = False

            # Check if recovering from open state
            if self._was_open:
                if self._metrics:
                    self._metrics.increment_circuit_breaker_success_after_halfopen('ledger')
                self._circuit_breaker_state = 'closed'
                if self._metrics:
                    self._metrics.set_circuit_breaker_state('ledger', 'closed')
                self._was_open = False
                logger.info("Circuit breaker recovered to closed state", client='ledger')

            logger.info(
                "Opinion saved to ledger",
                opinion_id=opinion_id,
                plan_id=plan_id,
                specialist_type=specialist_type,
                schema_version=document.get('schema_version'),
                signed=document.get('digital_signature') is not None
            )

            return opinion_id

        except PyMongoError as e:
            if self._metrics:
                self._metrics.increment_circuit_breaker_failure('ledger', type(e).__name__)

            logger.error(
                "Failed to save opinion to ledger",
                plan_id=plan_id,
                specialist_type=specialist_type,
                error=str(e)
            )
            raise

    def _calculate_hash(self, document: Dict[str, Any]) -> str:
        """
        Calcula hash SHA-256 do documento para auditoria (formato legado).

        Args:
            document: Documento a ser hasheado

        Returns:
            Hash SHA-256 em hexadecimal
        """
        # Remover campos que não devem ser hasheados
        hashable_doc = {
            'opinion_id': document['opinion_id'],
            'plan_id': document['plan_id'],
            'intent_id': document['intent_id'],
            'specialist_type': document['specialist_type'],
            'correlation_id': document['correlation_id'],
            'opinion_data': document['opinion_data'],
            'timestamp': document['timestamp'].isoformat() if isinstance(document['timestamp'], datetime) else document['timestamp']
        }

        # Serializar para JSON ordenado
        json_str = json.dumps(hashable_doc, sort_keys=True, default=str)

        # Calcular hash SHA-256
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def _calculate_content_hash(self, document: Dict[str, Any]) -> str:
        """
        Calcula content_hash para OpinionDocumentV2.

        Args:
            document: Documento OpinionDocumentV2

        Returns:
            Hash SHA-256 em hexadecimal
        """
        # Usar o mesmo método do DigitalSigner
        if self.digital_signer:
            return self.digital_signer.compute_content_hash(document)

        # Fallback manual
        hashable_fields = ['opinion_id', 'plan_id', 'intent_id', 'specialist_type', 'opinion', 'evaluated_at']
        hashable_doc = {k: document[k] for k in hashable_fields if k in document}
        json_str = json.dumps(hashable_doc, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def verify_document_integrity(self, opinion_id: str) -> Optional[bool]:
        """
        Verifica integridade de um documento de opinião (método unificado).

        Prioriza verificação de assinatura digital se disponível, caso contrário
        usa verificação de hash legado.

        Args:
            opinion_id: ID da opinião

        Returns:
            True se íntegro, False se adulterado, None se não encontrado ou erro
        """
        try:
            document = self.get_opinion(opinion_id)
            if not document:
                logger.warning("Opinion not found for integrity check", opinion_id=opinion_id)
                return None

            # Prioridade 1: Verificar assinatura digital se disponível
            if 'digital_signature' in document and document.get('digital_signature'):
                if self.digital_signer:
                    try:
                        is_valid = self.digital_signer.verify_signature(document)
                        logger.info(
                            "Document integrity verified via digital signature",
                            opinion_id=opinion_id,
                            is_valid=is_valid
                        )
                        return is_valid
                    except Exception as e:
                        logger.error(
                            "Failed to verify digital signature, falling back to hash",
                            opinion_id=opinion_id,
                            error=str(e)
                        )
                        # Fallback para verificação de hash
                else:
                    logger.warning(
                        "Document has signature but signer not initialized, falling back to hash",
                        opinion_id=opinion_id
                    )

            # Prioridade 2: Fallback para verificação de hash legado
            return self.verify_integrity_impl(opinion_id)

        except Exception as e:
            logger.error(
                "Failed to verify document integrity",
                opinion_id=opinion_id,
                error=str(e)
            )
            return None

    def verify_signature(self, opinion_id: str) -> bool:
        """
        Verifica assinatura digital de uma opinião (wrapper para backward compatibility).

        Args:
            opinion_id: ID da opinião

        Returns:
            True se assinatura válida, False caso contrário
        """
        try:
            document = self.get_opinion(opinion_id)
            if not document:
                logger.warning("Opinion not found for signature verification", opinion_id=opinion_id)
                return False

            if not self.digital_signer:
                logger.warning("Digital signer not initialized, cannot verify signature")
                return False

            # Check if document has digital signature
            if 'digital_signature' not in document or not document['digital_signature']:
                logger.warning("Opinion has no digital signature", opinion_id=opinion_id)
                return False

            # Verify signature
            is_valid = self.digital_signer.verify_signature(document)

            logger.info(
                "Signature verification completed",
                opinion_id=opinion_id,
                is_valid=is_valid
            )

            return is_valid

        except Exception as e:
            logger.error(
                "Failed to verify signature",
                opinion_id=opinion_id,
                error=str(e)
            )
            return False

    def detect_tampering(self, opinion_id: str) -> bool:
        """
        Detecta adulteração em uma opinião.

        Args:
            opinion_id: ID da opinião

        Returns:
            True se adulteração detectada, False se íntegro
        """
        try:
            document = self.get_opinion(opinion_id)
            if not document:
                logger.warning("Opinion not found for tampering detection", opinion_id=opinion_id)
                return False

            if not self.digital_signer:
                logger.warning("Digital signer not initialized, cannot detect tampering")
                return False

            # Detect tampering
            is_tampered = self.digital_signer.detect_tampering(document)

            if is_tampered:
                logger.error(
                    "Tampering detected",
                    opinion_id=opinion_id
                )
            else:
                logger.debug(
                    "No tampering detected",
                    opinion_id=opinion_id
                )

            return is_tampered

        except Exception as e:
            logger.error(
                "Failed to detect tampering",
                opinion_id=opinion_id,
                error=str(e)
            )
            return False

    def save_opinion_with_fallback(
        self,
        opinion: Dict[str, Any],
        plan_id: str,
        intent_id: str,
        specialist_type: str,
        correlation_id: str,
        specialist_version: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> str:
        """
        Salva parecer com fallback para buffer em memória.

        Args:
            opinion: Parecer estruturado do especialista
            plan_id: ID do plano cognitivo
            intent_id: ID da intenção original
            specialist_type: Tipo do especialista
            correlation_id: ID de correlação
            specialist_version: Versão do especialista (opcional, default do config)
            trace_id: ID de trace OpenTelemetry (opcional)
            span_id: ID de span OpenTelemetry (opcional)
            processing_time_ms: Tempo de processamento em ms (opcional, será calculado se None)
            tenant_id: ID do tenant (opcional, default do config)

        Returns:
            opinion_id: ID único do parecer (com prefixo 'buffered-' se buffered)
        """
        try:
            return self.save_opinion(
                opinion, plan_id, intent_id, specialist_type, correlation_id,
                specialist_version, trace_id, span_id, processing_time_ms, tenant_id
            )
        except CircuitBreakerError:
            # Update circuit breaker state
            self._circuit_breaker_state = 'open'
            if self._metrics:
                self._metrics.set_circuit_breaker_state('ledger', 'open')
                self._metrics.increment_circuit_breaker_failure('ledger', 'CircuitBreakerError')
            self._was_open = True

            logger.warning(
                "Circuit breaker open, buffering opinion in memory",
                plan_id=plan_id,
                specialist_type=specialist_type
            )

            # Gerar opinion_id sem prefixo (clean UUID)
            opinion_id = str(uuid.uuid4())

            # Bufferar documento com flag buffered
            document = {
                'opinion_id': opinion_id,
                'plan_id': plan_id,
                'intent_id': intent_id,
                'specialist_type': specialist_type,
                'correlation_id': correlation_id,
                'opinion_data': opinion,
                'timestamp': datetime.utcnow(),
                'immutable': True,
                'buffered': True
            }

            # Use Queue.put_nowait for thread-safe buffering
            try:
                self._opinion_buffer.put_nowait(document)
            except Full:
                logger.error(
                    "Opinion buffer full, cannot buffer more opinions",
                    buffer_size=self._opinion_buffer.qsize(),
                    max_size=self._buffer_max_size
                )
                raise Exception("Opinion buffer full")

            # Mark last save as buffered
            self._last_save_was_buffered = True

            if self._metrics:
                self._metrics.increment_fallback_invocation('ledger', 'in_memory_buffer')

            logger.info(
                "Opinion buffered in memory",
                opinion_id=opinion_id,
                buffer_size=self._opinion_buffer.qsize(),
                buffered=True
            )

            return opinion_id

        except Exception as e:
            logger.error(
                "Failed to save opinion with fallback",
                plan_id=plan_id,
                specialist_type=specialist_type,
                error=str(e)
            )
            raise

    def _buffer_opinion(self, opinion_data: Dict[str, Any]):
        """
        Adiciona opinião ao buffer em memória (método privado para testes).

        Args:
            opinion_data: Dados da opinião a bufferar
        """
        try:
            self._opinion_buffer.put_nowait(opinion_data)
            logger.debug(
                "Opinion buffered",
                opinion_id=opinion_data.get('opinion_id'),
                buffer_size=self._opinion_buffer.qsize()
            )
        except Full:
            logger.error(
                "Opinion buffer full, cannot buffer more opinions",
                buffer_size=self._opinion_buffer.qsize(),
                max_size=self._buffer_max_size
            )
            raise Exception("Opinion buffer full")

    def flush_buffer(self) -> int:
        """
        Tenta salvar opiniões do buffer quando o circuito recuperar.

        Returns:
            Número de opiniões flushadas com sucesso
        """
        return self.flush_buffered_opinions()

    def flush_buffered_opinions(self) -> int:
        """
        Tenta salvar opiniões do buffer quando o circuito recuperar.

        Returns:
            Número de opiniões flushadas com sucesso
        """
        buffer_size = self._opinion_buffer.qsize()
        if buffer_size == 0:
            return 0

        logger.info(
            "Attempting to flush buffered opinions",
            buffer_size=buffer_size
        )

        flushed_count = 0
        failed_opinions = []

        # Drain the queue
        while True:
            try:
                document = self._opinion_buffer.get_nowait()
            except Empty:
                break

            try:
                # Remove buffered flag before persisting
                document.pop('buffered', None)

                # Calcular hash
                document['hash'] = self._calculate_hash(document)

                # Inserir no MongoDB
                self.collection.insert_one(document)

                flushed_count += 1
                logger.info(
                    "Buffered opinion flushed successfully",
                    opinion_id=document['opinion_id']
                )

            except Exception as e:
                logger.error(
                    "Failed to flush buffered opinion",
                    opinion_id=document['opinion_id'],
                    error=str(e)
                )
                failed_opinions.append(document)

        # Re-queue failed opinions
        for doc in failed_opinions:
            try:
                self._opinion_buffer.put_nowait(doc)
            except Full:
                logger.error(
                    "Cannot re-queue failed opinion, buffer full",
                    opinion_id=doc['opinion_id']
                )

        logger.info(
            "Buffer flush completed",
            flushed_count=flushed_count,
            remaining_in_buffer=self._opinion_buffer.qsize()
        )

        return flushed_count

    def get_opinion(self, opinion_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera parecer por ID.

        Args:
            opinion_id: ID do parecer

        Returns:
            Documento do parecer ou None se não encontrado
        """
        if self.config.enable_circuit_breaker and self._get_opinion_breaker:
            return self._get_opinion_breaker.call(self.get_opinion_impl, opinion_id)
        else:
            return self.get_opinion_impl(opinion_id)

    def get_opinion_impl(self, opinion_id: str) -> Optional[Dict[str, Any]]:
        """
        Implementação interna de get_opinion.

        Args:
            opinion_id: ID do parecer

        Returns:
            Documento do parecer ou None se não encontrado
        """
        try:
            document = self.collection.find_one({'opinion_id': opinion_id})

            if document:
                # Remover _id do MongoDB
                document.pop('_id', None)

            # Audit log operação de leitura
            if self.audit_logger:
                try:
                    specialist_type = getattr(self.config, 'specialist_type', 'unknown')
                    self.audit_logger.log_data_access(
                        accessed_by=f"specialist:{specialist_type}",
                        resource_type='opinion',
                        resource_id=opinion_id,
                        action='read',
                        metadata={
                            'query_type': 'by_opinion_id',
                            'found': document is not None
                        }
                    )
                except Exception as e:
                    logger.error("Failed to audit log read operation", error=str(e))

            return document

        except PyMongoError as e:
            logger.error(
                "Failed to get opinion from ledger",
                opinion_id=opinion_id,
                error=str(e)
            )
            return None

    def get_opinions_by_plan(self, plan_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Recupera todos os pareceres de um plano.

        Args:
            plan_id: ID do plano cognitivo
            tenant_id: ID do tenant (opcional, para isolamento multi-tenant)

        Returns:
            Lista de documentos de pareceres
        """
        if self.config.enable_circuit_breaker and self._get_opinions_by_plan_breaker:
            return self._get_opinions_by_plan_breaker.call(self.get_opinions_by_plan_impl, plan_id, tenant_id)
        else:
            return self.get_opinions_by_plan_impl(plan_id, tenant_id)

    def get_opinions_by_plan_impl(self, plan_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Implementação interna de get_opinions_by_plan.

        Args:
            plan_id: ID do plano cognitivo
            tenant_id: ID do tenant (opcional, para isolamento multi-tenant)

        Returns:
            Lista de documentos de pareceres
        """
        try:
            # Construir query com tenant_id se fornecido
            query = {'plan_id': plan_id}
            if tenant_id is not None:
                query['tenant_id'] = tenant_id

            cursor = self.collection.find(query)
            opinions = []

            for document in cursor:
                # Remover _id do MongoDB
                document.pop('_id', None)
                opinions.append(document)

            logger.debug(
                "Retrieved opinions for plan",
                plan_id=plan_id,
                count=len(opinions)
            )

            # Audit log operação de leitura
            if self.audit_logger:
                try:
                    specialist_type = getattr(self.config, 'specialist_type', 'unknown')
                    self.audit_logger.log_data_access(
                        accessed_by=f"specialist:{specialist_type}",
                        resource_type='opinion',
                        resource_id=plan_id,
                        action='read',
                        metadata={
                            'query_type': 'by_plan_id',
                            'count': len(opinions)
                        }
                    )
                except Exception as e:
                    logger.error("Failed to audit log read operation", error=str(e))

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to get opinions for plan",
                plan_id=plan_id,
                error=str(e)
            )
            return []

    def get_opinions_by_intent(self, intent_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Recupera todos os pareceres de uma intenção.

        Args:
            intent_id: ID da intenção original
            tenant_id: ID do tenant (opcional, para isolamento multi-tenant)

        Returns:
            Lista de documentos de pareceres
        """
        if self.config.enable_circuit_breaker and self._get_opinions_by_intent_breaker:
            return self._get_opinions_by_intent_breaker.call(self.get_opinions_by_intent_impl, intent_id, tenant_id)
        else:
            return self.get_opinions_by_intent_impl(intent_id, tenant_id)

    def get_opinions_by_intent_impl(self, intent_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Implementação interna de get_opinions_by_intent.

        Args:
            intent_id: ID da intenção original
            tenant_id: ID do tenant (opcional, para isolamento multi-tenant)

        Returns:
            Lista de documentos de pareceres
        """
        try:
            # Construir query com tenant_id se fornecido
            query = {'intent_id': intent_id}
            if tenant_id is not None:
                query['tenant_id'] = tenant_id

            cursor = self.collection.find(query)
            opinions = []

            for document in cursor:
                document.pop('_id', None)
                opinions.append(document)

            # Audit log operação de leitura
            if self.audit_logger:
                try:
                    specialist_type = getattr(self.config, 'specialist_type', 'unknown')
                    self.audit_logger.log_data_access(
                        accessed_by=f"specialist:{specialist_type}",
                        resource_type='opinion',
                        resource_id=intent_id,
                        action='read',
                        metadata={
                            'query_type': 'by_intent_id',
                            'count': len(opinions)
                        }
                    )
                except Exception as e:
                    logger.error("Failed to audit log read operation", error=str(e))

            return opinions

        except PyMongoError as e:
            logger.error(
                "Failed to get opinions for intent",
                intent_id=intent_id,
                error=str(e)
            )
            return []

    def get_opinions_by_plan_id(self, plan_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias para get_opinions_by_plan (backward compatibility)."""
        return self.get_opinions_by_plan(plan_id, tenant_id)

    def get_opinions_by_intent_id(self, intent_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias para get_opinions_by_intent (backward compatibility)."""
        return self.get_opinions_by_intent(intent_id, tenant_id)

    def verify_integrity(self, opinion_id: str) -> bool:
        """
        Verifica integridade de um parecer.

        Args:
            opinion_id: ID do parecer

        Returns:
            True se integridade válida, False caso contrário
        """
        if self.config.enable_circuit_breaker and self._verify_integrity_breaker:
            return self._verify_integrity_breaker.call(self.verify_integrity_impl, opinion_id)
        else:
            return self.verify_integrity_impl(opinion_id)

    def verify_opinion_integrity(self, opinion_id: str) -> bool:
        """Alias para verify_integrity (backward compatibility)."""
        return self.verify_integrity(opinion_id)

    def verify_integrity_impl(self, opinion_id: str) -> bool:
        """
        Implementação interna de verify_integrity.

        Args:
            opinion_id: ID do parecer

        Returns:
            True se integridade válida, False caso contrário
        """
        try:
            document = self.collection.find_one({'opinion_id': opinion_id})

            if not document:
                logger.warning("Opinion not found for integrity check", opinion_id=opinion_id)
                return False

            # Obter hash armazenado
            stored_hash = document.get('hash')

            if not stored_hash:
                logger.warning("No hash found in opinion", opinion_id=opinion_id)
                return False

            # Recalcular hash
            calculated_hash = self._calculate_hash(document)

            # Comparar hashes
            is_valid = stored_hash == calculated_hash

            if not is_valid:
                logger.error(
                    "Integrity check failed - hash mismatch",
                    opinion_id=opinion_id,
                    stored_hash=stored_hash,
                    calculated_hash=calculated_hash
                )
            else:
                logger.debug("Integrity check passed", opinion_id=opinion_id)

            return is_valid

        except Exception as e:
            logger.error(
                "Failed to verify opinion integrity",
                opinion_id=opinion_id,
                error=str(e)
            )
            return False

    def is_connected(self) -> bool:
        """Verifica conectividade com MongoDB."""
        try:
            # Tentar ping
            self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.warning("MongoDB not connected", error=str(e))
            return False

    def check_health(self) -> Dict[str, Any]:
        """
        Verifica saúde completa do MongoDB (conectividade + índices).

        Returns:
            Dict com status da saúde
        """
        try:
            # Verificar conectividade
            self.client.admin.command('ping')

            # Verificar se collection existe
            collections = self._db.list_collection_names()
            collection_exists = self.config.mongodb_opinions_collection in collections

            # Verificar índices
            indexes = list(self.collection.list_indexes())
            index_count = len(indexes)

            return {
                "connected": True,
                "collection_exists": collection_exists,
                "index_count": index_count,
                "database": self.config.mongodb_database
            }
        except Exception as e:
            logger.warning("MongoDB health check failed", error=str(e))
            return {
                "connected": False,
                "error": str(e)
            }

    def get_circuit_breaker_state(self) -> str:
        """Retorna o estado atual do circuit breaker."""
        return self._circuit_breaker_state

    def get_buffer_size(self) -> int:
        """Retorna o tamanho atual do buffer."""
        return self._opinion_buffer.qsize()

    def was_last_save_buffered(self) -> bool:
        """Retorna True se a última operação save_opinion_with_fallback foi bufferizada."""
        return self._last_save_was_buffered

    def get_opinions_by_domain(
        self,
        domain: str,
        limit: int = 100,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por domínio original do plano cognitivo.

        Args:
            domain: Domínio original (ex: 'data_processing', 'api_integration')
            limit: Número máximo de resultados
            skip: Número de documentos a pular (paginação)

        Returns:
            Lista de opiniões do domínio especificado
        """
        if not self._query_api:
            logger.warning("LedgerQueryAPI not initialized, cannot query by domain")
            return []

        return self._query_api.get_opinions_by_domain(domain, limit, skip)

    def get_opinions_by_feature(
        self,
        feature_name: str,
        min_score: Optional[float] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Busca opiniões por fator de raciocínio (reasoning_factor).

        Args:
            feature_name: Nome do fator (ex: 'security_analysis', 'architecture_patterns')
            min_score: Score mínimo do fator (opcional)
            limit: Número máximo de resultados

        Returns:
            Lista de opiniões que contêm o fator especificado
        """
        if not self._query_api:
            logger.warning("LedgerQueryAPI not initialized, cannot query by feature")
            return []

        return self._query_api.get_opinions_by_feature(feature_name, min_score, limit)

    def apply_retention_policies(self) -> Dict[str, int]:
        """
        Aplica políticas de retenção de dados (mascaramento e deleção).

        Executa todas as políticas configuradas, incluindo:
        - Mascaramento de campos sensíveis após período de retenção
        - Deleção automática de documentos após 365 dias

        Returns:
            Estatísticas de aplicação: {
                'documents_processed': int,
                'documents_masked': int,
                'documents_deleted': int,
                'errors': int
            }

        Example:
            >>> stats = ledger_client.apply_retention_policies()
            >>> print(f"Processados: {stats['documents_processed']}")
            >>> print(f"Mascarados: {stats['documents_masked']}")
            >>> print(f"Deletados: {stats['documents_deleted']}")
        """
        try:
            from .ledger.retention_manager import RetentionManager

            # Construir config para RetentionManager
            retention_config = {
                'mongodb_uri': self.config.mongodb_uri,
                'mongodb_database': self.config.mongodb_database,
                'retention_policies': []  # Usar políticas padrão
            }

            # Inicializar RetentionManager com componentes de compliance
            retention_manager = RetentionManager(
                config=retention_config,
                pii_detector=getattr(self, 'pii_detector', None),
                field_encryptor=self.field_encryptor
            )

            # Aplicar políticas
            stats = retention_manager.apply_retention_policies()

            # Audit log da operação de retenção
            if self.audit_logger:
                try:
                    self.audit_logger.log_retention_action(
                        action='apply_retention_policies',
                        documents_processed=stats['documents_processed'],
                        documents_masked=stats['documents_masked'],
                        documents_deleted=stats['documents_deleted'],
                        errors=stats['errors']
                    )
                except Exception as e:
                    logger.error("Failed to audit log retention action", error=str(e))

            # Registrar métricas se disponível
            if self._metrics:
                if hasattr(self._metrics, 'observe_retention_execution'):
                    self._metrics.observe_retention_execution(
                        masked=stats['documents_masked'],
                        deleted=stats['documents_deleted']
                    )

            logger.info(
                "Retention policies applied",
                **stats
            )

            return stats

        except Exception as e:
            logger.error("Failed to apply retention policies", error=str(e))
            return {
                'documents_processed': 0,
                'documents_masked': 0,
                'documents_deleted': 0,
                'errors': 1
            }

    def get_retention_status(self) -> Dict[str, Any]:
        """
        Retorna status atual das políticas de retenção.

        Returns:
            Status de retenção: {
                'total_documents': int,
                'masked_documents': int,
                'masked_percentage': float,
                'policies': {
                    'policy_name': {
                        'retention_days': int,
                        'expired_documents': int,
                        'action': str  # 'mask' ou 'delete'
                    }
                }
            }

        Example:
            >>> status = ledger_client.get_retention_status()
            >>> print(f"Total: {status['total_documents']}")
            >>> print(f"Mascarados: {status['masked_documents']} ({status['masked_percentage']:.1f}%)")
        """
        try:
            from .ledger.retention_manager import RetentionManager

            # Construir config para RetentionManager
            retention_config = {
                'mongodb_uri': self.config.mongodb_uri,
                'mongodb_database': self.config.mongodb_database,
                'retention_policies': []  # Usar políticas padrão
            }

            # Inicializar RetentionManager
            retention_manager = RetentionManager(
                config=retention_config,
                pii_detector=getattr(self, 'pii_detector', None),
                field_encryptor=self.field_encryptor
            )

            # Obter status
            status = retention_manager.get_retention_status()

            logger.debug("Retention status retrieved", **status)

            return status

        except Exception as e:
            logger.error("Failed to get retention status", error=str(e))
            return {}

    def close(self):
        """Fecha conexão com MongoDB."""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Ledger client connection closed")
