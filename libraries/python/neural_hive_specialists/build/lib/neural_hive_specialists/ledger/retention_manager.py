"""
RetentionManager: Gerenciamento de políticas de retenção e compliance.

Implementa políticas de data retention, mascaramento de campos sensíveis,
e conformidade com GDPR/LGPD para o ledger cognitivo.
"""

from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import structlog
import hashlib

logger = structlog.get_logger(__name__)

# Imports para compliance (optional, lazy loaded)
try:
    from ..compliance import PIIDetector, FieldEncryptor
    HAS_COMPLIANCE = True
except ImportError:
    HAS_COMPLIANCE = False
    PIIDetector = None
    FieldEncryptor = None


class RetentionPolicy:
    """Define política de retenção de dados."""

    def __init__(
        self,
        name: str,
        retention_days: int,
        apply_to_recommendations: Optional[List[str]] = None,
        mask_sensitive_fields: bool = True,
        delete_after_retention: bool = False
    ):
        """
        Inicializa política de retenção.

        Args:
            name: Nome da política
            retention_days: Dias de retenção
            apply_to_recommendations: Recomendações aplicáveis (None = todas)
            mask_sensitive_fields: Se deve mascarar campos sensíveis
            delete_after_retention: Se deve deletar após período
        """
        self.name = name
        self.retention_days = retention_days
        self.apply_to_recommendations = apply_to_recommendations
        self.mask_sensitive_fields = mask_sensitive_fields
        self.delete_after_retention = delete_after_retention

    def applies_to(self, document: Dict[str, Any]) -> bool:
        """
        Verifica se política se aplica ao documento.

        Args:
            document: Documento a verificar

        Returns:
            True se política aplicável
        """
        if self.apply_to_recommendations is None:
            return True

        recommendation = document.get('opinion', {}).get('recommendation')
        return recommendation in self.apply_to_recommendations


