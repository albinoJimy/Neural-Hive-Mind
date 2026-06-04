"""
Cliente MongoDB para GDPR Erasure Service
"""

import motor.motor_asyncio


class MongoDBClient:
    """Cliente MongoDB para o servico de exclusao"""

    def __init__(self, settings):
        """
        Inicializa o cliente.

        Args:
            settings: Configuracoes
        """
        self.settings = settings
        self.client: motor.motor_asyncio.AsyncIOMotorClient | None = None

    async def initialize(self) -> None:
        """Inicializa a conexao MongoDB"""
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.settings.mongodb_uri)
        # Ping para verificar conexao
        await self.client.admin.command("ping")
        print(f"MongoDB conectado: {self.settings.mongodb_uri}")

    async def close(self) -> None:
        """Fecha a conexao"""
        if self.client:
            self.client.close()
