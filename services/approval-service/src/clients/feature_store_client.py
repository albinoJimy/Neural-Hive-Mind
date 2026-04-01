"""
Feature Store Client para Approval Service

Cliente HTTP para interagir com o Feature Store Service.
"""

from typing import Any, Dict, Optional

import httpx
import structlog

from src.config.settings import Settings

logger = structlog.get_logger()


class FeatureStoreClient:
    """Cliente HTTP para Feature Store"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._base_url: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def base_url(self) -> str:
        """URL base do Feature Store"""
        if self._base_url is None:
            # Usa variável de ambiente ou default
            import os

            self._base_url = os.getenv(
                "FEATURE_STORE_URL", "http://feature-store.feature-store.svc.cluster.local:8080"
            )
        return self._base_url

    async def initialize(self):
        """Inicializa cliente HTTP"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
        logger.info("Feature Store client inicializado", url=self.base_url)

    async def close(self):
        """Fecha cliente HTTP"""
        if self._client:
            await self._client.aclose()
            logger.info("Feature Store client fechado")

    async def get_features(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca features de um plano

        Args:
            plan_id: ID do plano

        Returns:
            Dict com features ou None se não encontrado
        """
        if not self._client:
            logger.warning("Feature Store client não inicializado")
            return None

        try:
            response = await self._client.get(f"/api/v1/features/{plan_id}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.debug("Features não encontradas", plan_id=plan_id)
                return None
            else:
                logger.warning(
                    "Erro ao buscar features", plan_id=plan_id, status_code=response.status_code
                )
                return None

        except httpx.RequestError as e:
            logger.error("Erro de requisição ao Feature Store", plan_id=plan_id, error=str(e))
            return None
        except Exception as e:
            logger.error("Erro ao buscar features", plan_id=plan_id, error=str(e))
            return None

    async def compute_and_save_features(
        self, plan_id: str, cognitive_plan: Dict[str, Any], force_recompute: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Computa e salva features para um plano

        Args:
            plan_id: ID do plano
            cognitive_plan: Dados do plano cognitivo
            force_recompute: Se deve forçar recomputação

        Returns:
            Dict com features computadas ou None em caso de erro
        """
        if not self._client:
            logger.warning("Feature Store client não inicializado")
            return None

        try:
            request_data = {
                "plan_id": plan_id,
                "cognitive_plan": cognitive_plan,
                "force_recompute": force_recompute,
                "skip_cache": False,
            }

            response = await self._client.post(f"/api/v1/features/{plan_id}", json=request_data)

            if response.status_code == 200:
                features = response.json()
                logger.info("Features computadas com sucesso", plan_id=plan_id)
                return features
            else:
                logger.warning(
                    "Erro ao computar features", plan_id=plan_id, status_code=response.status_code
                )
                return None

        except httpx.RequestError as e:
            logger.error("Erro de requisição ao Feature Store", plan_id=plan_id, error=str(e))
            return None
        except Exception as e:
            logger.error("Erro ao computar features", plan_id=plan_id, error=str(e))
            return None

    async def get_features_by_plan_ids(self, plan_ids: list[str]) -> Dict[str, Dict[str, Any]]:
        """
        Busca features para múltiplos planos

        Args:
            plan_ids: Lista de IDs de planos

        Returns:
            Dict mapeando plan_id -> features
        """
        if not self._client:
            return {}

        try:
            params = {"plan_ids": ",".join(plan_ids)}
            response = await self._client.get("/api/v1/features/by-plan-ids", params=params)

            if response.status_code == 200:
                features_list = response.json()
                # Converte lista para dict
                return {f["plan_id"]: f for f in features_list}
            else:
                logger.warning(
                    "Erro ao buscar features múltiplas", status_code=response.status_code
                )
                return {}

        except Exception as e:
            logger.error("Erro ao buscar features múltiplas", error=str(e))
            return {}

    async def health_check(self) -> bool:
        """
        Verifica saúde do Feature Store

        Returns:
            True se saudável
        """
        if not self._client:
            return False

        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception:
            return False


def get_feature_store_client(settings: Settings) -> FeatureStoreClient:
    """Factory para FeatureStoreClient"""
    return FeatureStoreClient(settings)
