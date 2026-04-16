# Fluxo G - Fase 3: Knowledge & Approvals (RAG + Approval Gateway)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar dois serviços especializados: Knowledge Graph RAG (8016) para busca contextual de templates e código similar usando Neo4j + Qdrant, e Approval Gateway (8017) para orquestrar o ciclo de aprovação humana antes da geração de código.

**Architecture:** Knowledge Graph RAG estende o Neo4j existente com embeddings vectoriais via Qdrant para busca híbrida (graph + vector). Approval Gateway expõe API REST para submissão, revisão e aprovação/rejeição de artefactos, com armazenamento de versões no MongoDB e publicação de eventos Kafka.

**Tech Stack:** Python 3.12+, FastAPI, Neo4j, Qdrant (vector DB), OpenAI Embeddings, MongoDB, Redis, Kafka, JWT, structlog

---

## Estrutura de Ficheiros

```
services/
├── knowledge-graph-rag/                 # NOVO SERVIÇO (porta 8016)
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                      # NOVO - FastAPI app
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py              # NOVO - Configurações
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── retrieval.py             # NOVO - Modelos de RAG
│   │   │   └── similarity.py            # NOVO - Similaridade
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── rag_query_engine.py      # NOVO - Motor RAG
│   │   │   ├── template_indexer.py      # NOVO - Indexação de templates
│   │   │   ├── code_indexer.py          # NOVO - Indexação de código
│   │   │   └── contextual_retriever.py  # NOVO - Recuperação contextual
│   │   ├── embeddings/
│   │   │   ├── __init__.py
│   │   │   ├── openai_embedder.py       # NOVO - Embeddings OpenAI
│   │   │   └── cache.py                 # NOVO - Cache de embeddings
│   │   ├── graph/
│   │   │   ├── __init__.py
│   │   │   ├── neo4j_client.py         # NOVO - Cliente Neo4j
│   │   │   └── qdrant_client.py         # NOVO - Cliente Qdrant
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routers/
│   │   │       ├── __init__.py
│   │   │       └── rag.py               # NOVO - Endpoints REST
│   │   └── consumers/
│   │       ├── __init__.py
│   │       └── artifact_consumer.py     # NOVO - Kafka consumer
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_rag_query_engine.py
│   │   │   ├── test_template_indexer.py
│   │   │   └── test_contextual_retriever.py
│   │   └── integration/
│   │       └── test_rag_flow.py
│   ├── deployment/
│   │   ├── k8s-deployment.yaml
│   │   ├── k8s-service.yaml
│   │   └── Dockerfile
│   ├── pyproject.toml
│   └── README.md
│
└── approval-gateway/                    # NOVO SERVIÇO (porta 8017)
    ├── src/
    │   ├── __init__.py
    │   ├── main.py                      # NOVO - FastAPI app
    │   ├── config/
    │   │   ├── __init__.py
    │   │   └── settings.py              # NOVO - Configurações
    │   ├── models/
    │   │   ├── __init__.py
    │   │   ├── approval.py               # NOVO - Modelos de aprovação
    │   │   ├── artifact.py               # NOVO - Artefactos
    │   │   └── snapshot.py               # NOVO - Snapshots versionados
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── approval_service.py      # NOVO - Serviço de aprovação
    │   │   ├── artifact_store.py        # NOVO - Armazenamento
    │   │   ├── token_service.py         # NOVO - JWT approval tokens
    │   │   └── notification_service.py  # NOVO - Notificações
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── middleware/
    │   │   │   ├── __init__.py
    │   │   │   └── auth.py               # NOVO - Middleware JWT
    │   │   └── routers/
    │   │       ├── __init__.py
    │   │       ├── approval.py           # NOVO - API de aprovação
    │   │       └── artifacts.py          # NOVO - API de artefactos
    │   ├── producers/
    │   │   ├── __init__.py
    │   │   └── approval_producer.py     # NOVO - Kafka producer
    │   └── consumers/
    │       ├── __init__.py
    │       └── artifact_consumer.py     # NOVO - Kafka consumer
    ├── tests/
    │   ├── unit/
    │   │   ├── test_approval_service.py
    │   │   ├── test_token_service.py
    │   │   └── test_artifact_store.py
    │   └── integration/
    │       └── test_approval_flow.py
    ├── deployment/
    │   ├── k8s-deployment.yaml
    │   ├── k8s-service.yaml
    │   └── Dockerfile
    ├── pyproject.toml
    └── README.md
```

---

# PARTE 1: Knowledge Graph RAG (8016)

## Task 1: Criar estrutura base do knowledge-graph-rag

**Files:**
- Create: `services/knowledge-graph-rag/pyproject.toml`
- Create: `services/knowledge-graph-rag/src/__init__.py`
- Create: `services/knowledge-graph-rag/src/config/settings.py`

- [ ] **Step 1: Criar pyproject.toml**

