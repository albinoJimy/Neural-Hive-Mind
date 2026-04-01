import asyncio
import hashlib
import json
from typing import Any, Dict, List, Optional

import structlog

from .data_fusion_engine import DataFusionEngine

logger = structlog.get_logger()


class QueryEngine:
    def __init__(
        self,
        clickhouse_client,
        neo4j_client,
        elasticsearch_client,
        prometheus_client,
        redis_client,
        postgresql_client=None,
        data_fusion_engine=None,
    ):
        self.clickhouse = clickhouse_client
        self.neo4j = neo4j_client
        self.elasticsearch = elasticsearch_client
        self.prometheus = prometheus_client
        self.redis = redis_client
        self.postgresql = postgresql_client
        self.data_fusion = data_fusion_engine or DataFusionEngine()

    async def query_multi_source(self, query_spec: Dict) -> Dict:
        """Consultar múltiplas fontes em paralelo"""
        try:
            sources = query_spec.get("sources", [])
            use_cache = query_spec.get("use_cache", True)
            enable_fusion = query_spec.get("enable_fusion", False)

            # Gerar chave de cache
            query_key = self._generate_query_key(query_spec)

            # Verificar cache
            if use_cache:
                cached = await self.redis.get_cached_query_result(query_key)
                if cached:
                    logger.debug("query_cache_hit", query_key=query_key)
                    return {"results": cached, "cached": True}

            # Executar consultas em paralelo
            tasks = []
            for source in sources:
                if source == "clickhouse":
                    tasks.append(self._query_clickhouse(query_spec))
                elif source == "neo4j":
                    tasks.append(self._query_neo4j(query_spec))
                elif source == "elasticsearch":
                    tasks.append(self._query_elasticsearch(query_spec))
                elif source == "prometheus":
                    tasks.append(self._query_prometheus(query_spec))
                elif source == "postgresql" and self.postgresql:
                    tasks.append(self._query_postgresql(query_spec))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Consolidar resultados
            source_results = dict(zip(sources, results))

            # Aplicar fusão de dados se solicitado
            if enable_fusion and len(sources) > 1:
                query_request = self._create_query_request(query_spec)
                fused_result = await self.data_fusion.fuse_sources(query_request, source_results)
                consolidated = {"fused": fused_result.to_dict(), "by_source": source_results}
            else:
                consolidated = self.consolidate_results(source_results)

            # Cachear resultado
            if use_cache:
                await self.redis.cache_query_result(query_key, consolidated, ttl=600)

            return {"results": consolidated, "cached": False}

        except Exception as e:
            logger.error("query_multi_source_failed", error=str(e))
            return {"results": {}, "error": str(e)}

    def _create_query_request(self, query_spec: Dict):
        """Cria QueryRequest a partir do query_spec."""

        from ..models.query_request import QueryRequest

        return QueryRequest(
            query_id=query_spec.get("query_id", "auto"),
            plan_id=query_spec.get("plan_id"),
            analyst_types=query_spec.get("analyst_types", []),
            time_window=query_spec.get("time_window"),
            filters=query_spec.get("filters", {}),
        )

    async def _query_clickhouse(self, query_spec: Dict) -> Dict:
        """Consultar ClickHouse"""
        try:
            time_window = query_spec.get("time_window", {})
            query_spec.get("metrics", [])

            result = await self.clickhouse.get_execution_statistics(
                time_window.get("start"), time_window.get("end")
            )
            return {"source": "clickhouse", "data": result}
        except Exception as e:
            logger.error("clickhouse_query_failed", error=str(e))
            return {"source": "clickhouse", "error": str(e)}

    async def _query_neo4j(self, query_spec: Dict) -> Dict:
        """Consultar Neo4j"""
        try:
            filters = query_spec.get("filters", {})
            intent_id = filters.get("intent_id")

            if intent_id:
                result = await self.neo4j.analyze_intent_flow(intent_id)
                return {"source": "neo4j", "data": result}
            return {"source": "neo4j", "data": []}
        except Exception as e:
            logger.error("neo4j_query_failed", error=str(e))
            return {"source": "neo4j", "error": str(e)}

    async def _query_elasticsearch(self, query_spec: Dict) -> Dict:
        """Consultar Elasticsearch"""
        try:
            time_window = query_spec.get("time_window", {})
            filters = query_spec.get("filters", {})

            result = await self.elasticsearch.search_logs(
                time_window.get("start"), time_window.get("end"), filters
            )
            return {"source": "elasticsearch", "data": result}
        except Exception as e:
            logger.error("elasticsearch_query_failed", error=str(e))
            return {"source": "elasticsearch", "error": str(e)}

    async def _query_prometheus(self, query_spec: Dict) -> Dict:
        """Consultar Prometheus"""
        try:
            time_window = query_spec.get("time_window", {})
            metrics = query_spec.get("metrics", [])

            results = {}
            for metric in metrics:
                stat = await self.prometheus.get_metric_statistics(
                    metric, time_window.get("start"), time_window.get("end")
                )
                results[metric] = stat

            return {"source": "prometheus", "data": results}
        except Exception as e:
            logger.error("prometheus_query_failed", error=str(e))
            return {"source": "prometheus", "error": str(e)}

    async def _query_postgresql(self, query_spec: Dict) -> Dict:
        """Consultar PostgreSQL"""
        if not self.postgresql:
            return {"source": "postgresql", "error": "PostgreSQL client not configured"}

        try:
            filters = query_spec.get("filters", {})
            limit = query_spec.get("limit", 100)

            # Buscar insights se solicitado
            if query_spec.get("query_type") == "insights":
                time_window = query_spec.get("time_window", {})
                results = await self.postgresql.get_insights(
                    limit=limit, time_window=time_window, analyst_id=filters.get("analyst_id")
                )
                return {"source": "postgresql", "data": results, "count": len(results)}

            # Buscar ações de analista
            elif query_spec.get("query_type") == "actions":
                results = await self.postgresql.get_analyst_actions(
                    analyst_id=filters.get("analyst_id"),
                    action_type=filters.get("action_type"),
                    limit=limit,
                )
                return {"source": "postgresql", "data": results, "count": len(results)}

            # Buscar estatísticas de execução
            elif query_spec.get("query_type") == "execution_stats":
                time_window = query_spec.get("time_window", {})
                results = await self.postgresql.get_execution_statistics(
                    start=time_window.get("start"), end=time_window.get("end")
                )
                return {"source": "postgresql", "data": results}

            # Query genérica
            elif "sql" in query_spec:
                results = await self.postgresql.execute_query(
                    query_spec["sql"], tuple(query_spec.get("params", []))
                )
                return {"source": "postgresql", "data": results, "count": len(results)}

            return {"source": "postgresql", "data": []}

        except Exception as e:
            logger.error("postgresql_query_failed", error=str(e))
            return {"source": "postgresql", "error": str(e)}

    async def join_sources(
        self,
        sources: List[str],
        query_spec: Dict,
    ) -> Dict[str, Any]:
        """
        Junta dados de múltiplas fontes com correlação.

        Args:
            sources: Lista de fontes para juntar
            query_spec: Especificação da query

        Returns:
            Dados unidos com correlações
        """
        results = await self.query_multi_source(
            {"sources": sources, "use_cache": False, "enable_fusion": True, **query_spec}
        )

        if "error" in results:
            return results

        # Extrair resultados fundidos
        fused = results["results"].get("fused", {})

        # Adicionar correlações
        correlations = {}
        source_results = results["results"].get("by_source", {})

        # Buscar métricas comuns para correlacionar
        common_metrics = set()
        for source_data in source_results.values():
            if isinstance(source_data, dict) and "data" in source_data:
                data = source_data["data"]
                # Se data for um dict, extrair chaves com valores numéricos
                if isinstance(data, dict):
                    for key, val in data.items():
                        if isinstance(val, (int, float)):
                            common_metrics.add(key)
                # Se data for uma lista, procurar dicts dentro e extrair chaves
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for key, val in item.items():
                                if isinstance(val, (int, float)):
                                    common_metrics.add(key)

        # Calcular correlação para métricas comuns
        for metric in common_metrics:
            for other_metric in common_metrics:
                if metric < other_metric:  # Evitar duplicados
                    correlation = await self.data_fusion.get_correlation(
                        source_results, metric, other_metric
                    )
                    if correlation is not None:
                        correlations[f"{metric}_x_{other_metric}"] = correlation

        return {
            **fused,
            "correlations": correlations,
        }

    async def correlate_metrics(
        self,
        sources: List[str],
        metric_x: str,
        metric_y: str,
        time_window: Optional[Dict] = None,
    ) -> Optional[float]:
        """
        Calcula correlação entre duas métricas.

        Args:
            sources: Fontes de dados
            metric_x: Nome da métrica X
            metric_y: Nome da métrica Y
            time_window: Janela temporal opcional

        Returns:
            Coeficiente de correlação ou None
        """
        # Buscar dados das fontes
        query_spec = {
            "sources": sources,
            "use_cache": False,
            "time_window": time_window or {},
        }

        results = await self.query_multi_source(query_spec)

        if "error" in results:
            return None

        source_results = results["results"]
        return await self.data_fusion.get_correlation(source_results, metric_x, metric_y)

    def consolidate_results(self, results: Dict) -> Dict:
        """Consolidar resultados de múltiplas fontes"""
        consolidated = {}

        for source, result in results.items():
            if isinstance(result, Exception):
                consolidated[source] = {"error": str(result)}
            elif "error" in result:
                consolidated[source] = result
            else:
                consolidated[source] = result.get("data", {})

        return consolidated

    def _generate_query_key(self, query_spec: Dict) -> str:
        """Gerar chave de cache para consulta"""
        query_str = json.dumps(query_spec, sort_keys=True)
        return hashlib.md5(query_str.encode()).hexdigest()
