"""Cliente REST para integração com o serviço Analyst Agents"""
from typing import Dict, List, Optional
import httpx
import structlog

logger = structlog.get_logger(__name__)


class AnalystAgentsClient:
    """Cliente HTTP para interagir com o serviço Analyst Agents para RAG context"""

    def __init__(self, host: str, port: int):
        """
        Inicializar cliente Analyst Agents

        Args:
            host: Hostname do serviço Analyst Agents
            port: Porta do serviço Analyst Agents
        """
        self.base_url = f"http://{host}:{port}"
        self.client: Optional[httpx.AsyncClient] = None
        self.logger = logger.bind(service="analyst_agents_client", base_url=self.base_url)

    async def start(self):
        """Inicializar conexão HTTP"""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            follow_redirects=True
        )
        self.logger.info("analyst_agents_client_started")

    async def stop(self):
        """Fechar conexão HTTP"""
        if self.client:
            await self.client.aclose()
            self.logger.info("analyst_agents_client_stopped")

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Gerar embedding de texto

        Args:
            text: Texto para gerar embedding

        Returns:
            Lista de floats representando o embedding ou None se falhar
        """
        if not self.client:
            self.logger.error("client_not_initialized", operation="get_embedding")
            return None

        try:
            response = await self.client.post(
                "/api/v1/semantics/embedding",
                json={"text": text}
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding", [])

            self.logger.info(
                "embedding_generated",
                text_length=len(text),
                embedding_dim=len(embedding)
            )
            return embedding

        except httpx.HTTPError as e:
            self.logger.error(
                "embedding_failed",
                error=str(e),
                text_length=len(text)
            )
            return None

    async def find_similar_templates(self, embedding: List[float], top_k: int = 5) -> List[Dict]:
        """
        Buscar templates similares via busca semântica usando embedding

        Args:
            embedding: Embedding vetorial para buscar templates similares
            top_k: Número de templates a retornar

        Returns:
            Lista de dicts com templates similares e scores de similaridade
        """
        if not self.client:
            self.logger.error("client_not_initialized", operation="find_similar_templates")
            return []

        try:
            response = await self.client.post(
                "/api/v1/semantics/search",
                json={
                    "embedding": embedding,
                    "top_k": top_k,
                    "threshold": 0.7
                }
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            self.logger.info(
                "similar_templates_found",
                embedding_dim=len(embedding),
                results_count=len(results),
                top_k=top_k
            )
            return results

        except httpx.HTTPError as e:
            self.logger.error(
                "similar_templates_search_failed",
                error=str(e),
                embedding_dim=len(embedding),
                top_k=top_k
            )
            return []

    async def get_architectural_patterns(self, domain: str) -> List[str]:
        """
        Buscar padrões arquiteturais para um domínio

        Args:
            domain: Domínio (TECHNICAL, BUSINESS, BEHAVIOR, etc.)

        Returns:
            Lista de padrões arquiteturais recomendados
        """
        if not self.client:
            self.logger.warning(
                "client_not_initialized_using_fallback",
                operation="get_architectural_patterns",
                domain=domain
            )
            return self._get_fallback_patterns(domain)

        try:
            # Tentar buscar via API
            response = await self.client.get(f"/api/v1/patterns/{domain}")
            response.raise_for_status()
            data = response.json()
            patterns = data.get("patterns", [])

            self.logger.info(
                "architectural_patterns_retrieved",
                domain=domain,
                patterns_count=len(patterns)
            )
            return patterns

        except httpx.HTTPError as e:
            # Fallback para padrões hardcoded baseados no domínio
            self.logger.warning(
                "architectural_patterns_api_failed_using_fallback",
                error=str(e),
                domain=domain
            )
            return self._get_fallback_patterns(domain)

    def _get_fallback_patterns(self, domain: str) -> List[str]:
        """
        Padrões arquiteturais fallback baseados no domínio

        Args:
            domain: Domínio do specialist

        Returns:
            Lista de padrões arquiteturais
        """
        patterns_map = {
            "TECHNICAL": [
                "microservices",
                "event-driven",
                "REST API",
                "layered architecture",
                "repository pattern",
                "dependency injection"
            ],
            "BUSINESS": [
                "domain-driven design",
                "CQRS",
                "event sourcing",
                "saga pattern",
                "business process modeling"
            ],
            "BEHAVIOR": [
                "observer pattern",
                "strategy pattern",
                "state machine",
                "reactive programming"
            ],
            "EVOLUTION": [
                "feature toggles",
                "blue-green deployment",
                "canary releases",
                "evolutionary architecture"
            ],
            "ARCHITECTURE": [
                "hexagonal architecture",
                "clean architecture",
                "onion architecture",
                "ports and adapters"
            ]
        }

        patterns = patterns_map.get(domain.upper(), [
            "microservices",
            "REST API",
            "layered architecture"
        ])

        self.logger.info(
            "architectural_patterns_fallback_used",
            domain=domain,
            patterns_count=len(patterns)
        )

        return patterns
