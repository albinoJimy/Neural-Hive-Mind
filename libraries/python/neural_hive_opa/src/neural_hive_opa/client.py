"""
Cliente OPA (Open Policy Agent) para Neural Hive Mind.

Implementação unificada com:
- Connection pooling (aiohttp)
- Cache LRU com TTL
- Circuit breaker manual
- Batch evaluation
- Métricas Prometheus
- Retry com tenacity
"""
import asyncio
from datetime import datetime
from typing import Any

import aiohttp
import structlog
from cachetools import TTLCache
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from neural_hive_opa.config import OPAConfig
from neural_hive_opa.exceptions import (
    OPACircuitBreakerOpenError,
    OPAConnectionError,
    OPAEvaluationError,
    OPAPolicyNotFoundError,
)
from neural_hive_opa.metrics import OPAMetrics
from neural_hive_opa.utils import (
    _build_opa_url,
    _generate_cache_key,
    _is_success_status,
    _sanitize_input_data,
)

logger = structlog.get_logger(__name__)


class OPAClient:
    """
    Cliente OPA com cache, circuit breaker e métricas.

    Exemplo:
        config = OPAConfig(opa_url="http://opa:8181")
        client = OPAClient(config)
        await client.initialize()
        result = await client.evaluate("policy/allow", {"user": "alice"})
        await client.close()
    """

    def __init__(
        self,
        config: OPAConfig,
        metrics: OPAMetrics | None = None,
    ) -> None:
        """
        Inicializa cliente OPA.

        Args:
            config: Configuração OPA
            metrics: Instância de métricas (opcional)
        """
        self.config = config
        self.session: aiohttp.ClientSession | None = None

        # Cache LRU com TTL - usa getattr para compatibilidade com mocks
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=getattr(config, "opa_cache_max_size", 1000),
            ttl=config.opa_cache_ttl_seconds,
        )

        # Circuit breaker state
        self._circuit_state: str = "closed"  # closed, open, half_open
        self._failure_count: int = 0
        self._last_failure_time: datetime | None = None
        self._circuit_lock = asyncio.Lock()

        # Semaphore para batch evaluation
        self._semaphore = asyncio.Semaphore(getattr(config, "opa_max_concurrent_evaluations", 20))

        # Métricas - usa getattr para compatibilidade
        if metrics is None and getattr(config, "opa_enable_metrics", True):
            self.metrics = OPAMetrics(subsystem="neural_hive")
        else:
            self.metrics = metrics

        # Logger
        self.logger = logger.bind(component="opa_client")

    async def initialize(self) -> None:
        """
        Inicializa cliente e conexão HTTP.

        Deve ser chamado antes de usar o cliente.
        """
        if self.session is not None:
            self.logger.warning("Session already initialized")
            return

        connector = aiohttp.TCPConnector(
            limit=getattr(self.config, "opa_connection_pool_size", 100),
            keepalive_timeout=30,
        )

        timeout = aiohttp.ClientTimeout(total=self.config.opa_timeout_seconds)

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )

        self.logger.info(
            "OPA client initialized",
            opa_url=self.config.opa_url,
            cache_ttl=self.config.opa_cache_ttl_seconds,
            circuit_breaker_enabled=getattr(self.config, "opa_circuit_breaker_enabled", True),
        )

    async def close(self) -> None:
        """Fecha sessão HTTP e libera recursos."""
        if self.session is not None:
            await self.session.close()
            self.session = None
            self.logger.info("OPA client closed")

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão OPA.

        Returns:
            True se OPA está saudável
        """
        try:
            return await self._call_opa_health()
        except Exception as e:
            self.logger.error("Health check failed", error=str(e))
            return False

    async def evaluate(
        self,
        policy_path: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Avalia política OPA com cache e circuit breaker.

        Args:
            policy_path: Caminho da política (ex: neuralhive/allow)
            input_data: Dados de entrada para avaliação

        Returns:
            Resultado da avaliação (dict com 'allow' e outros campos)

        Raises:
            OPACircuitBreakerOpenError: Se circuit breaker está aberto
            OPAConnectionError: Se houver erro de conexão
            OPAEvaluationError: Se avaliação falhar
        """
        # Verificar circuit breaker
        if getattr(self.config, "opa_circuit_breaker_enabled", True):
            await self._check_circuit_breaker()

        # Sanitizar input
        sanitized_input = _sanitize_input_data(input_data)

        # Verificar cache
        cache_key = self._get_cache_key(policy_path, sanitized_input)
        cached_result = self._cache.get(cache_key)

        if cached_result is not None:
            self.logger.debug("Cache hit", policy=policy_path, cache_key=cache_key[:8])
            if self.metrics:
                self.metrics.record_cache_hit()
            return cached_result

        if self.metrics:
            self.metrics.record_cache_miss()

        # Executar avaliação
        result = await self._call_opa_with_retry(policy_path, sanitized_input)

        # Cachear resultado
        self._cache[cache_key] = result

        return result

    async def evaluate_batch(
        self,
        requests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Avalia múltiplas políticas em lote com controle de concorrência.

        Args:
            requests: Lista de requisições, cada uma com 'policy' e 'input'

        Returns:
            Lista de resultados na mesma ordem das requisições
        """
        if self.metrics:
            self.metrics.record_batch_evaluation(len(requests))

        async def _evaluate_single(req: dict[str, Any]) -> dict[str, Any]:
            policy = req.get("policy", req.get("policy_path", ""))
            input_data = req.get("input", req.get("input_data", {}))
            return await self.evaluate(policy, input_data)

        tasks = [_evaluate_single(req) for req in requests]

        # Executar com semaphore para limitar concorrência
        results = []
        for task in tasks:
            async with self._semaphore:
                try:
                    result = await task
                    results.append(result)
                except Exception as e:
                    self.logger.error("Batch evaluation failed", error=str(e))
                    results.append({"allow": False, "error": str(e)})

        return results

    async def _check_circuit_breaker(self) -> None:
        """
        Verifica estado do circuit breaker.

        Raises:
            OPACircuitBreakerOpenError: Se circuit breaker está aberto
        """
        async with self._circuit_lock:
            now = datetime.now()

            # Se circuit breaker está open, verificar timeout de reset
            if self._circuit_state == "open":
                # Se não temos last_failure_time, considera circuit breaker aberto
                if self._last_failure_time is None:
                    raise OPACircuitBreakerOpenError("Circuit breaker is open, blocking requests")

                elapsed = (now - self._last_failure_time).total_seconds()
                reset_timeout = getattr(
                    self.config, "opa_circuit_breaker_reset_timeout_seconds", 60
                )
                if elapsed >= reset_timeout:
                    # Tentar half_open
                    self._circuit_state = "half_open"
                    self.logger.info("Circuit breaker entering half_open state")
                    if self.metrics:
                        self.metrics.set_circuit_breaker_state(False)
                else:
                    raise OPACircuitBreakerOpenError("Circuit breaker is open, blocking requests")

    async def _call_opa_with_retry(
        self,
        policy_path: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Chama OPA com retry e circuit breaker.

        Args:
            policy_path: Caminho da política
            input_data: Dados de entrada

        Returns:
            Resultado da avaliação

        Raises:
            OPAEvaluationError: Se todas as tentativas falharem
        """
        try:
            return await self._call_opa_with_retry_impl(policy_path, input_data)
        except Exception as e:
            # Registrar falha no circuit breaker
            if getattr(self.config, "opa_circuit_breaker_enabled", True):
                await self._record_failure()

            if isinstance(e, (OPAConnectionError, OPAEvaluationError)):
                raise
            raise OPAEvaluationError(f"Evaluation failed: {e}", policy=policy_path)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=2.0),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def _call_opa_with_retry_impl(
        self,
        policy_path: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Implementação interna com decorator tenacity.

        Args:
            policy_path: Caminho da política
            input_data: Dados de entrada

        Returns:
            Resultado da avaliação
        """
        result = await self._call_opa(policy_path, input_data)

        # Registrar sucesso no circuit breaker
        if getattr(self.config, "opa_circuit_breaker_enabled", True):
            await self._record_success()

        return result

    async def _call_opa(
        self,
        policy_path: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Faz chamada HTTP ao OPA.

        Args:
            policy_path: Caminho da política
            input_data: Dados de entrada

        Returns:
            Resultado da avaliação

        Raises:
            OPAConnectionError: Se houver erro de conexão
            OPAPolicyNotFoundError: Se política não existir (404)
            OPAEvaluationError: Se avaliação falhar
        """
        if self.session is None:
            raise OPAConnectionError("Client not initialized. Call initialize() first.")

        url = _build_opa_url(self.config.opa_url, policy_path)

        try:
            async with self.session.post(
                url,
                json={"input": input_data},
                headers={"Content-Type": "application/json"},
            ) as response:
                status = response.status

                if status == 404:
                    raise OPAPolicyNotFoundError(policy_path, status)

                if not _is_success_status(status):
                    error_text = await response.text()
                    raise OPAEvaluationError(
                        f"OPA returned error status {status}: {error_text}",
                        policy=policy_path,
                    )

                data = await response.json()

                # Extrair resultado
                if isinstance(data, dict):
                    # OPA retorna {"result": {...}} ou diretamente o resultado
                    result = data.get("result", data)

                    # Normalizar resultado para incluir 'allow'
                    if "allow" not in result:
                        # Se não tiver 'allow', assume que o próprio resultado é a decisão
                        result = {"allow": bool(result.get("allowed", True)), **data}

                    self.logger.debug(
                        "OPA evaluation successful",
                        policy=policy_path,
                        allow=result.get("allow"),
                    )

                    return result

                return {"allow": True, "raw": data}

        except aiohttp.ClientConnectorError as e:
            raise OPAConnectionError(f"Failed to connect to OPA: {e}")
        except asyncio.TimeoutError as e:
            raise OPAConnectionError(f"OPA request timeout: {e}")
        except (OPAPolicyNotFoundError, OPAEvaluationError, OPAConnectionError):
            raise
        except Exception as e:
            raise OPAEvaluationError(f"Unexpected error: {e}", policy=policy_path)

    async def _call_opa_health(self) -> bool:
        """
        Chamada de health check ao OPA.

        Returns:
            True se OPA está saudável
        """
        if self.session is None:
            return False

        try:
            # Usar endpoint de health do OPA
            health_url = f"{self.config.opa_url.rstrip('/')}/health"

            async with self.session.get(
                health_url, timeout=aiohttp.ClientTimeout(total=2)
            ) as response:
                is_healthy = response.status == 200
                return is_healthy

        except Exception:
            return False

    async def _record_failure(self) -> None:
        """Registra falha e atualiza circuit breaker."""
        async with self._circuit_lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            failure_threshold = getattr(self.config, "opa_circuit_breaker_failure_threshold", 5)
            if self._failure_count >= failure_threshold:
                self._circuit_state = "open"
                self.logger.warning(
                    "Circuit breaker opened",
                    failure_count=self._failure_count,
                    threshold=failure_threshold,
                )

                if self.metrics:
                    self.metrics.record_circuit_breaker_failure()
                    self.metrics.set_circuit_breaker_state(True)

    async def _record_success(self) -> None:
        """Registra sucesso e reseta circuit breaker se necessário."""
        async with self._circuit_lock:
            if self._circuit_state == "half_open":
                # Se sucesso em half_open, fecha circuit breaker
                self._circuit_state = "closed"
                self._failure_count = 0
                self.logger.info("Circuit breaker closed after successful request")

                if self.metrics:
                    self.metrics.set_circuit_breaker_state(False)
            elif self._circuit_state == "closed":
                # Reset contador de falhas
                self._failure_count = 0

    def _get_cache_key(self, policy_path: str, input_data: dict[str, Any]) -> str:
        """
        Gera chave de cache para política e input.

        Args:
            policy_path: Caminho da política
            input_data: Dados de entrada

        Returns:
            Chave hash única
        """
        return _generate_cache_key(policy_path, input_data)

    def clear_cache(self) -> None:
        """Limpa todo o cache."""
        self._cache.clear()
        self.logger.info("Cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Retorna estatísticas do cache.

        Returns:
            Dict com tamanho atual e máximo
        """
        return {
            "current_size": len(self._cache),
            "max_size": self._cache.maxsize,
            "ttl": self._cache.ttl,
        }

    def get_circuit_breaker_state(self) -> dict[str, Any]:
        """
        Retorna estado do circuit breaker.

        Returns:
            Dict com estado e contadores
        """
        return {
            "state": self._circuit_state,
            "failure_count": self._failure_count,
            "threshold": getattr(self.config, "opa_circuit_breaker_failure_threshold", 5),
            "last_failure_time": (
                self._last_failure_time.isoformat() if self._last_failure_time else None
            ),
        }

    async def __aenter__(self) -> "OPAClient":
        """Suporte para async context manager."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Suporte para async context manager."""
        await self.close()