```toml
# services/knowledge-graph-rag/pyproject.toml
[tool.poetry]
name = "knowledge-graph-rag"
version = "0.1.0"
description = "Knowledge Graph RAG for Neural Hive-Mind"
authors = ["Neural Hive-Mind Team"]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.104.0"
uvicorn = {extras = ["standard"], version = "^0.24.0"}
pydantic = "^2.0"
pydantic-settings = "^2.0"
motor = "^3.0"
redis = {extras = ["hiredis"], version = "^5.0"}
aiokafka = "^0.9.0"
structlog = "^23.0"
openai = "^1.0"
anthropic = "^0.7"
neo4j = "^5.0"
qdrant-client = "^1.7.0"
numpy = "^1.24"
scipy = "^1.11"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 2: Criar settings.py**

```python
# services/knowledge-graph-rag/src/config/settings.py
"""Configurações do Knowledge Graph RAG Service."""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAG_",
    )

    # API
    api_title: str = "Knowledge Graph RAG API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8016

    # Embeddings
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: str = Field(default="", validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = "neo4j"

    # Qdrant
    qdrant_host: str = Field(default="localhost", validation_alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, validation_alias="QDRANT_PORT")
    qdrant_collection_templates: str = "nhm_templates"
    qdrant_collection_code: str = "nhm_code"

    # Redis (cache)
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    redis_cache_ttl: int = 3600

    # RAG
    rerank_top_k: int = 10
    hybrid_search_alpha: float = 0.5  # 0=only graph, 1=only vector
    min_similarity_threshold: float = 0.7

    # Kafka
    kafka_bootstrap_servers: str = Field(default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS")


@lru_cache
def get_settings() -> Settings:
    """Singleton das configurações."""
    return Settings()
```

- [ ] **Step 3: Criar packages base**

```python
# services/knowledge-graph-rag/src/__init__.py
"""Knowledge Graph RAG Service."""
__version__ = "0.1.0"
```

```python
# services/knowledge-graph-rag/src/config/__init__.py
"""Configurações."""
from .settings import get_settings, Settings
__all__ = ["get_settings", "Settings"]
```

- [ ] **Step 4: Commit**

```bash
git add services/knowledge-graph-rag/pyproject.toml \
        services/knowledge-graph-rag/src/
git commit -m "feat(knowledge-graph-rag): add base structure and settings"
```

---

## Task 2: Implementar clientes Neo4j e Qdrant

**Files:**
- Create: `services/knowledge-graph-rag/src/graph/__init__.py`
- Create: `services/knowledge-graph-rag/src/graph/neo4j_client.py`
- Create: `services/knowledge-graph-rag/src/graph/qdrant_client.py`

- [ ] **Step 1: Escrever testes**

```python
# services/knowledge-graph-rag/tests/unit/test_neo4j_client.py
"""Testes para Neo4jClient."""

import pytest
from unittest.mock import Mock, patch

from knowledge_graph_rag.graph.neo4j_client import Neo4jClient


@pytest.fixture
def client():
    return Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="test")


@pytest.mark.asyncio
async def test_find_similar_architectures(client):
    """Testa busca de arquiteturas similares."""
    with patch.object(client, "execute_query") as mock_query:
        mock_query.return_value = [
            {"plan_id": "ARCH-001", "similarity": 0.85, "architecture_type": "microservices"}
        ]

        results = await client.find_similar_architectures(
            requirements=["API REST", "Database"],
            limit=5
        )

        assert len(results) > 0
        assert results[0]["similarity"] >= 0.8


@pytest.mark.asyncio
async def test_get_connections_context(client):
    """Testa obtenção de contexto de conexões."""
    with patch.object(client, "execute_query") as mock_query:
        mock_query.return_value = [
            {"from": "API", "to": "Database", "type": "HTTP", "description": "REST calls"}
        ]

        context = await client.get_connections_context(node_id="service-123")

        assert "from" in context[0]
```

- [ ] **Step 2: Executar testes**

Expected: FAIL

- [ ] **Step 3: Implementar Neo4jClient**

```python
# services/knowledge-graph-rag/src/graph/neo4j_client.py
"""Cliente Neo4j para operações de grafo."""

from typing import Any, Dict, List, Optional

import structlog
from neo4j import AsyncGraphDatabase

from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class Neo4jClient:
    """Cliente para Neo4j."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None
    ):
        """Inicializa o cliente Neo4j.

        Args:
            uri: URI de conexão Neo4j
            user: Utilizador
            password: Password
            database: Nome da database
        """
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self.database = database or settings.neo4j_database
        self.driver = None

    async def connect(self):
        """Estabelece conexão com Neo4j."""
        self.driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )
        logger.info("neo4j_connected", uri=self.uri)

    async def close(self):
        """Fecha conexão com Neo4j."""
        if self.driver:
            await self.driver.close()
            logger.info("neo4j_closed")

    async def execute_query(
        self,
        query: str,
        parameters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Executa query Cypher.

        Args:
            query: Query Cypher
            parameters: Parâmetros da query

        Returns:
            Lista de resultados
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return [dict(record) for record in records]

    async def find_similar_architectures(
        self,
        requirements: List[str],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Encontra arquiteturas similares baseado em requisitos.

        Args:
            requirements: Lista de requisitos
            limit: Limite de resultados

        Returns:
            Lista de arquiteturas similares com scores
        """
        # Construir query para encontrar arquiteturas com componentes similares
        query = """
        MATCH (a:ArchitecturePlan)-[:HAS_COMPONENT]->(c:Component)
        WHERE ANY(req IN $requirements WHERE c.stack CONTAINS req OR c.name CONTAINS req)
        RETURN a.plan_id AS plan_id,
               a.architecture_type AS architecture_type,
               COUNT(DISTINCT c) AS matched_components,
               SIZE((a)-[:HAS_COMPONENT]->()) AS total_components,
               COUNT(DISTINCT c) * 1.0 / SIZE((a)-[:HAS_COMPONENT]->()) AS similarity
        ORDER BY similarity DESC
        LIMIT $limit
        """

        results = await self.execute_query(query, {
            "requirements": requirements,
            "limit": limit
        })

        logger.info("similar_architectures_found", count=len(results))

        return results

    async def get_connections_context(
        self,
        node_id: str,
        depth: int = 2
    ) -> List[Dict[str, Any]]:
        """Obtém contexto de conexões de um nó.

        Args:
            node_id: ID do nó
            depth: Profundidade da busca

        Returns:
            Lista de conexões
        """
        query = """
        MATCH path = (n {id: $node_id})-[*1..{depth}]-(connected)
        RETURN n.id AS from_id,
               connected.id AS to_id,
               [(n)-[r]-(connected) | type(r)][0] AS connection_type,
               [(n)-[r]-(connected) | r.description][0] AS description
        LIMIT 100
        """

        results = await self.execute_query(query, {
            "node_id": node_id,
            "depth": depth
        })

        return results

    async def get_component_templates(
        self,
        component_type: str
    ) -> List[Dict[str, Any]]:
        """Obtém templates para um tipo de componente.

        Args:
            component_type: Tipo do componente

        Returns:
            Lista de templates
        """
        query = """
        MATCH (t:Template)-[:FOR_TYPE]->(type:ComponentType {name: $type})
        RETURN t.id AS template_id,
               t.name AS template_name,
               t.description AS description,
               t.stack AS stack
        """

        results = await self.execute_query(query, {"type": component_type})

        return results

    async def create_architecture_node(
        self,
        plan_id: str,
        architecture_type: str,
        components: List[Dict[str, Any]]
    ) -> str:
        """Cria nó de arquitetura no grafo.

        Args:
            plan_id: ID do plano
            architecture_type: Tipo de arquitetura
            components: Lista de componentes

        Returns:
            ID do nó criado
        """
        query = """
        CREATE (a:ArchitecturePlan {
            plan_id: $plan_id,
            architecture_type: $architecture_type,
            created_at: datetime()
        })
        WITH a
        UNWIND $components AS comp
        CREATE (c:Component {
            id: comp.id,
            name: comp.name,
            stack: comp.stack
        })
        CREATE (a)-[:HAS_COMPONENT]->(c)
        RETURN a.plan_id AS plan_id
        """

        await self.execute_query(query, {
            "plan_id": plan_id,
            "architecture_type": architecture_type,
            "components": components
        })

        logger.info("architecture_node_created", plan_id=plan_id)

        return plan_id
```

- [ ] **Step 4: Implementar QdrantClient**

```python
# services/knowledge-graph-rag/src/graph/qdrant_client.py
"""Cliente Qdrant para busca vetorial."""

from typing import Any, Dict, List, Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class QdrantClient:
    """Cliente para Qdrant Vector Database."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None
    ):
        """Inicializa o cliente Qdrant.

        Args:
            host: Host Qdrant
            port: Porta Qdrant
        """
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.client: Optional[QdrantClient] = None
        self.collection_templates = settings.qdrant_collection_templates
        self.collection_code = settings.qdrant_collection_code

    async def connect(self):
        """Estabelece conexão com Qdrant."""
        self.client = QdrantClient(host=self.host, port=self.port)
        await self._ensure_collections()
        logger.info("qdrant_connected", host=self.host)

    async def close(self):
        """Fecha conexão com Qdrant."""
        if self.client:
            self.client.close()
            logger.info("qdrant_closed")

    async def _ensure_collections(self):
        """Garante que as coleções existem."""
        collections = [
            (self.collection_templates, "Templates de código"),
            (self.collection_code, "Código indexado")
        ]

        for collection_name, description in collections:
            try:
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimensions,
                        distance=Distance.COSINE
                    )
                )
                logger.info("qdrant_collection_created", collection=collection_name)
            except Exception as e:
                # Coleção já existe
                logger.debug("qdrant_collection_exists", collection=collection_name)

    async def search_templates(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Busca templates similares.

        Args:
            query_vector: Vetor de consulta
            limit: Limite de resultados
            score_threshold: Score mínimo

        Returns:
            Lista de templates similares
        """
        results = await self.client.search(
            collection_name=self.collection_templates,
            query_vector=query_vector,
            query_filter=None,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload
            }
            for r in results
        ]

    async def search_code(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        language_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Busca código similar.

        Args:
            query_vector: Vetor de consulta
            limit: Limite de resultados
            score_threshold: Score mínimo
            language_filter: Filtro de linguagem

        Returns:
            Lista de código similar
        """
        query_filter = None
        if language_filter:
            query_filter = Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=language_filter))]
            )

        results = await self.client.search(
            collection_name=self.collection_code,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload
            }
            for r in results
        ]

    async def index_template(
        self,
        template_id: str,
        vector: List[float],
        payload: Dict[str, Any]
    ):
        """Indexa um template.

        Args:
            template_id: ID do template
            vector: Vetor de embeddings
            payload: Metadados do template
        """
        point = PointStruct(
            id=template_id,
            vector=vector,
            payload=payload
        )

        await self.client.upsert(
            collection_name=self.collection_templates,
            points=[point]
        )

        logger.info("template_indexed", template_id=template_id)

    async def index_code(
        self,
        code_id: str,
        vector: List[float],
        payload: Dict[str, Any]
    ):
        """Indexa código.

        Args:
            code_id: ID do código
            vector: Vetor de embeddings
            payload: Metadados do código
        """
        point = PointStruct(
            id=code_id,
            vector=vector,
            payload=payload
        )

        await self.client.upsert(
            collection_name=self.collection_code,
            points=[point]
        )

        logger.info("code_indexed", code_id=code_id)

    async def delete_points(self, collection_name: str, ids: List[str]):
        """Remove pontos da coleção.

        Args:
            collection_name: Nome da coleção
            ids: IDs dos pontos a remover
        """
        await self.client.delete(
            collection_name=collection_name,
            points_selector=ids
        )

        logger.info("points_deleted", count=len(ids))
```

- [ ] **Step 5: Criar package**

```python
# services/knowledge-graph-rag/src/graph/__init__.py
"""Clientes de grafos e vetores."""

from .neo4j_client import Neo4jClient
from .qdrant_client import QdrantClient

__all__ = ["Neo4jClient", "QdrantClient"]
```

- [ ] **Step 6: Executar testes**

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/knowledge-graph-rag/src/graph/ \
        services/knowledge-graph-rag/tests/unit/test_neo4j_client.py
git commit -m "feat(knowledge-graph-rag): implement Neo4j and Qdrant clients"
```

---

## Task 3: Implementar serviço de embeddings

**Files:**
- Create: `services/knowledge-graph-rag/src/embeddings/__init__.py`
- Create: `services/knowledge-graph-rag/src/embeddings/openai_embedder.py`
- Create: `services/knowledge-graph-rag/src/embeddings/cache.py`

- [ ] **Step 1: Escrever testes**

```python
# services/knowledge-graph-rag/tests/unit/test_openai_embedder.py
"""Testes para OpenAIEmbedder."""

import pytest

from knowledge_graph_rag.embeddings.openai_embedder import OpenAIEmbedder


@pytest.fixture
def embedder():
    return OpenAIEmbedder()


@pytest.mark.asyncio
async def test_embed_single_text(embedder):
    """Testa embedding de texto único."""
    vector = await embedder.embed("Create a REST API with authentication")

    assert isinstance(vector, list)
    assert len(vector) == 1536  # text-embedding-3-small
    assert all(isinstance(x, float) for x in vector)


@pytest.mark.asyncio
async def test_embed_batch(embedder):
    """Testa embedding em lote."""
    texts = [
        "User authentication service",
        "Database connection pool",
        "API rate limiter"
    ]

    vectors = await embedder.embed_batch(texts)

    assert len(vectors) == 3
    assert all(len(v) == 1536 for v in vectors)
```

- [ ] **Step 2: Executar testes**

Expected: FAIL

- [ ] **Step 3: Implementar OpenAIEmbedder**

```python
# services/knowledge-graph-rag/src/embeddings/openai_embedder.py
"""Serviço de embeddings usando OpenAI API."""

from typing import List

import numpy as np
import structlog
from openai import AsyncOpenAI

from ..config.settings import get_settings
from .cache import EmbeddingCache

logger = structlog.get_logger()
settings = get_settings()


class OpenAIEmbedder:
    """Gerador de embeddings usando OpenAI."""

    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        cache: EmbeddingCache = None
    ):
        """Inicializa o embedder.

        Args:
            api_key: Chave API OpenAI
            model: Modelo de embeddings
            cache: Cache de embeddings
        """
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self.model = model or settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.batch_size = settings.embedding_batch_size
        self.cache = cache or EmbeddingCache()

    async def embed(self, text: str) -> List[float]:
        """Gera embedding para um texto.

        Args:
            text: Texto para gerar embedding

        Returns:
            Vetor de embeddings
        """
        # Verificar cache
        cached = await self.cache.get(text)
        if cached:
            return cached

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text
            )
            vector = response.data[0].embedding

            # Salvar no cache
            await self.cache.set(text, vector)

            return vector

        except Exception as e:
            logger.error("embedding_failed", text_length=len(text), error=str(e))
            raise

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Gera embeddings para múltiplos textos.

        Args:
            texts: Lista de textos

        Returns:
            Lista de vetores
        """
        # Verificar cache para todos
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        for i, text in enumerate(texts):
            cached = await self.cache.get(text)
            if cached:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Gerar embeddings para textos não cacheados
        if uncached_texts:
            # Processar em batches
            for i in range(0, len(uncached_texts), self.batch_size):
                batch_texts = uncached_texts[i:i + self.batch_size]
                batch_indices = uncached_indices[i:i + self.batch_size]

                try:
                    response = await self.client.embeddings.create(
                        model=self.model,
                        input=batch_texts
                    )

                    for j, embedding in enumerate(response.data):
                        vector = embedding.embedding
                        original_index = batch_indices[j]
                        results[original_index] = vector

                        # Salvar no cache
                        await self.cache.set(batch_texts[j], vector)

                except Exception as e:
                    logger.error("batch_embedding_failed", batch_size=len(batch_texts), error=str(e))
                    # Preencher com zeros como fallback
                    for j in range(len(batch_texts)):
                        results[batch_indices[j]] = [0.0] * self.dimensions

        return results

    async def compute_similarity(
        self,
        vector1: List[float],
        vector2: List[float]
    ) -> float:
        """Computa similaridade de cosseno entre dois vetores.

        Args:
            vector1: Primeiro vetor
            vector2: Segundo vetor

        Returns:
            Score de similaridade (0-1)
        """
        v1 = np.array(vector1)
        v2 = np.array(vector2)

        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))
