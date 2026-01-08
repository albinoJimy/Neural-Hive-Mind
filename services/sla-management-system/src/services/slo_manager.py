"""
Serviço para gerenciar definições de SLO.
"""

from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from datetime import datetime
import yaml
import structlog
from prometheus_client import Counter, Histogram

from ..clients.postgresql_client import PostgreSQLClient
from ..clients.prometheus_client import PrometheusClient
from ..models.slo_definition import SLODefinition

if TYPE_CHECKING:
    from ..clients.kubernetes_client import KubernetesClient

# Metricas para sincronizacao de CRDs
sla_crd_sync_total = Counter(
    'sla_crd_sync_total',
    'Total de sincronizacoes de CRDs',
    ['status']
)

sla_crd_sync_duration = Histogram(
    'sla_crd_sync_duration_seconds',
    'Duracao da sincronizacao de CRDs',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)


class SLOManager:
    """Gerenciador de definições de SLO."""

    def __init__(
        self,
        postgresql_client: PostgreSQLClient,
        prometheus_client: PrometheusClient,
        kubernetes_client: Optional["KubernetesClient"] = None
    ):
        self.postgresql_client = postgresql_client
        self.prometheus_client = prometheus_client
        self.kubernetes_client = kubernetes_client
        self.logger = structlog.get_logger(__name__)

    async def create_slo(self, slo: SLODefinition) -> str:
        """Cria novo SLO."""
        # Validar definição
        is_valid, error = self.validate_slo(slo)
        if not is_valid:
            raise ValueError(f"Invalid SLO definition: {error}")

        # Persistir
        slo_id = await self.postgresql_client.create_slo(slo)

        self.logger.info(
            "slo_created",
            slo_id=slo_id,
            name=slo.name,
            service=slo.service_name
        )

        return slo_id

    async def get_slo(self, slo_id: str) -> Optional[SLODefinition]:
        """Busca SLO por ID."""
        return await self.postgresql_client.get_slo(slo_id)

    async def list_slos(
        self,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SLODefinition]:
        """Lista SLOs com filtros opcionais."""
        if not filters:
            return await self.postgresql_client.list_slos()

        # Aplicar filtros
        service_name = filters.get("service_name")
        enabled_only = filters.get("enabled", True)

        slos = await self.postgresql_client.list_slos(
            service_name=service_name,
            enabled_only=enabled_only
        )

        # Filtros adicionais (layer, slo_type)
        if "layer" in filters:
            slos = [s for s in slos if s.layer == filters["layer"]]

        if "slo_type" in filters:
            slos = [s for s in slos if s.slo_type.value == filters["slo_type"]]

        return slos

    async def update_slo(
        self,
        slo_id: str,
        updates: Dict[str, Any]
    ) -> Optional[SLODefinition]:
        """Atualiza campos do SLO."""
        # Validar campos permitidos
        allowed_fields = {
            "name", "description", "target", "sli_query",
            "enabled", "window_days", "metadata"
        }

        invalid_fields = set(updates.keys()) - allowed_fields
        if invalid_fields:
            raise ValueError(f"Invalid fields for update: {invalid_fields}")

        # Atualizar
        from datetime import datetime
        updates["updated_at"] = datetime.utcnow()

        success = await self.postgresql_client.update_slo(slo_id, updates)
        if not success:
            return None

        self.logger.info(
            "slo_updated",
            slo_id=slo_id,
            updated_fields=list(updates.keys())
        )

        # Retornar SLO atualizado
        return await self.postgresql_client.get_slo(slo_id)

    async def delete_slo(self, slo_id: str) -> bool:
        """Soft delete de SLO."""
        success = await self.postgresql_client.delete_slo(slo_id)

        if success:
            self.logger.info("slo_deleted", slo_id=slo_id)

        return success

    async def import_from_alerts(self, alert_rules_path: str) -> List[str]:
        """Importa SLOs de arquivo de alertas Prometheus."""
        try:
            with open(alert_rules_path, 'r') as f:
                alert_rules = yaml.safe_load(f)

            slo_ids = []

            # Iterar grupos de alertas
            for group in alert_rules.get("groups", []):
                for rule in group.get("rules", []):
                    # Verificar se é alerta de SLO
                    labels = rule.get("labels", {})
                    if "slo" not in labels:
                        continue

                    # Extrair informações
                    slo_name = labels.get("slo")
                    service_name = labels.get("service", "unknown")
                    severity = labels.get("severity", "warning")

                    # Determinar tipo de SLO baseado no nome
                    slo_type = self._infer_slo_type(slo_name)

                    # Extrair query (simplificado)
                    expr = rule.get("expr", "")

                    # Criar SLO
                    from ..models.slo_definition import SLOType, SLIQuery
                    slo = SLODefinition(
                        name=slo_name,
                        description=rule.get("annotations", {}).get("description", ""),
                        slo_type=slo_type,
                        service_name=service_name,
                        layer="orquestracao",  # Default
                        target=0.999,  # Default 99.9%
                        window_days=30,
                        sli_query=SLIQuery(
                            metric_name=slo_name,
                            query=expr,
                            aggregation="avg"
                        ),
                        enabled=True
                    )

                    # Verificar se já existe
                    existing_slos = await self.list_slos({
                        "service_name": service_name
                    })
                    already_exists = any(
                        s.name == slo_name for s in existing_slos
                    )

                    if not already_exists:
                        slo_id = await self.create_slo(slo)
                        slo_ids.append(slo_id)

            self.logger.info(
                "slos_imported_from_alerts",
                count=len(slo_ids),
                source=alert_rules_path
            )

            return slo_ids

        except Exception as e:
            self.logger.error(
                "slo_import_failed",
                error=str(e),
                source=alert_rules_path
            )
            raise

    async def sync_from_crds(
        self,
        namespace: Optional[str] = None
    ) -> List[str]:
        """
        Sincroniza SLOs de CRDs Kubernetes para PostgreSQL.

        Complementa o operator (tempo real) com reconciliacao periodica.
        Usado pelo CronJob para recuperacao de drift e consistencia.

        Args:
            namespace: Namespace especifico ou None para todos.

        Returns:
            Lista de slo_ids sincronizados.
        """
        if not self.kubernetes_client:
            self.logger.warning(
                "crd_sync.kubernetes_client_not_available",
                reason="kubernetes_client nao foi configurado"
            )
            return []

        if not self.kubernetes_client.is_healthy():
            self.logger.warning(
                "crd_sync.kubernetes_client_not_healthy",
                reason="cliente nao conectado ao cluster"
            )
            return []

        synced_ids: List[str] = []

        with sla_crd_sync_duration.time():
            try:
                # Listar todos os CRDs SLODefinition
                crds = await self.kubernetes_client.list_slo_definitions(namespace)

                self.logger.info(
                    "crd_sync.started",
                    crd_count=len(crds),
                    namespace=namespace or "all"
                )

                for crd in crds:
                    try:
                        slo_id = await self._sync_single_crd(crd)
                        if slo_id:
                            synced_ids.append(slo_id)
                    except Exception as e:
                        crd_name = crd.get("metadata", {}).get("name", "unknown")
                        crd_namespace = crd.get("metadata", {}).get("namespace", "unknown")
                        self.logger.error(
                            "crd_sync.single_crd_failed",
                            crd_name=crd_name,
                            crd_namespace=crd_namespace,
                            error=str(e)
                        )

                sla_crd_sync_total.labels(status="success").inc()

                self.logger.info(
                    "crd_sync.completed",
                    synced_count=len(synced_ids),
                    total_crds=len(crds)
                )

                return synced_ids

            except Exception as e:
                sla_crd_sync_total.labels(status="error").inc()
                self.logger.error(
                    "crd_sync.failed",
                    error=str(e)
                )
                return []

    async def _sync_single_crd(self, crd: Dict[str, Any]) -> Optional[str]:
        """
        Sincroniza um unico CRD para PostgreSQL.

        Args:
            crd: CRD completo do Kubernetes.

        Returns:
            slo_id se sincronizado, None se erro.
        """
        metadata = crd.get("metadata", {})
        spec = crd.get("spec", {})
        crd_name = metadata.get("name")
        crd_namespace = metadata.get("namespace")

        if not spec:
            self.logger.warning(
                "crd_sync.missing_spec",
                crd_name=crd_name,
                crd_namespace=crd_namespace
            )
            return None

        # Converter CRD para SLODefinition
        # Mapear campos camelCase do CRD para snake_case do modelo
        sli_query_spec = spec.get("sliQuery", {})
        slo_data = SLODefinition.from_crd({
            "name": spec.get("name"),
            "description": spec.get("description", ""),
            "sloType": spec.get("sloType"),
            "serviceName": spec.get("serviceName"),
            "component": spec.get("component"),
            "layer": spec.get("layer"),
            "target": spec.get("target"),
            "windowDays": spec.get("windowDays", 30),
            "sliQuery": {
                "metricName": sli_query_spec.get("metricName"),
                "query": sli_query_spec.get("query"),
                "aggregation": sli_query_spec.get("aggregation", "avg"),
                "labels": sli_query_spec.get("labels", {})
            },
            "enabled": spec.get("enabled", True),
            "metadata": spec.get("metadata", {})
        })

        # Adicionar metadados do CRD
        slo_data.metadata["crd_name"] = crd_name
        slo_data.metadata["crd_namespace"] = crd_namespace

        # Verificar se SLO ja existe (por nome + namespace no metadata)
        existing_slos = await self.list_slos({
            "service_name": slo_data.service_name,
            "enabled": None  # Incluir desabilitados
        })

        existing_slo = None
        for slo in existing_slos:
            if (slo.metadata.get("crd_name") == crd_name and
                    slo.metadata.get("crd_namespace") == crd_namespace):
                existing_slo = slo
                break

        slo_id: str

        if existing_slo:
            # Verificar se houve mudancas
            if self._slo_needs_update(existing_slo, slo_data):
                updates = {
                    "name": slo_data.name,
                    "description": slo_data.description,
                    "target": slo_data.target,
                    "window_days": slo_data.window_days,
                    "sli_query": slo_data.sli_query.model_dump(),
                    "enabled": slo_data.enabled,
                    "metadata": slo_data.metadata
                }
                await self.update_slo(existing_slo.slo_id, updates)
                self.logger.info(
                    "crd_sync.slo_updated",
                    slo_id=existing_slo.slo_id,
                    crd_name=crd_name
                )
            else:
                self.logger.debug(
                    "crd_sync.slo_unchanged",
                    slo_id=existing_slo.slo_id,
                    crd_name=crd_name
                )
            slo_id = existing_slo.slo_id
        else:
            # Criar novo SLO
            slo_id = await self.create_slo(slo_data)
            self.logger.info(
                "crd_sync.slo_created",
                slo_id=slo_id,
                crd_name=crd_name
            )

        # Atualizar status do CRD
        if self.kubernetes_client:
            await self.kubernetes_client.update_slo_status(
                name=crd_name,
                namespace=crd_namespace,
                status={
                    "synced": True,
                    "sloId": slo_id
                }
            )

        return slo_id

    def _slo_needs_update(
        self,
        existing: SLODefinition,
        new_data: SLODefinition
    ) -> bool:
        """
        Verifica se SLO precisa ser atualizado.

        Compara campos relevantes para detectar mudancas.
        """
        if existing.name != new_data.name:
            return True
        if existing.description != new_data.description:
            return True
        if abs(existing.target - new_data.target) > 0.0001:
            return True
        if existing.window_days != new_data.window_days:
            return True
        if existing.enabled != new_data.enabled:
            return True
        if existing.sli_query.query != new_data.sli_query.query:
            return True
        if existing.sli_query.metric_name != new_data.sli_query.metric_name:
            return True
        if existing.sli_query.aggregation != new_data.sli_query.aggregation:
            return True
        if existing.sli_query.labels != new_data.sli_query.labels:
            return True

        return False

    def validate_slo(self, slo: SLODefinition) -> Tuple[bool, Optional[str]]:
        """Valida definição de SLO."""
        # Target entre 0 e 1
        if not (0 <= slo.target <= 1):
            return False, "Target must be between 0 and 1"

        # Query não vazia
        if not slo.sli_query.query:
            return False, "SLI query cannot be empty"

        # Service name não vazio
        if not slo.service_name:
            return False, "Service name cannot be empty"

        # Window days > 0
        if slo.window_days <= 0:
            return False, "Window days must be positive"

        return True, None

    async def test_slo_query(
        self,
        slo: SLODefinition
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Testa query do SLO contra Prometheus."""
        try:
            # Executar query
            result = await self.prometheus_client.query(slo.sli_query.query)

            # Verificar resultado
            if result.get("resultType") == "vector":
                results = result.get("result", [])
                if results:
                    value = float(results[0].get("value", [0, 0])[1])
                    return True, value, None
                else:
                    return False, None, "Query returned no results"

            elif result.get("resultType") == "matrix":
                results = result.get("result", [])
                if results:
                    values = results[0].get("values", [])
                    if values:
                        value = float(values[-1][1])
                        return True, value, None

            return False, None, "Query returned unexpected result type"

        except Exception as e:
            return False, None, str(e)

    def _infer_slo_type(self, slo_name: str) -> "SLOType":
        """Infere tipo de SLO baseado no nome."""
        from ..models.slo_definition import SLOType

        name_lower = slo_name.lower()

        if "latency" in name_lower or "duration" in name_lower:
            return SLOType.LATENCY
        elif "availability" in name_lower or "uptime" in name_lower:
            return SLOType.AVAILABILITY
        elif "error" in name_lower or "failure" in name_lower:
            return SLOType.ERROR_RATE
        else:
            return SLOType.CUSTOM
