"""
Token caching and automatic refresh mechanism
"""

import asyncio
from typing import Optional, Dict, Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import structlog
from prometheus_client import Counter, Gauge


# Prometheus metrics
cache_hits_total = Counter(
    "token_cache_hits_total",
    "Total token cache hits"
)
cache_misses_total = Counter(
    "token_cache_misses_total",
    "Total token cache misses"
)
cache_refresh_total = Counter(
    "token_cache_refresh_total",
    "Total token cache refreshes",
    ["status"]
)
cache_size = Gauge(
    "token_cache_size",
    "Current number of cached tokens"
)


logger = structlog.get_logger(__name__)


class RefreshStrategy(str, Enum):
    """Token refresh strategies"""
    EAGER = "eager"      # Refresh proactively before expiration
    LAZY = "lazy"        # Refresh on access if expired
    DISABLED = "disabled"  # No automatic refresh


@dataclass
class CachedToken:
    """Cached token metadata"""
    value: str
    expiry: datetime
    refresh_at: datetime


class TokenCache:
    """
    Token cache with automatic refresh

    Features:
    - In-memory LRU cache with TTL
    - Thread-safe async operations
    - Automatic background refresh
    - Configurable refresh threshold
    - Metrics for monitoring
    """

    def __init__(
        self,
        refresh_threshold: float = 0.8,
        refresh_strategy: RefreshStrategy = RefreshStrategy.EAGER
    ):
        """
        Initialize token cache

        Args:
            refresh_threshold: Refresh when this fraction of TTL remains (0.0-1.0)
            refresh_strategy: Refresh strategy (EAGER, LAZY, DISABLED)
        """
        self.refresh_threshold = refresh_threshold
        self.refresh_strategy = refresh_strategy
        self.logger = logger.bind(component="token_cache")

        self._cache: Dict[str, CachedToken] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._refresh_callbacks: Dict[str, Callable[[str], Awaitable[str]]] = {}
        self._refresh_task: Optional[asyncio.Task] = None

    async def get(self, key: str) -> Optional[str]:
        """
        Retrieve token from cache

        Args:
            key: Cache key

        Returns:
            Token value or None if not found/expired
        """
        if key not in self._cache:
            cache_misses_total.inc()
            self.logger.debug("cache_miss", key=key)
            return None

        cached = self._cache[key]
        now = datetime.utcnow()

        # Check if expired
        if now >= cached.expiry:
            self.logger.debug("token_expired", key=key)
            del self._cache[key]
            cache_size.set(len(self._cache))
            cache_misses_total.inc()
            return None

        # Check if refresh needed (lazy strategy)
        if self.refresh_strategy == RefreshStrategy.LAZY and now >= cached.refresh_at:
            self.logger.debug("triggering_lazy_refresh", key=key)
            await self._refresh_token(key)

        cache_hits_total.inc()
        return cached.value

    async def set(
        self,
        key: str,
        token: str,
        ttl: int,
        refresh_callback: Optional[Callable[[str], Awaitable[str]]] = None
    ):
        """
        Store token in cache

        Args:
            key: Cache key
            token: Token value
            ttl: Time to live in seconds
            refresh_callback: Optional async function to refresh token
        """
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        refresh_at = datetime.utcnow() + timedelta(seconds=ttl * self.refresh_threshold)

        self._cache[key] = CachedToken(
            value=token,
            expiry=expiry,
            refresh_at=refresh_at
        )

        if refresh_callback:
            self._refresh_callbacks[key] = refresh_callback

        # Create lock for this key if it doesn't exist
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        cache_size.set(len(self._cache))
        self.logger.debug(
            "token_cached",
            key=key,
            ttl=ttl,
            refresh_at=refresh_at.isoformat()
        )

    async def invalidate(self, key: str):
        """
        Remove token from cache

        Args:
            key: Cache key
        """
        if key in self._cache:
            del self._cache[key]
            cache_size.set(len(self._cache))
            self.logger.debug("token_invalidated", key=key)

        if key in self._refresh_callbacks:
            del self._refresh_callbacks[key]

        if key in self._locks:
            del self._locks[key]

    async def _refresh_token(self, key: str):
        """
        Refresh a single token

        Args:
            key: Cache key
        """
        if key not in self._refresh_callbacks:
            self.logger.warning("no_refresh_callback", key=key)
            return

        # Acquire lock to prevent concurrent refreshes
        async with self._locks[key]:
            try:
                self.logger.debug("refreshing_token", key=key)

                # Call refresh callback
                new_token = await self._refresh_callbacks[key](key)

                # Update cache with new token
                if key in self._cache:
                    cached = self._cache[key]
                    cached.value = new_token
                    # Reset refresh time
                    ttl = (cached.expiry - datetime.utcnow()).total_seconds()
                    cached.refresh_at = datetime.utcnow() + timedelta(seconds=ttl * self.refresh_threshold)

                cache_refresh_total.labels(status="success").inc()
                self.logger.info("token_refreshed", key=key)

            except Exception as e:
                cache_refresh_total.labels(status="error").inc()
                self.logger.error("token_refresh_failed", key=key, error=str(e))

    async def start_refresh_loop(self):
        """Start background refresh task (EAGER strategy)"""
        if self.refresh_strategy != RefreshStrategy.EAGER:
            self.logger.debug("refresh_loop_disabled", strategy=self.refresh_strategy.value)
            return

        self.logger.info("starting_refresh_loop")
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self):
        """Background task for proactive token refresh"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                now = datetime.utcnow()
                for key, cached in list(self._cache.items()):
                    # Check if refresh needed
                    if now >= cached.refresh_at and key in self._refresh_callbacks:
                        self.logger.debug("proactive_refresh", key=key)
                        await self._refresh_token(key)

            except asyncio.CancelledError:
                self.logger.info("refresh_loop_cancelled")
                break
            except Exception as e:
                self.logger.error("refresh_loop_error", error=str(e))

    async def stop_refresh_loop(self):
        """Stop background refresh task"""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self.logger.info("refresh_loop_stopped")

    def clear(self):
        """Clear all cached tokens"""
        self._cache.clear()
        self._refresh_callbacks.clear()
        self._locks.clear()
        cache_size.set(0)
        self.logger.info("cache_cleared")
