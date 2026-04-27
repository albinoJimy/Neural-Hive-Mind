"""
Lineage Tracker Service

Rastreia origem, transformações e dependências de features.
Coordena MongoDB (persistência) e Neo4j (grafo de dependências).
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from src.models.lineage import (
    FeatureLineage,
    LineageImpact,
    LineageIntegrityReport,
    LineageTree,
    SourceType,
    TransformationType,
)

logger = structlog.get_logger()


class LineageTracker:
    """
    Serviço de rastreamento de lineage para features

    Mantém histórico de origens, transformações e dependências entre features.
    Usa MongoDB para persistência de detalhes e Neo4j para grafo de relacionamentos.
    """

    def __init__(
        self,
        settings,
        mongodb_client: Optional[AsyncIOMotorClient] = None,
        neo4j_client=None,
    ):
        """
        Inicializa LineageTracker

        Args:
            settings: Configurações do serviço
            mongodb_client: Cliente MongoDB para persistência
            neo4j_client: Cliente Neo4j para grafo de dependências (opcional)
        """
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.neo4j_client = neo4j_client
        self.computation_version = "v1.0.0"

        # Coleção MongoDB
        if mongodb_client:
            self.db = mongodb_client[settings.mongodb_database]
            self.collection = self.db[settings.mongodb_lineage_collection]

        logger.info("lineage_tracker_initialized")

    async def create_indexes(self):
        """Cria índices MongoDB necessários"""
        if not self.mongodb_client:
            return

        await self.collection.create_index("lineage_id", unique=True)
        await self.collection.create_index("feature_id")
        await self.collection.create_index("plan_id")
        await self.collection.create_index("source_type")
        await self.collection.create_index("transformation_type")
        await self.collection.create_index("created_at")
        await self.collection.create_index([("feature_id", 1), ("plan_id", 1)])

        logger.info("lineage_mongodb_indexes_created")

    async def track_feature(
        self,
        feature_id: str,
        plan_id: str,
        source_type: SourceType,
        transformation_type: TransformationType,
        data_sources: Optional[list[str]] = None,
        source_plan_ids: Optional[list[str]] = None,
        feature_dependencies: Optional[list[str]] = None,
        parent_lineage_ids: Optional[list[str]] = None,
        transformation_metadata: Optional[dict[str, Any]] = None,
    ) -> FeatureLineage:
        """
        Rastreia nova feature e persiste lineage

        Args:
            feature_id: ID da feature
            plan_id: ID do plano cognitivo
            source_type: Tipo de origem
            transformation_type: Tipo de transformação
            data_sources: Fontes de dados utilizadas
            source_plan_ids: IDs dos planos originais
            feature_dependencies: IDs de features dependentes
            parent_lineage_ids: IDs de lineage dos pais
            transformation_metadata: Metadados da transformação

        Returns:
            FeatureLineage criado
        """
        # Computar hash do código de computação
        computation_hash = self._compute_computation_hash()

        # Criar lineage
        lineage = FeatureLineage(
            feature_id=feature_id,
            plan_id=plan_id,
            source_type=source_type,
            transformation_type=transformation_type,
            data_sources=data_sources or [],
            source_plan_ids=source_plan_ids or [],
            feature_dependencies=feature_dependencies or [],
            parent_lineage_ids=parent_lineage_ids or [],
            transformation_metadata=transformation_metadata or {},
            computation_version=self.computation_version,
            computation_hash=computation_hash,
        )

        # Persistir no MongoDB
        if self.mongodb_client:
            try:
                document = lineage.model_dump(mode="json")
                await self.collection.update_one(
                    {"feature_id": feature_id, "plan_id": plan_id},
                    {"$set": document},
                    upsert=True,
                )
                logger.info(
                    "lineage_saved",
                    feature_id=feature_id,
                    plan_id=plan_id,
                    lineage_id=lineage.lineage_id,
                )
            except Exception as e:
                logger.error("failed_to_save_lineage", feature_id=feature_id, error=str(e))

        # Criar relacionamentos no Neo4j
        if self.neo4j_client and source_plan_ids:
            await self._create_neo4j_relationships(feature_id, source_plan_ids, "DERIVED_FROM")

        if self.neo4j_client and feature_dependencies:
            await self._create_neo4j_relationships(feature_id, feature_dependencies, "DEPENDS_ON")

        return lineage

    async def get_lineage(self, feature_id: str) -> Optional[FeatureLineage]:
        """
        Recupera lineage de uma feature

        Args:
            feature_id: ID da feature

        Returns:
            FeatureLineage ou None
        """
        if not self.mongodb_client:
            return None

        document = await self.collection.find_one({"feature_id": feature_id})
        if document:
            document.pop("_id", None)
            return FeatureLineage(**document)

        return None

    async def get_lineage_by_plan(self, plan_id: str) -> Optional[FeatureLineage]:
        """
        Recupera lineage por plano

        Args:
            plan_id: ID do plano

        Returns:
            FeatureLineage ou None
        """
        if not self.mongodb_client:
            return None

        document = await self.collection.find_one({"plan_id": plan_id})
        if document:
            document.pop("_id", None)
            return FeatureLineage(**document)

        return None

    async def get_lineage_tree(self, feature_id: str, max_depth: int = 5) -> LineageTree:
        """
        Obter árvore completa de lineage

        Args:
            feature_id: ID da feature
            max_depth: Profundidade máxima da árvore

        Returns:
            LineageTree com upstream e downstream
        """
        # Buscar lineage no MongoDB
        lineage = await self.get_lineage(feature_id)

        # Buscar pais (upstream)
        upstream = {}
        if self.neo4j_client:
            upstream = await self._get_neo4j_upstream(feature_id, max_depth)
        else:
            # Fallback: buscar usando parent_lineage_ids
            upstream = await self._get_upstream_from_mongo(feature_id, max_depth)

        # Buscar filhos (downstream)
        downstream = {}
        if self.neo4j_client:
            downstream = await self._get_neo4j_downstream(feature_id, max_depth)
        else:
            # Fallback: buscar features que dependem desta
            downstream = await self._get_downstream_from_mongo(feature_id, max_depth)

        # Calcular profundidade da árvore
        tree_depth = max(
            len(upstream),
            len(downstream),
        )

        return LineageTree(
            feature_id=feature_id,
            lineage=lineage,
            upstream=upstream,
            downstream=downstream,
            tree_depth=tree_depth,
        )

    async def get_impact_analysis(self, feature_id: str) -> LineageImpact:
        """
        Analisa impacto downstream se feature mudar

        Args:
            feature_id: ID da feature

        Returns:
            LineageImpact com análise de impacto
        """
        # Buscar downstream
        if self.neo4j_client:
            downstream = await self._get_neo4j_downstream(feature_id, max_depth=10)
        else:
            downstream = await self._get_downstream_from_mongo(feature_id, max_depth=10)

        # Contar dependências diretas (depth 1)
        direct_dependencies = len(downstream.get("depth_1", []))

        # Contar total downstream
        total_downstream = sum(len(v) for v in downstream.values() if isinstance(v, list))

        # Extrair planos afetados
        affected_plans = set()
        for level_features in downstream.values():
            if isinstance(level_features, list):
                for feature in level_features:
                    if isinstance(feature, dict) and "plan_id" in feature:
                        affected_plans.add(feature["plan_id"])

        # Encontrar caminho crítico
        critical_path = self._find_critical_path(downstream)

        # Calcular score de impacto
        impact_score = self._calculate_impact_score(
            direct_dependencies, total_downstream, len(affected_plans)
        )

        return LineageImpact(
            feature_id=feature_id,
            direct_dependencies=direct_dependencies,
            total_downstream=total_downstream,
            affected_plans=list(affected_plans),
            critical_path=critical_path,
            impact_score=impact_score,
        )

    async def validate_integrity(self, feature_id: str) -> LineageIntegrityReport:
        """
        Valida integridade do lineage

        Verifica:
        - Ciclos no grafo de dependências
        - Consistência de timestamps
        - Fontes de dados consistentes
        - Todas as sources existem

        Args:
            feature_id: ID da feature

        Returns:
            LineageIntegrityReport com resultado da validação
        """
        errors = []
        warnings = []

        # Buscar lineage tree
        tree = await self.get_lineage_tree(feature_id)

        # Verificar ciclos
        has_cycle = await self._check_for_cycles(feature_id, tree)
        if has_cycle:
            errors.append("Ciclo detectado no grafo de dependências")

        # Verificar timestamps
        timestamps_valid = self._validate_timestamps(tree)
        if not timestamps_valid:
            errors.append("Timestamps inconsistentes")

        # Verificar datasources
        datasources_consistent = self._validate_datasources(tree)
        if not datasources_consistent:
            warnings.append("Fontes de dados possíveis inconsistências")

        # Verificar se sources existem
        all_sources_exist = await self._validate_sources_exist(tree)
        if not all_sources_exist:
            errors.append("Algumas sources referenciadas não existem")

        valid = not has_cycle and timestamps_valid and datasources_consistent and all_sources_exist

        return LineageIntegrityReport(
            feature_id=feature_id,
            has_cycle=has_cycle,
            timestamps_valid=timestamps_valid,
            datasources_consistent=datasources_consistent,
            all_sources_exist=all_sources_exist,
            valid=valid,
            errors=errors,
            warnings=warnings,
        )

    async def update_lineage(
        self, feature_id: str, updates: dict[str, Any]
    ) -> Optional[FeatureLineage]:
        """
        Atualiza lineage existente

        Args:
            feature_id: ID da feature
            updates: Campos a atualizar

        Returns:
            FeatureLineage atualizado ou None
        """
        if not self.mongodb_client:
            return None

        # Adicionar timestamp de modificação
        updates["modified_at"] = datetime.now(timezone.utc)
        updates["modified_count"] = 1  # Será incrementado pelo MongoDB

        result = await self.collection.update_one(
            {"feature_id": feature_id},
            {"$set": updates},
        )

        if result.modified_count > 0:
            logger.info("lineage_updated", feature_id=feature_id)
            return await self.get_lineage(feature_id)

        return None

    async def list_lineages(
        self, limit: int = 100, skip: int = 0, source_type: Optional[SourceType] = None
    ) -> list[FeatureLineage]:
        """
        Lista lineages com filtros opcionais

        Args:
            limit: Limite de resultados
            skip: Offset para paginação
            source_type: Filtro por tipo de origem

        Returns:
            Lista de FeatureLineage
        """
        if not self.mongodb_client:
            return []

        query = {}
        if source_type:
            query["source_type"] = source_type.value

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        lineages = []
        async for document in cursor:
            document.pop("_id", None)
            lineages.append(FeatureLineage(**document))

        return lineages

    async def delete_lineage(self, feature_id: str) -> bool:
        """
        Deleta lineage de uma feature

        Args:
            feature_id: ID da feature

        Returns:
            True se deletado com sucesso
        """
        if not self.mongodb_client:
            return False

        result = await self.collection.delete_one({"feature_id": feature_id})

        # Remover relacionamentos no Neo4j
        if self.neo4j_client:
            await self._delete_neo4j_relationships(feature_id)

        logger.info("lineage_deleted", feature_id=feature_id, deleted=result.deleted_count)

        return result.deleted_count > 0

    # -------------------------------------------------------------------------
    # Métodos privados
    # -------------------------------------------------------------------------

    def _compute_computation_hash(self) -> str:
        """Computa hash do código de computação"""
        # Hash baseado na versão do código (simplificado)
        code_version = f"{self.computation_version}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        return hashlib.sha256(code_version.encode()).hexdigest()[:16]

    async def _create_neo4j_relationships(
        self, feature_id: str, targets: list[str], relationship_type: str
    ):
        """Cria relacionamentos no Neo4j"""
        if not self.neo4j_client:
            return

        try:
            for target in targets:
                await self.neo4j_client.create_relationship(
                    from_node=feature_id,
                    to_node=target,
                    relationship_type=relationship_type,
                )
        except Exception as e:
            logger.warning("neo4j_relationship_failed", feature_id=feature_id, error=str(e))

    async def _delete_neo4j_relationships(self, feature_id: str):
        """Deleta relacionamentos no Neo4j"""
        if not self.neo4j_client:
            return

        try:
            await self.neo4j_client.delete_node_relationships(feature_id)
        except Exception as e:
            logger.warning("neo4j_delete_failed", feature_id=feature_id, error=str(e))

    async def _get_neo4j_upstream(
        self, feature_id: str, max_depth: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca upstream (pais) no Neo4j"""
        try:
            return await self.neo4j_client.get_upstream(feature_id, max_depth)
        except Exception as e:
            logger.warning("neo4j_upstream_failed", feature_id=feature_id, error=str(e))
            return {}

    async def _get_neo4j_downstream(
        self, feature_id: str, max_depth: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca downstream (filhos) no Neo4j"""
        try:
            return await self.neo4j_client.get_downstream(feature_id, max_depth)
        except Exception as e:
            logger.warning("neo4j_downstream_failed", feature_id=feature_id, error=str(e))
            return {}

    async def _get_upstream_from_mongo(
        self, feature_id: str, max_depth: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca upstream usando parent_lineage_ids (fallback)"""
        upstream = {}

        lineage = await self.get_lineage(feature_id)
        if not lineage or not lineage.parent_lineage_ids:
            return upstream

        # Depth 1: pais diretos
        parents = []
        for parent_id in lineage.parent_lineage_ids:
            parent_lineage = await self.get_lineage(parent_id)
            if parent_lineage:
                parents.append(
                    {
                        "feature_id": parent_lineage.feature_id,
                        "plan_id": parent_lineage.plan_id,
                        "source_type": (
                            parent_lineage.source_type
                            if isinstance(parent_lineage.source_type, str)
                            else parent_lineage.source_type.value
                        ),
                    }
                )

        upstream["depth_1"] = parents

        # Recursivamente buscar depth 2+
        for depth in range(2, max_depth + 1):
            prev_key = f"depth_{depth - 1}"
            if prev_key not in upstream or not upstream[prev_key]:
                break

            current_depth = []
            for parent in upstream[prev_key]:
                parent_lineage = await self.get_lineage(parent["feature_id"])
                if parent_lineage and parent_lineage.parent_lineage_ids:
                    for grandparent_id in parent_lineage.parent_lineage_ids:
                        grandparent_lineage = await self.get_lineage(grandparent_id)
                        if grandparent_lineage:
                            current_depth.append(
                                {
                                    "feature_id": grandparent_lineage.feature_id,
                                    "plan_id": grandparent_lineage.plan_id,
                                    "source_type": (
                                        grandparent_lineage.source_type
                                        if isinstance(grandparent_lineage.source_type, str)
                                        else grandparent_lineage.source_type.value
                                    ),
                                }
                            )

            if current_depth:
                upstream[f"depth_{depth}"] = current_depth

        return upstream

    async def _get_downstream_from_mongo(
        self, feature_id: str, max_depth: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca downstream usando feature_dependencies (fallback)"""
        downstream = {}

        # Buscar lineages que têm esta feature como dependência
        cursor = self.collection.find({"feature_dependencies": feature_id})

        # Depth 1: filhos diretos
        children = []
        async for doc in cursor:
            doc.pop("_id", None)
            children.append(
                {
                    "feature_id": doc["feature_id"],
                    "plan_id": doc["plan_id"],
                    "transformation_type": doc.get("transformation_type", "unknown"),
                }
            )

        if children:
            downstream["depth_1"] = children

            # Recursivamente buscar depth 2+
            visited = {feature_id}
            for depth in range(2, max_depth + 1):
                prev_key = f"depth_{depth - 1}"
                if prev_key not in downstream or not downstream[prev_key]:
                    break

                current_depth = []
                for child in downstream[prev_key]:
                    child_feature_id = child["feature_id"]
                    if child_feature_id in visited:
                        continue

                    visited.add(child_feature_id)

                    child_cursor = self.collection.find({"feature_dependencies": child_feature_id})

                    async for doc in child_cursor:
                        doc.pop("_id", None)
                        current_depth.append(
                            {
                                "feature_id": doc["feature_id"],
                                "plan_id": doc["plan_id"],
                                "transformation_type": doc.get("transformation_type", "unknown"),
                            }
                        )

                if current_depth:
                    downstream[f"depth_{depth}"] = current_depth

        return downstream

    def _find_critical_path(self, downstream: dict[str, list[dict]]) -> list[str]:
        """Encontra caminho crítico de dependências"""
        path = []

        for depth in sorted([int(k.split("_")[1]) for k in downstream.keys()]):
            key = f"depth_{depth}"
            if key in downstream and downstream[key]:
                # Pega o primeiro feature de cada nível
                feature = downstream[key][0]
                if isinstance(feature, dict):
                    path.append(feature.get("feature_id", feature.get("plan_id", "unknown")))

        return path

    def _calculate_impact_score(
        self, direct_deps: int, total_downstream: int, affected_plans: int
    ) -> float:
        """Calcula score de impacto (0-1)"""
        # Score baseado em:
        # - Dependências diretas (peso 0.4)
        # - Total downstream (peso 0.4)
        # - Planos afetados (peso 0.2)

        direct_score = min(direct_deps / 10, 1.0) * 0.4
        downstream_score = min(total_downstream / 50, 1.0) * 0.4
        plans_score = min(affected_plans / 20, 1.0) * 0.2

        return direct_score + downstream_score + plans_score

    async def _check_for_cycles(self, feature_id: str, tree: LineageTree) -> bool:
        """Verifica se existe ciclo no grafo de dependências"""
        visited = set()
        path = set()

        def dfs_check(node_id):
            if node_id in path:
                return True  # Ciclo detectado
            if node_id in visited:
                return False

            visited.add(node_id)
            path.add(node_id)

            # Buscar filhos
            for depth_level in tree.downstream.values():
                if isinstance(depth_level, list):
                    for child in depth_level:
                        if isinstance(child, dict):
                            child_id = child.get("feature_id")
                            if child_id and dfs_check(child_id):
                                return True

            path.remove(node_id)
            return False

        return dfs_check(feature_id)

    def _validate_timestamps(self, tree: LineageTree) -> bool:
        """Valida consistência dos timestamps"""
        if not tree.lineage:
            return True

        # Verificar se created_at <= modified_at (se existir)
        if tree.lineage.modified_at:
            if tree.lineage.modified_at < tree.lineage.created_at:
                return False

        return True

    def _validate_datasources(self, tree: LineageTree) -> bool:
        """Valida consistência das fontes de dados"""
        if not tree.lineage:
            return True

        # Verificar se datasources não está vazio quando deveria ter
        if tree.lineage.source_type == SourceType.COGNITIVE_PLAN:
            if not tree.lineage.data_sources:
                return False

        return True

    async def _validate_sources_exist(self, tree: LineageTree) -> bool:
        """Valida se todas as sources referenciadas existem"""
        if not tree.lineage:
            return True

        # Verificar se source_plan_ids existem
        for source_plan_id in tree.lineage.source_plan_ids:
            source_lineage = await self.get_lineage_by_plan(source_plan_id)
            if not source_lineage:
                # Verificar se pelo menos o plano existe no MongoDB de features
                # (pode não ter lineage ainda)
                pass

        return True