```

- [ ] **Step 4: Implementar EmbeddingCache**

```python
# services/knowledge-graph-rag/src/embeddings/cache.py
"""Cache de embeddings usando Redis."""

import hashlib
import json
from typing import List, Optional

import aioredis
import structlog

from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class EmbeddingCache:
    """Cache de embeddings em Redis."""

    def __init__(self, redis_url: str = None):
        """Inicializa o cache.

        Args:
            redis_url: URL de conexão Redis
        """
        self.redis_url = redis_url or settings.redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.ttl = settings.redis_cache_ttl

    async def connect(self):
        """Estabelece conexão com Redis."""
        self.redis = await aioredis.from_url(self.redis_url)
        logger.info("embedding_cache_connected")

    async def close(self):
        """Fecha conexão com Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("embedding_cache_closed")

    def _make_key(self, text: str) -> str:
        """Gera chave de cache."""
        # Hash do texto como chave
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"emb:{self.model_name()}:{text_hash}"

    @staticmethod
    def model_name() -> str:
        """Nome do modelo de embeddings."""
        return "text-embedding-3-small"

    async def get(self, text: str) -> Optional[List[float]]:
        """Obtém embedding do cache.

        Args:
            text: Texto original

        Returns:
            Vetor ou None se não encontrado
        """
        if not self.redis:
            return None

        key = self._make_key(text)
        cached = await self.redis.get(key)

        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                return None

        return None

    async def set(self, text: str, vector: List[float]):
        """Salva embedding no cache.

        Args:
            text: Texto original
            vector: Vetor de embeddings
        """
        if not self.redis:
            return

        key = self._make_key(text)
        value = json.dumps(vector)

        await self.redis.setex(key, self.ttl, value)

    async def invalidate(self, text: str):
        """Invalida entrada do cache.

        Args:
            text: Texto a invalidar
        """
        if not self.redis:
            return

        key = self._make_key(text)
        await self.redis.delete(key)
```

- [ ] **Step 5: Criar package**

```python
# services/knowledge-graph-rag/src/embeddings/__init__.py
"""Serviços de embeddings."""

from .cache import EmbeddingCache
from .openai_embedder import OpenAIEmbedder

__all__ = ["EmbeddingCache", "OpenAIEmbedder"]
```

- [ ] **Step 6: Executar testes**

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/knowledge-graph-rag/src/embeddings/ \
        services/knowledge-graph-rag/tests/unit/test_openai_embedder.py
git commit -m "feat(knowledge-graph-rag): implement embedding service with cache"
```

---

## Task 4: Implementar RAG Query Engine

**Files:**
- Create: `services/knowledge-graph-rag/src/services/__init__.py`
- Create: `services/knowledge-graph-rag/src/services/rag_query_engine.py`
- Create: `services/knowledge-graph-rag/src/services/contextual_retriever.py`
- Create: `services/knowledge-graph-rag/tests/unit/test_rag_query_engine.py`

- [ ] **Step 1: Escrever testes**

```python
# services/knowledge-graph-rag/tests/unit/test_rag_query_engine.py
"""Testes para RAGQueryEngine."""

import pytest
from unittest.mock import Mock, AsyncMock

from knowledge_graph_rag.services.rag_query_engine import RAGQueryEngine
from knowledge_graph_rag.models.retrieval import RetrievalResult


@pytest.fixture
def mock_engine():
    """Fixture para RAGQueryEngine com mocks."""
    engine = RAGQueryEngine()
    engine.neo4j = Mock()
    engine.qdrant = Mock()
    engine.embedder = Mock()

    # Setup async mocks
    engine.neo4j.find_similar_architectures = AsyncMock(return_value=[
        {"plan_id": "ARCH-001", "similarity": 0.85}
    ])
    engine.qdrant.search_templates = AsyncMock(return_value=[
        {"id": "TPL-001", "score": 0.9}
    ])
    engine.embedder.embed = AsyncMock(return_value=[0.1] * 1536)

    return engine


@pytest.mark.asyncio
async def test_hybrid_search(mock_engine):
    """Testa busca híbrida (graph + vector)."""
    results = await mock_engine.hybrid_search(
        query="Create REST API for user management",
        alpha=0.5
    )

    assert len(results) > 0
    assert isinstance(results[0], RetrievalResult)


@pytest.mark.asyncio
async def test_contextual_retrieval(mock_engine):
    """Testa recuperação contextual."""
    context = await mock_engine.retrieve_context(
        query="User authentication",
        artifact_type="architecture"
    )

    assert "similar_architectures" in context or "similar_templates" in context
```

- [ ] **Step 2: Executar testes**

Expected: FAIL

- [ ] **Step 3: Criar modelos de retrieval**

```python
# services/knowledge-graph-rag/src/models/retrieval.py
"""Modelos de dados para RAG."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RetrievalResult(BaseModel):
    """Resultado de uma operação de RAG."""
    id: str = Field(..., description="ID do item recuperado")
    type: str = Field(..., description="Tipo: architecture, template, code")
    score: float = Field(..., description="Score de similaridade (0-1)")
    content: Optional[str] = Field(None, description="Conteúdo recuperado")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados")


class RetrievalContext(BaseModel):
    """Contexto recuperado para geração."""
    query: str = Field(..., description="Query original")
    similar_architectures: List[RetrievalResult] = Field(
        default_factory=list,
        description="Arquiteturas similares"
    )
    similar_templates: List[RetrievalResult] = Field(
        default_factory=list,
        description="Templates similares"
    )
    code_snippets: List[RetrievalResult] = Field(
        default_factory=list,
        description="Trechos de código similar"
    )
    connections: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Conexões no grafo"
    )
```

- [ ] **Step 4: Implementar RAGQueryEngine**

```python
# services/knowledge-graph-rag/src/services/rag_query_engine.py
"""Motor de busca RAG (Retrieval-Augmented Generation)."""

from typing import Any, Dict, List, Optional

import structlog
from numpy import array

