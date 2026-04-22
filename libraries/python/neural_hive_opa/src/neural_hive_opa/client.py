"""
Cliente OPA (Open Policy Agent) para consultas de políticas.

Implementa cliente HTTP com retry, circuit breaker e cache.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from prometheus_client import Counter, Histogram
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()


# Métricas Prometheus
opa_requests_total = Counter(
    "opa_requests_total",
    "Total de requisições ao OPA",
    ["service", "policy_path", "status"],
)

opa_latency_seconds = Histogram(
    "opa_latency_seconds",
    "Latência das requisições ao OPA",
    ["service", "policy_path"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

opa_cache_hits_total = Counter(
    "opa_cache_hits_total",
    "Total de cache hits no cliente OPA",
    ["service"],
)


@dataclass
class OPARequestOptions:
    """Opções para requisição OPA."""

    timeout_seconds: int = 5
    retry_attempts: int = 3
    enable_cache: bool = True
    cache_ttl_seconds: int = 300  # 5 minutos
    fail_open: bool = False  # Se True, permite acesso quando OPA está indisponível


@dataclass
class OPAClientConfig:
    """Configuração do cliente OPA."""

    opa_url: str
    default_timeout: int = 5
    retry_attempts: int = 3
    enable_cache: bool = True
    cache_ttl_seconds: int = 300
    fail_open: bool = False
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: int = 60


class CircuitBreakerOpenException(Exception):
    """Exceção quando circuit breaker está aberto."""

    pass


class CircuitBreaker:
    """
    Circuit Breaker para prevenir cascading failures.

    Estados:
    - CLOSED: Operação normal
    - OPEN: Circuit breaker aberto, falhas rápidas
    - HALF_OPEN: Tentando recuperar
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        service_name: str = "opa",
    ):
        """
        Inicializa Circuit Breaker.

        Args:
            failure_threshold: Número de falhas consecutivas antes de abrir
            reset_timeout: Segundos antes de tentar fechar o circuito
            service_name: Nome do serviço para logging/métricas
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.service_name = service_name
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._logger = logger.bind(component="circuit_breaker", service=service_name)

    def record_success(self):
        """Registra sucesso e fecha o circuito se estiver HALF_OPEN."""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self._logger.info("circuit_breaker_closed", state=self.state)

    def record_failure(self):
        """Registra falha e possibly abre o circuito."""
        self.failure_count += 1
        self.last_failure_time = (
            self.last_failure_time or 0
        )  # Just for type checking, real value set below

        import time

        self.last_failure_time = time.time()

        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            self._logger.warning(
                "circuit_breaker_opened_after_half_open",
                failure_count=self.failure_count,
            )
        elif self.failure_count >= self.failure_threshold and self.state == "CLOSED":
            self.state = "OPEN"
            self._logger.warning(
                "circuit_breaker_opened",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )

    def allow_request(self) -> bool:
        """
        Verifica se a requisição deve ser permitida.

        Returns:
            True se requisição pode prosseguir, False se circuit breaker está aberto
        """
        import time

        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # Verificar se já passou o timeout de reset
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) >= self.reset_timeout
            ):
                self.state = "HALF_OPEN"
                self._logger.info("circuit_breaker_half_open")
                return True
            return False

        # HALF_OPEN
        return True

    def get_state(self) -> str:
        """Retorna estado atual do circuit breaker."""
        return self.state


class OPAClient:
    """
    Cliente OPA com cache, retry e circuit breaker.

    Exemplo:
        ```python
        client = OPAClient(
            opa_url="http://opa:8181",
            policy_path="neuralhive/orchestrator/authz"
        )

        result = client.check(
            input_data={
                "user": {"id": "123", "role": "admin"},
                "request": {"method": "GET", "path": "/api/v1/workflows"}
            }
        )

        if result.allow:
            print("Acesso permitido")
        else:
            print(f"Acesso negado: {result.reason}")
        ```
    """

    def __init__(
        self,
        opa_url: str,
        policy_path: str | None = None,
        config: OPAClientConfig | None = None,
    ):
        """
        Inicializa cliente OPA.

        Args:
            opa_url: URL base do OPA (ex: http://opa:8181)
            policy_path: Path da política padrão (ex: neuralhive/orchestrator/authz)
            config: Configuração opcional do cliente
        """
        self.opa_url = opa_url.rstrip("/")
        self.policy_path = policy_path or ""
        self.config = config or OPAClientConfig(opa_url=opa_url)
        self._cache: dict[str, tuple[Any, float]] = {}
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            reset_timeout=self.config.circuit_breaker_reset_timeout,
            service_name="opa",
        )
        self._logger = logger.bind(component="opa_client", opa_url=opa_url)
        self._client = httpx.AsyncClient(
            timeout=self.config.default_timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    def _generate_cache_key(self, policy_path: str, input_data: dict[str, Any]) -> str:
        """Gera chave de cache baseada no path e input."""
        content = f"{policy_path}:{json.dumps(input_data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Any | None:
        """Tenta obter resultado do cache."""
        import time

        if cache_key in self._cache:
            result, expiry = self._cache[cache_key]
            if time.time() < expiry:
                opa_cache_hits_total.labels(service="orchestrator").inc()
                return result
            else:
                # Cache expirado
                del self._cache[cache_key]
        return None

    def _store_in_cache(self, cache_key: str, result: Any):
        """Armazena resultado no cache."""
        import time

        expiry = time.time() + self.config.cache_ttl_seconds
        self._cache[cache_key] = (result, expiry)

    def _clear_expired_cache(self):
        """Limpa entradas expiradas do cache."""
        import time

        now = time.time()
        expired = [k for k, (_, expiry) in self._cache.items() if expiry < now]
        for k in expired:
            del self._cache[k]

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _make_request(
        self,
        policy_path: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Faz requisição ao OPA com retry automático.

        Args:
            policy_path: Path da política
            input_data: Dados de input para a política

        Returns:
            Resposta do OPA

        Raises:
            httpx.HTTPError: Em caso de erro na requisição
        """
        url = f"{self.opa_url}/v1/data/{policy_path}"

        self._logger.debug("opa_request", url=url, policy_path=policy_path)

        response = await self._client.post(
            url,
            json={"input": input_data},
            headers={"Content-Type": "application/json"},
        )

        response.raise_for_status()
        return response.json()

    async def check(
        self,
        input_data: dict[str, Any],
        policy_path: str | None = None,
        options: OPARequestOptions | None = None,
    ) -> "OPAResult":
        """
        Verifica autorização via OPA.

        Args:
            input_data: Dados de input para a política (user, request, etc)
            policy_path: Path da política (usa default se não especificado)
            options: Opções da requisição

        Returns:
            OPAResult com decisão e metadados
        """
        path = policy_path or self.policy_path
        opts = options or OPARequestOptions()
        service_name = "orchestrator"

        # Verificar circuit breaker
        if self._circuit_breaker.get_state() == "OPEN":
            if opts.fail_open:
                self._logger.warning("opa_circuit_breaker_open_fail_open")
                return OPAResult(allow=True, reason="fail_open", cached=False)
            else:
                self._logger.warning("opa_circuit_breaker_open_fail_closed")
                raise CircuitBreakerOpenException("OPA circuit breaker is open - too many failures")

        # Tentar cache
        if opts.enable_cache and self.config.enable_cache:
            cache_key = self._generate_cache_key(path, input_data)
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return OPAResult(
                    allow=cached_result.get("allow", False),
                    reason=cached_result.get("reason", "cached"),
                    cached=True,
                )

        # Fazer requisição ao OPA
        import time

        start_time = time.time()

        try:
            response = await self._make_request(path, input_data)

            latency = time.time() - start_time
            opa_latency_seconds.labels(service=service_name, policy_path=path).observe(latency)
            opa_requests_total.labels(
                service=service_name, policy_path=path, status="success"
            ).inc()

            self._circuit_breaker.record_success()

            # Extrair decisão da resposta
            # Formato OPA: {"result": {"allow": true}} ou {"result": true}
            result_data = response.get("result", {})
            if isinstance(result_data, bool):
                allow = result_data
                reason = "opa_decision"
            elif isinstance(result_data, dict):
                allow = result_data.get("allow", False)
                reason = result_data.get("reason", "opa_decision")
            else:
                allow = False
                reason = "invalid_response"

            # Armazenar no cache
            if opts.enable_cache and self.config.enable_cache:
                self._store_in_cache(cache_key, {"allow": allow, "reason": reason})

            return OPAResult(allow=allow, reason=reason, cached=False)

        except httpx.HTTPError as e:
            latency = time.time() - start_time
            opa_requests_total.labels(service=service_name, policy_path=path, status="error").inc()

            self._circuit_breaker.record_failure()

            if opts.fail_open:
                self._logger.error("opa_error_fail_open", error=str(e))
                return OPAResult(allow=True, reason="fail_open", cached=False)
            else:
                self._logger.error("opa_error_fail_closed", error=str(e))
                raise

    async def check_batch(
        self,
        requests: list[dict[str, Any]],
        policy_path: str | None = None,
    ) -> list["OPAResult"]:
        """
        Verifica múltiplas autorizações em batch.

        Args:
            requests: Lista de inputs para verificar
            policy_path: Path da política

        Returns:
            Lista de OPAResult na mesma ordem
        """
        results = []
        for input_data in requests:
            result = await self.check(input_data, policy_path)
            results.append(result)
        return results

    async def close(self):
        """Fecha o cliente HTTP e limpa recursos."""
        await self._client.aclose()
        self._cache.clear()

    def get_circuit_breaker_state(self) -> str:
        """Retorna estado atual do circuit breaker."""
        return self._circuit_breaker.get_state()

    def clear_cache(self):
        """Limpa todo o cache."""
        self._cache.clear()

    def get_cache_stats(self) -> dict[str, int]:
        """Retorna estatísticas do cache."""
        import time

        now = time.time()
        valid_entries = sum(1 for _, expiry in self._cache.values() if expiry > now)
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
        }


@dataclass
class OPAResult:
    """Resultado de uma consulta OPA."""

    allow: bool
    reason: str = ""
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "allow": self.allow,
            "reason": self.reason,
            "cached": self.cached,
            "metadata": self.metadata,
        }
