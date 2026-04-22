"""Serviço RAG (Retrieval Augmented Generation) para Knowledge Graph."""

from typing import Any, List, Optional
from openai import AsyncOpenAI
import structlog

from knowledge_graph_rag.models.knowledge import (
    KnowledgeNode,
    KnowledgeRelation,
    GraphQuery,
    GraphSearchResult,
    RAGContext,
    NodeType,
    RelationType,
)
from knowledge_graph_rag.config.settings import get_settings

logger = structlog.get_logger(__name__)


class KnowledgeGraphRAG:
    """Serviço para busca no grafo de conhecimento com RAG."""

    def __init__(
        self, llm_client: Optional[AsyncOpenAI] = None, neo4j_driver: Optional[Any] = None
    ):
        """Inicializa o serviço RAG."""
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._embedding_model = settings.embedding_model
        self._embedding_dim = settings.embedding_dimensions
        self._logger = logger

    async def create_node(
        self, node_type: NodeType, name: str, description: str, properties: dict
    ) -> KnowledgeNode:
        """Cria um novo nó no grafo."""
        import uuid

        node_id = f"{node_type.value.upper()}:{uuid.uuid4().hex[:8]}"

        # Gerar embedding
        embedding = await self._generate_embedding(f"{name}. {description}")

        node = KnowledgeNode(
            id=node_id,
            node_type=node_type,
            name=name,
            description=description,
            properties=properties,
            embedding=embedding,
        )

        # TODO: Persistir no Neo4j e Qdrant
        logger.info("node_created", node_id=node_id, node_type=node_type.value)

        return node

    async def create_relation(
        self, source_id: str, target_id: str, relation_type: RelationType, properties: dict
    ) -> KnowledgeRelation:
        """Cria uma relação entre nós."""
        import uuid

        relation_id = f"REL:{uuid.uuid4().hex[:8]}"

        relation = KnowledgeRelation(
            id=relation_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties,
        )

        # TODO: Persistir no Neo4j
        logger.info("relation_created", relation_id=relation_id)

        return relation

    async def search(self, query: GraphQuery) -> GraphSearchResult:
        """
        Busca nós no grafo usando busca semântica.

        Args:
            query: Query de busca

        Returns:
            Resultado da busca com nós e relações
        """
        self._logger.info("searching_graph", query=query.query_text)

        # Gerar embedding da query
        query_embedding = await self._generate_embedding(query.query_text)

        # TODO: Buscar no Qdrant por similaridade de cosseno
        # Por ora, retorna placeholder
        nodes = []
        relations = []

        return GraphSearchResult(
            nodes=nodes, relations=relations, total_found=0, query_id=f"Q-{query.query_text[:20]}"
        )

    async def generate_rag_context(
        self, query: str, retrieved_nodes: List[KnowledgeNode]
    ) -> RAGContext:
        """
        Gera contexto para RAG.

        Args:
            query: Query original
            retrieved_nodes: Nós recuperados

        Returns:
            Contexto RAG estruturado
        """
        context_parts = []

        for node in retrieved_nodes:
            context_parts.append(f"**{node.name}** ({node.node_type.value})")
            if node.description:
                context_parts.append(node.description)
            if node.properties:
                for key, value in node.properties.items():
                    context_parts.append(f"- {key}: {value}")

        context_text = "\n\n".join(context_parts)

        # Calcular scores de relevância
        relevance_scores = [self._calculate_relevance(query, node) for node in retrieved_nodes]

        return RAGContext(
            query=query,
            retrieved_nodes=retrieved_nodes,
            context_text=context_text,
            relevance_scores=relevance_scores,
        )

    async def query_with_rag(self, query_text: str, context: Optional[str] = None) -> str:
        """
        Realiza query usando RAG.

        Args:
            query_text: Texto da query
            context: Contexto adicional

        Returns:
            Resposta gerada com contexto do grafo
        """
        # Buscar nós relevantes
        graph_query = GraphQuery(query_text=query_text)
        search_result = await self.search(graph_query)

        if not search_result.nodes:
            return "Nenhum resultado encontrado no grafo de conhecimento."

        # Gerar contexto RAG
        rag_context = await self.generate_rag_context(
            query=query_text, retrieved_nodes=search_result.nodes
        )

        # Construir prompt com contexto
        prompt = f"""
Responda à seguinte query considerando o contexto do grafo de conhecimento:

**Contexto do Grafo:**
{rag_context.context_text}

**Query:**
{query_text}

{context or ""}

Baseado no contexto acima, forneça uma resposta precisa e detalhada.
"""

        # Chamar LLM
        response = await self._llm_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente especialista em Neural Hive-Mind.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        return response.choices[0].message.content

    async def _generate_embedding(self, text: str) -> List[float]:
        """Gera embedding usando OpenAI."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=get_settings().openai_api_key)

            response = await client.embeddings.create(model=self._embedding_model, input=text)

            return response.data[0].embedding

        except Exception as e:
            self._logger.error("embedding_generation_failed", error=str(e))
            # Retornar embedding zero
            return [0.0] * self._embedding_dim

    def _calculate_relevance(self, query: str, node: KnowledgeNode) -> float:
        """Calcula relevância de um nó para a query."""
        query_lower = query.lower()
        score = 0.0

        # Nome exato
        if node.name.lower() in query_lower:
            score += 0.5

        # Palavras na descrição
        if node.description:
            desc_words = set(node.description.lower().split())
            query_words = set(query_lower.split())
            overlap = desc_words & query_words
            if overlap:
                score += 0.3 * (len(overlap) / len(query_words))

        # Propriedades
        for key, value in node.properties.items():
            if str(value).lower() in query_lower:
                score += 0.1

        return min(score, 1.0)