from ..graph.neo4j_client import Neo4jClient
from ..graph.qdrant_client import QdrantClient
from ..embeddings.openai_embedder import OpenAIEmbedder
from ..models.retrieval import RetrievalResult, RetrievalContext
from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class RAGQueryEngine:
    """Motor de busca RAG combinando Neo4j e Qdrant."""

    def __init__(
        self,
        neo4j: Optional[Neo4jClient] = None,
        qdrant: Optional[QdrantClient] = None,
        embedder: Optional[OpenAIEmbedder] = None
    ):
        """Inicializa o motor RAG.

        Args:
            neo4j: Cliente Neo4j
            qdrant: Cliente Qdrant
            embedder: Serviço de embeddings
        """
        self.neo4j = neo4j
        self.qdrant = qdrant
        self.embedder = embedder
        self.settings = settings

    async def hybrid_search(
        self,
        query: str,
        alpha: float = 0.5,
        limit: int = 10,
        artifact_type: str = "all"
    ) -> List[RetrievalResult]:
        """Executa busca híbrida (graph + vector).

        Args:
            query: Query de busca
            alpha: Peso vector vs graph (0=only graph, 1=only vector)
            limit: Limite de resultados
            artifact_type: Tipo de artefacto

        Returns:
            Lista de resultados ordenados
        """
        # Gerar embedding da query
        query_vector = await self.embedder.embed(query)

        # Busca vectorial (Qdrant)
        vector_results = []
        if self.qdrant and alpha > 0:
            if artifact_type in ["all", "template"]:
                vector_results.extend(
                    await self.qdrant.search_templates(
                        query_vector=query_vector,
                        limit=limit
                    )
                )
            if artifact_type in ["all", "code"]:
                vector_results.extend(
                    await self.qdrant.search_code(
                        query_vector=query_vector,
                        limit=limit
                    )
                )

        # Busca no grafo (Neo4j)
        graph_results = []
        if self.neo4j and alpha < 1:
            # Extrair palavras-chave da query
            keywords = self._extract_keywords(query)

            if artifact_type in ["all", "architecture"]:
                graph_results.extend(
                    await self.neo4j.find_similar_architectures(
                        requirements=keywords,
                        limit=limit
                    )
                )

        # Combinar resultados com pesos
        combined = self._combine_results(
            vector_results=vector_results,
            graph_results=graph_results,
            alpha=alpha
        )

        # Ordenar e limitar
        combined.sort(key=lambda r: r.score, reverse=True)

        return combined[:limit]

    async def retrieve_context(
        self,
        query: str,
        artifact_type: str = "architecture",
        limit: int = 5
    ) -> RetrievalContext:
        """Recupera contexto enriquecido para geração.

        Args:
            query: Query original
            artifact_type: Tipo de artefacto
            limit: Limite por categoria

        Returns:
            Contexto recuperado
        """
        context = RetrievalContext(query=query)

        # Buscar arquiteturas similares
        if artifact_type in ["all", "architecture"]:
            arch_results = await self.hybrid_search(
                query=query,
                alpha=0.5,
                limit=limit,
                artifact_type="architecture"
            )
            context.similar_architectures = arch_results

        # Buscar templates similares
        if artifact_type in ["all", "template"]:
            query_vector = await self.embedder.embed(query)

            if self.qdrant:
                template_results = await self.qdrant.search_templates(
                    query_vector=query_vector,
                    limit=limit
                )
                context.similar_templates = [
                    RetrievalResult(
                        id=r["id"],
                        type="template",
                        score=r["score"],
                        metadata=r["payload"]
                    )
                    for r in template_results
                ]

        # Buscar conexões no grafo
        if self.neo4j and context.similar_architectures:
            first_arch = context.similar_architectures[0]
            connections = await self.neo4j.get_connections_context(
                node_id=first_arch.id
            )
            context.connections = connections

        logger.info(
            "context_retrieved",
            architectures=len(context.similar_architectures),
            templates=len(context.similar_templates),
            connections=len(context.connections)
        )

        return context

    def _extract_keywords(self, query: str) -> List[str]:
        """Extrai palavras-chave da query.

        Args:
            query: Query original

        Returns:
            Lista de palavras-chave
        """
        # Implementação simples - pode ser melhorada com NLP
        stop_words = {"a", "o", "de", "para", "com", "sem", "um", "uma", "create", "make"}
        words = query.lower().split()

        keywords = [w for w in words if len(w) > 3 and w not in stop_words]

        return keywords[:10]  # Limitar a 10 keywords

    def _combine_results(
        self,
        vector_results: List[Dict],
        graph_results: List[Dict],
        alpha: float
    ) -> List[RetrievalResult]:
        """Combina resultados de vector e graph.

        Args:
            vector_results: Resultados da busca vectorial
            graph_results: Resultados da busca no grafo
            alpha: Peso (0=only graph, 1=only vector)

        Returns:
            Lista combinada de resultados
        """
        combined_map = {}

        # Adicionar resultados vectoriais
        for r in vector_results:
            result = RetrievalResult(
                id=r["id"],
                type="vector",
                score=alpha * r["score"],  # Aplicar peso alpha
                metadata=r.get("payload", r)
            )
            combined_map[result.id] = result

        # Adicionar resultados do grafo
        for r in graph_results:
            plan_id = r.get("plan_id", r.get("id"))
            similarity = r.get("similarity", r.get("score", 0))

            if plan_id in combined_map:
                # Combinar scores
                combined_map[plan_id].score += (1 - alpha) * similarity
                combined_map[plan_id].type = "hybrid"
            else:
                result = RetrievalResult(
                    id=plan_id,
                    type="graph",
                    score=(1 - alpha) * similarity,
                    metadata=r
                )
                combined_map[plan_id] = result

        return list(combined_map.values())
```

- [ ] **Step 5: Implementar ContextualRetriever**

```python
# services/knowledge-graph-rag/src/services/contextual_retriever.py
"""Recuperação contextual para geração de código."""

from typing import Any, Dict, List

import structlog

from .rag_query_engine import RAGQueryEngine
from ..models.retrieval import RetrievalContext

logger = structlog.get_logger()


