"""
Cliente Redis para GDPR Erasure Service
"""

import aioredis


class RedisClient:
    """Cliente Redis para o servico de exclusao"""

    def __init__(self, settings):
        """
        Inicializa o cliente.

        Args:
            settings: Configuracoes
        """
        self.settings = settings
        self.client: aioredis.Redis | None = None

    async def initialize(self) -> None:
        """Inicializa a conexao Redis"""
        self.client = await aioredis.from_url(
            self.settings.redis_url, encoding="utf-8", decode_responses=True
        )
        # Ping para verificar conexao
        await self.client.ping()
        print(f"Redis conectado: {self.settings.redis_url}")

    async def close(self) -> None:
        """Fecha a conexao"""
        if self.client:
            await self.client.close()
