"""
Audit logger para registrar eventos de compliance em MongoDB.
"""
import structlog
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

logger = structlog.get_logger(__name__)


class AuditLogger:
    """
    Registra eventos de compliance em collection MongoDB.

    Eventos auditados:
    - config_change: mudanças de configuração
    - data_access: acessos a dados sensíveis (queries no ledger)
    - retention_action: ações de retenção (mascaramento, deleção)
    - pii_detection: detecções de PII
    - encryption_operation: operações de criptografia

    Estrutura do documento:
        {
            'audit_id': str (UUID),
            'timestamp': datetime (UTC),
            'specialist_type': str,
            'event_type': str,
            'event_data': dict,
            'actor': str (quem executou),
            'severity': str (info, warning, critical),
            'correlation_id': str (opcional),
            'metadata': dict
        }
    """

    def __init__(self, config, specialist_type: str):
        """
        Inicializa AuditLogger.

        Args:
            config: SpecialistConfig
            specialist_type: Tipo do especialista
        """
        self.config = config
        self.specialist_type = specialist_type
        self.enabled = config.enable_audit_logging
        self._mongo_client = None
        self._collection = None

        if not self.enabled:
            logger.info("AuditLogger desabilitado por configuração")
            return

        try:
            # Lazy initialization do MongoDB client
            self._initialize_mongo()

            logger.info(
                "AuditLogger inicializado com sucesso",
                collection=config.audit_log_collection,
                retention_days=config.audit_log_retention_days
            )

        except Exception as e:
            logger.error(
                "Falha ao inicializar AuditLogger - audit logging desabilitado",
                error=str(e)
            )
            self.enabled = False

    def _initialize_mongo(self):
        """Inicializa conexão MongoDB e cria índices."""
        self._mongo_client = MongoClient(self.config.mongodb_uri)
        db = self._mongo_client[self.config.mongodb_database]
        self._collection = db[self.config.audit_log_collection]

        # Criar índices otimizados
        self._collection.create_index([('timestamp', DESCENDING)])
        self._collection.create_index([('event_type', ASCENDING), ('timestamp', DESCENDING)])
        self._collection.create_index([('specialist_type', ASCENDING), ('timestamp', DESCENDING)])
        self._collection.create_index([('correlation_id', ASCENDING)])

        # TTL index para retenção automática
        ttl_seconds = self.config.audit_log_retention_days * 24 * 3600
        self._collection.create_index(
            [('timestamp', ASCENDING)],
            expireAfterSeconds=ttl_seconds
        )

        logger.info("Índices de audit log criados/verificados")

    def log_config_change(
        self,
        changed_by: str,
        old_config: Dict,
        new_config: Dict,
        reason: str
    ):
        """
        Registra mudança de configuração.

        Args:
            changed_by: Quem fez a mudança (user, service account)
            old_config: Configuração anterior
            new_config: Nova configuração
            reason: Motivo da mudança
        """
        if not self.enabled:
            return

        # Calcular diff
        changes = self._calculate_config_diff(old_config, new_config)

        event_data = {
            'old_config': old_config,
            'new_config': new_config,
            'changes': changes,
            'reason': reason
        }

        self._log_event(
            event_type='config_change',
            event_data=event_data,
            actor=changed_by,
            severity='warning'
        )

    def log_data_access(
        self,
        accessed_by: str,
        resource_type: str,
        resource_id: str,
        action: str,
        metadata: Optional[Dict] = None
    ):
        """
        Registra acesso a dados sensíveis.

        Args:
            accessed_by: Quem acessou (specialist:type, user:id)
            resource_type: Tipo de recurso (opinion, plan)
            resource_id: ID do recurso
            action: Ação executada (create, read, update, delete)
            metadata: Contexto adicional
        """
        if not self.enabled:
            return

        event_data = {
            'resource_type': resource_type,
            'resource_id': resource_id,
            'action': action
        }

        if metadata:
            event_data.update(metadata)

        self._log_event(
            event_type='data_access',
            event_data=event_data,
            actor=accessed_by,
            severity='info',
            correlation_id=metadata.get('correlation_id') if metadata else None
        )

    def log_retention_action(
        self,
        action_type: str,
        affected_documents: int,
        policy_name: str,
        metadata: Optional[Dict] = None
    ):
        """
        Registra ação de política de retenção.

        Args:
            action_type: Tipo de ação (apply_policies, delete, mask)
            affected_documents: Número de documentos afetados
            policy_name: Nome da política aplicada
            metadata: Estatísticas adicionais
        """
        if not self.enabled:
            return

        event_data = {
            'action_type': action_type,
            'affected_documents': affected_documents,
            'policy_name': policy_name
        }

        if metadata:
            event_data.update(metadata)

        severity = 'warning' if affected_documents > 0 else 'info'

        self._log_event(
            event_type='retention_action',
            event_data=event_data,
            actor='system:retention_manager',
            severity=severity
        )

    def log_pii_detection(
        self,
        plan_id: str,
        entities_detected: List[Dict],
        anonymization_applied: bool
    ):
        """
        Registra detecção de PII.

        Args:
            plan_id: ID do plano analisado
            entities_detected: Lista de entidades PII detectadas
            anonymization_applied: Se anonimização foi aplicada
        """
        if not self.enabled:
            return

        # Sanitizar entidades (não logar dados sensíveis)
        sanitized_entities = []
        for entity in entities_detected:
            sanitized_entities.append({
                'entity_type': entity.get('entity_type'),
                'score': entity.get('score'),
                'field': entity.get('field')
            })

        event_data = {
            'plan_id': plan_id,
            'entities_count': len(entities_detected),
            'entities': sanitized_entities,
            'anonymization_applied': anonymization_applied
        }

        severity = 'warning' if len(entities_detected) > 0 else 'info'

        self._log_event(
            event_type='pii_detection',
            event_data=event_data,
            actor=f'system:pii_detector',
            severity=severity
        )

    def log_encryption_operation(
        self,
        operation: str,
        field_name: str,
        success: bool,
        error: Optional[str] = None
    ):
        """
        Registra operação de criptografia.

        Args:
            operation: Tipo de operação (encrypt, decrypt)
            field_name: Nome do campo
            success: Se operação foi bem-sucedida
            error: Mensagem de erro (se falhou)
        """
        if not self.enabled:
            return

        event_data = {
            'operation': operation,
            'field_name': field_name,
            'success': success
        }

        if error:
            event_data['error'] = error

        severity = 'info' if success else 'warning'

        self._log_event(
            event_type='encryption_operation',
            event_data=event_data,
            actor=f'system:field_encryptor',
            severity=severity
        )

    def query_audit_logs(
        self,
        filters: Optional[Dict] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Consulta audit logs com filtros.

        Args:
            filters: Filtros de query (event_type, specialist_type, start_date, end_date)
            limit: Número máximo de resultados

        Returns:
            Lista de documentos de audit
        """
        if not self.enabled or not self._collection:
            return []

        try:
            query = {}

            if filters:
                if 'event_type' in filters:
                    query['event_type'] = filters['event_type']

                if 'specialist_type' in filters:
                    query['specialist_type'] = filters['specialist_type']

                if 'start_date' in filters or 'end_date' in filters:
                    query['timestamp'] = {}
                    if 'start_date' in filters:
                        query['timestamp']['$gte'] = filters['start_date']
                    if 'end_date' in filters:
                        query['timestamp']['$lte'] = filters['end_date']

                if 'actor' in filters:
                    query['actor'] = filters['actor']

            results = list(
                self._collection.find(query)
                .sort('timestamp', DESCENDING)
                .limit(limit)
            )

            return results

        except PyMongoError as e:
            logger.error("Erro ao consultar audit logs", error=str(e))
            return []

    def get_audit_summary(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Retorna resumo de auditoria para período.

        Args:
            start_date: Data inicial
            end_date: Data final

        Returns:
            Estatísticas de auditoria
        """
        if not self.enabled or not self._collection:
            return {}

        try:
            pipeline = [
                {
                    '$match': {
                        'timestamp': {'$gte': start_date, '$lte': end_date}
                    }
                },
                {
                    '$group': {
                        '_id': '$event_type',
                        'count': {'$sum': 1}
                    }
                }
            ]

            results = list(self._collection.aggregate(pipeline))

            summary = {
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'events_by_type': {r['_id']: r['count'] for r in results},
                'total_events': sum(r['count'] for r in results)
            }

            return summary

        except PyMongoError as e:
            logger.error("Erro ao gerar resumo de auditoria", error=str(e))
            return {}

    def _log_event(
        self,
        event_type: str,
        event_data: Dict,
        actor: str,
        severity: str = 'info',
        correlation_id: Optional[str] = None
    ):
        """
        Registra evento de audit no MongoDB.

        Args:
            event_type: Tipo de evento
            event_data: Dados do evento
            actor: Quem executou
            severity: Nível de severidade
            correlation_id: ID de correlação
        """
        if not self.enabled or not self._collection:
            return

        try:
            document = {
                'audit_id': str(uuid.uuid4()),
                'timestamp': datetime.utcnow(),
                'specialist_type': self.specialist_type,
                'event_type': event_type,
                'event_data': event_data,
                'actor': actor,
                'severity': severity,
                'metadata': {}
            }

            if correlation_id:
                document['correlation_id'] = correlation_id

            self._collection.insert_one(document)

            logger.debug(
                "Evento de audit registrado",
                event_type=event_type,
                severity=severity,
                audit_id=document['audit_id']
            )

        except PyMongoError as e:
            # Não bloquear fluxo principal se audit falhar
            logger.error(
                "Falha ao registrar evento de audit",
                event_type=event_type,
                error=str(e)
            )

    @staticmethod
    def _calculate_config_diff(old: Dict, new: Dict) -> List[Dict]:
        """
        Calcula diferenças entre configurações.

        Returns:
            Lista de mudanças: [{'field': ..., 'old_value': ..., 'new_value': ...}]
        """
        changes = []

        all_keys = set(old.keys()) | set(new.keys())

        for key in all_keys:
            old_value = old.get(key)
            new_value = new.get(key)

            if old_value != new_value:
                # Sanitizar valores sensíveis
                if 'secret' in key.lower() or 'password' in key.lower() or 'key' in key.lower():
                    old_value = '***'
                    new_value = '***'

                changes.append({
                    'field': key,
                    'old_value': str(old_value),
                    'new_value': str(new_value)
                })

        return changes
