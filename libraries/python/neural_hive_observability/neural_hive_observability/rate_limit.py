"""
Middleware de Rate Limiting para FastAPI.

Implementa rate limiting per-user usando TokenBucket e SlidingWindow algorithms.
"""

import asyncio
import time
from collections import defaultdict
from functools import wraps
from typing import Awaitable, Callable, Optional

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


class InMemoryRateLimiter:
    """
    Rate limiter em memória com limpeza automática de entradas antigas.

    Usa Token Bucket algorithm para rate limiting per-user.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10,
        cleanup_interval: int = 300,
    ):
        """
        Inicializa rate limiter.

        Args:
            requests_per_minute: Limite por minuto (padrão: 60)
            requests_per_hour: Limite por hora (padrão: 1000)
            burst_size: Tamanho burst (padrão: 10)
            cleanup_interval: Intervalo de limpeza em segundos (padrão: 300)
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_size = burst_size
        self.cleanup_interval = cleanup_interval

        # Storage: {user_id: {"tokens": float, "last_update": float, "minute_tokens": int}}
        self._users = defaultdict(
            lambda: {
                "tokens": float(burst_size),
                "last_update": time.time(),
                "minute_tokens": 0,
                "hour_tokens": 0,
                "minute_window": time.time(),
                "hour_window": time.time(),
            }
        )

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Inicia task de limpeza em background."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Para task de limpeza."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self):
        """Loop de limpeza de entradas antigas."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                now = time.time()
                # Remover usuários inativos por mais de 1 hora
                cutoff = now - 3600
                inactive = [
                    user_id for user_id, data in self._users.items() if data["last_update"] < cutoff
                ]
                for user_id in inactive:
                    del self._users[user_id]
                if inactive:
                    logger.debug(
                        f"Rate limiter cleanup: {len(inactive)} usuários inativos removidos"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Erro no cleanup do rate limiter: {e}")

    def _get_user_id(self, request: Request) -> str:
        """
        Extrai user_id da request.

        Prioridade:
        1. Header X-User-ID
        2. Header X-Forwarded-For (IP)
        3. Client host
        """
        # Tentar obter user_id do header
        user_id = request.headers.get("X-User-ID")
        if user_id:
            return f"user:{user_id}"

        # Usar IP como fallback
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
            return f"ip:{ip}"

        # Usar client host
        client = request.client
        if client:
            return f"ip:{client.host}"

        return "anonymous"

    def _refill_tokens(self, user_id: str, now: float) -> None:
        """Reabastece tokens baseado no tempo passado."""
        data = self._users[user_id]
        elapsed = now - data["last_update"]
        data["last_update"] = now

        # Refill baseado em burst_size por minuto
        tokens_to_add = elapsed * (self.requests_per_minute / 60.0)
        data["tokens"] = min(self.burst_size, data["tokens"] + tokens_to_add)

        # Reset windows se passou o tempo
        if now - data["minute_window"] >= 60:
            data["minute_tokens"] = 0
            data["minute_window"] = now

        if now - data["hour_window"] >= 3600:
            data["hour_tokens"] = 0
            data["hour_window"] = now

    async def check_rate_limit(self, user_id: str) -> tuple[bool, dict]:
        """
        Verifica se user_id pode fazer uma requisição.

        Returns:
            (allowed, info_dict)
        """
        now = time.time()
        self._refill_tokens(user_id, now)
        data = self._users[user_id]

        # Verificar burst tokens
        if data["tokens"] >= 1:
            data["tokens"] -= 1
            data["minute_tokens"] += 1
            data["hour_tokens"] += 1

            return True, {
                "allowed": True,
                "remaining": int(data["tokens"]),
                "minute_used": data["minute_tokens"],
                "minute_limit": self.requests_per_minute,
                "hour_used": data["hour_tokens"],
                "hour_limit": self.requests_per_hour,
            }

        # Rate limit exceeded
        retry_after = int(60 / self.requests_per_minute)

        return False, {
            "allowed": False,
            "retry_after": retry_after,
            "minute_used": data["minute_tokens"],
            "minute_limit": self.requests_per_minute,
            "hour_used": data["hour_tokens"],
            "hour_limit": self.requests_per_hour,
        }


class RateLimitMiddleware:
    """
    Middleware FastAPI para rate limiting per-user.

    Adiciona headers de rate limit às respostas:
    - X-RateLimit-Limit: Limite total
    - X-RateLimit-Remaining: Tokens restantes
    - X-RateLimit-Reset: Unix timestamp de reset

    Em caso de excessão, retorna 429 Too Many Requests.
    """

    def __init__(
        self,
        app,
        limiter: InMemoryRateLimiter,
        excluded_paths: Optional[list[str]] = None,
    ):
        """
        Inicializa middleware.

        Args:
            app: Aplicação FastAPI
            limiter: Instância de InMemoryRateLimiter
            excluded_paths: Paths excluídos do rate limit (ex: /health, /metrics)
        """
        self.app = app
        self.limiter = limiter
        self.excluded_paths = set(excluded_paths or ["/health", "/ready", "/metrics"])

    async def __call__(self, scope, receive, send):
        """Processa request através do middleware."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Verificar se path está excluído
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                await self.app(scope, receive, send)
                return

        # Criar request mock para extrair user_id
        headers = dict(scope.get("headers", []))

        async def receive_wrapper():
            return await receive()

        # Criar wrapper para send que adiciona headers de rate limit
        request = Request(scope, receive_wrapper)

        # Verificar rate limit
        user_id = self._get_user_id(headers, request)
        allowed, info = await self.limiter.check_rate_limit(user_id)

        async def send_wrapper(message):
            """Adiciona headers de rate limit à resposta."""
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))

                # Adicionar headers de rate limit
                headers.append(
                    (
                        b"x-ratelimit-limit",
                        str(info.get("minute_limit", 60)).encode(),
                    )
                )
                headers.append(
                    (
                        b"x-ratelimit-remaining",
                        str(info.get("remaining", 0)).encode(),
                    )
                )
                headers.append(
                    (
                        b"x-ratelimit-reset",
                        str(int(time.time() + 60)).encode(),
                    )
                )

                message["headers"] = [(k, v) for k, v in headers.items()]

            await send(message)

        if not allowed:
            # Retornar 429 Too Many Requests
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "retry_after": info.get("retry_after", 60),
                    "message": f"Rate limit exceeded. Try again in {info.get('retry_after', 60)} seconds.",
                },
                headers={
                    "X-RateLimit-Limit": str(info.get("minute_limit", 60)),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(info.get("retry_after", 60)),
                },
            )

            await response(scope, receive_wrapper, send_wrapper)
            return

        await self.app(scope, receive_wrapper, send_wrapper)

    def _get_user_id(self, headers: dict, request: Request) -> str:
        """Extrai user_id de headers ou request."""
        user_id = headers.get(b"x-user-id")
        if user_id:
            return f"user:{user_id.decode()}"

        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.decode().split(",")[0].strip()
            return f"ip:{ip}"

        client = request.client
        if client:
            return f"ip:{client.host}"

        return "anonymous"


