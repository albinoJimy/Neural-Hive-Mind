"""
Cliente MongoDB para persistência de Cognitive Plans e Execution Tickets.

NOTA: Motor 3.7+ requer parameter names em snake_case:
- maxPoolSize -> max_pool_size
- serverSelectionTimeoutMS -> server_selection_timeout_ms
"""
import hashlib
import json
from datetime import datetime
from typing import Optional, Dict, Any

from pymongo.errors import DuplicateKeyError, PyMongoError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_exception
import structlog

from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError
from src.observability.metrics import get_metrics

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB para ledger de planos cognitivos e tickets de execução."""

    # Índices esperados por coleção (usado em validate_indexes)
    EXPECTED_INDEXES = {
        'execution_tickets': [
            'ticket_id_1',
            'plan_id_1',
            'intent_id_1',
            'decision_id_1',
            'status_1',
            'plan_id_1_created_at_-1'
        ],
        'cognitive_ledger': [
            'plan_id_1',
            'intent_id_1',
            'created_at_1',
            'status_1_created_at_-1'
        ],
        'workflows': [
            'workflow_id_1',
            'plan_id_1',
            'status_1'
        ],
        'validation_audit': [
            'plan_id_1',
            'workflow_id_1',
            'timestamp_1',
            'plan_id_1_timestamp_-1'
        ],
        'workflow_results': [
            'workflow_id_1',
            'plan_id_1',
            'status_1',
            'consolidated_at_1',
            'status_1_consolidated_at_-1'
        ]
    }

    def __init__(self, config, uri_override: Optional[str] = None):
        """
        Inicializa o cliente MongoDB.

        Args:
            config: Configurações da aplicação
            uri_override: URI MongoDB alternativa (para integração Vault)

        Raises:
            ValueError: Se mongodb_collection_tickets não estiver configurado
        """
        # Validar configuração crítica antes de prosseguir
        collection_tickets = getattr(config, 'mongodb_collection_tickets', None)
        if not collection_tickets:
            raise ValueError(
                'mongodb_collection_tickets não configurado. '
                'Configure MONGODB_COLLECTION_TICKETS no ambiente ou Helm values.'
            )

        self.config = config
        self.uri_override = uri_override
        self.client = None
        self.db = None
        self.cognitive_ledger = None
        self.execution_tickets = None
        self.workflows = None
        self.validation_audit = None
        self.workflow_results = None
        self.incidents = None
        self.telemetry_buffer = None
        self.execution_ticket_breaker = None
        self.validation_audit_breaker = None
        self.workflow_results_breaker = None
        self.circuit_breaker_enabled = getattr(config, "CIRCUIT_BREAKER_ENABLED", False)

        # Log configuração carregada
        logger.info(
            'mongodb_client_initialized',
            collection_tickets=collection_tickets,
            collection_workflows=getattr(config, 'mongodb_collection_workflows', 'workflows'),
            fail_open_tickets=getattr(config, 'MONGODB_FAIL_OPEN_EXECUTION_TICKETS', False),
            circuit_breaker_enabled=self.circuit_breaker_enabled
        )

    async def initialize(self):
        """Inicializar cliente MongoDB e criar índices."""
        from motor.motor_asyncio import AsyncIOMotorClient

        mongodb_uri = self.uri_override if self.uri_override else self.config.mongodb_uri

        # Motor/PyMongo usam camelCase para parameter names
        self.client = AsyncIOMotorClient(
            mongodb_uri,
            maxPoolSize=self.config.MONGODB_MAX_POOL_SIZE,
            minPoolSize=self.config.MONGODB_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=5000,
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.config.mongodb_database]
        self.cognitive_ledger = self.db['cognitive_ledger']
        self.execution_tickets = self.db[self.config.mongodb_collection_tickets]
        self.workflows = self.db[self.config.mongodb_collection_workflows]
        self.validation_audit = self.db['validation_audit']
        self.workflow_results = self.db['workflow_results']
        self.incidents = self.db['incidents']
        self.telemetry_buffer = self.db['telemetry_buffer']

        if self.circuit_breaker_enabled:
            self.execution_ticket_breaker = MonitoredCircuitBreaker(
                service_name=self.config.service_name,
                circuit_name="execution_ticket_persistence",
                fail_max=self.config.CIRCUIT_BREAKER_FAIL_MAX,
                timeout_duration=self.config.CIRCUIT_BREAKER_TIMEOUT,
                recovery_timeout=getattr(
                    self.config,
                    "CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
                    self.config.CIRCUIT_BREAKER_TIMEOUT,
                ),
                expected_exception=Exception,
            )
            self.validation_audit_breaker = MonitoredCircuitBreaker(
                service_name=self.config.service_name,
                circuit_name="validation_audit_persistence",
                fail_max=self.config.CIRCUIT_BREAKER_FAIL_MAX,
                timeout_duration=self.config.CIRCUIT_BREAKER_TIMEOUT,
                recovery_timeout=getattr(
                    self.config,
                    "CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
                    self.config.CIRCUIT_BREAKER_TIMEOUT,
                ),
                expected_exception=Exception,
            )
            self.workflow_results_breaker = MonitoredCircuitBreaker(
                service_name=self.config.service_name,
                circuit_name="workflow_result_persistence",
                fail_max=self.config.CIRCUIT_BREAKER_FAIL_MAX,
                timeout_duration=self.config.CIRCUIT_BREAKER_TIMEOUT,
                recovery_timeout=getattr(
                    self.config,
                    "CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
                    self.config.CIRCUIT_BREAKER_TIMEOUT,
                ),
                expected_exception=Exception,
            )

        # Garantir que coleções críticas existam antes de criar índices
        critical_collections = [
            self.config.mongodb_collection_tickets,  # execution_tickets
            'cognitive_ledger',
            'validation_audit',
            'workflow_results',
            'incidents',
            'telemetry_buffer',
        ]
        for collection_name in critical_collections:
            await self.ensure_collection_exists(collection_name)

        # Criar índices
        await self._create_indexes()

        # Validar índices criados
        await self.validate_indexes()

        # Verificar conectividade
        await self.client.admin.command('ping')
        logger.info(
            'mongodb_client_ready',
            database=self.config.mongodb_database,
            collections_initialized=len(critical_collections)
        )

    async def _create_indexes(self):
        """Criar índices necessários para performance e integridade."""
        # Índices para cognitive_ledger
        await self.cognitive_ledger.create_index('plan_id', unique=True)
        await self.cognitive_ledger.create_index('intent_id')
        await self.cognitive_ledger.create_index('created_at')
        await self.cognitive_ledger.create_index([('status', 1), ('created_at', -1)])

        # Índices para execution_tickets
        await self.execution_tickets.create_index('ticket_id', unique=True)
        await self.execution_tickets.create_index('plan_id')
        await self.execution_tickets.create_index('intent_id')
        await self.execution_tickets.create_index('decision_id')
        await self.execution_tickets.create_index('status')
        await self.execution_tickets.create_index([('plan_id', 1), ('created_at', -1)])

        # Índices para workflows
        await self.workflows.create_index('workflow_id', unique=True)
        await self.workflows.create_index('plan_id')
        await self.workflows.create_index('status')

        await self._create_indexes_extended()

    async def ensure_collection_exists(self, collection_name: str) -> bool:
        """
        Garante que uma coleção existe no MongoDB, criando-a se necessário.

        Args:
            collection_name: Nome da coleção a verificar/criar

        Returns:
            True se coleção existe ou foi criada com sucesso

        Raises:
            PyMongoError: Se falhar ao criar coleção
        """
        try:
            existing_collections = await self.db.list_collection_names()

            if collection_name in existing_collections:
                logger.debug(
                    'collection_already_exists',
                    collection=collection_name
                )
                return True

            # Criar coleção explicitamente
            await self.db.create_collection(collection_name)

            logger.info(
                'collection_created',
                collection=collection_name
            )
            return True

        except Exception as e:
            logger.error(
                'collection_creation_failed',
                collection=collection_name,
                error=str(e)
            )
            raise

    async def validate_indexes(self) -> None:
        """
        Validar que índices críticos foram criados corretamente.

        Não bloqueia startup, apenas loga warnings para índices faltantes.
        """
        metrics = get_metrics()

        for collection_name, expected_indexes in self.EXPECTED_INDEXES.items():
            try:
                collection = self.db[collection_name]
                indexes = await collection.list_indexes().to_list(length=None)
                existing_names = {idx['name'] for idx in indexes}

                # Remover índice _id_ da comparação (sempre existe)
                existing_names.discard('_id_')

                missing = set(expected_indexes) - existing_names
                if missing:
                    logger.warning(
                        'indexes_missing',
                        collection=collection_name,
                        missing_indexes=list(missing),
                        existing_indexes=list(existing_names)
                    )
                    metrics.record_mongodb_index_validation(collection_name, 'missing', len(missing))
                else:
                    logger.info(
                        'indexes_validated',
                        collection=collection_name,
                        count=len(expected_indexes)
                    )
                    metrics.record_mongodb_index_validation(collection_name, 'validated', len(expected_indexes))

            except Exception as e:
                logger.error(
                    'index_validation_failed',
                    collection=collection_name,
                    error=str(e)
                )
                metrics.record_mongodb_index_validation(collection_name, 'error', 0)

    async def _create_indexes_extended(self):
        """Criar índices adicionais para coleções de auditoria e telemetria."""
        await self.validation_audit.create_index('plan_id')
        await self.validation_audit.create_index('workflow_id')
        await self.validation_audit.create_index('timestamp')
        await self.validation_audit.create_index([('plan_id', 1), ('timestamp', -1)])

        await self.workflow_results.create_index('workflow_id', unique=True)
        await self.workflow_results.create_index('plan_id')
        await self.workflow_results.create_index('status')
        await self.workflow_results.create_index('consolidated_at')
        await self.workflow_results.create_index([('status', 1), ('consolidated_at', -1)])

        await self.incidents.create_index('workflow_id')
        await self.incidents.create_index('type')
        await self.incidents.create_index('severity')
        await self.incidents.create_index('timestamp')
        await self.incidents.create_index([('severity', 1), ('timestamp', -1)])

        await self.telemetry_buffer.create_index('workflow_id')
        await self.telemetry_buffer.create_index('buffered_at')
        await self.telemetry_buffer.create_index('retry_count')
        await self.telemetry_buffer.create_index([('retry_count', 1), ('buffered_at', 1)])

    async def get_cognitive_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca um Cognitive Plan no ledger e retorna os dados do plano.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Dados do plano (plan_data) com plan_id e intent_id incluídos,
            ou None se não encontrado
        """
        document = await self.cognitive_ledger.find_one({'plan_id': plan_id})

        if not document:
            return None

        # Extrair plan_data e adicionar campos de identificação
        plan_data = document.get('plan_data', {})
        plan_data['plan_id'] = document.get('plan_id')
        plan_data['intent_id'] = document.get('intent_id')

        return plan_data

    async def save_execution_ticket(self, ticket: Dict[str, Any]):
        """
        Persiste um Execution Ticket no MongoDB para auditoria.

        Erros críticos (configuração, schema) propagam exceção.
        Erros transitórios usam circuit breaker com retry automático.

        Args:
            ticket: Ticket de execução a ser salvo

        Raises:
            CircuitBreakerError: Se circuit breaker estiver aberto
            RuntimeError: Para erros de persistência quando fail-open está desabilitado
            PyMongoError: Para erros de persistência não recuperáveis
        """
        metrics = get_metrics()
        start_time = datetime.now()

        document = ticket.copy()
        document['_id'] = ticket['ticket_id']
        ticket_id = ticket['ticket_id']
        plan_id = ticket.get('plan_id', 'unknown')

        # Função interna com retry para erros transitórios
        # Exclui DuplicateKeyError do retry para permitir fallback para replace_one
        retry_decorator = self._get_retry_decorator(exclude_duplicate_key=True)

        @retry_decorator
        async def _persist_with_retry():
            await self._execute_with_breaker(
                self.execution_ticket_breaker,
                self.execution_tickets.insert_one,
                document
            )

        try:
            await _persist_with_retry()

            duration = (datetime.now() - start_time).total_seconds()
            metrics.record_mongodb_persistence_duration(
                'execution_tickets',
                'insert',
                duration
            )

            logger.info(
                'execution_ticket_saved',
                ticket_id=ticket_id,
                plan_id=plan_id,
                duration_ms=duration * 1000
            )

        except DuplicateKeyError:
            # Ticket já existe, atualizar
            try:
                await self._execute_with_breaker(
                    self.execution_ticket_breaker,
                    self.execution_tickets.replace_one,
                    {'ticket_id': ticket_id},
                    document
                )

                duration = (datetime.now() - start_time).total_seconds()
                metrics.record_mongodb_persistence_duration(
                    'execution_tickets',
                    'update',
                    duration
                )

                logger.info(
                    'execution_ticket_updated',
                    ticket_id=ticket_id,
                    plan_id=plan_id
                )
            except CircuitBreakerError:
                metrics.record_mongodb_persistence_error(
                    'execution_tickets',
                    'update',
                    'CircuitBreakerError'
                )
                logger.error(
                    'execution_ticket_update_circuit_open',
                    ticket_id=ticket_id,
                    plan_id=plan_id
                )
                raise
            except Exception as e:
                metrics.record_mongodb_persistence_error(
                    'execution_tickets',
                    'update',
                    type(e).__name__
                )
                logger.error(
                    'execution_ticket_update_failed',
                    ticket_id=ticket_id,
                    plan_id=plan_id,
                    error=str(e)
                )
                raise

        except CircuitBreakerError:
            metrics.record_mongodb_persistence_error(
                'execution_tickets',
                'insert',
                'CircuitBreakerError'
            )
            logger.error(
                'execution_ticket_circuit_open',
                ticket_id=ticket_id,
                plan_id=plan_id
            )
            raise

        except Exception as e:
            error_type = type(e).__name__
            metrics.record_mongodb_persistence_error(
                'execution_tickets',
                'insert',
                error_type
            )

            # Verificar política de fail-open
            fail_open = getattr(self.config, 'MONGODB_FAIL_OPEN_EXECUTION_TICKETS', False)

            logger.error(
                'execution_ticket_save_failed',
                ticket_id=ticket_id,
                plan_id=plan_id,
                error=str(e),
                error_type=error_type,
                fail_open_enabled=fail_open
            )

            if fail_open:
                # Fail-open: registrar métrica e continuar sem persistência
                logger.warning(
                    'execution_ticket_persist_fail_open_activated',
                    ticket_id=ticket_id,
                    plan_id=plan_id
                )
                metrics.record_mongodb_persistence_fail_open('execution_tickets')
            else:
                # Fail-closed: propagar erro para retry do Temporal
                raise RuntimeError(
                    f'Falha crítica na persistência do ticket {ticket_id}: {str(e)}'
                )

    async def update_ticket_status(self, ticket_id: str, status: str, **kwargs):
        """
        Atualiza o status de um ticket.

        Args:
            ticket_id: ID do ticket
            status: Novo status
            **kwargs: Campos adicionais a atualizar
        """
        update_fields = {'status': status, **kwargs}
        await self.execution_tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': update_fields}
        )

    async def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca um ticket por ID.

        Args:
            ticket_id: ID do ticket

        Returns:
            Documento do ticket ou None se não encontrado
        """
        return await self.execution_tickets.find_one({'ticket_id': ticket_id})

    def _get_retry_decorator(self, exclude_duplicate_key: bool = False):
        """Retorna decorator de retry configurado conforme settings.

        Args:
            exclude_duplicate_key: Se True, não faz retry em DuplicateKeyError
        """
        if exclude_duplicate_key:
            # Retry em PyMongoError EXCETO DuplicateKeyError
            retry_condition = retry_if_exception(
                lambda e: isinstance(e, PyMongoError) and not isinstance(e, DuplicateKeyError)
            )
        else:
            retry_condition = retry_if_exception_type(PyMongoError)

        return retry(
            stop=stop_after_attempt(self.config.retry_max_attempts),
            wait=wait_exponential(
                multiplier=self.config.retry_backoff_coefficient,
                min=self.config.retry_initial_interval_ms / 1000,
                max=self.config.retry_max_interval_ms / 1000
            ),
            retry=retry_condition
        )

    async def save_validation_audit(self, plan_id: str, validation_result: Dict[str, Any], workflow_id: str) -> None:
        """
        Persiste auditoria de validação de plano cognitivo.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()
        document = {
            'plan_id': plan_id,
            'validation_result': validation_result,
            'workflow_id': workflow_id,
            'timestamp': datetime.now().isoformat(),
            'hash': hashlib.sha256(json.dumps(validation_result, sort_keys=True).encode()).hexdigest()
        }

        @retry_decorator
        async def _persist():
            await self._execute_with_breaker(
                self.validation_audit_breaker,
                self.validation_audit.insert_one,
                document
            )

        try:
            await _persist()
            logger.info(
                'validation_audit_saved',
                plan_id=plan_id,
                workflow_id=workflow_id
            )
        except Exception as e:
            logger.error(
                'validation_audit_save_failed',
                plan_id=plan_id,
                workflow_id=workflow_id,
                error=str(e)
            )
        except CircuitBreakerError:
            logger.warning(
                'validation_audit_circuit_open',
                plan_id=plan_id,
                workflow_id=workflow_id
            )
            raise

    async def save_workflow_result(self, workflow_result: Dict[str, Any]) -> None:
        """
        Persiste resultado consolidado de workflow.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()
        workflow_id = workflow_result.get('workflow_id')
        document = {**workflow_result}
        if workflow_id:
            document['_id'] = workflow_id

        @retry_decorator
        async def _persist():
            await self._execute_with_breaker(
                self.workflow_results_breaker,
                self.workflow_results.replace_one,
                {'_id': document.get('_id')},
                document,
                upsert=True
            )

        try:
            await _persist()
            logger.info(
                'workflow_result_saved',
                workflow_id=workflow_id,
                status=workflow_result.get('status'),
                total_tickets=workflow_result.get('metrics', {}).get('total_tickets')
            )
        except Exception as e:
            logger.error(
                'workflow_result_save_failed',
                workflow_id=workflow_id,
                error=str(e)
            )
        except CircuitBreakerError:
            logger.warning(
                'workflow_result_circuit_open',
                workflow_id=workflow_id
            )
            raise

    async def save_incident(self, incident_event: Dict[str, Any]) -> None:
        """
        Persiste incidente de autocura.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()

        @retry_decorator
        async def _persist():
            await self.incidents.insert_one(incident_event)

        try:
            await _persist()
            logger.warning(
                'incident_saved',
                workflow_id=incident_event.get('workflow_id'),
                incident_type=incident_event.get('type'),
                severity=incident_event.get('severity')
            )
        except Exception as e:
            logger.error(
                'incident_save_failed',
                workflow_id=incident_event.get('workflow_id'),
                error=str(e)
            )

    async def save_telemetry_buffer(self, telemetry_frame: Dict[str, Any]) -> None:
        """
        Persiste frame de telemetria em buffer para retry.

        Fail-open: erros são logados mas não propagados.
        """
        retry_decorator = self._get_retry_decorator()

        @retry_decorator
        async def _persist():
            await self.telemetry_buffer.insert_one(telemetry_frame)

        try:
            await _persist()
            logger.warning(
                'telemetry_buffered',
                workflow_id=telemetry_frame.get('correlation', {}).get('workflow_id'),
                source=telemetry_frame.get('source')
            )
        except Exception as e:
            logger.error(
                'telemetry_buffer_failed',
                workflow_id=telemetry_frame.get('correlation', {}).get('workflow_id'),
                error=str(e)
            )

    async def close(self):
        """Fechar cliente MongoDB."""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')

    async def _execute_with_breaker(self, breaker, func, *args, **kwargs):
        """
        Executa operação MongoDB protegida por circuit breaker (quando habilitado).
        """
        if not self.circuit_breaker_enabled or breaker is None:
            return await func(*args, **kwargs)

        return await breaker.call_async(func, *args, **kwargs)