class RetentionManager:
    """Gerencia políticas de retenção e compliance."""

    # Campos sensíveis que podem conter PII
    SENSITIVE_FIELDS = {
        'correlation_id',
        'trace_id',
        'span_id',
        'intent_id',
        'plan_id'
    }

    def __init__(
        self,
        config: Dict[str, Any],
        pii_detector: Optional['PIIDetector'] = None,
        field_encryptor: Optional['FieldEncryptor'] = None
    ):
        """
        Inicializa gerenciador de retenção.

        Args:
            config: Configuração com mongodb_uri, mongodb_database, retention_policies
            pii_detector: Detector de PII opcional (para mascaramento inteligente)
            field_encryptor: Encriptador de campos opcional (para proteção adicional)
        """
        self.config = config
        self.mongodb_uri = config.get('mongodb_uri')
        self.mongodb_database = config.get('mongodb_database', 'neural_hive')
        self._mongo_client: Optional[MongoClient] = None

        # Componentes de compliance opcionais
        self.pii_detector = pii_detector
        self.field_encryptor = field_encryptor

        # Carregar políticas de retenção
        self.policies = self._load_policies()

        logger.info(
            "RetentionManager initialized",
            policies_count=len(self.policies),
            has_pii_detector=pii_detector is not None,
            has_field_encryptor=field_encryptor is not None
        )

    @property
    def mongo_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                self.mongodb_uri,
                serverSelectionTimeoutMS=5000
            )
        return self._mongo_client

    @property
    def collection(self):
        """Retorna collection de opiniões."""
        db = self.mongo_client[self.mongodb_database]
        return db['cognitive_ledger']

    def _load_policies(self) -> List[RetentionPolicy]:
        """
        Carrega políticas de retenção da configuração.

        Returns:
            Lista de políticas configuradas
        """
        policies_config = self.config.get('retention_policies', [])

        if not policies_config:
            # Políticas padrão GDPR-compliant
            return [
                RetentionPolicy(
                    name='high_risk_extended',
                    retention_days=365,  # 1 ano para alto risco
                    apply_to_recommendations=['reject'],
                    mask_sensitive_fields=True,
                    delete_after_retention=False
                ),
                RetentionPolicy(
                    name='standard_retention',
                    retention_days=90,  # 90 dias padrão
                    apply_to_recommendations=['approve', 'conditional'],
                    mask_sensitive_fields=True,
                    delete_after_retention=False
                ),
                RetentionPolicy(
                    name='review_required_extended',
                    retention_days=180,  # 6 meses para revisão
                    apply_to_recommendations=['review_required'],
                    mask_sensitive_fields=True,
                    delete_after_retention=False
                ),
                RetentionPolicy(
                    name='delete_after_365_days',
                    retention_days=365,  # Deleção automática após 1 ano
                    apply_to_recommendations=None,  # Aplica a todas as recomendações
                    mask_sensitive_fields=False,  # Não mascarar, apenas deletar
                    delete_after_retention=True  # DELEÇÃO ATIVADA
                )
            ]

        # Carregar políticas customizadas
        policies = []
        for policy_config in policies_config:
            policies.append(RetentionPolicy(**policy_config))

        return policies

    def apply_retention_policies(self) -> Dict[str, int]:
        """
        Aplica todas as políticas de retenção configuradas.

        Returns:
            Estatísticas de aplicação (masked, deleted, etc.)
        """
        stats = {
            'documents_processed': 0,
            'documents_masked': 0,
            'documents_deleted': 0,
            'errors': 0
        }

        try:
            for policy in self.policies:
                policy_stats = self._apply_policy(policy)
                stats['documents_processed'] += policy_stats['processed']
                stats['documents_masked'] += policy_stats['masked']
                stats['documents_deleted'] += policy_stats['deleted']
                stats['errors'] += policy_stats['errors']

            logger.info(
                "Retention policies applied",
                **stats
            )

            return stats

        except Exception as e:
            logger.error("Failed to apply retention policies", error=str(e))
            stats['errors'] += 1
            return stats

    def _apply_policy(self, policy: RetentionPolicy) -> Dict[str, int]:
        """
        Aplica política específica de retenção.

        Args:
            policy: Política a aplicar

        Returns:
            Estatísticas de aplicação
        """
        stats = {
            'processed': 0,
            'masked': 0,
            'deleted': 0,
            'errors': 0
        }

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_days)

            # Query documentos que excedem período de retenção
            query: Dict[str, Any] = {'evaluated_at': {'$lt': cutoff_date}}

            if policy.apply_to_recommendations:
                query['opinion.recommendation'] = {'$in': policy.apply_to_recommendations}

            documents = self.collection.find(query)

            for document in documents:
                stats['processed'] += 1

                try:
                    if policy.delete_after_retention:
                        # Deletar documento
                        self.collection.delete_one({'_id': document['_id']})
                        stats['deleted'] += 1
                        logger.debug(
                            "Document deleted by retention policy",
                            opinion_id=document.get('opinion_id'),
                            policy=policy.name
                        )
                    elif policy.mask_sensitive_fields:
                        # Mascarar campos sensíveis
                        self._mask_sensitive_data(document)
                        stats['masked'] += 1

                except Exception as e:
                    logger.error(
                        "Failed to apply policy to document",
                        opinion_id=document.get('opinion_id'),
                        policy=policy.name,
                        error=str(e)
                    )
                    stats['errors'] += 1

            logger.info(
                "Policy applied",
                policy=policy.name,
                **stats
            )

        except PyMongoError as e:
            logger.error(
                "Failed to apply retention policy",
                policy=policy.name,
                error=str(e)
            )
            stats['errors'] += 1

        return stats

    def _mask_sensitive_data(self, document: Dict[str, Any]) -> bool:
        """
        Mascara campos sensíveis em um documento usando PIIDetector quando disponível.

        Args:
            document: Documento a mascarar

        Returns:
            True se mascaramento bem-sucedido
        """
        try:
            masked_fields = []

            # Se PIIDetector disponível, detectar PII em campos de texto
            if self.pii_detector:
                text_fields = ['opinion.reasoning_summary']
                for field_path in text_fields:
                    value = self._get_nested_value(document, field_path)
                    if value and isinstance(value, str):
                        try:
                            anonymized_text, pii_metadata = self.pii_detector.anonymize_text(value)
                            if pii_metadata:
                                self._set_nested_value(document, field_path, anonymized_text)
                                masked_fields.append(field_path)
                                logger.debug(
                                    "PII detected and anonymized in field",
                                    field=field_path,
                                    entities_count=len(pii_metadata)
                                )
                        except Exception as e:
                            logger.warning(
                                "Failed to anonymize field with PIIDetector",
                                field=field_path,
                                error=str(e)
                            )

            # Mascarar campos sensíveis de primeiro nível (IDs)
            for field in self.SENSITIVE_FIELDS:
                if field in document and document[field]:
                    original_value = document[field]
                    masked_value = self._mask_value(original_value)
                    document[field] = masked_value
                    masked_fields.append(field)

            # Se FieldEncryptor disponível, criptografar campos adicionalmente
            if self.field_encryptor:
                fields_to_encrypt = ['correlation_id', 'trace_id', 'span_id', 'intent_id']
                for field in fields_to_encrypt:
                    if field in document and document[field]:
                        try:
                            # Se já foi mascarado, criptografar o valor mascarado
                            encrypted_value = self.field_encryptor.encrypt_field(document[field])
                            document[field] = encrypted_value
                            if field not in masked_fields:
                                masked_fields.append(f"{field}_encrypted")
                            logger.debug(
                                "Field encrypted",
                                field=field
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to encrypt field",
                                field=field,
                                error=str(e)
                            )

            # Adicionar metadados de mascaramento
            document['masked_fields'] = masked_fields
            document['masked_at'] = datetime.utcnow()
            document['retention_policy'] = 'gdpr_compliant_masking'
            document['compliance_enhanced'] = self.pii_detector is not None or self.field_encryptor is not None

            # Atualizar documento no MongoDB
            self.collection.update_one(
                {'_id': document['_id']},
                {'$set': {
                    **{field: self._get_nested_value(document, field) or document.get(field)
                       for field in masked_fields if field in document or '.' in field},
                    'masked_fields': masked_fields,
                    'masked_at': document['masked_at'],
                    'retention_policy': document['retention_policy'],
                    'compliance_enhanced': document['compliance_enhanced']
                }}
            )

            logger.debug(
                "Document masked",
                opinion_id=document.get('opinion_id'),
                masked_fields=masked_fields,
                compliance_enhanced=document['compliance_enhanced']
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to mask document",
                opinion_id=document.get('opinion_id'),
                error=str(e)
            )
            return False

    def _mask_value(self, value: str) -> str:
        """
        Mascara valor individual (hash SHA-256).

        Args:
            value: Valor a mascarar

        Returns:
            Valor mascarado (primeiros 8 chars do hash)
        """
        if not value:
            return 'MASKED'

        hash_value = hashlib.sha256(value.encode('utf-8')).hexdigest()
        return f"MASKED_{hash_value[:8]}"

    def delete_by_correlation_id(
        self,
        correlation_id: str,
        reason: str = "user_request"
    ) -> int:
        """
        Deleta todos os documentos de uma correlation_id (direito ao esquecimento).

        Args:
            correlation_id: ID de correlação
            reason: Motivo da deleção (para auditoria)

        Returns:
            Número de documentos deletados
        """
        try:
            # Registrar deleção para auditoria
            deleted_count = self._audit_deletion(correlation_id, reason)

            # Deletar documentos
            result = self.collection.delete_many({'correlation_id': correlation_id})

            logger.warning(
                "Documents deleted by correlation_id (GDPR right to erasure)",
                correlation_id=correlation_id,
                deleted_count=result.deleted_count,
                reason=reason
            )

            return result.deleted_count

        except PyMongoError as e:
            logger.error(
                "Failed to delete by correlation_id",
                correlation_id=correlation_id,
                error=str(e)
            )
            return 0

    def _audit_deletion(self, correlation_id: str, reason: str) -> int:
        """
        Registra deleção para auditoria (antes de deletar).

        Args:
            correlation_id: ID de correlação
            reason: Motivo da deleção

        Returns:
            Número de documentos a serem deletados
        """
        try:
            # Contar documentos que serão deletados
            count = self.collection.count_documents({'correlation_id': correlation_id})

            # Registrar em collection de auditoria
            db = self.mongo_client[self.mongodb_database]
            audit_collection = db['deletion_audit']

            audit_record = {
                'correlation_id': correlation_id,
                'deleted_at': datetime.utcnow(),
                'reason': reason,
                'documents_count': count
            }

            audit_collection.insert_one(audit_record)

            logger.info(
                "Deletion audited",
                correlation_id=correlation_id,
                count=count,
                reason=reason
            )

            return count

        except Exception as e:
            logger.error(
                "Failed to audit deletion",
                correlation_id=correlation_id,
                error=str(e)
            )
            return 0

    def export_user_data(
        self,
        correlation_id: str,
        include_masked: bool = False
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Exporta dados de um usuário (GDPR data portability).

        Args:
            correlation_id: ID de correlação
            include_masked: Se deve incluir documentos mascarados

        Returns:
            Lista de documentos ou None se erro
        """
        try:
            query: Dict[str, Any] = {'correlation_id': correlation_id}

            if not include_masked:
                query['masked_fields'] = {'$exists': False}

            documents = list(self.collection.find(query))

            # Remover _id do MongoDB
            for doc in documents:
                doc.pop('_id', None)

            logger.info(
                "User data exported",
                correlation_id=correlation_id,
                documents_count=len(documents)
            )

            return documents

        except PyMongoError as e:
            logger.error(
                "Failed to export user data",
                correlation_id=correlation_id,
                error=str(e)
            )
            return None

    def get_retention_status(self) -> Dict[str, Any]:
        """
        Retorna status atual das políticas de retenção.

        Returns:
            Estatísticas de retenção
        """
        try:
            total_documents = self.collection.count_documents({})
            masked_documents = self.collection.count_documents({'masked_fields': {'$exists': True}})

            # Contar documentos por política
            policy_stats = {}
            for policy in self.policies:
                cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_days)
                query: Dict[str, Any] = {'evaluated_at': {'$lt': cutoff_date}}

                if policy.apply_to_recommendations:
                    query['opinion.recommendation'] = {'$in': policy.apply_to_recommendations}

                expired_count = self.collection.count_documents(query)

                policy_stats[policy.name] = {
                    'retention_days': policy.retention_days,
                    'expired_documents': expired_count,
                    'action': 'delete' if policy.delete_after_retention else 'mask'
                }

            status = {
                'total_documents': total_documents,
                'masked_documents': masked_documents,
                'masked_percentage': (masked_documents / total_documents * 100) if total_documents > 0 else 0.0,
                'policies': policy_stats
            }

            logger.info("Retention status retrieved", **status)

            return status

        except PyMongoError as e:
            logger.error("Failed to get retention status", error=str(e))
            return {}

    @staticmethod
    def _get_nested_value(data: Dict, path: str) -> Any:
        """
        Obtém valor de path aninhado (ex: 'opinion.reasoning_summary').

        Args:
            data: Dicionário fonte
            path: Path separado por pontos

        Returns:
            Valor encontrado ou None
        """
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    @staticmethod
    def _set_nested_value(data: Dict, path: str, value: Any) -> None:
        """
        Define valor de path aninhado.

        Args:
            data: Dicionário destino
            path: Path separado por pontos
            value: Valor a definir
        """
        keys = path.split('.')
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