class ContextualRetriever:
    """Recupera contexto enriquecido para geração."""

    def __init__(self, rag_engine: RAGQueryEngine):
        """Inicializa o retriever.

        Args:
            rag_engine: Motor RAG
        """
        self.rag_engine = rag_engine

    async def retrieve_for_code_generation(
        self,
        requirements: List[str],
        tech_stack: Dict[str, str]
    ) -> Dict[str, Any]:
        """Recupera contexto para geração de código.

        Args:
            requirements: Lista de requisitos
            tech_stack: Stack tecnológico

        Returns:
            Contexto enriquecido
        """
        # Construir query a partir dos requisitos
        query = " ".join(requirements[:3])  # Usar os 3 primeiros requisitos

        # Recuperar contexto
        retrieval_context = await self.rag_engine.retrieve_context(
            query=query,
            artifact_type="all",
            limit=5
        )

        # Enriquecer com tech stack
        context = {
            "query": query,
            "tech_stack": tech_stack,
            "similar_architectures": [
                {
                    "id": r.id,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in retrieval_context.similar_architectures
            ],
            "similar_templates": [
                {
                    "id": r.id,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in retrieval_context.similar_templates
            ],
            "connections": retrieval_context.connections
        }

        logger.info(
            "code_generation_context_retrieved",
            architectures_count=len(context["similar_architectures"]),
            templates_count=len(context["similar_templates"])
        )

        return context

    async def retrieve_for_architecture_design(
        self,
        requirements: List[str],
        constraints: List[str]
    ) -> Dict[str, Any]:
        """Recupera contexto para design de arquitetura.

        Args:
            requirements: Lista de requisitos
            constraints: Lista de restrições

        Returns:
            Contexto para arquitetura
        """
        query = " ".join(requirements + constraints)

        context = await self.rag_engine.retrieve_context(
            query=query,
            artifact_type="architecture",
            limit=10
        )

        return {
            "requirements": requirements,
            "constraints": constraints,
            "similar_architectures": [
                {
                    "plan_id": r.id,
                    "similarity": r.score,
                    "type": r.metadata.get("architecture_type", "unknown")
                }
                for r in context.similar_architectures
            ],
            "connections": context.connections
        }
```

- [ ] **Step 6: Criar packages**

```python
# services/knowledge-graph-rag/src/services/__init__.py
"""Serviços RAG."""

from .contextual_retriever import ContextualRetriever
from .rag_query_engine import RAGQueryEngine

__all__ = ["RAGQueryEngine", "ContextualRetriever"]
```

```python
# services/knowledge-graph-rag/src/models/__init__.py
"""Modelos RAG."""

from .retrieval import RetrievalContext, RetrievalResult

__all__ = ["RetrievalContext", "RetrievalResult"]
```

- [ ] **Step 7: Executar testes**

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add services/knowledge-graph-rag/src/services/ \
        services/knowledge-graph-rag/src/models/ \
        services/knowledge-graph-rag/tests/unit/test_rag_query_engine.py
git commit -m "feat(knowledge-graph-rag): implement RAG query engine and contextual retriever"
```

---

## Task 5: Criar API REST do knowledge-graph-rag

**Files:**
- Create: `services/knowledge-graph-rag/src/main.py`
- Create: `services/knowledge-graph-rag/src/api/routers/rag.py`

- [ ] **Step 1: Criar main.py**

```python
# services/knowledge-graph-rag/src/main.py
"""Aplicação FastAPI para Knowledge Graph RAG."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.rag import router as rag_router
from config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    print(f"Starting {settings.api_title} on port {settings.port}")
    yield
    print(f"Stopping {settings.api_title}")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": "knowledge-graph-rag",
        "status": "healthy",
        "version": settings.api_version
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
```

- [ ] **Step 2: Criar router rag.py**

```python
# services/knowledge-graph-rag/src/api/routers/rag.py
"""Router REST para RAG."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...services.rag_query_engine import RAGQueryEngine
from ...services.contextual_retriever import ContextualRetriever
from ...models.retrieval import RetrievalResult

router = APIRouter(prefix="/rag", tags=["rag"])


class SearchRequest(BaseModel):
    """Request para busca RAG."""
    query: str
    alpha: float = 0.5
    limit: int = 10
    artifact_type: str = "all"


class SearchResponse(BaseModel):
    """Response da busca RAG."""
    results: List[dict]
    total_count: int


class CodeContextRequest(BaseModel):
    """Request para contexto de geração de código."""
    requirements: List[str]
    tech_stack: dict


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Executa busca RAG híbrida."""
    try:
        engine = RAGQueryEngine()

        results = await engine.hybrid_search(
            query=request.query,
            alpha=request.alpha,
            limit=request.limit,
            artifact_type=request.artifact_type
        )

        return SearchResponse(
            results=[
                {
                    "id": r.id,
                    "type": r.type,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in results
            ],
            total_count=len(results)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/context/code")
async def get_code_generation_context(request: CodeContextRequest):
    """Obtém contexto para geração de código."""
    try:
        engine = RAGQueryEngine()
        retriever = ContextualRetriever(engine)

        context = await retriever.retrieve_for_code_generation(
            requirements=request.requirements,
            tech_stack=request.tech_stack
        )

        return context

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context retrieval failed: {str(e)}"
        )
```

- [ ] **Step 3: Criar packages**

```python
# services/knowledge-graph-rag/src/api/__init__.py
"""API REST."""
```

```python
# services/knowledge-graph-rag/src/api/routers/__init__.py
"""Routers."""
```

- [ ] **Step 4: Commit**

```bash
git add services/knowledge-graph-rag/src/main.py \
        services/knowledge-graph-rag/src/api/
git commit -m "feat(knowledge-graph-rag): add REST API endpoints"
```

---

## Task 6: Criar deployment do knowledge-graph-rag

**Files:**
- Create: `services/knowledge-graph-rag/deployment/Dockerfile`
- Create: `services/knowledge-graph-rag/deployment/k8s-deployment.yaml`
- Create: `services/knowledge-graph-rag/deployment/k8s-service.yaml`

- [ ] **Step 1: Criar manifestos**

```dockerfile
# services/knowledge-graph-rag/deployment/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --only=main --no-dev

# Copiar código
COPY src/ ./src/

# Expor porta
EXPOSE 8016

# Executar
CMD ["poetry", "run", "python", "src/main.py"]
```

```yaml
# services/knowledge-graph-rag/deployment/k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: knowledge-graph-rag
spec:
  replicas: 2
  selector:
    matchLabels:
      app: knowledge-graph-rag
  template:
    metadata:
      labels:
        app: knowledge-graph-rag
    spec:
      containers:
      - name: knowledge-graph-rag
        image: knowledge-graph-rag:latest
        ports:
        - containerPort: 8016
        env:
        - name: RAG_OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-secrets
              key: openai-api-key
        - name: RAG_NEO4J_URI
          valueFrom:
            configMapKeyRef:
              name: infrastructure
              key: neo4j-uri
        - name: RAG_QDRANT_HOST
          value: "qdrant"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

```yaml
# services/knowledge-graph-rag/deployment/k8s-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: knowledge-graph-rag
spec:
  selector:
    app: knowledge-graph-rag
  ports:
  - port: 8016
    targetPort: 8016
  type: ClusterIP
```

- [ ] **Step 2: Commit**

```bash
git add services/knowledge-graph-rag/deployment/
git commit -m "feat(knowledge-graph-rag): add Kubernetes deployment"
```

---

# PARTE 2: Approval Gateway (8017)

## Task 7: Criar estrutura base do approval-gateway

**Files:**
- Create: `services/approval-gateway/pyproject.toml`
- Create: `services/approval-gateway/src/config/settings.py`

- [ ] **Step 1: Criar pyproject.toml**

```toml
# services/approval-gateway/pyproject.toml
[tool.poetry]
name = "approval-gateway"
version = "0.1.0"
description = "Approval Gateway for Neural Hive-Mind"
authors = ["Neural Hive-Mind Team"]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.104.0"
uvicorn = {extras = ["standard"], version = "^0.24.0"}
pydantic = "^2.0"
pydantic-settings = "^2.0"
motor = "^3.0"
redis = {extras = ["hiredis"], version = "^5.0"}
aiokafka = "^0.9.0"
structlog = "^23.0"
python-jose = {extras = ["cryptography"], version = "^3.3"}
passlib = {extras = ["bcrypt"], version = "^1.7"}
python-multipart = "^0.0.6"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 2: Criar settings.py**

```python
# services/approval-gateway/src/config/settings.py
"""Configurações do Approval Gateway."""

from functools import lru_cache
from datetime import timedelta

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APPROVAL_",
    )

    # API
    api_title: str = "Approval Gateway API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8017

    # JWT
    jwt_secret_key: str = Field(default="change-me", validation_alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_approval_token_expire_hours: int = 24

    # MongoDB
    mongodb_url: str = Field(default="mongodb://localhost:27017", validation_alias="MONGODB_URL")
    mongodb_database: str = "approval_gateway"
    mongodb_collection_artifacts: str = "artifacts"
    mongodb_collection_snapshots: str = "snapshots"

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Kafka
    kafka_bootstrap_servers: str = Field(default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_input_topic: str = "artifacts.for_approval"
    kafka_output_topic: str = "artifacts.approved"
    kafka_dlq_topic: str = "approvals.dlq"

    # Approval
    max_approval_cycles: int = 5
    auto_approve_threshold: float = 0.95
    notify_on_changes: bool = True


@lru_cache
def get_settings() -> Settings:
    """Singleton."""
    return Settings()
```

- [ ] **Step 3: Commit**

```bash
git add services/approval-gateway/pyproject.toml \
        services/approval-gateway/src/config/
git commit -m "feat(approval-gateway): add base structure"
```

---

## Task 8: Implementar modelos de aprovação

**Files:**
- Create: `services/approval-gateway/src/models/__init__.py`
- Create: `services/approval-gateway/src/models/approval.py`
- Create: `services/approval-gateway/src/models/artifact.py`
- Create: `services/approval-gateway/src/models/snapshot.py`

- [ ] **Step 1: Criar modelos**

```python
# services/approval-gateway/src/models/artifact.py
"""Modelos de artefactos."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """Tipo de artefacto."""

    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    DOCUMENTATION = "documentation"
    CODE = "code"
    IAC = "iac"


class ArtifactStatus(str, Enum):
    """Status de artefacto."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Artifact(BaseModel):
    """Artefacto para aprovação."""

    id: str = Field(..., description="ID único")
    artifact_type: ArtifactType = Field(..., description="Tipo do artefacto")
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT)

    # Conteúdo
    title: str = Field(..., description="Título")
    description: str = Field(..., description="Descrição")
    content: str = Field(..., description="Conteúdo do artefacto")
    content_format: str = Field(default="markdown", description="Formato do conteúdo")

    # Metadados
    cognitive_plan_id: Optional[str] = Field(None)
    architecture_plan_id: Optional[str] = Field(None)
    requirements_set_id: Optional[str] = Field(None)

    # Aprovação
    approval_cycle: int = Field(default=0, description="Ciclo atual de aprovação")
    approval_token: Optional[str] = Field(None, description="Token JWT para aprovação")

    # Feedback
    feedback: List[str] = Field(default_factory=list, description="Feedback recebido")
    rejection_reason: Optional[str] = Field(None)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)
    approved_at: Optional[datetime] = Field(None)
    expires_at: Optional[datetime] = Field(None)

    # Submissão
    submitted_by: Optional[str] = Field(None)
    reviewed_by: Optional[str] = Field(None)

    metadata: Dict[str, Any] = Field(default_factory=dict)
```

```python
# services/approval-gateway/src/models/snapshot.py
"""Modelos de snapshots versionados."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SnapshotType(str, Enum):
    """Tipo de snapshot."""

    INITIAL = "initial"
    MODIFIED = "modified"
    FEEDBACK_APPLIED = "feedback_applied"


class ArtifactSnapshot(BaseModel):
    """Snapshot versionado de um artefacto."""

    id: str = Field(..., description="ID único")
    artifact_id: str = Field(..., description="ID do artefacto")
    version: int = Field(..., description="Número da versão")
    snapshot_type: SnapshotType = Field(default=SnapshotType.INITIAL)

    # Conteúdo
    content: str = Field(..., description="Conteúdo snapshotado")
    content_hash: str = Field(..., description="Hash do conteúdo")

    # Metadados
    changes_summary: Optional[str] = Field(None, description="Resumo das mudanças")
    feedback_applied: List[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Criador
    created_by: Optional[str] = Field(None)

    metadata: Dict[str, Any] = Field(default_factory=dict)
```

```python
# services/approval-gateway/src/models/approval.py
"""Modelos de aprovação."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    """Decisão de aprovação."""

    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ApprovalRequest(BaseModel):
    """Request de aprovação."""

    artifact_id: str = Field(..., description="ID do artefacto")
    decision: ApprovalDecision = Field(..., description="Decisão")
    feedback: Optional[str] = Field(None, description="Feedback opcional")
    reviewer: str = Field(..., description="Revisor")
    token: str = Field(..., description="Token de aprovação JWT")


class ApprovalResponse(BaseModel):
    """Response de aprovação."""

    artifact_id: str
    decision: ApprovalDecision
    new_cycle: bool
    approval_token: Optional[str] = None
    message: str
```

- [ ] **Step 2: Criar __init__.py**

```python
# services/approval-gateway/src/models/__init__.py
"""Modelos do Approval Gateway."""

from .approval import ApprovalDecision, ApprovalRequest, ApprovalResponse
from .artifact import Artifact, ArtifactStatus, ArtifactType
from .snapshot import ArtifactSnapshot, SnapshotType

__all__ = [
    "Artifact",
    "ArtifactStatus",
    "ArtifactType",
    "ArtifactSnapshot",
    "SnapshotType",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalDecision",
]
```

- [ ] **Step 3: Commit**

```bash
git add services/approval-gateway/src/models/
git commit -m "feat(approval-gateway): add data models"
```

---

## Task 9: Implementar TokenService (JWT)

**Files:**
- Create: `services/approval-gateway/src/services/__init__.py`
- Create: `services/approval-gateway/src/services/token_service.py`
- Create: `services/approval-gateway/tests/unit/test_token_service.py`

- [ ] **Step 1: Escrever testes**

```python
# services/approval-gateway/tests/unit/test_token_service.py
"""Testes para TokenService."""

import pytest

from approval_gateway.services.token_service import TokenService


@pytest.fixture
def token_service():
    return TokenService(secret_key="test-secret")


def test_create_approval_token(token_service):
    """Testa criação de token de aprovação."""
    token = token_service.create_approval_token(
        artifact_id="ART-001",
        cycle=1
    )

    assert isinstance(token, str)
    assert len(token) > 0


def test_verify_approval_token(token_service):
    """Testa verificação de token."""
    token = token_service.create_approval_token(
        artifact_id="ART-001",
        cycle=1
    )

    payload = token_service.verify_approval_token(token)

    assert payload is not None
    assert payload["artifact_id"] == "ART-001"
    assert payload["cycle"] == 1


def test_verify_invalid_token(token_service):
    """Testa verificação de token inválido."""
    payload = token_service.verify_approval_token("invalid-token")

    assert payload is None
```

- [ ] **Step 2: Executar testes**

Expected: FAIL

- [ ] **Step 3: Implementar TokenService**

```python
# services/approval-gateway/src/services/token_service.py
"""Serviço de tokens JWT para aprovação."""

from datetime import datetime, timedelta
from typing import Dict, Optional

import structlog
from jose import JWTError, jwt

from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class TokenService:
    """Serviço para geração e validação de tokens JWT."""

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = None
    ):
        """Inicializa o serviço.

        Args:
            secret_key: Chave secreta para JWT
            algorithm: Algoritmo JWT
        """
        self.secret_key = secret_key or settings.jwt_secret_key
        self.algorithm = algorithm or settings.jwt_algorithm
        self.approval_token_expire_hours = settings.jwt_approval_token_expire_hours

    def create_approval_token(
        self,
        artifact_id: str,
        cycle: int,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Cria token de aprovação.

        Args:
            artifact_id: ID do artefacto
            cycle: Ciclo de aprovação
            expires_delta: Delta de expiração (opcional)

        Returns:
            Token JWT codificado
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=self.approval_token_expire_hours)

        to_encode = {
            "artifact_id": artifact_id,
            "cycle": cycle,
            "type": "approval",
            "exp": expire,
            "iat": datetime.utcnow()
        }

        encoded = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        logger.info("approval_token_created", artifact_id=artifact_id, cycle=cycle)

        return encoded

    def verify_approval_token(self, token: str) -> Optional[Dict]:
        """Verifica token de aprovação.

        Args:
            token: Token JWT

        Returns:
            Payload decodificado ou None se inválido
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Verificar tipo
            if payload.get("type") != "approval":
                logger.warning("invalid_token_type", token_type=payload.get("type"))
                return None

            return payload

        except JWTError as e:
            logger.warning("token_verification_failed", error=str(e))
            return None

    def create_access_token(
        self,
        data: Dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Cria token de acesso.

        Args:
            data: Dados para incluir no token
            expires_delta: Delta de expiração

        Returns:
            Token JWT
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)

        to_encode = {
            **data,
            "exp": expire,
            "iat": datetime.utcnow()
        }

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_access_token(self, token: str) -> Optional[Dict]:
        """Verifica token de acesso.

        Args:
            token: Token JWT

        Returns:
            Payload decodificado ou None
        """
        try:
            return jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
        except JWTError:
            return None
```

- [ ] **Step 4: Executar testes**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/approval-gateway/src/services/token_service.py \
        services/approval-gateway/tests/unit/test_token_service.py
git commit -m "feat(approval-gateway): implement JWT token service"
```

---

## Task 10: Implementar ApprovalService

**Files:**
- Create: `services/approval-gateway/src/services/approval_service.py`
- Create: `services/approval-gateway/src/services/artifact_store.py`
- Create: `services/approval-gateway/tests/unit/test_approval_service.py`

- [ ] **Step 1: Escrever testes**

```python
# services/approval-gateway/tests/unit/test_approval_service.py
"""Testes para ApprovalService."""

import pytest
from unittest.mock import AsyncMock

from approval_gateway.services.approval_service import ApprovalService
from approval_gateway.models.artifact import Artifact, ArtifactStatus
from approval_gateway.models.approval import ApprovalDecision


@pytest.fixture
def mock_store():
    """Mock para ArtifactStore."""
    store = AsyncMock()
    store.create_artifact = AsyncMock(return_value="ART-001")
    store.get_artifact = AsyncMock(return_value=Artifact(
        id="ART-001",
        artifact_type="requirements",
        title="Test Requirements",
        description="Test",
        content="Content"
    ))
    store.update_artifact = AsyncMock()
    return store


@pytest.fixture
def mock_token_service():
    """Mock para TokenService."""
    service = AsyncMock()
    service.create_approval_token = AsyncMock(return_value="jwt-token")
    service.verify_approval_token = AsyncMock(return_value={
        "artifact_id": "ART-001",
        "cycle": 1
    })
    return service


@pytest.mark.asyncio
async def test_submit_for_approval(mock_store, mock_token_service):
    """Testa submissão para aprovação."""
    service = ApprovalService(
        artifact_store=mock_store,
        token_service=mock_token_service
    )

    artifact = Artifact(
        id="ART-001",
        artifact_type="requirements",
        title="Test",
        description="Test",
        content="Content"
    )

    result = await service.submit_for_approval(artifact, submitted_by="user@example.com")

    assert result["status"] == ArtifactStatus.PENDING_REVIEW
    assert "approval_token" in result


@pytest.mark.asyncio
async def test_approve_artifact(mock_store, mock_token_service):
    """Testa aprovação de artefacto."""
    service = ApprovalService(
        artifact_store=mock_store,
        token_service=mock_token_service
    )

    request = {
        "artifact_id": "ART-001",
        "decision": ApprovalDecision.APPROVED,
        "reviewer": "admin@example.com",
        "token": "jwt-token"
    }

    result = await service.process_approval(request)

    assert result["decision"] == ApprovalDecision.APPROVED
    assert result["new_cycle"] is False
```

- [ ] **Step 2: Executar testes**

Expected: FAIL

- [ ] **Step 3: Implementar ArtifactStore**

```python
# services/approval-gateway/src/services/artifact_store.py
"""Armazenamento de artefactos no MongoDB."""

from typing import List, Optional

import motor.motor_asyncio
import structlog
from bson import ObjectId

from ..models.artifact import Artifact, ArtifactStatus
from ..models.snapshot import ArtifactSnapshot
from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class ArtifactStore:
    """Armazenamento de artefactos."""

    def __init__(self, mongodb_url: str = None):
        """Inicializa o store.

        Args:
            mongodb_url: URL de conexão MongoDB
        """
        self.mongodb_url = mongodb_url or settings.mongodb_url
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db = None
        self.artifacts_collection = settings.mongodb_collection_artifacts
        self.snapshots_collection = settings.mongodb_collection_snapshots

    async def connect(self):
        """Estabelece conexão com MongoDB."""
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongodb_url)
        self.db = self.client[settings.mongodb_database]
        logger.info("artifact_store_connected")

    async def close(self):
        """Fecha conexão."""
        if self.client:
            self.client.close()
            logger.info("artifact_store_closed")

    async def create_artifact(self, artifact: Artifact) -> str:
        """Cria novo artefacto.

        Args:
            artifact: Artefacto a criar

        Returns:
            ID do artefacto criado
        """
        doc = artifact.model_dump()

        result = await self.db[self.artifacts_collection].insert_one(doc)

        logger.info("artifact_created", artifact_id=artifact.id, mongo_id=str(result.inserted_id))

        return artifact.id

    async def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Obtém artefacto por ID.

        Args:
            artifact_id: ID do artefacto

        Returns:
            Artefacto ou None
        """
        doc = await self.db[self.artifacts_collection].find_one({"id": artifact_id})

        if doc:
            doc.pop("_id", None)
            return Artifact(**doc)

        return None

    async def update_artifact(
        self,
        artifact_id: str,
        updates: dict
    ) -> bool:
        """Actualiza artefacto.

        Args:
            artifact_id: ID do artefacto
            updates: Campos a actualizar

        Returns:
            True se actualizado
        """
        result = await self.db[self.artifacts_collection].update_one(
            {"id": artifact_id},
            {"$set": updates}
        )

        logger.info("artifact_updated", artifact_id=artifact_id, modified=result.modified_count)

        return result.modified_count > 0

    async def create_snapshot(self, snapshot: ArtifactSnapshot) -> str:
        """Cria snapshot de artefacto.

        Args:
            snapshot: Snapshot a criar

        Returns:
            ID do snapshot criado
        """
        doc = snapshot.model_dump()

        result = await self.db[self.snapshots_collection].insert_one(doc)

        return snapshot.id

    async def get_snapshots(self, artifact_id: str) -> List[ArtifactSnapshot]:
        """Obtém snapshots de um artefacto.

        Args:
            artifact_id: ID do artefacto

        Returns:
            Lista de snapshots
        """
        cursor = self.db[self.snapshots_collection].find(
            {"artifact_id": artifact_id}
        ).sort("version", 1)

        snapshots = []
        async for doc in cursor:
            doc.pop("_id", None)
            snapshots.append(ArtifactSnapshot(**doc))

        return snapshots

    async def list_pending_artifacts(
        self,
        limit: int = 50
    ) -> List[Artifact]:
        """Lista artefactos pendentes de aprovação.

        Args:
            limit: Limite de resultados

        Returns:
            Lista de artefactos
        """
        cursor = self.db[self.artifacts_collection].find(
            {"status": ArtifactStatus.PENDING_REVIEW}
        ).sort("created_at", 1).limit(limit)

        artifacts = []
        async for doc in cursor:
            doc.pop("_id", None)
            artifacts.append(Artifact(**doc))

        return artifacts
```

- [ ] **Step 4: Implementar ApprovalService**

```python
# services/approval-gateway/src/services/approval_service.py
"""Serviço principal de aprovação."""

from datetime import datetime
from typing import Dict, Optional

import structlog
from passlib.context import CryptContext

from ..models.artifact import Artifact, ArtifactStatus
from ..models.approval import ApprovalDecision, ApprovalRequest, ApprovalResponse
from ..models.snapshot import ArtifactSnapshot, SnapshotType
from .artifact_store import ArtifactStore
from .token_service import TokenService
from ..config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class ApprovalService:
    """Serviço de aprovação de artefactos."""

    def __init__(
        self,
        artifact_store: ArtifactStore = None,
        token_service: TokenService = None
    ):
        """Inicializa o serviço.

        Args:
            artifact_store: Armazenamento de artefactos
            token_service: Serviço de tokens
        """
        self.artifact_store = artifact_store or ArtifactStore()
        self.token_service = token_service or TokenService()
        self.max_cycles = settings.max_approval_cycles
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async def submit_for_approval(
        self,
        artifact: Artifact,
        submitted_by: str
    ) -> Dict:
        """Submete artefacto para aprovação.

        Args:
            artifact: Artefacto a submeter
            submitted_by: Email de quem submeteu

        Returns:
            Dicionário com resultado
        """
        # Criar snapshot inicial
        snapshot = ArtifactSnapshot(
            id=f"SNAP-{artifact.id}-{artifact.approval_cycle}",
            artifact_id=artifact.id,
            version=artifact.approval_cycle + 1,
            snapshot_type=SnapshotType.INITIAL,
            content=artifact.content,
            content_hash=self._hash_content(artifact.content),
            created_by=submitted_by
        )

        await self.artifact_store.create_snapshot(snapshot)

        # Actualizar status
        artifact.status = ArtifactStatus.PENDING_REVIEW
        artifact.submitted_by = submitted_by
        artifact.updated_at = datetime.utcnow()

        # Gerar token de aprovação
        token = self.token_service.create_approval_token(
            artifact_id=artifact.id,
            cycle=artifact.approval_cycle
        )
        artifact.approval_token = token

        # Expiração do token
        from datetime import timedelta
        artifact.expires_at = datetime.utcnow() + timedelta(hours=settings.jwt_approval_token_expire_hours)

        # Salvar artefacto
        if artifact.id == "TEMP":
            # Gerar ID se não existir
            import uuid
            artifact.id = f"ART-{uuid.uuid4().hex[:8].upper()}"

        await self.artifact_store.create_artifact(artifact)

        logger.info(
            "artifact_submitted_for_approval",
            artifact_id=artifact.id,
            cycle=artifact.approval_cycle,
            submitted_by=submitted_by
        )

        return {
            "artifact_id": artifact.id,
            "status": artifact.status,
            "approval_token": token,
            "cycle": artifact.approval_cycle,
            "expires_at": artifact.expires_at.isoformat() if artifact.expires_at else None
        }

    async def process_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Processa decisão de aprovação.

        Args:
            request: Request de aprovação

        Returns:
            Response da aprovação
        """
        # Verificar token
        payload = self.token_service.verify_approval_token(request.token)
        if not payload:
            return ApprovalResponse(
                artifact_id=request.artifact_id,
                decision=request.decision,
                new_cycle=False,
                message="Invalid or expired token"
            )

        # Obter artefacto
        artifact = await self.artifact_store.get_artifact(request.artifact_id)
        if not artifact:
            return ApprovalResponse(
                artifact_id=request.artifact_id,
                decision=request.decision,
                new_cycle=False,
                message="Artifact not found"
            )

        # Verificar ciclo
        if payload["cycle"] != artifact.approval_cycle:
            return ApprovalResponse(
                artifact_id=request.artifact_id,
                decision=request.decision,
                new_cycle=False,
                message="Token cycle mismatch"
            )

        # Processar decisão
        if request.decision == ApprovalDecision.APPROVED:
            return await self._approve_artifact(artifact, request.reviewer)
        elif request.decision == ApprovalDecision.REJECTED:
            return await self._reject_artifact(artifact, request.reviewer, request.feedback)
        else:  # CHANGES_REQUESTED
            return await self._request_changes(artifact, request.reviewer, request.feedback)

    async def _approve_artifact(
        self,
        artifact: Artifact,
        reviewer: str
    ) -> ApprovalResponse:
        """Aprova artefacto.

        Args:
            artifact: Artefacto a aprovar
            reviewer: Revisor

        Returns:
            Response
        """
        artifact.status = ArtifactStatus.APPROVED
        artifact.reviewed_by = reviewer
        artifact.approved_at = datetime.utcnow()
        artifact.updated_at = datetime.utcnow()

        await self.artifact_store.update_artifact(
            artifact.id,
            {
                "status": artifact.status,
                "reviewed_by": artifact.reviewed_by,
                "approved_at": artifact.approved_at,
                "updated_at": artifact.updated_at
            }
        )

        logger.info("artifact_approved", artifact_id=artifact.id, reviewer=reviewer)

        return ApprovalResponse(
            artifact_id=artifact.id,
            decision=ApprovalDecision.APPROVED,
            new_cycle=False,
            message="Artifact approved successfully"
        )

    async def _reject_artifact(
        self,
        artifact: Artifact,
        reviewer: str,
        feedback: Optional[str]
    ) -> ApprovalResponse:
        """Rejeita artefacto.

        Args:
            artifact: Artefacto a rejeitar
            reviewer: Revisor
            feedback: Feedback

        Returns:
            Response
        """
        artifact.status = ArtifactStatus.REJECTED
        artifact.reviewed_by = reviewer
        artifact.rejection_reason = feedback
        artifact.updated_at = datetime.utcnow()

        await self.artifact_store.update_artifact(
            artifact.id,
            {
                "status": artifact.status,
                "reviewed_by": artifact.reviewed_by,
                "rejection_reason": artifact.rejection_reason,
                "updated_at": artifact.updated_at
            }
        )

        logger.info(
            "artifact_rejected",
            artifact_id=artifact.id,
            reviewer=reviewer,
            feedback=feedback
        )

        return ApprovalResponse(
            artifact_id=artifact.id,
            decision=ApprovalDecision.REJECTED,
            new_cycle=False,
            message="Artifact rejected"
        )

    async def _request_changes(
        self,
        artifact: Artifact,
        reviewer: str,
        feedback: Optional[str]
    ) -> ApprovalResponse:
        """Solicita mudanças ao artefacto.

        Args:
            artifact: Artefacto
            reviewer: Revisor
            feedback: Feedback

        Returns:
            Response
        """
        # Verificar limite de ciclos
        if artifact.approval_cycle >= self.max_cycles:
            return ApprovalResponse(
                artifact_id=artifact.id,
                decision=ApprovalDecision.REJECTED,
                new_cycle=False,
                message=f"Maximum approval cycles ({self.max_cycles}) exceeded"
            )

        # Adicionar feedback
        if feedback:
            artifact.feedback.append(feedback)

        # Criar snapshot com feedback aplicado
        snapshot = ArtifactSnapshot(
            id=f"SNAP-{artifact.id}-{artifact.approval_cycle + 1}",
            artifact_id=artifact.id,
            version=artifact.approval_cycle + 1,
            snapshot_type=SnapshotType.FEEDBACK_APPLIED,
            content=artifact.content,
            content_hash=self._hash_content(artifact.content),
            feedback_applied=artifact.feedback.copy()
        )

        await self.artifact_store.create_snapshot(snapshot)

        # Incrementar ciclo
        artifact.approval_cycle += 1
        artifact.status = ArtifactStatus.DRAFT
        artifact.reviewed_by = reviewer
        artifact.updated_at = datetime.utcnow()

        # Gerar novo token
        new_token = self.token_service.create_approval_token(
            artifact_id=artifact.id,
            cycle=artifact.approval_cycle
        )
        artifact.approval_token = new_token

        await self.artifact_store.update_artifact(
            artifact.id,
            {
                "approval_cycle": artifact.approval_cycle,
                "status": artifact.status,
                "reviewed_by": artifact.reviewed_by,
                "feedback": artifact.feedback,
                "approval_token": new_token,
                "updated_at": artifact.updated_at
            }
        )

        logger.info(
            "changes_requested",
            artifact_id=artifact.id,
            new_cycle=artifact.approval_cycle,
            reviewer=reviewer
        )

        return ApprovalResponse(
            artifact_id=artifact.id,
            decision=ApprovalDecision.CHANGES_REQUESTED,
            new_cycle=True,
            message="Changes requested. Please resubmit.",
            approval_token=new_token
        )

    def _hash_content(self, content: str) -> str:
        """Gera hash do conteúdo.

        Args:
            content: Conteúdo a hashar

        Returns:
            Hash SHA256
        """
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()
```

- [ ] **Step 5: Criar package**

```python
# services/approval-gateway/src/services/__init__.py
"""Serviços do Approval Gateway."""

from .approval_service import ApprovalService
from .artifact_store import ArtifactStore
from .token_service import TokenService

__all__ = ["ApprovalService", "ArtifactStore", "TokenService"]
```

- [ ] **Step 6: Executar testes**

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/approval-gateway/src/services/ \
        services/approval-gateway/tests/unit/test_approval_service.py
git commit -m "feat(approval-gateway): implement ApprovalService and ArtifactStore"
```

---

## Task 11: Criar API REST do approval-gateway

**Files:**
- Create: `services/approval-gateway/src/main.py`
- Create: `services/approval-gateway/src/api/middleware/auth.py`
- Create: `services/approval-gateway/src/api/routers/approval.py`

- [ ] **Step 1: Criar middleware de autenticação**

```python
# services/approval-gateway/src/api/middleware/auth.py
"""Middleware de autenticação JWT."""

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ...services.token_service import TokenService

security = HTTPBearer()
token_service = TokenService()


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifica token JWT.

    Args:
        credentials: Credenciais HTTP Bearer

    Returns:
        Payload do token

    Raises:
        HTTPException: Se token inválido
    """
    token = credentials.credentials

    payload = token_service.verify_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
```

- [ ] **Step 2: Criar routers**

```python
# services/approval-gateway/src/api/routers/approval.py
"""Router REST para aprovação."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...services.approval_service import ApprovalService
from ...services.artifact_store import ArtifactStore
from ...models.artifact import Artifact, ArtifactStatus
from ...models.approval import ApprovalRequest, ApprovalResponse

router = APIRouter(prefix="/approval", tags=["approval"])


class SubmitRequest(BaseModel):
    """Request para submissão."""
    artifact_type: str
    title: str
    description: str
    content: str
    submitted_by: str
    cognitive_plan_id: str = None
    architecture_plan_id: str = None


@router.post("/submit")
async def submit_artifact(request: SubmitRequest):
    """Submete artefacto para aprovação."""
    service = ApprovalService()

    artifact = Artifact(
        id="TEMP",  # Será gerado
        artifact_type=request.artifact_type,
        title=request.title,
        description=request.description,
        content=request.content,
        cognitive_plan_id=request.cognitive_plan_id,
        architecture_plan_id=request.architecture_plan_id
    )

    result = await service.submit_for_approval(
        artifact=artifact,
        submitted_by=request.submitted_by
    )

    return result


@router.post("/process")
async def process_approval(request: ApprovalRequest):
    """Processa decisão de aprovação."""
    service = ApprovalService()

    response = await service.process_approval(request)

    return response


@router.get("/pending")
async def list_pending():
    """Lista artefactos pendentes."""
    store = ArtifactStore()
    await store.connect()

    artifacts = await store.list_pending_artifacts(limit=50)

    await store.close()

    return {
        "count": len(artifacts),
        "artifacts": [
            {
                "id": a.id,
                "type": a.artifact_type,
                "title": a.title,
                "cycle": a.approval_cycle,
                "submitted_by": a.submitted_by,
                "created_at": a.created_at.isoformat()
            }
            for a in artifacts
        ]
    }


@router.get("/artifact/{artifact_id}")
async def get_artifact(artifact_id: str):
    """Obtém detalhes de um artefacto."""
    store = ArtifactStore()
    await store.connect()

    artifact = await store.get_artifact(artifact_id)

    await store.close()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found"
        )

    return {
        "id": artifact.id,
        "type": artifact.artifact_type,
        "title": artifact.title,
        "description": artifact.description,
        "content": artifact.content,
        "status": artifact.status,
        "cycle": artifact.approval_cycle,
        "feedback": artifact.feedback,
        "created_at": artifact.created_at.isoformat()
    }


@router.get("/artifact/{artifact_id}/snapshots")
async def get_artifact_snapshots(artifact_id: str):
    """Obtém snapshots de um artefacto."""
    store = ArtifactStore()
    await store.connect()

    snapshots = await store.get_snapshots(artifact_id)

    await store.close()

    return {
        "artifact_id": artifact_id,
        "snapshots": [
            {
                "id": s.id,
                "version": s.version,
                "type": s.snapshot_type,
                "created_at": s.created_at.isoformat(),
                "changes_summary": s.changes_summary
            }
            for s in snapshots
        ]
    }
```

- [ ] **Step 3: Criar main.py**

```python
# services/approval-gateway/src/main.py
"""Aplicação FastAPI para Approval Gateway."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.approval import router as approval_router
from config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    print(f"Starting {settings.api_title} on port {settings.port}")
    yield
    print(f"Stopping {settings.api_title}")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(approval_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    """Health check."""
    return {
        "service": "approval-gateway",
        "status": "healthy",
        "version": settings.api_version
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
```

- [ ] **Step 4: Commit**

```bash
git add services/approval-gateway/src/main.py \
        services/approval-gateway/src/api/
git commit -m "feat(approval-gateway): add REST API endpoints"
```

---

## Task 12: Criar deployment do approval-gateway

**Files:**
- Create: `services/approval-gateway/deployment/Dockerfile`
- Create: `services/approval-gateway/deployment/k8s-deployment.yaml`
- Create: `services/approval-gateway/deployment/k8s-service.yaml`

- [ ] **Step 1: Criar manifestos**

```dockerfile
# services/approval-gateway/deployment/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --only=main --no-dev

COPY src/ ./src/

EXPOSE 8017

CMD ["poetry", "run", "python", "src/main.py"]
```

```yaml
# services/approval-gateway/deployment/k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: approval-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: approval-gateway
  template:
    metadata:
      labels:
        app: approval-gateway
    spec:
      containers:
      - name: approval-gateway
        image: approval-gateway:latest
        ports:
        - containerPort: 8017
        env:
        - name: APPROVAL_JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: jwt-secrets
              key: secret-key
        - name: APPROVAL_MONGODB_URL
          valueFrom:
            configMapKeyRef:
              name: infrastructure
              key: mongodb-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

```yaml
# services/approval-gateway/deployment/k8s-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: approval-gateway
spec:
  selector:
    app: approval-gateway
  ports:
  - port: 8017
    targetPort: 8017
  type: ClusterIP
```

- [ ] **Step 2: Commit final**

```bash
git add services/approval-gateway/deployment/
git commit -m "feat(approval-gateway): add Kubernetes deployment"
```

---

## Resumo dos Serviços Criados

### Knowledge Graph RAG (8016)

**Componentes implementados:**
- `Neo4jClient` - Cliente para operações de grafo (arquiteturas similares, conexões)
- `QdrantClient` - Cliente para busca vetorial (templates, código)
- `OpenAIEmbedder` - Serviço de embeddings com cache Redis
- `RAGQueryEngine` - Motor de busca híbrida (graph + vector)
- `ContextualRetriever` - Recuperação contextual para geração
- REST API: `/api/v1/rag/search`, `/api/v1/rag/context/code`

### Approval Gateway (8017)

**Componentes implementados:**
- `TokenService` - Serviço JWT para tokens de aprovação
- `ArtifactStore` - Armazenamento MongoDB de artefactos e snapshots
- `ApprovalService` - Serviço principal com workflow cíclico
- REST API: `/api/v1/approval/submit`, `/api/v1/approval/process`, `/api/v1/approval/pending`
- Suporte para snapshots versionados
- Limite de ciclos configurável
- Feedback acumulativo

---

## Próximos Passos

**Fase 4: Orchestration Integration**
- Integração de todos os serviços no orchestrator-dynamic
- Fluxo Kafka end-to-end
- Rotas de fallback

**Fase 5: Testing & Hardening**
- Testes E2E do fluxo completo Fluxo G
- Performance tuning
- Security hardening
- Documentação final
