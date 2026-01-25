"""
Cliente HTTP assíncrono para OPA REST API.

Otimizações de performance:
- Connection pooling com reutilização de conexões
- Cache LRU com TTL para decisões
- Batch evaluation paralelo com semaphore
- Prefetching de políticas comuns
- Circuit breaker para prevenir cascading failures
"""

import asyncio
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import aiohttp
from cachetools import TTLCache
import structlog
import time

from ..observability.metrics import get_metrics

logger = structlog.get_logger(__name__)


class OPAConnectionError(Exception):
    """Falha de conexão com OPA."""
    pass


class OPAPolicyNotFoundError(Exception):
    """Política não encontrada (404)."""
    pass


class OPAEvaluationError(Exception):
    """Erro na avaliação da política."""
    pass


class OPAClient:
    """Cliente HTTP assíncrono para OPA REST API."""

    def __init__(self, config, metrics=None, mongodb_client=None):
        """
        Inicializar cliente OPA.

        Args:
            config: OrchestratorSettings com configurações OPA
            metrics: OrchestratorMetrics para métricas Prometheus (opcional)
            mongodb_client: MongoDBClient para audit logging (opcional)
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.base_url = f"http://{config.opa_host}:{config.opa_port}"
        self.timeout = aiohttp.ClientTimeout(total=config.opa_timeout_seconds)
        self.session: Optional[aiohttp.ClientSession] = None
        self.metrics = metrics or get_metrics()

        # Cache LRU de decisões com TTL
        self._cache = TTLCache(
            maxsize=1000,
            ttl=config.opa_cache_ttl_seconds
        )

        # Estatísticas de cache para métricas
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Semaphore para limitar concorrência de batch evaluation
        self._batch_semaphore = asyncio.Semaphore(
            getattr(config, 'opa_max_concurrent_evaluations', 20)
        )

        # Circuit Breaker para prevenir cascading failures (implementação assíncrona manual)
        self._circuit_breaker_enabled = config.opa_circuit_breaker_enabled
        self._circuit_state: str = 'closed'  # closed, half_open, open
        self._circuit_failure_count: int = 0
        self._circuit_opened_at: Optional[datetime] = None
        self._last_failure_time: Optional[datetime] = None

        # Políticas comuns para prefetch
        self._common_policies: List[str] = [
            'neuralhive/orchestrator/resource_limits',
            'neuralhive/orchestrator/sla_enforcement',
            'neuralhive/orchestrator/feature_flags',
            'neuralhive/orchestrator/security_constraints'
        ]

        logger.info(
            "OPAClient inicializado",
            base_url=self.base_url,
            timeout_seconds=config.opa_timeout_seconds,
            cache_ttl_seconds=config.opa_cache_ttl_seconds,
            circuit_breaker_enabled=self._circuit_breaker_enabled,
            circuit_breaker_failure_threshold=config.opa_circuit_breaker_failure_threshold,
            circuit_breaker_reset_timeout=config.opa_circuit_breaker_reset_timeout
        )

    def _set_circuit_state(self, new_state: str):
        """Atualiza estado do circuit breaker e registra métricas."""
        previous_state = getattr(self, "_circuit_state", "closed")
        if new_state == previous_state:
            return

        self._circuit_state = new_state
        self.metrics.record_opa_circuit_breaker_state(new_state, self._circuit_failure_count)
        self.metrics.record_opa_circuit_breaker_transition(previous_state, new_state)

        logger.warning(
            "Circuit breaker OPA mudou de estado",
            old_state=previous_state,
            new_state=new_state,
            failure_count=self._circuit_failure_count,
            timestamp=datetime.now().isoformat()
        )

        if new_state == 'open':
            self._last_failure_time = datetime.now()
            self._circuit_opened_at = self._last_failure_time
        elif new_state == 'closed':
            self._circuit_opened_at = None

    async def initialize(self):
        """Criar sessão aiohttp com connection pooling."""
        connector = aiohttp.TCPConnector(
            limit=100,  # Max connections
            limit_per_host=30,
            ttl_dns_cache=300
        )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            raise_for_status=False
        )

        logger.info("OPA session criada")

    def _update_cache_hit_ratio(self):
        """Atualizar métrica de cache hit ratio."""
        total = self._cache_hits + self._cache_misses
        if total > 0:
            ratio = self._cache_hits / total
            self.metrics.opa_cache_hit_ratio.set(ratio)

    async def close(self):
        """Fechar sessão aiohttp gracefully."""
        if self.session:
            await self.session.close()
            logger.info("OPA session fechada")

    def _get_cache_key(self, policy_path: str, input_data: dict) -> str:
        """Gerar chave de cache para decisão."""
        # Usar hash do input_data como parte da chave
        import hashlib
        import json

        input_str = json.dumps(input_data, sort_keys=True)
        input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]

        return f"{policy_path}:{input_hash}"

    def _determine_decision(self, result: dict) -> str:
        """
        Determina decisão (allow/deny) baseado no resultado da avaliação.

        Args:
            result: Resultado da avaliação OPA

        Returns:
            'allow' ou 'deny'
        """
        decision = 'allow'
        result_data = result.get('result', {})
        if isinstance(result_data, dict):
            # Se há violações, decisão é deny
            violations = result_data.get('violations', [])
            if violations:
                decision = 'deny'
            # Verificar campo 'allow' explícito
            if 'allow' in result_data:
                decision = 'allow' if result_data['allow'] else 'deny'
        return decision

    async def _evaluate_policy_internal(
        self,
        policy_path: str,
        input_data: dict,
        cache_key: str
    ) -> dict:
        """
        Lógica interna de avaliação de política (usada pelo circuit breaker).

        Args:
            policy_path: Path da política
            input_data: Dados de entrada
            cache_key: Chave de cache pré-calculada

        Returns:
            Resultado da avaliação

        Raises:
            OPAConnectionError: Falha de conexão
            OPAPolicyNotFoundError: Política não encontrada
            OPAEvaluationError: Erro na avaliação
        """
        url = f"{self.base_url}/v1/data/{policy_path}"

        # Usar configuração de retry em vez de valor hardcoded
        max_attempts = self.config.opa_retry_attempts
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            start_time = datetime.now()

            try:
                async with self.session.post(url, json=input_data) as response:
                    duration_ms = (datetime.now() - start_time).total_seconds() * 1000

                    if response.status == 404:
                        logger.error(
                            "Política não encontrada",
                            policy_path=policy_path,
                            status=response.status
                        )
                        raise OPAPolicyNotFoundError(f"Política não encontrada: {policy_path}")

                    if response.status >= 500:
                        # Invalidar cache em caso de erro 5xx
                        if cache_key in self._cache:
                            del self._cache[cache_key]

                        error_text = await response.text()
                        logger.error(
                            "Erro do servidor OPA",
                            policy_path=policy_path,
                            status=response.status,
                            error=error_text,
                            attempt=attempt,
                            max_attempts=max_attempts
                        )
                        raise OPAEvaluationError(f"Erro do servidor OPA: {error_text}")

                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            "Erro na avaliação OPA",
                            policy_path=policy_path,
                            status=response.status,
                            error=error_text
                        )
                        raise OPAEvaluationError(f"Erro na avaliação: {error_text}")

                    result = await response.json()

                    # Adicionar policy_path ao resultado para preservar nas decisões agregadas
                    result['policy_path'] = policy_path

                    logger.info(
                        "Política avaliada",
                        policy_path=policy_path,
                        input_size=len(str(input_data)),
                        duration_ms=duration_ms,
                        attempt=attempt
                    )

                    # Cachear resultado
                    self._cache[cache_key] = result

                    return result

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e

                if isinstance(e, asyncio.TimeoutError):
                    logger.warning(
                        "Timeout na avaliação OPA",
                        policy_path=policy_path,
                        timeout_seconds=self.config.opa_timeout_seconds,
                        attempt=attempt,
                        max_attempts=max_attempts
                    )
                else:
                    logger.warning(
                        "Erro de conexão com OPA",
                        policy_path=policy_path,
                        error=str(e),
                        attempt=attempt,
                        max_attempts=max_attempts
                    )

                # Se não é a última tentativa, aguardar antes de retry
                if attempt < max_attempts:
                    # Backoff exponencial: 0.5s, 1s, 2s, 4s
                    wait_time = min(0.5 * (2 ** (attempt - 1)), 4.0)
                    logger.info(
                        "Aguardando antes de retry",
                        wait_seconds=wait_time,
                        next_attempt=attempt + 1
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Última tentativa falhou
                    if isinstance(e, asyncio.TimeoutError):
                        logger.error(
                            "Timeout final na avaliação OPA após retries",
                            policy_path=policy_path,
                            timeout_seconds=self.config.opa_timeout_seconds,
                            total_attempts=max_attempts
                        )
                        raise OPAConnectionError(f"Timeout após {self.config.opa_timeout_seconds}s e {max_attempts} tentativas")
                    else:
                        logger.error(
                            "Erro de conexão final com OPA após retries",
                            policy_path=policy_path,
                            error=str(e),
                            total_attempts=max_attempts,
                            exc_info=True
                        )
                        raise OPAConnectionError(f"Erro de conexão: {str(e)} após {max_attempts} tentativas")

        # Fallback caso loop termine sem retornar (não deveria acontecer)
        if last_exception:
            raise OPAConnectionError(f"Falha após {max_attempts} tentativas: {str(last_exception)}")

    async def evaluate_policy(
        self,
        policy_path: str,
        input_data: dict
    ) -> dict:
        """
        Avaliar política via POST /v1/data/{policy_path} com circuit breaker.

        Args:
            policy_path: Path da política (ex: 'neuralhive/orchestrator/resource_limits')
            input_data: Dados de entrada para a política

        Returns:
            Resultado da avaliação da política

        Raises:
            OPAConnectionError: Falha de conexão ou circuit breaker aberto
            OPAPolicyNotFoundError: Política não encontrada
            OPAEvaluationError: Erro na avaliação
        """
        if not self.session:
            raise OPAConnectionError("OPA session não inicializada")

        # Verificar cache
        cache_key = self._get_cache_key(policy_path, input_data)
        if cache_key in self._cache:
            self._cache_hits += 1
            self._update_cache_hit_ratio()
            logger.debug("Cache hit", policy_path=policy_path)
            self.metrics.record_opa_cache_hit()

            # Auditar decisão do cache (Comment 1: decisões em cache também devem ser auditadas)
            cached_result = self._cache[cache_key]
            decision = self._determine_decision(cached_result)
            await self._log_authorization_decision(
                policy_path=policy_path,
                input_data=input_data,
                result=cached_result,
                decision=decision
            )

            return cached_result

        # Cache miss - registrar métrica
        self._cache_misses += 1
        self._update_cache_hit_ratio()
        self.metrics.record_opa_cache_miss()

        # Verificar estado do circuit breaker
        if self._circuit_breaker_enabled:
            # Se aberto e dentro do reset timeout, falhar imediatamente
            if self._circuit_state == 'open' and self._circuit_opened_at:
                elapsed = (datetime.now() - self._circuit_opened_at).total_seconds()
                if elapsed < self.config.opa_circuit_breaker_reset_timeout:
                    self.metrics.record_opa_error('circuit_breaker_open')
                    raise OPAConnectionError(
                        f"Circuit breaker aberto após {self.config.opa_circuit_breaker_failure_threshold} falhas"
                    )
                # Após reset_timeout, permitir tentativa em half-open
                self._set_circuit_state('half_open')

        try:
            result = await self._evaluate_policy_internal(policy_path, input_data, cache_key)

            # Sucesso: fechar circuit breaker e resetar contadores
            if self._circuit_breaker_enabled:
                self._circuit_failure_count = 0
                if self._circuit_state != 'closed':
                    self._set_circuit_state('closed')

            # Determinar decisão (allow/deny) baseado no resultado
            decision = self._determine_decision(result)

            # Registrar decisão no audit log (fail-open)
            await self._log_authorization_decision(
                policy_path=policy_path,
                input_data=input_data,
                result=result,
                decision=decision
            )

            return result

        except OPAPolicyNotFoundError:
            # 404 não deve afetar circuit breaker
            raise

        except (OPAConnectionError, OPAEvaluationError) as e:
            if self._circuit_breaker_enabled:
                if self._circuit_state == 'half_open':
                    # Uma falha em half-open reabre imediatamente
                    self._circuit_failure_count = self.config.opa_circuit_breaker_failure_threshold
                else:
                    self._circuit_failure_count += 1

                self._last_failure_time = datetime.now()

                if self._circuit_failure_count >= self.config.opa_circuit_breaker_failure_threshold:
                    self._set_circuit_state('open')

            raise

    async def _log_authorization_decision(
        self,
        policy_path: str,
        input_data: dict,
        result: dict,
        decision: str
    ):
        """
        Registra decisão de autorização no audit log.

        Fail-open: erros não propagam para não bloquear avaliações.

        Args:
            policy_path: Path da política avaliada
            input_data: Dados de entrada
            result: Resultado da avaliação
            decision: 'allow' ou 'deny'
        """
        if not self.mongodb_client:
            return  # Audit logging desabilitado

        try:
            # Extrair contexto da decisão
            resource = input_data.get('input', {}).get('resource', {})
            context = input_data.get('input', {}).get('context', {})
            security = input_data.get('input', {}).get('security', {})

            # Extrair violações (se houver)
            violations = []
            result_data = result.get('result', {})
            if isinstance(result_data, dict):
                violations = result_data.get('violations', [])

            audit_entry = {
                'timestamp': datetime.now().isoformat(),
                'user_id': context.get('user_id'),
                'tenant_id': resource.get('tenant_id') or security.get('tenant_id'),
                'resource': {
                    'type': resource.get('type'),
                    'id': resource.get('id'),
                    'task_type': resource.get('task_type')
                },
                'action': context.get('action', 'evaluate'),
                'decision': decision,
                'policy_path': policy_path,
                'violations': violations,
                'context': {
                    'workflow_id': context.get('workflow_id'),
                    'plan_id': context.get('plan_id'),
                    'correlation_id': context.get('correlation_id')
                }
            }

            # Persistir de forma assíncrona (fail-open)
            await self.mongodb_client.save_authorization_audit(audit_entry)

            # Registrar métrica com tenant_id para filtros no dashboard
            tenant_id = audit_entry.get('tenant_id') or 'unknown'
            self.metrics.record_authorization_audit_logged(
                policy_path=policy_path,
                decision=decision,
                tenant_id=tenant_id
            )

        except Exception as e:
            logger.warning(
                'authorization_audit_logging_failed',
                policy_path=policy_path,
                error=str(e)
            )
            # Fail-open: não propagar erro

    async def _evaluate_with_semaphore(
        self,
        policy_path: str,
        input_data: dict
    ) -> dict:
        """
        Avaliar política com controle de concorrência via semaphore.

        Args:
            policy_path: Path da política
            input_data: Dados de entrada

        Returns:
            Resultado da avaliação
        """
        async with self._batch_semaphore:
            start_time = time.perf_counter()
            try:
                result = await self.evaluate_policy(policy_path, input_data)
                duration = time.perf_counter() - start_time
                self.metrics.record_opa_policy_decision_duration(policy_path, duration)
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                self.metrics.record_opa_policy_decision_duration(policy_path, duration)
                raise

    async def batch_evaluate(
        self,
        evaluations: List[Tuple[str, dict]]
    ) -> List[dict]:
        """
        Avaliar múltiplas políticas em paralelo com controle de concorrência.

        Otimizações:
        - Semaphore para limitar requisições concorrentes
        - Métricas de duração por policy_path
        - Separação de cache hits vs misses

        Args:
            evaluations: Lista de tuplas (policy_path, input_data)

        Returns:
            Lista de resultados na mesma ordem
        """
        if not evaluations:
            return []

        # Registrar tamanho do batch
        batch_size = len(evaluations)
        self.metrics.record_opa_batch_evaluation(batch_size)

        start_time = time.perf_counter()

        # Separar cache hits de misses para otimizar
        cache_results: Dict[int, dict] = {}
        pending_evaluations: List[Tuple[int, str, dict]] = []

        for idx, (policy_path, input_data) in enumerate(evaluations):
            cache_key = self._get_cache_key(policy_path, input_data)
            if cache_key in self._cache:
                self._cache_hits += 1
                self.metrics.record_opa_cache_hit()
                cache_results[idx] = self._cache[cache_key]
            else:
                pending_evaluations.append((idx, policy_path, input_data))

        # Avaliar apenas os que não estão em cache (com semaphore)
        if pending_evaluations:
            tasks = [
                self._evaluate_with_semaphore(policy_path, input_data)
                for _, policy_path, input_data in pending_evaluations
            ]

            pending_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, (idx, policy_path, _) in enumerate(pending_evaluations):
                result = pending_results[i]
                if isinstance(result, Exception):
                    logger.error(
                        "Erro em batch evaluation",
                        policy_path=policy_path,
                        error=str(result)
                    )
                    cache_results[idx] = {
                        'error': str(result),
                        'policy_path': policy_path
                    }
                else:
                    cache_results[idx] = result

        # Reconstruir lista na ordem original
        processed_results = [cache_results[i] for i in range(len(evaluations))]

        self._update_cache_hit_ratio()

        total_duration = time.perf_counter() - start_time
        logger.info(
            "Batch evaluation concluído",
            batch_size=batch_size,
            cache_hits=len(evaluations) - len(pending_evaluations),
            cache_misses=len(pending_evaluations),
            total_duration_ms=total_duration * 1000
        )

        return processed_results

    async def health_check(self) -> bool:
        """
        Verificar saúde do OPA via GET /health.

        Returns:
            True se OPA está saudável, False caso contrário
        """
        if not self.session:
            return False

        try:
            url = f"{self.base_url}/health"
            async with self.session.get(url) as response:
                is_healthy = response.status == 200

                logger.info(
                    "OPA health check",
                    healthy=is_healthy,
                    status=response.status
                )

                return is_healthy

        except Exception as e:
            logger.error(
                "Erro em health check OPA",
                error=str(e)
            )
            return False

    def get_circuit_breaker_state(self) -> dict:
        """
        Obter estado atual do circuit breaker.

        Returns:
            Dicionário com informações do circuit breaker:
            - enabled: bool
            - state: str (closed/open/half_open)
            - failure_count: int
            - last_failure_time: Optional[str] (ISO format)
        """
        if not self._circuit_breaker_enabled:
            return {
                'enabled': False,
                'state': 'disabled',
                'failure_count': 0,
                'last_failure_time': None
            }

        return {
            'enabled': True,
            'state': self._circuit_state,
            'failure_count': self._circuit_failure_count,
            'last_failure_time': self._last_failure_time.isoformat() if self._last_failure_time else None
        }

    def get_cache_stats(self) -> dict:
        """
        Obter estatísticas do cache.

        Returns:
            Dicionário com estatísticas de cache:
            - size: número atual de entradas
            - maxsize: tamanho máximo do cache
            - hits: total de cache hits
            - misses: total de cache misses
            - hit_ratio: proporção de hits
        """
        total = self._cache_hits + self._cache_misses
        hit_ratio = self._cache_hits / total if total > 0 else 0.0

        return {
            'size': len(self._cache),
            'maxsize': self._cache.maxsize,
            'ttl_seconds': self._cache.ttl,
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'hit_ratio': hit_ratio
        }

    def invalidate_cache(self, policy_path: Optional[str] = None):
        """
        Invalidar cache de decisões.

        Args:
            policy_path: Se fornecido, invalida apenas entradas para esta política.
                        Se None, invalida todo o cache.
        """
        if policy_path is None:
            self._cache.clear()
            logger.info("Cache OPA completamente invalidado")
        else:
            # Remover entradas que começam com o policy_path
            keys_to_remove = [
                key for key in self._cache.keys()
                if key.startswith(policy_path)
            ]
            for key in keys_to_remove:
                del self._cache[key]
            logger.info(
                "Cache OPA invalidado para política",
                policy_path=policy_path,
                entries_removed=len(keys_to_remove)
            )

    async def warm_cache(self, warmup_inputs: Optional[List[Tuple[str, dict]]] = None):
        """
        Pré-aquecer cache com avaliações comuns.

        Args:
            warmup_inputs: Lista opcional de (policy_path, input_data) para pré-carregar.
                          Se None, usa configuração padrão de policies.
        """
        if not self.session:
            logger.warning("Sessão não inicializada, pulando warm-up de cache")
            return

        if warmup_inputs:
            policies_to_warm = warmup_inputs
        else:
            # Usar uma avaliação básica para cada política comum
            default_input = {'input': {'resource': {}, 'context': {}}}
            policies_to_warm = [
                (policy, default_input) for policy in self._common_policies
            ]

        logger.info(
            "Iniciando warm-up de cache OPA",
            num_policies=len(policies_to_warm)
        )

        results = await self.batch_evaluate(policies_to_warm)

        success_count = sum(1 for r in results if 'error' not in r)
        logger.info(
            "Warm-up de cache OPA concluído",
            total=len(policies_to_warm),
            success=success_count,
            failed=len(policies_to_warm) - success_count
        )

    # =========================================================================
    # Policy Versioning Support
    # =========================================================================

    async def get_policy_revision(self, policy_path: str) -> Optional[str]:
        """
        Obter revisão atual de uma política via GET /v1/policies/{policy_path}.

        Args:
            policy_path: Path da política (ex: 'neuralhive/orchestrator/resource_limits')

        Returns:
            String de revisão ou None se não disponível
        """
        if not self.session:
            return None

        try:
            url = f"{self.base_url}/v1/policies/{policy_path}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # OPA retorna 'id' e opcionalmente 'raw' com o conteúdo
                    return data.get('id')
                elif response.status == 404:
                    logger.warning(
                        "Política não encontrada para revisão",
                        policy_path=policy_path
                    )
                    return None
                else:
                    logger.error(
                        "Erro ao obter revisão de política",
                        policy_path=policy_path,
                        status=response.status
                    )
                    return None
        except Exception as e:
            logger.error(
                "Exceção ao obter revisão de política",
                policy_path=policy_path,
                error=str(e)
            )
            return None

    async def list_policies(self) -> List[dict]:
        """
        Listar todas as políticas carregadas via GET /v1/policies.

        Returns:
            Lista de políticas com seus metadados
        """
        if not self.session:
            return []

        try:
            url = f"{self.base_url}/v1/policies"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    policies = data.get('result', [])
                    logger.info(
                        "Políticas listadas",
                        count=len(policies)
                    )
                    return policies
                else:
                    logger.error(
                        "Erro ao listar políticas",
                        status=response.status
                    )
                    return []
        except Exception as e:
            logger.error(
                "Exceção ao listar políticas",
                error=str(e)
            )
            return []

    async def get_policy_metadata(self, policy_path: str) -> Optional[dict]:
        """
        Obter metadados completos de uma política.

        Args:
            policy_path: Path da política

        Returns:
            Dicionário com metadados ou None se não disponível
        """
        if not self.session:
            return None

        try:
            url = f"{self.base_url}/v1/policies/{policy_path}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'id': data.get('id'),
                        'path': policy_path,
                        'raw': data.get('raw'),  # Conteúdo Rego
                        'ast': data.get('ast'),  # AST compilado
                    }
                elif response.status == 404:
                    return None
                else:
                    logger.error(
                        "Erro ao obter metadados de política",
                        policy_path=policy_path,
                        status=response.status
                    )
                    return None
        except Exception as e:
            logger.error(
                "Exceção ao obter metadados de política",
                policy_path=policy_path,
                error=str(e)
            )
            return None

    async def upload_policy(
        self,
        policy_path: str,
        rego_content: str,
        invalidate_cache: bool = True
    ) -> bool:
        """
        Fazer upload/atualização de uma política via PUT /v1/policies/{policy_path}.

        NOTA: Esta operação requer permissões de administração no OPA.

        Args:
            policy_path: Path da política
            rego_content: Conteúdo Rego da política
            invalidate_cache: Se True, invalida cache para esta política

        Returns:
            True se upload bem-sucedido, False caso contrário
        """
        if not self.session:
            return False

        try:
            url = f"{self.base_url}/v1/policies/{policy_path}"
            headers = {'Content-Type': 'text/plain'}

            async with self.session.put(url, data=rego_content, headers=headers) as response:
                if response.status in (200, 201):
                    logger.info(
                        "Política atualizada com sucesso",
                        policy_path=policy_path,
                        status=response.status
                    )

                    if invalidate_cache:
                        self.invalidate_cache(policy_path)

                    return True
                else:
                    error_text = await response.text()
                    logger.error(
                        "Erro ao fazer upload de política",
                        policy_path=policy_path,
                        status=response.status,
                        error=error_text
                    )
                    return False
        except Exception as e:
            logger.error(
                "Exceção ao fazer upload de política",
                policy_path=policy_path,
                error=str(e)
            )
            return False

    async def delete_policy(
        self,
        policy_path: str,
        invalidate_cache: bool = True
    ) -> bool:
        """
        Deletar uma política via DELETE /v1/policies/{policy_path}.

        NOTA: Esta operação requer permissões de administração no OPA.

        Args:
            policy_path: Path da política
            invalidate_cache: Se True, invalida cache para esta política

        Returns:
            True se deleção bem-sucedida, False caso contrário
        """
        if not self.session:
            return False

        try:
            url = f"{self.base_url}/v1/policies/{policy_path}"

            async with self.session.delete(url) as response:
                if response.status in (200, 204):
                    logger.info(
                        "Política deletada com sucesso",
                        policy_path=policy_path
                    )

                    if invalidate_cache:
                        self.invalidate_cache(policy_path)

                    return True
                elif response.status == 404:
                    logger.warning(
                        "Política não encontrada para deleção",
                        policy_path=policy_path
                    )
                    return False
                else:
                    error_text = await response.text()
                    logger.error(
                        "Erro ao deletar política",
                        policy_path=policy_path,
                        status=response.status,
                        error=error_text
                    )
                    return False
        except Exception as e:
            logger.error(
                "Exceção ao deletar política",
                policy_path=policy_path,
                error=str(e)
            )
            return False

    async def check_policy_versions(self) -> dict:
        """
        Verificar versões de todas as políticas configuradas.

        Returns:
            Dicionário mapeando policy_path -> revision/status
        """
        versions = {}

        for policy_path in self._common_policies:
            metadata = await self.get_policy_metadata(policy_path)
            if metadata:
                versions[policy_path] = {
                    'status': 'loaded',
                    'id': metadata.get('id'),
                    'has_content': bool(metadata.get('raw'))
                }
            else:
                versions[policy_path] = {
                    'status': 'not_found',
                    'id': None,
                    'has_content': False
                }

        logger.info(
            "Verificação de versões de políticas concluída",
            total=len(self._common_policies),
            loaded=sum(1 for v in versions.values() if v['status'] == 'loaded'),
            not_found=sum(1 for v in versions.values() if v['status'] == 'not_found')
        )

        return versions