def rate_limit_decorator(
    limiter: InMemoryRateLimiter,
    get_user_id: Optional[Callable[[Request], str]] = None,
):
    """
    Decorador para rate limit em endpoints específicos.

    Args:
        limiter: Instância de InMemoryRateLimiter
        get_user_id: Função customizada para extrair user_id (opcional)

    Example:
        ```python
        limiter = InMemoryRateLimiter(requests_per_minute=30)

        @app.get("/api/expensive")
        @rate_limit_decorator(limiter)
        async def expensive_operation():
            return {"result": "expensive"}
        ```
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Extrair user_id
            if get_user_id:
                user_id = get_user_id(request)
            else:
                # Extração padrão
                user_id = request.headers.get(
                    "X-User-ID",
                    f"ip:{request.client.host if request.client else 'unknown'}",
                )

            # Verificar rate limit
            allowed, info = await limiter.check_rate_limit(user_id)

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "retry_after": info.get("retry_after", 60),
                    },
                    headers={
                        "X-RateLimit-Limit": str(info.get("minute_limit", 60)),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": str(info.get("retry_after", 60)),
                    },
                )

            # Executar função
            result = await func(request, *args, **kwargs)

            # Adicionar headers à resposta se for Response
            if hasattr(result, "headers"):
                result.headers["X-RateLimit-Limit"] = str(info.get("minute_limit", 60))
                result.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))

            return result

        return wrapper

    return decorator


async def check_rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    limiter: InMemoryRateLimiter,
) -> Response:
    """
    Função de middleware compatível com FastAPI middleware pattern.

    Example:
        ```python
        app.add_middleware(
            RateLimitMiddleware,
            limiter=limiter,
            excluded_paths=["/health", "/metrics"]
        )
        ```
    """
    # Excluir paths de health check
    if request.url.path in ["/health", "/ready", "/metrics", "/health/startup"]:
        return await call_next(request)

    # Extrair user_id
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else (request.client.host if request.client else "unknown")
        )
        user_id = f"ip:{ip}"
    else:
        user_id = f"user:{user_id}"

    # Verificar rate limit
    allowed, info = await limiter.check_rate_limit(user_id)

    response = await call_next(request)

    # Adicionar headers
    response.headers["X-RateLimit-Limit"] = str(info.get("minute_limit", 60))
    response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))

    if not allowed:
        response = JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "retry_after": info.get("retry_after", 60),
            },
            headers={
                "Retry-After": str(info.get("retry_after", 60)),
            },
        )

    return response
