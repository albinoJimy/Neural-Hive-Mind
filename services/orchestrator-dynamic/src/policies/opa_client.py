"""
Cliente HTTP assíncrono para OPA REST API.
"""

import asyncio
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import aiohttp
from cachetools import TTLCache
import structlog

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

    def __init__(self, config):
        """
        Inicializar cliente OPA.

        Args:
            config: OrchestratorSettings com configurações OPA
        """
        self.config = config
        self.base_url = f"http://{config.opa_host}:{config.opa_port}"
        self.timeout = aiohttp.ClientTimeout(total=config.opa_timeout_seconds)
        self.session: Optional[aiohttp.ClientSession] = None
        self.metrics = get_metrics()

        # Cache LRU de decisões com TTL
        self._cache = TTLCache(
            maxsize=1000,
            ttl=config.opa_cache_ttl_seconds
        )

        # Circuit Breaker para prevenir cascading failures (implementação assíncrona manual)
        self._circuit_breaker_enabled = config.opa_circuit_breaker_enabled
        self._circuit_state: str = 'closed'  # closed, half_open, open
        self._circuit_failure_count: int = 0
        self._circuit_opened_at: Optional[datetime] = None
        self._last_failure_time: Optional[datetime] = None

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
            logger.debug("Cache hit", policy_path=policy_path)
            self.metrics.record_opa_cache_hit()
            return self._cache[cache_key]

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

    async def batch_evaluate(
        self,
        evaluations: List[Tuple[str, dict]]
    ) -> List[dict]:
        """
        Avaliar múltiplas políticas em paralelo.

        Args:
            evaluations: Lista de tuplas (policy_path, input_data)

        Returns:
            Lista de resultados na mesma ordem
        """
        tasks = [
            self.evaluate_policy(policy_path, input_data)
            for policy_path, input_data in evaluations
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Converter exceções em dicts de erro
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                policy_path = evaluations[i][0]
                logger.error(
                    "Erro em batch evaluation",
                    policy_path=policy_path,
                    error=str(result)
                )
                processed_results.append({
                    'error': str(result),
                    'policy_path': policy_path
                })
            else:
                processed_results.append(result)

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
