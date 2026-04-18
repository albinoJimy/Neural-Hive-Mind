"""Repositório para planos arquiteturais."""

from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError
from structlog import get_logger

from src.config.settings import get_settings
from src.models.architecture import ArchitecturePlan, ArchitectureType
from src.repositories.base import BaseRepository

logger = get_logger(__name__)


class ArchitectureRepository(BaseRepository[ArchitecturePlan]):
    """Repositório para planos de arquiteturais."""

    def __init__(self):
        """Inicializa repositório de planos arquiteturais."""
        settings = get_settings()
        super().__init__(settings.mongodb.collection_architecture, ArchitecturePlan)

    async def _ensure_indexes(self):
        """Garante que índices MongoDB existam."""
        try:
            # Índices para campos estendidos do Fluxo G
            await self.collection.create_index([("bounded_contexts.name", 1)])
            await self.collection.create_index([("tech_stack.category", 1)])
            await self.collection.create_index([("diagrams.type", 1)])
            logger.info("mongodb_indexes_created")
        except Exception as e:
            logger.warning("mongodb_indexes_creation_failed", error=str(e))

    def _validate_extended_fields(self, plan: ArchitecturePlan):
        """Valida campos estendidos do Fluxo G.

        Args:
            plan: Plano arquitetural a validar

        Raises:
            ValueError: Se campos estendidos forem inválidos
        """
        # Validar bounded_contexts
        if plan.bounded_contexts is not None:
            if not plan.bounded_contexts:
                raise ValueError("bounded_contexts cannot be empty list")
            for i, ctx in enumerate(plan.bounded_contexts):
                if not ctx.name or not ctx.name.strip():
                    raise ValueError(f"bounded_contexts[{i}].name cannot be empty")
                if not ctx.description or not ctx.description.strip():
                    raise ValueError(f"bounded_contexts[{i}].description cannot be empty")

        # Validar tech_stack
        if plan.tech_stack is not None:
            if not plan.tech_stack:
                raise ValueError("tech_stack cannot be empty list")
            for i, choice in enumerate(plan.tech_stack):
                if not choice.category or not choice.category.strip():
                    raise ValueError(f"tech_stack[{i}].category cannot be empty")
                if not choice.name or not choice.name.strip():
                    raise ValueError(f"tech_stack[{i}].name cannot be empty")

        # Validar diagrams
        if plan.diagrams is not None:
            if not plan.diagrams:
                raise ValueError("diagrams cannot be empty list")
            for i, diagram in enumerate(plan.diagrams):
                if not diagram.type:
                    raise ValueError(f"diagrams[{i}].type cannot be empty")

    def _doc_to_model(self, doc: dict) -> ArchitecturePlan:
        """Converte documento MongoDB para modelo Pydantic."""
        doc_copy = doc.copy()
        doc_id = doc_copy.pop("_id", None)
        if doc_id:
            doc_copy["plan_id"] = doc_id
        return ArchitecturePlan(**doc_copy)

    async def create(self, plan: ArchitecturePlan) -> str:
        """Cria novo plano arquitetural.

        Args:
            plan: Plano arquitetural a criar

        Returns:
            ID do plano criado

        Raises:
            ValueError: Se plano for inválido ou já existir
        """
        # Validar campos estendidos
        self._validate_extended_fields(plan)

        doc = plan.model_dump(by_alias=True, exclude_none=True)
        doc["_id"] = plan.plan_id
        doc["created_at"] = datetime.now(UTC)

        try:
            await self.collection.insert_one(doc)

            # Criar índices (background, não bloqueia criação)
            await self._ensure_indexes()

            return plan.plan_id
        except DuplicateKeyError as e:
            raise ValueError(f"Plano com ID {plan.plan_id} já existe") from e

    async def get_by_plan_id(self, plan_id: str) -> ArchitecturePlan | None:
        """Busca plano por plan_id."""
        doc = await self.collection.find_one({"_id": plan_id})
        if doc:
            return self._doc_to_model(doc)
        return None

    async def get_by_cognitive_plan_id(self, cognitive_plan_id: str) -> list[ArchitecturePlan]:
        """Busca planos por cognitive_plan_id."""
        cursor = self.collection.find({"cognitive_plan_id": cognitive_plan_id})
        docs = await cursor.to_list(length=100)
        return [self._doc_to_model(doc) for doc in docs]

    async def list_by_type(
        self, arch_type: ArchitectureType, limit: int = 50
    ) -> list[ArchitecturePlan]:
        """Lista planos por tipo de arquitetura."""
        cursor = self.collection.find({"architecture_type": arch_type.value}).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def update_rationale(self, plan_id: str, rationale: str) -> bool:
        """Atualiza rationale de um plano."""
        result = await self.collection.update_one(
            {"_id": plan_id},
            {
                "$set": {
                    "rationale": rationale,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count > 0

    async def list_by_bounded_context(
        self, context_name: str, limit: int = 50
    ) -> list[ArchitecturePlan]:
        """Lista planos que contêm um bounded context específico.

        Args:
            context_name: Nome do bounded context
            limit: Limite de resultados

        Returns:
            Lista de planos com o bounded context
        """
        cursor = self.collection.find({"bounded_contexts.name": context_name}).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def list_by_diagram_type(
        self, diagram_type: str, limit: int = 50
    ) -> list[ArchitecturePlan]:
        """Lista planos que contêm um tipo de diagrama específico.

        Args:
            diagram_type: Tipo de diagrama
            limit: Limite de resultados

        Returns:
            Lista de planos com o diagrama
        """
        cursor = self.collection.find({"diagrams.type": diagram_type}).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]
